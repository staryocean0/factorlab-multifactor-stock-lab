"""Static validation for one proposed support-diagnostic execution profile.

This module performs no file, network, credential, job or repository operation.
Validation does not establish that the pinned private files exist, that inputs
are scientifically admitted, or that the profile is registered with a broker.
"""
from __future__ import annotations
import re
from collections.abc import Mapping

PROFILE_NAME = 'liq01-support-v1'
ROOT = 'research/systematic-factor-expansion-20260913'
SUPPORT = ROOT + '/liq01_support_audit'
MANIFEST_PATH = ROOT + '/liq01/INPUT_MANIFEST.json'
SOURCE_PATHS = frozenset((
    ROOT + '/liq01/liquidity_v1.py',
    ROOT + '/liq01/RUN_CONTRACT.json',
    MANIFEST_PATH,
    'research/data_quality_20260913/quality_gate.py',
    SUPPORT + '/support_diagnostics.py',
    SUPPORT + '/support_io.py',
    SUPPORT + '/run_support_study.py',
    SUPPORT + '/verify_support_study.py',
    SUPPORT + '/SUPPORT_RUN_CONTRACT.json',
))
INPUT_FILES = frozenset((
    'daily.parquet', 'calendar.npy', 'symbols.npy', 'decisions.npy',
    'beta_1430.npy', 'mask_1430.npy', 'returns_h20_1430.npy',
    'beta_1445.npy', 'mask_1445.npy', 'returns_h20_1445.npy',
))
COMMAND = (SUPPORT + '/run_support_study.py', '--inputs', '/work/inputs', '--out', '/results/study')
VERIFY_COMMAND = (SUPPORT + '/verify_support_study.py', '--inputs', '/work/inputs', '--results', '/results/study')
KEYS = frozenset((
    'private_ref', 'source_files', 'manifest_path', 'manifest_sha256',
    'data_release_tag', 'data_asset_name', 'data_asset_sha256',
    'data_asset_bytes', 'input_files', 'command', 'verify_command',
    'command_timeout_seconds', 'verification_timeout_seconds',
    'new_training', 'production_authority',
))

class ProfileError(ValueError):
    """Only constant, non-sensitive reason codes are returned."""


def _require(condition, reason):
    if not condition:
        raise ProfileError(reason)


def _digest(value, length=64):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{' + str(length) + '}', value) is not None


def _file_table(value, names, maximum):
    _require(isinstance(value, Mapping) and set(value) == names, 'unexpected_file_set')
    for record in value.values():
        _require(isinstance(record, Mapping) and set(record) == {'bytes', 'sha256'}, 'invalid_file_record')
        _require(type(record['bytes']) is int and 1 <= record['bytes'] <= maximum, 'invalid_file_size')
        _require(_digest(record['sha256']), 'invalid_file_digest')


def validate_profile(value):
    """Check exact paths, commands and bounded metadata; return no authority."""
    _require(isinstance(value, Mapping) and set(value) == KEYS, 'unexpected_profile_fields')
    _require(_digest(value['private_ref'], 40), 'immutable_commit_required')
    _require(value['new_training'] is False and value['production_authority'] is False, 'diagnostic_only')
    _require(value['manifest_path'] == MANIFEST_PATH and _digest(value['manifest_sha256']), 'invalid_manifest')
    _require(value['data_release_tag'] == 'liq01-input-v1-20260913', 'unexpected_release')
    _require(value['data_asset_name'] == 'liq01-input.tar.gz', 'unexpected_asset')
    _require(type(value['data_asset_bytes']) is int and 1 <= value['data_asset_bytes'] <= 1024**3, 'archive_size_limit')
    _require(_digest(value['data_asset_sha256']), 'invalid_archive_digest')
    for key, expected in (('command', COMMAND), ('verify_command', VERIFY_COMMAND)):
        _require(type(value[key]) is list and value[key] == list(expected), 'unexpected_command')
    for key, expected in (('command_timeout_seconds', 600), ('verification_timeout_seconds', 300)):
        _require(type(value[key]) is int and value[key] == expected, 'unexpected_timeout')
    _file_table(value['source_files'], SOURCE_PATHS, 1024**2)
    _file_table(value['input_files'], INPUT_FILES, 1024**3)
    _require(sum(record['bytes'] for record in value['input_files'].values()) <= 1024**3, 'input_total_limit')
    _require(value['source_files'][MANIFEST_PATH]['sha256'] == value['manifest_sha256'], 'manifest_digest_disagreement')
    return {'profile': PROFILE_NAME, 'metadata_valid': True,
            'private_source_verified': False, 'profile_registered': False,
            'execution_authorized': False}
