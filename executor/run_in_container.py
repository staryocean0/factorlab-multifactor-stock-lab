"""Credential-free compute. All private output stays in mounted private results."""

import importlib
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


def runtime_check():
    forbidden = [n for n in os.environ if any(x in n.upper() for x in ["TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY"])]
    if forbidden:
        raise RuntimeError("credential-like environment reached compute")
    # --network none must leave only loopback, independent of DNS/firewall luck.
    interfaces = [name for _, name in socket.if_nameindex()]
    if interfaces != ["lo"]:
        raise RuntimeError("compute network is not isolated")
    for module in ["numpy", "pandas", "pyarrow", "scipy", "torch", "pydantic", "yaml"]:
        importlib.import_module(module)
    return {
        "python": sys.version.split()[0],
        "versions": {n: importlib.metadata.version(n) for n in ["numpy", "pandas", "pyarrow", "scipy", "torch", "pydantic", "PyYAML"]},
        "network_interfaces": interfaces,
        "credential_environment_entries": 0,
    }


def main():
    runtime = runtime_check()
    if sys.argv[1:] == ["runtime-smoke"]:
        print(json.dumps({"status": "runtime_smoke_passed", **runtime, "synthetic_total": 17 * 3 + 23 * 2 + 5 * 11}))
        return
    profile = json.loads(Path("/execution/profile.json").read_text())
    results = Path("/results")
    receipts = []
    for index, command in enumerate(profile["commands"]):
        started = time.monotonic()
        with (results / f"compute_{index:02}.log").open("xb") as stream:
            result = subprocess.run(
                [sys.executable, *command],
                cwd="/work",
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=profile["command_timeout_seconds"],
                check=False,
            )
        receipts.append({"command_index": index, "exit_code": result.returncode, "seconds": time.monotonic() - started})
        if result.returncode:
            break
    passed = len(receipts) == len(profile["commands"]) and all(r["exit_code"] == 0 for r in receipts)
    (results / "compute_receipt.json").write_text(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "runtime": runtime,
                "commands": receipts,
                "new_training": profile["new_training"],
                "production_authority": False,
            },
            indent=2,
        )
    )
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
