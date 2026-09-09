"""Counterexamples for accepting split uploads and actual model tensor bytes."""
import hashlib
import json

import numpy as np
import pytest

from factor_lab.governance.reaka_r1_upload_audit import ArtifactReader, checkpoint_state, contained, digest


def split_fixture(tmp_path):
    source = tmp_path / "input"
    parts = source / "some/original.bin.parts"
    parts.mkdir(parents=True)
    chunks = [b"original-", b"frozen-bytes"]
    rows = []
    for i, chunk in enumerate(chunks):
        name = f"{i:02d}.bin"
        (parts / name).write_bytes(chunk)
        rows.append({"name": name, "bytes": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest()})
    data = b"".join(chunks)
    m = {"original_path": "some/original.bin", "original_bytes": len(data), "original_sha256": hashlib.sha256(data).hexdigest(), "parts": rows}
    (parts / "manifest.json").write_text(json.dumps(m))
    return ArtifactReader(source, tmp_path / "restored"), parts, m


def test_restore_preserves_source_and_checks_receipt(tmp_path):
    reader, parts, m = split_fixture(tmp_path)
    path = reader.file(m["original_path"], "sha256:" + m["original_sha256"])
    assert path.read_bytes() == b"original-frozen-bytes"
    assert not (reader.root / m["original_path"]).exists()
    assert (parts / "00.bin").read_bytes() == b"original-"
    with pytest.raises(ValueError, match="file digest mismatch"):
        reader.file(m["original_path"], "sha256:" + "0" * 64)


@pytest.mark.parametrize("kind", ["corrupt", "reordered", "duplicate", "wrong_destination"])
def test_invalid_split_never_publishes_original(tmp_path, kind):
    reader, parts, m = split_fixture(tmp_path)
    if kind == "corrupt":
        (parts / "00.bin").write_bytes(b"tampered!")
    elif kind == "reordered":
        m["parts"].reverse()
    elif kind == "duplicate":
        m["parts"].append(m["parts"][0])
    else:
        m["original_path"] = "other.bin"
    (parts / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError):
        reader.file("some/original.bin")
    assert not (reader.restored / "some/original.bin").exists()


@pytest.mark.parametrize("path", ["../escape", "/absolute", "x/../../escape", ""])
def test_rejects_path_escape(tmp_path, path):
    with pytest.raises(ValueError):
        contained(tmp_path, path)


def test_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "outside").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        contained(root, "outside/not-in-root")


def test_actual_state_bytes_must_match_manifest(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    h = hashlib.sha256()
    tensors = []
    for i, (name, shape) in enumerate([("feature_encoder.weight_ih_l0", (32, 71)), ("operators", (1, 8, 8))]):
        a = np.zeros(shape, dtype=np.float32)
        path = source / f"{i}.npy"
        np.save(path, a, allow_pickle=False)
        h.update(name.encode()); h.update(str(a.dtype).encode()); h.update(str(a.shape).encode()); h.update(a.tobytes())
        tensors.append({"position": i, "name": name, "filename": path.name, "digest": digest(path)})
    manifest = {"tensors": tensors, "tensor_count": 2, "state_digest": "sha256:" + h.hexdigest()}
    reader = ArtifactReader(source, tmp_path / "restored")
    assert checkpoint_state(reader, ".", manifest)["operator_shape"] == [1, 8, 8]
    # File checksums may be resealed while the independently bound state is old.
    np.save(source / "1.npy", np.ones((1, 8, 8), dtype=np.float32), allow_pickle=False)
    tensors[1]["digest"] = digest(source / "1.npy")
    with pytest.raises(ValueError, match="state digest mismatch"):
        checkpoint_state(ArtifactReader(source, tmp_path / "again"), ".", manifest)
