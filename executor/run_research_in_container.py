"""Credential-free LIQ-01 compute wrapper. Private stdout/stderr stay in mounted results."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path


def runtime_check():
    forbidden = [n for n in os.environ if any(x in n.upper() for x in ["TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY"])]
    if forbidden:
        raise RuntimeError("credential-like environment reached compute")
    interfaces = [name for _, name in socket.if_nameindex()]
    if interfaces != ["lo"]:
        raise RuntimeError("compute network is not isolated")
    return {"network_interfaces": interfaces, "credential_environment_entries": 0}


def run_compute(profile):
    # The private producer owns creation of its fresh study directory.
    Path("/results").mkdir(parents=True, exist_ok=True)
    try:
        with Path("/results/compute.log").open("xb") as stream:
            completed = subprocess.run(
                [sys.executable, *profile["command"]],
                cwd="/work",
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=profile["command_timeout_seconds"],
                check=False,
            )
        code = completed.returncode
    except subprocess.TimeoutExpired:
        code = 124
    except Exception:
        code = 1
    Path("/results/compute_receipt.json").write_text(
        json.dumps(
            {
                "status": "passed" if code == 0 else "failed",
                "exit_code": code,
                "new_training": False,
                "production_authority": False,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if code == 0 else 1


def run_verify(profile):
    try:
        completed = subprocess.run(
            [sys.executable, *profile["verify_command"]],
            cwd="/work",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=profile["verification_timeout_seconds"],
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("validator_timeout", file=sys.stderr)
        return 124
    except Exception:
        print("validator_failed", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(completed.stdout)
    sys.stderr.buffer.write(completed.stderr)
    return 0 if completed.returncode == 0 else 1


def main():
    try:
        runtime_check()
    except Exception:
        print("isolated_runtime_check_failed", file=sys.stderr)
        sys.exit(1)
    try:
        profile = json.loads(Path("/execution/profile.json").read_text())
    except Exception:
        print("profile_unavailable", file=sys.stderr)
        sys.exit(1)
    args = sys.argv[1:]
    if args == ["validate-research"]:
        sys.exit(run_verify(profile))
    if args:
        print("unapproved_container_mode", file=sys.stderr)
        sys.exit(1)
    sys.exit(run_compute(profile))


if __name__ == "__main__":
    main()
