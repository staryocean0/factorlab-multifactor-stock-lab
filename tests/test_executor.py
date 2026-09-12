import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("broker", ROOT / "executor/broker.py")
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


class ExecutorTests(unittest.TestCase):
    def test_context_rejects_fork_push_private_and_other_branch(self):
        good = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": broker.PUBLIC_REPO,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": broker.BRANCH,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        broker.require_context(good)
        for key, value in [
            ("GITHUB_REPOSITORY", "attacker/fork"),
            ("GITHUB_EVENT_NAME", "pull_request_target"),
            ("GITHUB_EVENT_NAME", "push"),
            ("GITHUB_REF", "refs/heads/unreviewed"),
            ("GITHUB_RUN_ID", "1;bad"),
        ]:
            with self.subTest(key=key, value=value), self.assertRaises(broker.GateError):
                broker.require_context({**good, key: value})

    def test_profile_is_complete_and_fixed(self):
        p = json.loads((ROOT / "executor/profiles.json").read_text())["profiles"]["baseline-replay-v1"]
        broker.validate_profile(p)
        for key, value in [
            ("private_ref", "main"),
            ("new_training", True),
            ("packages", ["hourly-stock"]),
            ("commands", p["commands"][:3]),
            ("output_mount", "../escape"),
        ]:
            with self.subTest(key=key), self.assertRaises(broker.GateError):
                broker.validate_profile({**p, key: value})
        bad = json.loads(json.dumps(p))
        bad["commands"][0][0] = "arbitrary.py"
        with self.assertRaises(broker.GateError):
            broker.validate_profile(bad)

    def test_compute_has_no_credentials_or_host_network(self):
        args = broker.docker_command()
        self.assertEqual(args[args.index("--network") + 1], "none")
        self.assertIn("--read-only", args)
        self.assertIn("--cap-drop=ALL", args)
        self.assertIn("--security-opt=no-new-privileges", args)
        self.assertNotIn("--privileged", args)
        self.assertNotIn("/var/run/docker.sock", " ".join(args))
        self.assertNotIn("TOKEN", " ".join(args))
        self.assertNotIn("--env-file", args)

    def test_redirect_strips_token_and_rejects_foreign_host(self):
        request = urllib.request.Request(
            "https://api.github.com/repos/test/releases/assets/1", headers={"Authorization": "Bearer synthetic"}
        )
        handler = broker.SafeRedirect()
        redirected = handler.redirect_request(request, None, 302, "", {}, "https://release-assets.githubusercontent.com/file")
        self.assertFalse(redirected.has_header("Authorization"))
        for url in ["https://attacker.example/file", "http://api.github.com/file"]:
            with self.assertRaises(broker.GateError):
                handler.redirect_request(request, None, 302, "", {}, url)

    def test_paths_reject_escape(self):
        for value in ["/absolute", "../escape", "foo/../../escape", "foo\\bar"]:
            with self.assertRaises(broker.GateError):
                broker.safe_path(Path("/safe"), value)

    def test_archive_refuses_links_duplicates_and_unregistered_files(self):
        for case in ["link", "duplicate", "unexpected"]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                tar_path = root / "payload.tar"
                with tarfile.open(tar_path, "w") as archive:
                    member = tarfile.TarInfo("data.bin")
                    if case == "link":
                        member.type = tarfile.SYMTYPE
                        member.linkname = "/tmp"
                        archive.addfile(member)
                    else:
                        member.size = 1
                        archive.addfile(member, io.BytesIO(b"x"))
                        if case == "duplicate":
                            archive.addfile(member, io.BytesIO(b"x"))
                with self.assertRaises(broker.GateError):
                    broker.unpack(tar_path, root / "out", expected={})

    def test_exact_archive_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tar_path = root / "payload.tar"
            with tarfile.open(tar_path, "w") as archive:
                member = tarfile.TarInfo("nested/data.bin")
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
            expected = {"nested/data.bin": {"bytes": 1, "sha256": broker.hashlib.sha256(b"x").hexdigest()}}
            broker.unpack(tar_path, root / "out", expected)
            with self.assertRaises(broker.GateError):
                broker.unpack(tar_path, root / "out", expected)

    def test_workflow_is_manual_standard_only_without_public_artifacts(self):
        text = (ROOT / ".github/workflows/public-compute.yml").read_text()
        self.assertIn("runs-on: ubuntu-24.04", text)
        self.assertIn("workflow_dispatch:", text)
        for forbidden in [
            "pull_request_target:",
            "pull_request:",
            "push:",
            "upload-artifact",
            "actions/cache",
            "contents: write",
            "self-hosted",
        ]:
            self.assertNotIn(forbidden, text)
        self.assertIn("persist-credentials: false", text)


if __name__ == "__main__":
    unittest.main()
