import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("support_broker", ROOT / "executor/support_broker.py")
support_broker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(support_broker)


class SupportBrokerTests(unittest.TestCase):
    def test_registered_profile_is_fixed_and_passes_both_validators(self):
        profile = support_broker.base.load_profile("liq01-support-v1")
        self.assertEqual(profile["private_ref"], "99966aee28c3881497c099e98b90db5c704dc682")
        self.assertEqual(set(profile["source_files"]), set(support_broker.SOURCE_PATHS))
        self.assertEqual(profile["command"], support_broker.COMMAND)
        self.assertEqual(profile["verify_command"], support_broker.VERIFY_COMMAND)
        self.assertEqual(profile["command_timeout_seconds"], 600)
        self.assertEqual(profile["verification_timeout_seconds"], 300)
        self.assertIs(profile["new_training"], False)
        self.assertIs(profile["production_authority"], False)
        support_broker.validate_profile(profile)

    def test_other_research_profile_is_not_accepted_by_support_broker(self):
        with self.assertRaises(support_broker.base.GateError) as caught:
            support_broker.base.load_profile("liq01-attribution-v1")
        self.assertEqual(str(caught.exception), "unknown_profile")

    def test_wrapper_keeps_reviewed_transport_and_isolation_functions(self):
        self.assertIs(support_broker.base.prepare_inputs, support_broker.base.prepare_inputs)
        self.assertIs(support_broker.base.docker_command, support_broker.base.docker_command)
        self.assertEqual(support_broker.base.VALIDATE_HOST_TIMEOUT_SECONDS, 330)
        self.assertEqual(support_broker.base.SOURCE_BYTES_MAX, 1048576)
        self.assertEqual(support_broker.base.ARCHIVE_BYTES_MAX, 1024**3)

    def test_profile_catalog_has_no_extra_support_authority(self):
        catalog = json.loads((ROOT / "executor/research_profiles.json").read_text())
        profile = catalog["profiles"]["liq01-support-v1"]
        self.assertEqual(set(profile), support_broker.base.PROFILE_KEYS)
        self.assertFalse(profile["new_training"])
        self.assertFalse(profile["production_authority"])
        self.assertNotIn("pdf", " ".join(profile["source_files"]).lower())
        self.assertIn("run_support_checked.py", profile["source_files"])
        self.assertIn("test_support_integration.py", profile["source_files"])

    def test_compute_rejects_private_token_before_state_or_docker(self):
        with (
            mock.patch.dict(support_broker.base.os.environ, {"FACTORLAB_PRIVATE_TOKEN": "synthetic"}),
            mock.patch.object(support_broker.base, "load_state", side_effect=AssertionError("no state read")),
            self.assertRaises(support_broker.base.GateError) as caught,
        ):
            support_broker.base.compute()
        self.assertEqual(str(caught.exception), "private_token_must_not_reach_compute_step")


if __name__ == "__main__":
    unittest.main()
