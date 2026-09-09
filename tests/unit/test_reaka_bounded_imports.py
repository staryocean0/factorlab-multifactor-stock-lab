from __future__ import annotations

import importlib
import subprocess
import sys


def test_bounded_pairing_module_import_does_not_require_unshipped_shared_services():
    subprocess.run(
        [sys.executable, "-c", "import factor_lab.factor_rotation.reaka_v2_stage4_observable_factor_pairing_v1"],
        check=True,
    )


def test_existing_lightweight_package_exports_remain_available():
    package = importlib.import_module("factor_lab.factor_rotation")
    constants = importlib.import_module("factor_lab.factor_rotation.constants")
    assert package.FACTOR_ROTATION_FRAMEWORK_VERSION == constants.FACTOR_ROTATION_FRAMEWORK_VERSION
    assert "FactorSpec" in dir(package)
