import base64
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("research_broker", ROOT / "executor/research_broker.py")
research_broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research_broker)
GateError = research_broker.GateError
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
PRIVATE_REF = "c" * 40


def _pair(data):
    raw = data if isinstance(data, bytes) else data.encode()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def valid_profile(**overrides):
    source_files = {
        path: {"bytes": 12, "sha256": DIGEST_A} for path in research_broker.SOURCE_PATHS
    }
    input_files = {name: {"bytes": 4, "sha256": DIGEST_B} for name in research_broker.INPUT_FILES}
    profile = {
        "private_ref": PRIVATE_REF,
        "source_files": source_files,
        "manifest_path": research_broker.MANIFEST_PATH,
        "manifest_sha256": DIGEST_A,
        "data_release_tag": research_broker.DATA_RELEASE_TAG,
        "data_asset_name": research_broker.DATA_ASSET_NAME,
        "data_asset_sha256": DIGEST_B,
        "data_asset_bytes": 32,
        "input_files": input_files,
        "command": list(research_broker.COMMAND),
        "verify_command": list(research_broker.VERIFY_COMMAND),
        "command_timeout_seconds": 600,
        "verification_timeout_seconds": 180,
        "new_training": False,
        "production_authority": False,
    }
    profile.update(overrides)
    return profile


def tar_bytes(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def synthetic_bundle():
    input_payloads = {name: f"syn-{name}".encode() for name in research_broker.INPUT_FILES}
    input_files = {name: _pair(data) for name, data in input_payloads.items()}
    manifest = (json.dumps({"files": input_files}, separators=(",", ":")) + "\n").encode()
    sources = {
        research_broker.SOURCE_PATHS[0]: b"# synthetic liquidity_v1\n",
        research_broker.SOURCE_PATHS[1]: b"# synthetic run_study\n",
        research_broker.SOURCE_PATHS[2]: b"# synthetic verify_study\n",
        research_broker.SOURCE_PATHS[3]: b'{"synthetic":true}\n',
        research_broker.SOURCE_PATHS[4]: manifest,
    }
    archive = tar_bytes(input_payloads)
    profile = valid_profile(
        source_files={path: _pair(data) for path, data in sources.items()},
        manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        input_files=input_files,
        data_asset_sha256=hashlib.sha256(archive).hexdigest(),
        data_asset_bytes=len(archive),
    )
    return profile, sources, archive


def contents_payload(data):
    return {
        "type": "file",
        "encoding": "base64",
        "size": len(data),
        "content": base64.b64encode(data).decode(),
    }


def urllib_unquote(value):
    return research_broker.urllib.parse.unquote(value)


class ResearchExecutorTests(unittest.TestCase):
    def test_incomplete_catalog_is_not_dispatched(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "research_profiles.json").write_text(
                json.dumps({"schema_id": "factorlab.public_research_profiles@1.0", "profiles": {}})
            )
            with mock.patch.object(research_broker, "HERE", directory), self.assertRaises(GateError) as error:
                research_broker.load_profile("liq01-attribution-v1")
        self.assertEqual(str(error.exception), "incomplete_profile")

    def test_profile_allowlist_is_strict_and_commands_are_fixed(self):
        research_broker.validate_profile(valid_profile())
        for key, value in [
            ("private_ref", "main"),
            ("new_training", True),
            ("production_authority", True),
            ("command_timeout_seconds", 180),
            ("verification_timeout_seconds", 60),
            ("data_release_tag", "other-tag"),
            ("data_asset_name", "other.tar.gz"),
            ("manifest_path", "INPUT_MANIFEST.json"),
            ("command", ["arbitrary.py"]),
        ]:
            with self.subTest(key=key), self.assertRaises(GateError):
                research_broker.validate_profile(valid_profile(**{key: value}))
        extra = valid_profile()
        extra["extra_docker"] = "--privileged"
        with self.assertRaises(GateError):
            research_broker.validate_profile(extra)

    def test_pdf_and_nonallowlisted_sources_are_rejected(self):
        profile = valid_profile()
        profile["source_files"] = {
            **profile["source_files"],
            "research/systematic-factor-expansion-20260913/liq01/notes.pdf": {
                "bytes": 12,
                "sha256": DIGEST_A,
            },
        }
        with self.assertRaises(GateError) as error:
            research_broker.validate_profile(profile)
        self.assertEqual(str(error.exception), "pdf_source_not_allowed")
        missing = valid_profile()
        missing["source_files"] = {
            path: missing["source_files"][path] for path in research_broker.SOURCE_PATHS[:-1]
        }
        with self.assertRaises(GateError):
            research_broker.validate_profile(missing)

    def test_unknown_profile_name_rejected(self):
        with self.assertRaises(GateError) as error:
            research_broker.load_profile("baseline-replay-v1")
        self.assertEqual(str(error.exception), "unknown_profile")

    def test_compute_and_validator_mounts_are_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = root / "profile.json"
            profile.write_text("{}")
            compute = research_broker.docker_command(root / "work", root / "results", profile)
            validate = research_broker.docker_command(root / "work", root / "results", profile, validator=True)
        joined = " ".join(compute)
        self.assertEqual(compute[compute.index("--network") + 1], "none")
        self.assertIn("--read-only", compute)
        self.assertIn("--cap-drop=ALL", compute)
        self.assertIn("--security-opt=no-new-privileges", compute)
        self.assertNotIn("--privileged", compute)
        self.assertNotIn("/var/run/docker.sock", joined)
        self.assertNotIn("TOKEN", joined)
        self.assertNotIn("--env-file", compute)
        self.assertEqual(compute[compute.index("--cpus") + 1], "4")
        self.assertEqual(compute[compute.index("--memory") + 1], "12g")
        self.assertEqual(compute[compute.index("--pids-limit") + 1], "256")
        self.assertEqual(compute[compute.index("--entrypoint") + 1], "python3")
        self.assertIn("/run_research_in_container.py", compute)
        self.assertEqual(compute[-1], "/run_research_in_container.py")
        self.assertIn(f"type=bind,src={root / 'work'},dst=/work,readonly", compute)
        self.assertIn(f"type=bind,src={root / 'results'},dst=/results", compute)
        self.assertNotIn("dst=/results,readonly", " ".join(compute))
        self.assertIn(f"type=bind,src={root / 'results'},dst=/results,readonly", validate)
        self.assertEqual(validate[-2:], ["/run_research_in_container.py", "validate-research"])

    def test_redirect_reuses_broker_allowlist(self):
        request = urllib.request.Request(
            "https://api.github.com/repos/test/releases/assets/1", headers={"Authorization": "Bearer synthetic"}
        )
        handler = research_broker.broker.SafeRedirect()
        redirected = handler.redirect_request(
            request, None, 302, "", {}, "https://release-assets.githubusercontent.com/file"
        )
        self.assertFalse(redirected.has_header("Authorization"))
        for url in ["https://attacker.example/file", "http://api.github.com/file"]:
            with self.assertRaises(GateError):
                handler.redirect_request(request, None, 302, "", {}, url)
        self.assertEqual(research_broker.collect_result_files, research_broker.broker.collect_result_files)
        self.assertEqual(research_broker.upload_result, research_broker.broker.upload_result)

    def test_result_symlink_never_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.parquet"
            outside.write_bytes(b"synthetic-private")
            results = root / "results"
            results.mkdir()
            (results / "study.parquet").symlink_to(outside)
            with mock.patch.object(research_broker, "sha", side_effect=AssertionError("must not dereference")), self.assertRaises(GateError):
                research_broker.collect_result_files(results)

    def test_timeout_cleans_only_owned_container_and_scrubs_environment(self):
        process = mock.Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired("docker", 1), 0]
        process.poll.return_value = None
        cleanup = subprocess.CompletedProcess([], 0, "", "")
        with (
            mock.patch.dict(os.environ, {"FACTORLAB_PRIVATE_TOKEN": "synthetic"}),
            mock.patch.object(research_broker.broker.subprocess, "Popen", return_value=process) as popen,
            mock.patch.object(research_broker.broker.subprocess, "run", return_value=cleanup) as removed,
        ):
            self.assertEqual(research_broker.run_container(["docker", "run"], None, 1), 124)
            self.assertEqual(set(popen.call_args.kwargs["env"]), {"PATH", "LANG"})
            self.assertEqual(removed.call_args.args[0], ["docker", "rm", "--force", "factorlab-compute"])
            process.kill.assert_called_once()

    def test_compute_and_cleanup_reject_token_before_inputs(self):
        with (
            mock.patch.dict(os.environ, {"FACTORLAB_PRIVATE_TOKEN": "synthetic"}),
            mock.patch.object(research_broker, "load_state", side_effect=AssertionError("no input reads")),
            self.assertRaises(GateError),
        ):
            research_broker.compute()
        with (
            mock.patch.dict(os.environ, {"FACTORLAB_PRIVATE_TOKEN": "synthetic"}),
            mock.patch.object(research_broker.subprocess, "run", side_effect=AssertionError("no docker")),
            self.assertRaises(GateError),
        ):
            research_broker.cleanup()

    def test_source_blob_digest_mismatch(self):
        profile, sources, archive = synthetic_bundle()
        api = mock.Mock()
        api.request.return_value = contents_payload(b"wrong-bytes")
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(GateError) as error:
            research_broker.prepare_inputs(api, Path(temp), profile)
        self.assertIn(str(error.exception), {"source_blob_identity_failed", "source_blob_digest_mismatch"})
        self.assertFalse(any("tarball" in str(call.args[0]) for call in api.request.call_args_list))

    def test_data_asset_digest_mismatch(self):
        profile, sources, archive = synthetic_bundle()
        calls = []

        def request(path, data=None, method=None, binary_path=None, max_bytes=None):
            calls.append(path)
            if "/contents/" in path:
                rel = path.split("/contents/")[1].split("?ref=")[0]
                return contents_payload(sources[urllib_unquote(rel)])
            if "/releases/tags/" in path:
                return {
                    "draft": False,
                    "assets": [
                        {
                            "id": 9,
                            "name": research_broker.DATA_ASSET_NAME,
                            "state": "uploaded",
                            "size": len(archive),
                            "digest": "sha256:" + ("0" * 64),
                        }
                    ],
                }
            raise AssertionError("unexpected " + path)

        api = mock.Mock()
        api.request.side_effect = request
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(GateError) as error:
            research_broker.prepare_inputs(api, Path(temp), profile)
        self.assertEqual(str(error.exception), "remote_asset_identity_failed")
        self.assertFalse(any("tarball" in path for path in calls))

    def test_downloaded_asset_digest_mismatch(self):
        profile, sources, archive = synthetic_bundle()

        def request(path, data=None, method=None, binary_path=None, max_bytes=None):
            if "/contents/" in path:
                rel = path.split("/contents/")[1].split("?ref=")[0]
                return contents_payload(sources[urllib_unquote(rel)])
            if "/releases/tags/" in path:
                return {
                    "draft": False,
                    "assets": [
                        {
                            "id": 9,
                            "name": research_broker.DATA_ASSET_NAME,
                            "state": "uploaded",
                            "size": profile["data_asset_bytes"],
                            "digest": "sha256:" + profile["data_asset_sha256"],
                        }
                    ],
                }
            if binary_path is not None:
                binary_path.write_bytes(b"not-the-registered-archive")
                return None
            raise AssertionError("unexpected " + path)

        api = mock.Mock()
        api.request.side_effect = request
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(GateError) as error:
            research_broker.prepare_inputs(api, Path(temp), profile)
        self.assertEqual(str(error.exception), "downloaded_asset_digest_failed")

    def test_prepare_fetches_contents_after_write_proof_and_prints_generic_status(self):
        profile, sources, archive = synthetic_bundle()
        calls = []

        def request(path, data=None, method=None, binary_path=None, max_bytes=None):
            calls.append((method or "GET", path))
            if path.endswith("/git/refs"):
                return {"ref": data["ref"]}
            if "/contents/" in path:
                rel = path.split("/contents/")[1].split("?ref=")[0]
                return contents_payload(sources[urllib_unquote(rel)])
            if "/releases/tags/" in path:
                return {
                    "draft": False,
                    "assets": [
                        {
                            "id": 9,
                            "name": research_broker.DATA_ASSET_NAME,
                            "state": "uploaded",
                            "size": profile["data_asset_bytes"],
                            "digest": "sha256:" + profile["data_asset_sha256"],
                        }
                    ],
                }
            if binary_path is not None:
                binary_path.write_bytes(archive)
                return None
            raise AssertionError("unexpected " + path)

        api = mock.Mock()
        api.request.side_effect = request
        with tempfile.TemporaryDirectory() as temp:
            env = {
                "RUNNER_TEMP": temp,
                "GITHUB_RUN_ID": "77",
                "GITHUB_RUN_ATTEMPT": "2",
                "PATH": os.environ.get("PATH", "/usr/bin"),
            }
            stdout = io.StringIO()
            with (
                mock.patch.dict(os.environ, env, clear=False),
                mock.patch.object(research_broker, "require_private_api", return_value=api),
                mock.patch("sys.stdout", stdout),
            ):
                research_broker.prepare("liq01-attribution-v1", profile)
            text = stdout.getvalue()
            self.assertEqual(text, "Fixed private research inputs verified; prepare step complete.\n")
            self.assertNotIn("syn-daily.parquet", text)
            self.assertNotIn(PRIVATE_REF, text)
            self.assertNotIn("github_pat_", text)
            self.assertFalse(any("tarball" in path for _, path in calls))
            self.assertLess(
                next(i for i, item in enumerate(calls) if item[0] == "POST" and item[1].endswith("/git/refs")),
                next(i for i, item in enumerate(calls) if "/contents/" in item[1]),
            )
            work = Path(json.loads((Path(temp) / "factorlab-research-state.json").read_text())["root"]) / "work"
            self.assertTrue((work / "inputs" / "daily.parquet").is_file())
            self.assertTrue((work / research_broker.MANIFEST_PATH).is_file())
            self.assertEqual(
                json.loads((work / research_broker.MANIFEST_PATH).read_text())["files"],
                profile["input_files"],
            )

    def test_output_self_pass_is_insufficient_without_validator_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            results = root / "results"
            results.mkdir()
            (root / "work").mkdir()
            (root / "profile.json").write_text(json.dumps(valid_profile()))
            state = {"run_id": "9-1", "root": str(root), "prepare_ready": True, "compute_success": False}

            def fake_run(command, output, timeout, error_output=subprocess.STDOUT):
                if command[-1] == "validate-research":
                    output.write(b'{"status":"failed"}\n')
                    return 0
                (results / "compute_receipt.json").write_text('{"status":"passed"}\n')
                (results / "study").mkdir()
                (results / "study" / "out.bin").write_bytes(b"x")
                output.write(b"private-compute-bytes-must-not-print")
                return 0

            stdout = io.StringIO()
            env = {k: v for k, v in os.environ.items() if k != "FACTORLAB_PRIVATE_TOKEN"}
            env.update({"RUNNER_TEMP": temp, "GITHUB_RUN_ID": "9", "GITHUB_RUN_ATTEMPT": "1", "PATH": os.environ.get("PATH", "/usr/bin")})
            with (
                mock.patch.dict(os.environ, env, clear=True),
                mock.patch.object(research_broker, "load_state", return_value=(state, root)),
                mock.patch.object(research_broker, "write_state"),
                mock.patch.object(research_broker, "run_container", side_effect=fake_run),
                mock.patch("sys.stdout", stdout),
                self.assertRaises(GateError) as error,
            ):
                research_broker.compute()
            self.assertEqual(str(error.exception), "compute_failed_private_publish_step_will_report")
            self.assertFalse(state["compute_success"])
            self.assertNotIn("private-compute-bytes-must-not-print", stdout.getvalue())

    def test_no_receipt_before_result_upload_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            results = root / "results"
            results.mkdir()
            (results / "compute.log").write_text("synthetic")
            api = mock.Mock()
            api.request.return_value = {"id": 123}
            state = {
                "cleanup_complete": True,
                "run_id": "123-1",
                "branch": "runs/public-research/123-1",
                "compute_success": True,
                "profile_name": "liq01-attribution-v1",
            }
            with (
                mock.patch.object(research_broker, "load_state", return_value=(state, root)),
                mock.patch.object(research_broker, "require_private_api", return_value=api),
                mock.patch.object(research_broker, "upload_result", side_effect=GateError("synthetic_upload_failure")),
                self.assertRaises(GateError),
            ):
                research_broker.publish(valid_profile())
            self.assertEqual(api.request.call_count, 1)
            self.assertTrue(api.request.call_args.args[1]["draft"])
            self.assertEqual(api.request.call_args.args[1]["tag_name"], "public-research-run-123-1")
            self.assertNotIn("contents/", api.request.call_args.args[0])

    def test_unhandled_exception_is_generic(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["research_broker.py", "compute"]),
            mock.patch.object(research_broker, "require_context", side_effect=RuntimeError("/private/secret-path")),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
            self.assertRaises(SystemExit),
        ):
            research_broker.run()
        self.assertNotIn("/private/secret-path", stdout.getvalue() + stderr.getvalue())
        self.assertIn("no private diagnostic content was published", stderr.getvalue())

    def test_workflow_keeps_baseline_boundaries_and_routes_liq(self):
        text = (ROOT / ".github/workflows/public-compute.yml").read_text()
        self.assertIn("- liq01-attribution-v1", text)
        self.assertIn("python3 executor/broker.py runtime-smoke", text)
        self.assertIn("python3 executor/broker.py prepare", text)
        self.assertIn("python3 executor/broker.py compute", text)
        self.assertIn("python3 executor/research_broker.py prepare", text)
        self.assertIn("python3 executor/research_broker.py compute", text)
        compute = text.split("- name: Compute without")[1].split("- name: Stop owned")[0]
        cleanup = text.split("- name: Stop owned")[1].split("- name: Return verified")[0]
        self.assertNotIn("secrets.", compute + cleanup)
        self.assertEqual(text.count("secrets.FACTORLAB_PRIVATE_TOKEN"), 2)
        for forbidden in ["pull_request_target:", "pull_request:", "push:", "upload-artifact", "actions/cache", "self-hosted"]:
            self.assertNotIn(forbidden, text)
        values = [int(v) for v in re.findall(r"timeout-minutes: (\d+)", text)]
        self.assertLessEqual(sum(values[1:]), values[0])
        dockerfile = (ROOT / "executor/Dockerfile").read_text()
        self.assertIn("COPY run_research_in_container.py /run_research_in_container.py", dockerfile)
        self.assertIn('ENTRYPOINT ["python", "/run_in_container.py"]', dockerfile)
        wrapper = (ROOT / "executor/run_research_in_container.py").read_text()
        self.assertIn("stdout", wrapper)
        self.assertIn("stderr", wrapper)
        self.assertIn("validate-research", wrapper)
        self.assertIn("/results/compute.log", wrapper)


class ControllerIntegrationTests(unittest.TestCase):
    def test_container_leaves_study_directory_to_producer(self):
        definition = importlib.util.spec_from_file_location("research_wrapper", ROOT / "executor/run_research_in_container.py")
        wrapper = importlib.util.module_from_spec(definition)
        definition.loader.exec_module(wrapper)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def mapped_path(value):
                return root / value.removeprefix("/results").lstrip("/")
            def child(*args, **kwargs):
                self.assertFalse((root / "study").exists())
                (root / "study").mkdir()
                return subprocess.CompletedProcess(args[0], 0)
            with mock.patch.object(wrapper, "Path", side_effect=mapped_path), mock.patch.object(wrapper.subprocess, "run", side_effect=child):
                self.assertEqual(wrapper.run_compute({"command": ["synthetic.py"], "command_timeout_seconds": 1}), 0)

    def test_boolean_sizes_and_total_input_overflow_are_rejected(self):
        profile = valid_profile()
        profile["source_files"][research_broker.SOURCE_PATHS[0]]["bytes"] = True
        with self.assertRaises(GateError):
            research_broker.validate_profile(profile)
        profile = valid_profile()
        for row in profile["input_files"].values():
            row["bytes"] = 200 * 1024 * 1024
        with self.assertRaises(GateError):
            research_broker.validate_profile(profile)


if __name__ == "__main__":
    unittest.main()
