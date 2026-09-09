"""V1.3 regression tests exercise V1.3 bytes, not an editing lock on V1.4.

Current semantics, navigation, scope reporting and actual source behavior are
covered independently by test_reaka_infrastructure_v1_4 and the other unit tests.
"""
from pathlib import Path

from factor_lab.governance.reaka_historical_snapshot import load_historical_contract_tests

load_historical_contract_tests(globals(), Path(__file__).resolve().parents[2])
