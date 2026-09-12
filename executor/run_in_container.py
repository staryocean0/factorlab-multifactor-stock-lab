"""Credential-free compute. All private output stays in mounted private results."""

import importlib
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import tempfile
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


def validate_baseline(actual_root, expected_root, runtime):
    import pandas as pd

    cases = []
    for period in ["repair_2018_2020", "validation_2021_2022"]:
        for clock in ["1430", "1445"]:
            actual, expected = actual_root / period / clock, expected_root / period / clock
            for name in ["portfolio_daily", "holdings", "trades", "events"]:
                path = actual / "snapshot" / (name + ".parquet")
                if path.is_symlink() or not path.resolve().is_relative_to(actual_root.resolve()):
                    raise ValueError("unsafe result path")
                pd.testing.assert_frame_equal(
                    pd.read_parquet(path), pd.read_parquet(expected / "snapshot" / (name + ".parquet")), check_exact=True
                )
            a, b = [json.loads((p / "result.json").read_text()) for p in [actual, expected]]
            for key in ["net_return", "cagr", "max_drawdown", "total_cost"]:
                if a[key] != b[key]:
                    raise ValueError("result differs from frozen baseline")
            if a["new_training"] is not False or a["production_authority"] is not False:
                raise ValueError("unexpected authority claim")
            cases.append({"period": period, "clock": clock, "four_account_frames_exact": True, "metrics_exact": True})
    return {"status": "passed", "cases_verified": len(cases), "cases": cases, "runtime": runtime}


def validator_canary(runtime):
    import pandas as pd

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for side in ["actual", "expected"]:
            for period in ["repair_2018_2020", "validation_2021_2022"]:
                for clock in ["1430", "1445"]:
                    p = root / side / period / clock
                    (p / "snapshot").mkdir(parents=True)
                    for name in ["portfolio_daily", "holdings", "trades", "events"]:
                        pd.DataFrame({"synthetic_only": [1.0]}).to_parquet(p / "snapshot" / (name + ".parquet"))
                    (p / "result.json").write_text(
                        json.dumps(
                            {
                                "net_return": 0,
                                "cagr": 0,
                                "max_drawdown": 0,
                                "total_cost": 0,
                                "new_training": False,
                                "production_authority": False,
                            }
                        )
                    )
        assert validate_baseline(root / "actual", root / "expected", runtime)["cases_verified"] == 4
        bad = root / "actual/repair_2018_2020/1430/snapshot/trades.parquet"
        pd.DataFrame({"synthetic_only": [2.0]}).to_parquet(bad)
        try:
            validate_baseline(root / "actual", root / "expected", runtime)
        except AssertionError:
            return True
        raise RuntimeError("output tamper not detected")


def main():
    runtime = runtime_check()
    if sys.argv[1:] == ["runtime-smoke"]:
        print(
            json.dumps(
                {
                    "status": "runtime_smoke_passed",
                    **runtime,
                    "synthetic_total": 17 * 3 + 23 * 2 + 5 * 11,
                    "validator_tamper_canary": validator_canary(runtime),
                }
            )
        )
        return
    if sys.argv[1:] == ["validate-baseline"]:
        print(json.dumps(validate_baseline(Path("/results/accounts"), Path("/work/runtime/expected"), runtime)))
        return
    if sys.argv[1:] == ["timeout-probe"]:
        time.sleep(10)
        return
    profile = json.loads(Path("/execution/profile.json").read_text())
    results = Path("/results")
    receipts = []
    for index, command in enumerate(profile["commands"]):
        started = time.monotonic()
        try:
            with (results / f"compute_{index:02}.log").open("xb") as stream:
                result = subprocess.run(
                    [sys.executable, *command],
                    cwd="/work",
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=profile["command_timeout_seconds"],
                    check=False,
                )
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
        receipts.append({"command_index": index, "exit_code": code, "seconds": time.monotonic() - started})
        if code:
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
