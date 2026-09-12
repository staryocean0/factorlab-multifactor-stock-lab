"""Trusted public transport broker. Never print private bytes or pass credentials to compute."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

PUBLIC_REPO = "staryocean0/factorlab-multifactor-stock-lab"
PRIVATE_REPO = "staryocean0/factorlab-multifactor-research-private"
BRANCH = "refs/heads/cloud-workspace-v1"
OUTPUT_MOUNT = "runtime/output/factor-rotation/reaka_frozen_validation_2021_2022_v1_20260912/accounts_v2"
IMAGE = "factorlab-runtime:local"
HERE = Path(__file__).resolve().parent
DOWNLOAD_HOSTS = {
    "api.github.com",
    "codeload.github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
    "github.com",
}


class GateError(Exception):
    """Only fixed non-sensitive reason codes may reach the public log."""


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in DOWNLOAD_HOSTS:
            raise GateError("unapproved_download_destination")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if parsed.netloc != urllib.parse.urlsplit(req.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_path(root, name):
    part = PurePosixPath(name)
    if part.is_absolute() or not part.parts or ".." in part.parts or "\\" in name:
        raise GateError("unsafe_path")
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()):
        raise GateError("path_escape")
    return target


def unpack(archive, target, expected=None, strip_root=False):
    with tarfile.open(archive, "r:*") as tar:
        entries, seen = [], set()
        for member in tar:
            parts = PurePosixPath(member.name).parts
            if strip_root:
                parts = parts[1:]
            if not parts:
                continue
            name = str(PurePosixPath(*parts))
            destination = safe_path(target, name)
            if member.isdir():
                continue
            if not member.isfile() or name in seen:
                raise GateError("nonregular_or_duplicate_archive_member")
            seen.add(name)
            if expected is not None and (name not in expected or member.size != expected[name]["bytes"]):
                raise GateError("unregistered_package_member")
            if destination.exists():
                raise GateError("archive_overwrite")
            entries.append((member, destination, name))
        if expected is not None and seen != set(expected):
            raise GateError("package_member_set_mismatch")
        if sum(m.size for m, _, _ in entries) > 1024**3:
            raise GateError("bounded_archive_too_large")
        for member, destination, name in entries:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                shutil.copyfileobj(tar.extractfile(member), stream)
            if expected is not None and sha(destination) != expected[name]["sha256"]:
                raise GateError("package_file_digest_mismatch")


def require_context(env):
    if (
        env.get("GITHUB_ACTIONS") != "true"
        or env.get("GITHUB_REPOSITORY") != PUBLIC_REPO
        or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or env.get("GITHUB_REF") != BRANCH
    ):
        raise GateError("not_approved_public_dispatch")
    if not re.fullmatch(r"[0-9]+", env.get("GITHUB_RUN_ID", "")) or not re.fullmatch(r"[0-9]+", env.get("GITHUB_RUN_ATTEMPT", "")):
        raise GateError("invalid_run_identity")


def validate_profile(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value.get("private_ref", "")) or not re.fullmatch(
        r"[0-9a-f]{64}", value.get("catalog_sha256", "")
    ):
        raise GateError("profile_not_immutable")
    if value.get("new_training") is not False or value.get("production_authority") is not False:
        raise GateError("scope_not_authorized")
    if value.get("packages") != ["baseline-replay"] or not 1 <= value.get("command_timeout_seconds", 0) <= 600:
        raise GateError("profile_scope_changed")
    if len(value.get("commands", [])) != 4:
        raise GateError("incomplete_baseline_family")
    for args in value["commands"]:
        if (
            len(args) != 5
            or args[0] != "tools/cloud_replay.py"
            or args[1] != "--period"
            or args[2] not in {"repair", "validation"}
            or args[3] != "--clock"
            or args[4] not in {"1430", "1445"}
        ):
            raise GateError("unapproved_command")
    if {(a[2], a[4]) for a in value["commands"]} != {(p, c) for p in ["repair", "validation"] for c in ["1430", "1445"]}:
        raise GateError("duplicate_or_missing_case")
    if value.get("output_mount") != OUTPUT_MOUNT:
        raise GateError("unapproved_output_mount")
    return value


class GitHub:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(SafeRedirect())

    def request(self, path, data=None, method=None, binary_path=None):
        url = "https://api.github.com/" + path
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "factorlab-private-broker",
        }
        payload = None if data is None else json.dumps(data).encode()
        if binary_path is not None:
            headers["Accept"] = "application/octet-stream"
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=120) as response:
                if binary_path is not None:
                    with binary_path.open("xb") as stream:
                        shutil.copyfileobj(response, stream)
                    return None
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise GateError("github_http_" + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise GateError("github_transport_failed") from None

    def private_identity(self):
        value = self.request("repos/" + PRIVATE_REPO)
        if value.get("full_name") != PRIVATE_REPO or value.get("private") is not True:
            raise GateError("private_identity_failed")


def docker_command(work=None, results=None, profile_path=None):
    args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--memory",
        "12g",
        "--cpus",
        "4",
        "--pids-limit",
        "256",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=512m",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        "OPENBLAS_NUM_THREADS=1",
    ]
    if work is None:
        return args + [IMAGE, "runtime-smoke"]
    profile = json.loads(profile_path.read_text())
    target = safe_path(work, profile["output_mount"])
    target.mkdir(parents=True, exist_ok=True)
    (results / "accounts").mkdir()
    args += [
        "--mount",
        f"type=bind,src={work},dst=/work,readonly",
        "--mount",
        f"type=bind,src={results},dst=/results",
        "--mount",
        f"type=bind,src={results / 'accounts'},dst=/work/{profile['output_mount']}",
        "--mount",
        f"type=bind,src={profile_path},dst=/execution/profile.json,readonly",
    ]
    return args + [IMAGE, "private-task"]


def prepare_inputs(api, root, profile):
    api.private_identity()
    archive = root / "source.tar.gz"
    api.request(f"repos/{PRIVATE_REPO}/tarball/{profile['private_ref']}", binary_path=archive)
    work = root / "work"
    work.mkdir()
    unpack(archive, work, strip_root=True)
    catalog_path = work / "packages/catalog.json"
    if sha(catalog_path) != profile["catalog_sha256"]:
        raise GateError("catalog_digest_failed")
    for name, digest in json.loads((work / "source_manifest.json").read_text())["source_sha256"].items():
        if sha(safe_path(work / "runtime", name)) != digest:
            raise GateError("executor_source_digest_failed")
    catalog = json.loads(catalog_path.read_text())
    release = api.request(f"repos/{PRIVATE_REPO}/releases/tags/{catalog['release']}")
    if release.get("draft") is not False:
        raise GateError("private_data_release_not_published")
    assets = {a["name"]: a for a in release["assets"]}
    for name in profile["packages"]:
        package = catalog["packages"][name]
        if package["admission"] != "retained_fixed_research_scope_not_new_training_grant":
            raise GateError("package_admission_failed")
        combined = root / (name + ".tar")
        with combined.open("xb") as stream:
            for index, part in enumerate(package["parts"]):
                asset = assets[part["name"]]
                if asset["state"] != "uploaded" or asset["size"] != part["bytes"] or asset.get("digest") != "sha256:" + part["sha256"]:
                    raise GateError("remote_asset_identity_failed")
                path = root / f"part-{index}.bin"
                api.request(f"repos/{PRIVATE_REPO}/releases/assets/{asset['id']}", binary_path=path)
                if path.stat().st_size != part["bytes"] or sha(path) != part["sha256"]:
                    raise GateError("downloaded_part_digest_failed")
                with path.open("rb") as source:
                    shutil.copyfileobj(source, stream)
                path.unlink()  # validated temporary download; immutable remote/local originals are retained
        unpack(combined, work / "runtime", expected=package["files"])
    return work


def save_private_result(api, results, profile, run_id, success):
    api.private_identity()
    branch = "runs/public-baseline/" + run_id
    api.request(f"repos/{PRIVATE_REPO}/git/refs", {"ref": "refs/heads/" + branch, "sha": profile["private_ref"]}, method="POST")
    files = {str(p.relative_to(results)): {"bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(results.rglob("*")) if p.is_file()}
    receipt = {
        "schema_id": "factorlab.public_runner_receipt@1.0",
        "status": "passed" if success else "failed",
        "public_run_id": run_id,
        "public_repository": PUBLIC_REPO,
        "private_source_ref": profile["private_ref"],
        "execution": "public_standard_runner_network_isolated_container",
        "catalog_sha256": profile["catalog_sha256"],
        "files": files,
        "new_training": False,
        "production_authority": False,
    }
    compute = results / "compute_receipt.json"
    if compute.exists():
        receipt["compute"] = json.loads(compute.read_text())
    payload = (json.dumps(receipt, indent=2) + "\n").encode()
    api.request(
        f"repos/{PRIVATE_REPO}/contents/research/public-runs/{run_id}.json",
        {"message": "Record public runner result [skip ci]", "branch": branch, "content": base64.b64encode(payload).decode()},
        method="PUT",
    )
    # Complete logs/snapshots stay private and off Actions artifacts/cache.
    archive = results.parent / "results.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in files:
            tar.add(results / name, arcname=name, recursive=False)
    if archive.stat().st_size > 512 * 1024 * 1024:
        raise GateError("private_result_archive_too_large")
    # gh handles streamed release upload; its output is suppressed and token is
    # passed only to this trusted transport subprocess, never to compute.
    env = {"PATH": os.environ["PATH"], "GH_TOKEN": api.token}
    tag = "public-run-" + run_id
    subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            PRIVATE_REPO,
            "--target",
            profile["private_ref"],
            "--prerelease",
            "--title",
            "Public runner result " + run_id,
            "--notes",
            "Private result; no production authority.",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=120,
    )
    subprocess.run(
        ["gh", "release", "upload", tag, "--repo", PRIVATE_REPO, str(archive)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=600,
    )
    release = api.request(f"repos/{PRIVATE_REPO}/releases/tags/{tag}")
    if not any(a["name"] == archive.name and a.get("digest") == "sha256:" + sha(archive) for a in release["assets"]):
        raise GateError("private_writeback_digest_failed")
    returned = api.request(f"repos/{PRIVATE_REPO}/contents/research/public-runs/{run_id}.json?ref=" + urllib.parse.quote(branch, safe=""))
    if base64.b64decode(returned["content"]) != payload:
        raise GateError("private_receipt_readback_failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=["runtime-smoke", "baseline-replay-v1"])
    args = parser.parse_args()
    require_context(os.environ)
    if args.profile == "runtime-smoke":
        subprocess.run(docker_command(), check=True, timeout=120)
        print("Public standard-runner isolated runtime verified; no private inputs used.")
        return
    token = os.environ.get("FACTORLAB_PRIVATE_TOKEN")
    if not token:
        raise GateError("missing_FACTORLAB_PRIVATE_TOKEN_no_private_data_requested")
    profile = validate_profile(json.loads((HERE / "profiles.json").read_text())["profiles"][args.profile])
    run_id = os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
    root = Path(tempfile.mkdtemp(prefix="private-research-", dir=os.environ["RUNNER_TEMP"]))
    results = root / "results"
    results.mkdir()
    api = GitHub(token)
    work = prepare_inputs(api, root, profile)
    profile_path = root / "profile.json"
    profile_path.write_text(json.dumps(profile))
    with (results / "container.log").open("xb") as stream:
        result = subprocess.run(docker_command(work, results, profile_path), stdout=stream, stderr=subprocess.STDOUT, timeout=2700)
    compute_path = results / "compute_receipt.json"
    computed = json.loads(compute_path.read_text()) if compute_path.is_file() else {}
    cases = computed.get("commands", [])
    success = (
        result.returncode == 0 and computed.get("status") == "passed" and len(cases) == 4 and all(c.get("exit_code") == 0 for c in cases)
    )
    save_private_result(api, results, profile, run_id, success)
    print("Private result and full logs saved and verified for public run " + run_id + ".")
    if not success:
        raise GateError("compute_failed_consult_private_receipt")


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print("Execution stopped: " + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        # Never emit private paths, remote bodies, dataframes, credentials, or URLs.
        print("Execution failed; no private diagnostic content was published.", file=sys.stderr)
        sys.exit(1)
