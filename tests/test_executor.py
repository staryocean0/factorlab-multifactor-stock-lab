import importlib.util
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("broker", ROOT / "executor/broker.py")
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


class ExecutorTests(unittest.TestCase):
    def test_binary_archive_and_release_asset_use_distinct_accept_headers(self):
        api = broker.GitHub("synthetic-not-a-token")
        for route, accept in [
            ("repos/example/project/tarball/" + "a" * 40, "application/vnd.github+json"),
            ("repos/example/project/releases/assets/123", "application/octet-stream"),
        ]:
            with self.subTest(route=route), tempfile.TemporaryDirectory() as temp:
                response = io.BytesIO(b"synthetic binary")
                with mock.patch.object(api.opener, "open", return_value=response) as opened:
                    dest = Path(temp) / "download.bin"
                    api.request(route, binary_path=dest)
                    self.assertEqual(opened.call_args.args[0].get_header("Accept"), accept)
                    self.assertEqual(dest.read_bytes(), b"synthetic binary")

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

    def test_unknown_profile_field_rejected(self):
        p = json.loads((ROOT / "executor/profiles.json").read_text())["profiles"]["baseline-replay-v1"]
        with self.assertRaises(broker.GateError):
            broker.validate_profile({**p, "extra_docker": "--privileged"})

    def test_compute_step_has_no_private_secret_and_budget_fits(self):
        text = (ROOT / ".github/workflows/public-compute.yml").read_text()
        compute = text.split("- name: Compute without")[1].split("- name: Stop owned")[0]
        cleanup = text.split("- name: Stop owned")[1].split("- name: Return verified")[0]
        self.assertNotIn("secrets.", compute + cleanup)
        self.assertEqual(text.count("secrets.FACTORLAB_PRIVATE_TOKEN"), 2)
        values = [int(v) for v in re.findall(r"timeout-minutes: (\d+)", text)]
        self.assertLessEqual(sum(values[1:]), values[0])

    def test_result_symlink_never_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.json"
            outside.write_text('{"synthetic_secret":"not-real"}')
            results = root / "results"
            results.mkdir()
            (results / "compute_receipt.json").symlink_to(outside)
            with mock.patch.object(broker, "sha", side_effect=AssertionError("must not dereference")), self.assertRaises(broker.GateError):
                broker.collect_result_files(results)

    def test_timeout_cleans_only_owned_container_and_scrubs_environment(self):
        process = mock.Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired("docker", 1), 0]
        process.poll.return_value = None
        cleanup = subprocess.CompletedProcess([], 0, "", "")
        with (
            mock.patch.dict(os.environ, {"FACTORLAB_PRIVATE_TOKEN": "synthetic"}),
            mock.patch.object(broker.subprocess, "Popen", return_value=process) as popen,
            mock.patch.object(broker.subprocess, "run", return_value=cleanup) as removed,
        ):
            self.assertEqual(broker.run_container(["docker", "run"], None, 1), 124)
            self.assertEqual(set(popen.call_args.kwargs["env"]), {"PATH", "LANG"})
            self.assertEqual(removed.call_args.args[0], ["docker", "rm", "--force", "factorlab-compute"])
            process.kill.assert_called_once()

    def test_compute_refuses_token_before_loading_inputs(self):
        with (
            mock.patch.dict(os.environ, {"FACTORLAB_PRIVATE_TOKEN": "synthetic"}),
            mock.patch.object(broker, "load_state", side_effect=AssertionError("no input reads")),
            self.assertRaises(broker.GateError),
        ):
            broker.compute()

    def test_broad_oauth_is_rejected_before_private_request(self):
        with (
            mock.patch.dict(os.environ, {"FACTORLAB_PRIVATE_TOKEN": "gho_synthetic_not_real"}),
            mock.patch.object(broker, "GitHub", side_effect=AssertionError("no network")),
            self.assertRaises(broker.GateError),
        ):
            broker.require_private_api()

    def test_no_success_receipt_before_result_upload_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            results = root / "results"
            results.mkdir()
            (results / "compute.log").write_text("synthetic")
            api = mock.Mock()
            api.request.return_value = {"id": 123}
            state = {"cleanup_complete": True, "run_id": "123-1", "branch": "runs/test", "compute_success": True}
            with (
                mock.patch.object(broker, "load_state", return_value=(state, root)),
                mock.patch.object(broker, "require_private_api", return_value=api),
                mock.patch.object(broker, "upload_result", side_effect=broker.GateError("synthetic_upload_failure")),
                self.assertRaises(broker.GateError),
            ):
                broker.publish({"private_ref": "a" * 40})
            self.assertEqual(api.request.call_count, 1)
            self.assertTrue(api.request.call_args.args[1]["draft"])

    def test_validator_mount_is_readonly_and_has_no_output_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = root / "profile.json"
            profile.write_text(json.dumps({"output_mount": broker.OUTPUT_MOUNT}))
            command = broker.docker_command(root / "work", root / "results", profile, validator=True)
            self.assertIn(f"type=bind,src={root / 'results'},dst=/results,readonly", command)
            self.assertNotIn(f"dst=/work/{broker.OUTPUT_MOUNT}", " ".join(command))
            self.assertEqual(command[-1], "validate-baseline")


if __name__ == "__main__":
    unittest.main()
