from __future__ import annotations
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/reaka_local_source_receipt.py'
SPEC = importlib.util.spec_from_file_location('local_source_receipt_under_test', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def request(path, expected):
    return {'missing_declared_source_files': [{'path': path, 'expected': expected}]}


def digest(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def test_metadata_only_preserves_source_bytes_and_does_not_claim_pit(tmp_path):
    source = tmp_path / 'input'
    source.write_bytes(b'private-array-placeholder')
    report = MODULE.collect(request('input', digest(source.read_bytes())), tmp_path)
    assert report['counts']['byte_match'] == 1
    assert report['external_pit_verified'] is False
    assert report['historical_reproduction'] is False
    assert report['scientific_acceptance'] is False
    assert report['raw_data_included'] is False
    assert 'private-array-placeholder' not in json.dumps(report)
    assert source.read_bytes() == b'private-array-placeholder'
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize('path', ['../x', '/etc/passwd', '..\\x'])
def test_escape_is_an_error_not_a_missing_source(tmp_path, path):
    report = MODULE.collect(request(path, digest(b'x')), tmp_path)
    assert report['counts']['error'] == 1
    assert report['counts']['missing'] == 0


def test_symlink_cannot_read_outside_selected_input_root(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'x')
    (source / 'link').symlink_to(outside)
    report = MODULE.collect(request('link', digest(b'x')), source)
    assert report['counts']['error'] == 1


def test_missing_input_not_accepted(tmp_path):
    report = MODULE.collect(request('missing', digest(b'x')), tmp_path)
    assert report['counts']['missing'] == 1


def test_corruption_is_mismatch_not_missing(tmp_path):
    (tmp_path / 'x').write_bytes(b'bad')
    report = MODULE.collect(request('x', digest(b'expected')), tmp_path)
    assert report['counts']['byte_mismatch'] == 1


def test_conflicting_expected_digests_refused(tmp_path):
    req = {'missing_declared_source_files': [{'path': 'x', 'expected': digest(b'a')}, {'path': 'x', 'expected': digest(b'b')}]}
    with pytest.raises(ValueError, match='conflicting'):
        MODULE.collect(req, tmp_path)


def test_empty_request_does_not_fake_complete_inventory(tmp_path):
    with pytest.raises(ValueError):
        MODULE.collect({}, tmp_path)


def test_unknown_ot_digest_convention_is_not_chosen_to_pass(tmp_path):
    base = tmp_path / 'ot/1430'
    expected = {}
    for ot in ('ot1', 'ot2', 'ot3'):
        (base / ot).mkdir(parents=True)
        (base / ot / 'manifest.json').write_bytes(b'{}')
        expected['formal_1430_' + ot] = digest(b'{}')
    req = {'required_bounded_upstream': [{'stage': 'P6.2', 'original_roots': ['ot/1430'], 'manifest_digests_recorded': expected}]}
    report = MODULE.collect(req, tmp_path)
    row = next(r for r in report['rows'] if r['path'].endswith('ot1/manifest.json'))
    assert row['raw_matches_recorded'] is True
    assert row['canonical_candidate_matches_recorded'] is True
    assert row['status'] == 'present_unbound'
    assert report['counts']['present_unbound'] == 3
    assert report['counts']['missing'] == 4
    assert report['scientific_acceptance'] is False


def test_target_fill_only_reads_explicit_bounded_paths(tmp_path):
    (tmp_path / 'formal').mkdir()
    (tmp_path / 'formal/calendar.npy').write_bytes(b'npy-placeholder')
    req = {'required_bounded_upstream': [{'stage': 'P6.1', 'original_root': 'formal', 'original_file_digests': {'calendar.npy': digest(b'npy-placeholder')}}]}
    report = MODULE.collect(req, tmp_path)
    assert len(report['rows']) == 1
    assert report['counts']['byte_match'] == 1


def test_account_source_gap_is_preserved_not_repaired(tmp_path):
    (tmp_path / 'x').write_bytes(b'x')
    req = request('x', digest(b'x'))
    req['unrecovered_account_sources'] = [{'path': 'old-account.py', 'expected': digest(b'old')}]
    report = MODULE.collect(req, tmp_path)
    assert report['account_source_gaps_not_repaired'] == req['unrecovered_account_sources']
    assert not (tmp_path / 'old-account.py').exists()


@pytest.mark.parametrize('mode,exit_code', [('match', 0), ('mismatch', 1), ('missing', 2)])
def test_cli_exit_codes_describe_inventory_not_scientific_acceptance(tmp_path, mode, exit_code):
    source = tmp_path / 'source'
    source.mkdir()
    if mode != 'missing':
        (source / 'x').write_bytes(b'x' if mode == 'match' else b'bad')
    req = tmp_path / 'request.json'
    req.write_text(json.dumps(request('x', digest(b'x'))))
    proc = subprocess.run([sys.executable, str(SCRIPT), '--request', str(req), '--input-root', str(source)], capture_output=True, text=True, timeout=15)
    assert proc.returncode == exit_code
    report = json.loads(proc.stdout)
    assert report['scientific_acceptance'] is False
    assert report['request_sha256'] == digest(req.read_bytes())
    assert report['collector_sha256'] == digest(SCRIPT.read_bytes())


def test_bad_cli_request_returns_json_error(tmp_path):
    req = tmp_path / 'invalid.json'
    req.write_text('{')
    proc = subprocess.run([sys.executable, str(SCRIPT), '--request', str(req), '--input-root', str(tmp_path)], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)['status'] == 'invalid_request'


@pytest.mark.parametrize('text', ['[]', '{"x": 1, "x": 2}', '{"x": NaN}'])
def test_ambiguous_request_json_is_rejected(text):
    with pytest.raises(ValueError):
        MODULE.load_request(text)


@pytest.mark.parametrize('bad', [{'missing_declared_source_files': [None]}, {'required_bounded_upstream': {}}, {'additional_transitive_source_dependencies': 'not-a-list'}])
def test_malformed_request_sections_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        MODULE.collect(bad, tmp_path)


def test_file_changed_during_inventory_does_not_pass(tmp_path, monkeypatch):
    source = tmp_path / 'x'
    source.write_bytes(b'x')
    original = MODULE.file_digest
    def changed(path):
        result = original(path)
        path.write_bytes(b'changed while reading')
        return result
    monkeypatch.setattr(MODULE, 'file_digest', changed)
    report = MODULE.collect(request('x', digest(b'x')), tmp_path)
    assert report['counts']['error'] == 1
    assert report['counts']['byte_match'] == 0
