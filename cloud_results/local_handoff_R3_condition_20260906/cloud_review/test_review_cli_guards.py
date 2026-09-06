"""Actual submitted runner guard calls; no FactorLab import, model or fit.

Supply the reviewed repository root through R3_REVIEW_REPO when reproducing.
"""
import importlib.util
import os
from pathlib import Path
import sys
import pytest

ROOT = Path(os.environ['R3_REVIEW_REPO'])
spec = importlib.util.spec_from_file_location('reviewed_r3_runner', ROOT / 'scripts/reaka_r3_condition_compare.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_actual_main_refuses_existing_output(tmp_path, monkeypatch):
    output = tmp_path / 'existing'
    output.mkdir()
    (output / 'sentinel').write_bytes(b'unchanged')
    monkeypatch.setattr(sys, 'argv', ['runner', '--factorlab-root', str(tmp_path), '--output-dir', str(output)])
    with pytest.raises(ValueError, match='NEW output'):
        runner.main()
    assert (output / 'sentinel').read_bytes() == b'unchanged'


@pytest.mark.parametrize('protected', ['output', 'data'])
def test_actual_main_refuses_new_path_in_protected_tree(tmp_path, monkeypatch, protected):
    output = tmp_path / protected / 'new'
    monkeypatch.setattr(sys, 'argv', ['runner', '--factorlab-root', str(tmp_path), '--output-dir', str(output)])
    with pytest.raises(ValueError, match='NEW output'):
        runner.main()
    assert not output.exists()
