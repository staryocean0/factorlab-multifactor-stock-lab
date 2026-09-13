"""Bounded public research broker for LIQ-01. Never print private bytes or pass credentials to compute."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_factorlab_baseline_broker", HERE / "broker.py")
broker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(broker)

GateError = broker.GateError
PRIVATE_REPO = broker.PRIVATE_REPO
PUBLIC_REPO = broker.PUBLIC_REPO
IMAGE = broker.IMAGE
sha = broker.sha
safe_path = broker.safe_path
unpack = broker.unpack
require_context = broker.require_context
collect_result_files = broker.collect_result_files
upload_result = broker.upload_result
require_private_api = broker.require_private_api
clean_env = broker.clean_env
run_container = broker.run_container

PROFILE_NAME = "liq01-attribution-v1"
PROFILE_SCHEMA = "factorlab.public_research_profiles@1.0"
RECEIPT_SCHEMA = "factorlab.public_research_runner_receipt@1.0"
SOURCE_ROOT = "research/systematic-factor-expansion-20260913/liq01"
SOURCE_PATHS = (
    f"{SOURCE_ROOT}/liquidity_v1.py",
    f"{SOURCE_ROOT}/run_study.py",
    f"{SOURCE_ROOT}/verify_study.py",
    f"{SOURCE_ROOT}/RUN_CONTRACT.json",
    f"{SOURCE_ROOT}/INPUT_MANIFEST.json",
)
MANIFEST_PATH = f"{SOURCE_ROOT}/INPUT_MANIFEST.json"
INPUT_FILES = (
    "daily.parquet",
    "calendar.npy",
    "symbols.npy",
    "decisions.npy",
    "beta_1430.npy",
    "mask_1430.npy",
    "returns_h20_1430.npy",
    "beta_1445.npy",
    "mask_1445.npy",
    "returns_h20_1445.npy",
)
COMMAND = [
    f"{SOURCE_ROOT}/run_study.py",
    "--inputs",
    "/work/inputs",
    "--out",
    "/results/study",
]
VERIFY_COMMAND = [
    f"{SOURCE_ROOT}/verify_study.py",
    "--inputs",
    "/work/inputs",
    "--results",
    "/results/study",
]
DATA_RELEASE_TAG = "liq01-input-v1-20260913"
DATA_ASSET_NAME = "liq01-input.tar.gz"
COMMAND_TIMEOUT_SECONDS = 600
VERIFICATION_TIMEOUT_SECONDS = 180
COMPUTE_HOST_TIMEOUT_SECONDS = 660
VALIDATE_HOST_TIMEOUT_SECONDS = 210
SOURCE_BYTES_MAX = 1048576
ARCHIVE_BYTES_MAX = 1024**3
PROFILE_KEYS = {
    "private_ref",
    "source_files",
    "manifest_path",
    "manifest_sha256",
    "data_release_tag",
    "data_asset_name",
    "data_asset_sha256",
    "data_asset_bytes",
    "input_files",
    "command",
    "verify_command",
    "command_timeout_seconds",
    "verification_timeout_seconds",
    "new_training",
    "production_authority",
}


def _digest_pair(value, min_bytes=1, max_bytes=SOURCE_BYTES_MAX):
    if not isinstance(value, dict) or set(value) != {"bytes", "sha256"}:
        raise GateError("unknown_profile_field")
    size = value["bytes"]
    digest = value["sha256"]
    if type(size) is not int or size < min_bytes or size > max_bytes:
        raise GateError("profile_file_size_invalid")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise GateError("profile_not_immutable")


def validate_profile(value):
    if not isinstance(value, dict) or set(value) != PROFILE_KEYS:
        raise GateError("unknown_profile_field")
    if not re.fullmatch(r"[0-9a-f]{40}", value.get("private_ref", "")) or not re.fullmatch(
        r"[0-9a-f]{64}", value.get("manifest_sha256", "")
    ):
        raise GateError("profile_not_immutable")
    if value.get("new_training") is not False or value.get("production_authority") is not False:
        raise GateError("scope_not_authorized")
    if value.get("manifest_path") != MANIFEST_PATH:
        raise GateError("unapproved_manifest_path")
    if value.get("data_release_tag") != DATA_RELEASE_TAG or value.get("data_asset_name") != DATA_ASSET_NAME:
        raise GateError("unapproved_data_identity")
    if value.get("command") != COMMAND or value.get("verify_command") != VERIFY_COMMAND:
        raise GateError("unapproved_command")
    if (
        value.get("command_timeout_seconds") != COMMAND_TIMEOUT_SECONDS
        or value.get("verification_timeout_seconds") != VERIFICATION_TIMEOUT_SECONDS
    ):
        raise GateError("profile_timeout_changed")
    if type(value.get("data_asset_bytes")) is not int or not 1 <= value["data_asset_bytes"] <= ARCHIVE_BYTES_MAX:
        raise GateError("profile_file_size_invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", value.get("data_asset_sha256", "")):
        raise GateError("profile_not_immutable")
    source_files = value.get("source_files")
    if not isinstance(source_files, dict):
        raise GateError("unknown_profile_field")
    if any(str(path).lower().endswith(".pdf") for path in source_files):
        raise GateError("pdf_source_not_allowed")
    if set(source_files) != set(SOURCE_PATHS):
        raise GateError("unapproved_source_set")
    for path in SOURCE_PATHS:
        _digest_pair(source_files[path], min_bytes=1, max_bytes=SOURCE_BYTES_MAX)
    input_files = value.get("input_files")
    if not isinstance(input_files, dict) or set(input_files) != set(INPUT_FILES):
        raise GateError("unapproved_input_set")
    for name in INPUT_FILES:
        _digest_pair(input_files[name], min_bytes=1, max_bytes=ARCHIVE_BYTES_MAX)
    if sum(row["bytes"] for row in input_files.values()) > ARCHIVE_BYTES_MAX:
        raise GateError("input_byte_budget_exceeded")
    return value


def load_profile(name):
    if name != PROFILE_NAME:
        raise GateError("unknown_profile")
    catalog = json.loads((HERE / "research_profiles.json").read_text())
    if not isinstance(catalog, dict) or set(catalog) != {"schema_id", "profiles"}:
        raise GateError("unknown_profile_field")
    if catalog.get("schema_id") != PROFILE_SCHEMA:
        raise GateError("unknown_profile_schema")
    profiles = catalog.get("profiles")
    if not isinstance(profiles, dict) or name not in profiles:
        raise GateError("incomplete_profile")
    return validate_profile(profiles[name])


def docker_command(work, results, profile_path, validator=False):
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
        "--entrypoint",
        "python3",
        "--mount",
        f"type=bind,src={work},dst=/work,readonly",
        "--mount",
        f"type=bind,src={profile_path},dst=/execution/profile.json,readonly",
    ]
    if validator:
        args += ["--mount", f"type=bind,src={results},dst=/results,readonly"]
        return args + [IMAGE, "/run_research_in_container.py", "validate-research"]
    args += ["--mount", f"type=bind,src={results},dst=/results"]
    return args + [IMAGE, "/run_research_in_container.py"]


def state_path():
    return Path(os.environ["RUNNER_TEMP"]) / "factorlab-research-state.json"


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
    if not root.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve()) or not root.name.startswith("fl-research-"):
        raise GateError("invalid_state_root")
    if state["run_id"] != os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]:
        raise GateError("state_run_identity_mismatch")
    if state["profiles_sha256"] != sha(HERE / "research_profiles.json"):
        raise GateError("profile_changed_between_phases")
    return state, root


def fetch_source_file(api, path, ref, expected):
    quoted = urllib.parse.quote(path, safe="/")
    meta = api.request(f"repos/{PRIVATE_REPO}/contents/{quoted}?ref={ref}")
    if meta.get("type") != "file" or meta.get("encoding") != "base64" or meta.get("size") != expected["bytes"]:
        raise GateError("source_blob_identity_failed")
    try:
        raw = base64.b64decode(meta["content"])
    except Exception:
        raise GateError("source_blob_identity_failed") from None
    if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
        raise GateError("source_blob_digest_mismatch")
    return raw


def prepare_inputs(api, root, profile):
    work = root / "work"
    work.mkdir()
    ref = profile["private_ref"]
    for path in SOURCE_PATHS:
        raw = fetch_source_file(api, path, ref, profile["source_files"][path])
        destination = safe_path(work, path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(raw)
        if sha(destination) != profile["source_files"][path]["sha256"]:
            raise GateError("source_blob_digest_mismatch")
    manifest_file = work / profile["manifest_path"]
    if sha(manifest_file) != profile["manifest_sha256"]:
        raise GateError("manifest_digest_failed")
    try:
        manifest = json.loads(manifest_file.read_text())
    except Exception:
        raise GateError("manifest_identity_failed") from None
    if manifest.get("files") != profile["input_files"]:
        raise GateError("manifest_input_set_mismatch")
    release = api.request(f"repos/{PRIVATE_REPO}/releases/tags/{profile['data_release_tag']}")
    if release.get("draft") is not False:
        raise GateError("private_data_release_not_published")
    assets = {item["name"]: item for item in release.get("assets") or []}
    asset = assets.get(profile["data_asset_name"])
    if (
        not asset
        or asset.get("state") != "uploaded"
        or asset.get("size") != profile["data_asset_bytes"]
        or asset.get("digest") != "sha256:" + profile["data_asset_sha256"]
    ):
        raise GateError("remote_asset_identity_failed")
    archive = root / DATA_ASSET_NAME
    api.request(
        f"repos/{PRIVATE_REPO}/releases/assets/{asset['id']}",
        binary_path=archive,
        max_bytes=profile["data_asset_bytes"],
    )
    if archive.stat().st_size != profile["data_asset_bytes"] or sha(archive) != profile["data_asset_sha256"]:
        raise GateError("downloaded_asset_digest_failed")
    inputs = work / "inputs"
    inputs.mkdir()
    unpack(archive, inputs, expected=profile["input_files"])
    return work


def prepare(profile_name, profile):
    api = require_private_api()
    if state_path().exists():
        raise GateError("existing_run_state")
    run_id = os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
    branch = "runs/public-research/" + run_id
    api.request(
        f"repos/{PRIVATE_REPO}/git/refs",
        {"ref": "refs/heads/" + branch, "sha": profile["private_ref"]},
        method="POST",
    )
    root = Path(tempfile.mkdtemp(prefix="fl-research-", dir=os.environ["RUNNER_TEMP"]))
    (root / "results").mkdir()
    prepare_inputs(api, root, profile)
    (root / "profile.json").write_text(json.dumps(profile))
    write_state(
        {
            "run_id": run_id,
            "root": str(root),
            "branch": branch,
            "profile_name": profile_name,
            "profiles_sha256": sha(HERE / "research_profiles.json"),
            "prepare_ready": True,
            "compute_success": False,
        }
    )
    print("Fixed private research inputs verified; prepare step complete.")


def _load_validator_status(path, validation_code):
    if validation_code != 0:
        return {}
    try:
        value = json.loads(path.read_text())
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def compute():
    if os.environ.get("FACTORLAB_PRIVATE_TOKEN"):
        raise GateError("private_token_must_not_reach_compute_step")
    state, root = load_state()
    results = root / "results"
    with (results / "container.log").open("xb") as stream:
        code = run_container(docker_command(root / "work", results, root / "profile.json"), stream, COMPUTE_HOST_TIMEOUT_SECONDS)
    collect_result_files(results)
    with (root / "validation.json").open("xb") as output, (root / "validation.log").open("xb") as errors:
        validation_code = run_container(
            docker_command(root / "work", results, root / "profile.json", validator=True),
            output,
            VALIDATE_HOST_TIMEOUT_SECONDS,
            errors,
        )
    broker.shutil.copyfile(root / "validation.json", results / "controller_validation.json")
    broker.shutil.copyfile(root / "validation.log", results / "controller_validation.log")
    validated = _load_validator_status(root / "validation.json", validation_code)
    success = code == 0 and validation_code == 0 and validated.get("status") == "passed"
    state.update(compute_success=success, compute_exit_code=code, validation_exit_code=validation_code)
    write_state(state)
    if not success:
        raise GateError("compute_failed_private_publish_step_will_report")
    print("Fixed research compute and trusted output comparison finished; results remain private.")


def cleanup():
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


def publish(profile):
    state, root = load_state()
    if not state.get("cleanup_complete"):
        raise GateError("cleanup_must_complete_before_private_publish")
    api = require_private_api()
    results = root / "results"
    try:
        files = collect_result_files(results)
    except GateError:
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
    tag = "public-research-run-" + state["run_id"]
    release = api.request(
        f"repos/{PRIVATE_REPO}/releases",
        {
            "tag_name": tag,
            "target_commitish": profile["private_ref"],
            "draft": True,
            "prerelease": True,
            "name": "Public research runner result " + state["run_id"],
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
        "schema_id": RECEIPT_SCHEMA,
        "status": "passed" if success else "failed",
        "delivery_status": "archive_uploaded_and_verified",
        "public_run_id": state["run_id"],
        "public_source_sha": os.environ["GITHUB_SHA"],
        "private_source_ref": profile["private_ref"],
        "profile": state["profile_name"],
        "manifest_sha256": profile["manifest_sha256"],
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
            "message": "Record verified public research runner result [skip ci]",
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
    parser.add_argument("phase", choices=["prepare", "compute", "cleanup", "publish"])
    parser.add_argument("profile", nargs="?", default=PROFILE_NAME)
    args = parser.parse_args()
    require_context(os.environ)
    os.umask(0o077)
    profile = load_profile(args.profile)
    if args.phase == "prepare":
        prepare(args.profile, profile)
    elif args.phase == "compute":
        compute()
    elif args.phase == "cleanup":
        cleanup()
    else:
        publish(profile)


def run():
    try:
        main()
    except GateError as error:
        print("Execution stopped: " + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Execution failed; no private diagnostic content was published.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
