"""Pure synthetic profile metadata tests; no credentials or real input data."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'executor'))
import support_profile_contract as p


def sample():
    return {
        'private_ref': 'a' * 40,
        'source_files': {k: {'bytes': 100, 'sha256': 'b' * 64} for k in p.SOURCE_PATHS},
        'input_files': {k: {'bytes': 100, 'sha256': 'c' * 64} for k in p.INPUT_FILES},
        'manifest_path': p.MANIFEST_PATH, 'manifest_sha256': 'b' * 64,
        'data_release_tag': 'liq01-input-v1-20260913', 'data_asset_name': 'liq01-input.tar.gz',
        'data_asset_sha256': 'c' * 64, 'data_asset_bytes': 1000,
        'command': list(p.COMMAND), 'verify_command': list(p.VERIFY_COMMAND),
        'command_timeout_seconds': 600, 'verification_timeout_seconds': 300,
        'new_training': False, 'production_authority': False,
    }

class ProfileTests(unittest.TestCase):
    def bad(self, change):
        x = sample(); change(x)
        with self.assertRaises(p.ProfileError): p.validate_profile(x)
    def test_valid_not_registration(self):
        x = sample(); before = copy.deepcopy(x); result = p.validate_profile(x)
        self.assertTrue(result['metadata_valid'])
        self.assertFalse(result['profile_registered'])
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['private_source_verified'])
        self.assertEqual(x, before)
    def test_moving_ref(self): self.bad(lambda x: x.update(private_ref='main'))
    def test_null_ref(self): self.bad(lambda x: x.update(private_ref=None))
    def test_extra_field(self): self.bad(lambda x: x.update(other='unused'))
    def test_extra_source(self): self.bad(lambda x: x['source_files'].update({'unlisted.py': {'bytes': 1, 'sha256': 'b'*64}}))
    def test_missing_source(self): self.bad(lambda x: x['source_files'].pop(p.MANIFEST_PATH))
    def test_missing_input(self): self.bad(lambda x: x['input_files'].pop('calendar.npy'))
    def test_nonregistered_command(self): self.bad(lambda x: x.update(command=['other_program.py']))
    def test_command_string(self): self.bad(lambda x: x.update(command=' '.join(p.COMMAND)))
    def test_wrong_verifier(self): self.bad(lambda x: x.update(verify_command=list(p.COMMAND)))
    def test_boolean_size(self): self.bad(lambda x: x.update(data_asset_bytes=True))
    def test_oversize(self): self.bad(lambda x: x.update(data_asset_bytes=1024**3+1))
    def test_timeout(self): self.bad(lambda x: x.update(command_timeout_seconds=601))
    def test_training(self): self.bad(lambda x: x.update(new_training=True))
    def test_non_boolean_false(self): self.bad(lambda x: x.update(new_training=0))
    def test_total_input_limit(self):
        self.bad(lambda x: [r.update(bytes=1024**3) for r in x['input_files'].values()])
    def test_manifest_mismatch(self): self.bad(lambda x: x.update(manifest_sha256='d'*64))
    def test_archive_digest(self): self.bad(lambda x: x.update(data_asset_sha256='not-a-digest'))
    def test_extra_file_record_field(self): self.bad(lambda x: x['source_files'][p.MANIFEST_PATH].update(other=1))
    def test_wrong_release(self): self.bad(lambda x: x.update(data_release_tag='another-release'))
    def test_checked_entry_required(self):
        self.assertEqual(p.COMMAND[0], p.SUPPORT + '/run_support_checked.py')
    def test_missing_native_check_entry(self):
        self.bad(lambda x: x['source_files'].pop(p.SUPPORT + '/run_support_checked.py'))
    def test_missing_integration_suite(self):
        self.bad(lambda x: x['source_files'].pop(p.SUPPORT + '/test_support_integration.py'))
    def test_direct_producer_not_execution_entry(self):
        command = list(p.COMMAND); command[0] = p.SUPPORT + '/run_support_study.py'
        self.bad(lambda x: x.update(command=command))

if __name__ == '__main__': unittest.main(verbosity=2)
