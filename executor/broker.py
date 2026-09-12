"""Trusted public transport broker. Never print private bytes or pass credentials to compute."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import shutil
import stat
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
        if (
            parsed.scheme != "https"
            or parsed.hostname not in DOWNLOAD_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
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
    if set(value) != {
        "private_ref",
        "catalog_sha256",
        "packages",
        "commands",
        "output_mount",
        "command_timeout_seconds",
        "new_training",
        "production_authority",
    }:
        raise GateError("unknown_profile_field")
    if not re.fullmatch(r"[0-9a-f]{40}", value.get("private_ref", "")) or not re.fullmatch(
        r"[0-9a-f]{64}", value.get("catalog_sha256", "")
    ):
        raise GateError("profile_not_immutable")
    if value.get("new_training") is not False or value.get("production_authority") is not False:
        raise GateError("scope_not_authorized")
    if value.get("packages") != ["baseline-replay"] or not 1 <= value.get("command_timeout_seconds", 0) <= 180:
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
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SafeRedirect())

    def request(self, path, data=None, method=None, binary_path=None, max_bytes=64 * 1024 * 1024):
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
                        total = 0
                        while block := response.read(1024 * 1024):
                            total += len(block)
                            if total > max_bytes:
                                raise GateError("download_byte_budget_exceeded")
                            stream.write(block)
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


def clean_env():
    return {"PATH": os.environ["PATH"], "LANG": "C.UTF-8"}


def docker_command(work=None, results=None, profile_path=None, validator=False):
    args = [
        "docker",
        "run",
        "--rm",
        "--name",
        "factorlab-compute",
        "--network",
        "none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--memory",
        "12g",
        "--memory-swap",
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
    args += [
        "--mount",
        f"type=bind,src={work},dst=/work,readonly",
        "--mount",
        f"type=bind,src={profile_path},dst=/execution/profile.json,readonly",
    ]
    if validator:
        args += ["--mount", f"type=bind,src={results},dst=/results,readonly"]
        return args + [IMAGE, "validate-baseline"]
    target = safe_path(work, profile["output_mount"])
    target.mkdir(parents=True, exist_ok=True)
    (results / "accounts").mkdir(exist_ok=True)
    args += [
        "--mount",
        f"type=bind,src={results},dst=/results",
        "--mount",
        f"type=bind,src={results / 'accounts'},dst=/work/{profile['output_mount']}",
    ]
    return args + [IMAGE, "private-task"]


def run_container(command, output, timeout, error_output=subprocess.STDOUT):
    process = subprocess.Popen(command, stdout=output, stderr=error_output, env=clean_env())
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        code = 124
    if code:
        cleanup = subprocess.run(
            ["docker", "rm", "--force", "factorlab-compute"], env=clean_env(), capture_output=True, text=True, timeout=30
        )
        if cleanup.returncode and "No such container" not in cleanup.stderr:
            process.kill()
            process.wait()
            raise GateError("container_cleanup_failed_no_result_collection")
        if process.poll() is None:
            process.kill()
            process.wait()
    return code


def collect_result_files(results):
    files, total = {}, 0
    for p in sorted(results.rglob("*")):
        info = p.lstat()
        if stat.S_ISLNK(info.st_mode) or not p.resolve().is_relative_to(results.resolve()):
            raise GateError("result_link_or_escape")
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise GateError("result_not_regular_single_link")
        total += info.st_size
        if total > 512 * 1024 * 1024 or len(files) >= 2000:
            raise GateError("result_budget_exceeded")
        files[str(p.relative_to(results))] = {"bytes": info.st_size, "sha256": sha(p)}
    return files


def prepare_inputs(api, root, profile):
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
                api.request(f"repos/{PRIVATE_REPO}/releases/assets/{asset['id']}", binary_path=path, max_bytes=part["bytes"])
                if path.stat().st_size != part["bytes"] or sha(path) != part["sha256"]:
                    raise GateError("downloaded_part_digest_failed")
                with path.open("rb") as source:
                    shutil.copyfileobj(source, stream)
                path.unlink()  # this validated temporary download only; immutable originals remain
        unpack(combined, work / "runtime", expected=package["files"])
    return work


def state_path():
    return Path(os.environ["RUNNER_TEMP"]) / "factorlab-executor-state.json"


def write_state(state):
    path = state_path()
    if path.is_symlink():
        raise GateError("state_path_is_link")
    temporary = path.with_suffix(".pending")
    with temporary.open("w") as stream:
        json.dump(state, stream, indent=2)
    temporary.replace(path)


def load_state():
    state = json.loads(state_path().read_text())
    root = Path(state["root"]).resolve()
    if not root.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve()) or not root.name.startswith("fl-private-"):
        raise GateError("invalid_state_root")
    if state["run_id"] != os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]:
        raise GateError("state_run_identity_mismatch")
    if state["profiles_sha256"] != sha(HERE / "profiles.json"):
        raise GateError("profile_changed_between_phases")
    return state, root


def require_private_api():
    token = os.environ.get("FACTORLAB_PRIVATE_TOKEN")
    if not token:
        raise GateError("missing_FACTORLAB_PRIVATE_TOKEN_no_private_data_requested")
    if not token.startswith("github_pat_"):
        raise GateError("requires_fine_grained_private_repo_token_not_local_oauth")
    api = GitHub(token)
    api.private_identity()
    return api


def prepare(profile_name, profile):
    api = require_private_api()
    if state_path().exists():
        raise GateError("existing_run_state")
    run_id = os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
    branch = "runs/public-baseline/" + run_id
    # Prove the exact private write authority before data or compute work.
    api.request(f"repos/{PRIVATE_REPO}/git/refs", {"ref": "refs/heads/" + branch, "sha": profile["private_ref"]}, method="POST")
    root = Path(tempfile.mkdtemp(prefix="fl-private-", dir=os.environ["RUNNER_TEMP"]))
    (root / "results").mkdir()
    prepare_inputs(api, root, profile)
    (root / "profile.json").write_text(json.dumps(profile))
    write_state(
        {
            "run_id": run_id,
            "root": str(root),
            "branch": branch,
            "profile_name": profile_name,
            "profiles_sha256": sha(HERE / "profiles.json"),
            "prepare_ready": True,
            "compute_success": False,
        }
    )
    print("Fixed private inputs verified; prepare step complete.")


def compute():
    if os.environ.get("FACTORLAB_PRIVATE_TOKEN"):
        raise GateError("private_token_must_not_reach_compute_step")
    state, root = load_state()
    results = root / "results"
    with (results / "container.log").open("xb") as stream:
        code = run_container(docker_command(root / "work", results, root / "profile.json"), stream, 840)
    collect_result_files(results)
    # A fresh trusted validator sees the stopped compute outputs read-only.
    # It never imports or executes private source code.
    with (root / "validation.json").open("xb") as output, (root / "validation.log").open("xb") as errors:
        validation_code = run_container(docker_command(root / "work", results, root / "profile.json", validator=True), output, 60, errors)
    shutil.copyfile(root / "validation.json", results / "controller_validation.json")
    shutil.copyfile(root / "validation.log", results / "controller_validation.log")
    validated = json.loads((root / "validation.json").read_text()) if validation_code == 0 else {}
    success = code == 0 and validation_code == 0 and validated.get("status") == "passed" and validated.get("cases_verified") == 4
    state.update(compute_success=success, compute_exit_code=code, validation_exit_code=validation_code)
    write_state(state)
    if not success:
        raise GateError("compute_failed_private_publish_step_will_report")
    print("Fixed compute and trusted output comparison finished; results remain private.")


def upload_result(api, release_id, archive):
    connection = http.client.HTTPSConnection("uploads.github.com", timeout=120)
    route = f"/repos/{PRIVATE_REPO}/releases/{release_id}/assets?name=" + urllib.parse.quote(archive.name, safe="")
    try:
        connection.putrequest("POST", route)
        for name, value in {
            "Authorization": "Bearer " + api.token,
            "Content-Type": "application/gzip",
            "Content-Length": str(archive.stat().st_size),
            "User-Agent": "factorlab-private-broker",
        }.items():
            connection.putheader(name, value)
        connection.endheaders()
        with archive.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                connection.send(block)
        response = connection.getresponse()
        if response.status != 201:
            raise GateError("private_result_upload_http_" + str(response.status))
        # No redirect handling and no response-body printing on this authenticated upload.
        body = response.read(1024 * 1024)
        return json.loads(body)
    finally:
        connection.close()


def publish(profile):
    state, root = load_state()
    if not state.get("cleanup_complete"):
        raise GateError("cleanup_must_complete_before_private_publish")
    api = require_private_api()
    results = root / "results"
    try:
        files = collect_result_files(results)
    except GateError:
        # Never dereference or archive an unsafe compute output.
        results = root / "safe-failure"
        results.mkdir()
        (results / "failure.json").write_text('{"status":"failed","reason":"unsafe_compute_output"}\n')
        files = collect_result_files(results)
        state["compute_success"] = False
    archive = root / "results.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in files:
            tar.add(results / name, arcname=name, recursive=False)
    if archive.stat().st_size > 512 * 1024 * 1024:
        raise GateError("private_result_archive_too_large")
    tag = "public-run-" + state["run_id"]
    release = api.request(
        f"repos/{PRIVATE_REPO}/releases",
        {
            "tag_name": tag,
            "target_commitish": profile["private_ref"],
            "draft": True,
            "prerelease": True,
            "name": "Public runner result " + state["run_id"],
            "body": "Pending verified result upload.",
        },
        method="POST",
    )
    uploaded = upload_result(api, release["id"], archive)
    expected_digest = "sha256:" + sha(archive)
    release = api.request(f"repos/{PRIVATE_REPO}/releases/{release['id']}")
    if (
        len(release["assets"]) != 1
        or uploaded.get("digest") != expected_digest
        or release["assets"][0]["size"] != archive.stat().st_size
        or release["assets"][0].get("digest") != expected_digest
        or release["assets"][0]["state"] != "uploaded"
    ):
        raise GateError("private_writeback_digest_failed")
    api.request(f"repos/{PRIVATE_REPO}/releases/{release['id']}", {"draft": False}, method="PATCH")
    success = state.get("compute_success", False)
    receipt = {
        "schema_id": "factorlab.public_runner_receipt@1.1",
        "status": "passed" if success else "failed",
        "delivery_status": "archive_uploaded_and_verified",
        "public_run_id": state["run_id"],
        "public_repository": PUBLIC_REPO,
        "public_source_sha": os.environ["GITHUB_SHA"],
        "private_source_ref": profile["private_ref"],
        "execution": "public_standard_runner_network_isolated_container",
        "catalog_sha256": profile["catalog_sha256"],
        "files": files,
        "archive": {"release_id": release["id"], "tag": tag, "sha256": sha(archive), "bytes": archive.stat().st_size},
        "new_training": False,
        "production_authority": False,
    }
    payload = (json.dumps(receipt, indent=2) + "\n").encode()
    target = f"repos/{PRIVATE_REPO}/contents/research/public-runs/{state['run_id']}.json"
    api.request(
        target,
        {
            "message": "Record verified public runner result [skip ci]",
            "branch": state["branch"],
            "content": base64.b64encode(payload).decode(),
        },
        method="PUT",
    )
    returned = api.request(target + "?ref=" + urllib.parse.quote(state["branch"], safe=""))
    if base64.b64decode(returned["content"]) != payload:
        raise GateError("private_receipt_readback_failed")
    print("Private result archive and receipt verified for public run " + state["run_id"] + ".")
    if not success:
        raise GateError("compute_failed_consult_private_receipt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["runtime-smoke", "prepare", "compute", "cleanup", "publish"])
    parser.add_argument("profile", nargs="?", choices=["baseline-replay-v1"], default="baseline-replay-v1")
    args = parser.parse_args()
    require_context(os.environ)
    os.umask(0o077)
    if args.phase == "runtime-smoke":
        if run_container(docker_command(), None, 90):
            raise GateError("runtime_smoke_failed")
        timeout_probe = docker_command()
        timeout_probe[-1] = "timeout-probe"
        if run_container(timeout_probe, subprocess.DEVNULL, 2) != 124:
            raise GateError("timeout_cleanup_canary_failed")
        print("Public standard-runner isolated runtime verified; no private inputs used.")
        return
    profile = validate_profile(json.loads((HERE / "profiles.json").read_text())["profiles"][args.profile])
    if args.phase == "prepare":
        prepare(args.profile, profile)
    elif args.phase == "compute":
        compute()
    elif args.phase == "cleanup":
        if os.environ.get("FACTORLAB_PRIVATE_TOKEN"):
            raise GateError("cleanup_step_must_not_have_private_token")
        removed = subprocess.run(
            ["docker", "rm", "--force", "factorlab-compute"], env=clean_env(), capture_output=True, text=True, timeout=30
        )
        if removed.returncode and "No such container" not in removed.stderr:
            raise GateError("container_cleanup_not_verified")
        state, _ = load_state()
        state["cleanup_complete"] = True
        write_state(state)
        print("Owned compute container is stopped; cleanup complete.")
    else:
        publish(profile)


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print("Execution stopped: " + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Execution failed; no private diagnostic content was published.", file=sys.stderr)
        sys.exit(1)
