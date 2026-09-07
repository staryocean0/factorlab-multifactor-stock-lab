from __future__ import annotations

from datetime import date
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "src/factor_lab/factor_rotation/reaka_r3_x_decomposition.py"


def load():
    spec = importlib.util.spec_from_file_location("r3x", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def features(batch=2, seq=10):
    x = np.zeros((batch, seq, 71), dtype=np.float32)
    x[:, :, :14] = 1.5
    x[:, :, 14:28] = 1.0
    x[:, :, 28:42] = 2.5
    x[:, :, 42:56] = 3.5
    x[:, :, 56:70] = 1.0
    return x


@pytest.mark.parametrize("arm", ["H", "E", "F", "STATE_VALUE_PLUS_E", "BETA_ONLY", "BETA_RELIABILITY"])
def test_projection_keeps_shape_and_slot_zero(arm):
    m = load(); out = m.project_x_view(features(), arm)
    assert out.shape == (2, 10, 71)
    assert np.all(out[:, :, 70] == 0)


def test_H_removes_all_direct_x():
    m = load(); out = m.project_x_view(features(), "H")
    assert np.count_nonzero(out) == 0


def test_E_keeps_only_exposure_package():
    m = load(); x = features(); out = m.project_x_view(x, "E")
    assert np.all(out[:, :, :28] == 0)
    assert np.array_equal(out[:, :, 28:70], x[:, :, 28:70])


def test_F_keeps_incumbent_channels_only():
    m = load(); x = features(); out = m.project_x_view(x, "F")
    assert np.array_equal(out[:, :, :70], x[:, :, :70])
    assert np.all(out[:, :, 70] == 0)


def test_fine_views_are_ordered_not_symmetric():
    m = load(); x = features()
    sve = m.project_x_view(x, "STATE_VALUE_PLUS_E")
    assert np.array_equal(sve[:, :, :14], x[:, :, :14])
    assert np.all(sve[:, :, 14:28] == 0)
    assert np.array_equal(sve[:, :, 28:70], x[:, :, 28:70])
    beta = m.project_x_view(x, "BETA_ONLY")
    assert np.array_equal(beta[:, :, 28:42], x[:, :, 28:42])
    assert np.count_nonzero(beta[:, :, :28]) == 0
    assert np.count_nonzero(beta[:, :, 42:]) == 0


def test_binary_mask_drift_rejected_before_projection():
    m = load(); x = features(); x[0, 0, 14] = 0.25
    with pytest.raises(ValueError, match="binary"):
        m.project_x_view(x, "E")


def test_previous_calendar_month_year_boundary():
    m = load()
    assert m.previous_calendar_month("2020-01-06") == "2019-12"
    assert m.previous_calendar_month("2020-02-03") == "2020-01"


def test_monthly_mapping_uses_each_endpoints_own_previous_month():
    m = load()
    records = [
        m.MonthlyEncodedValue("2019-12", date(2020, 1, 1), -1.0),
        m.MonthlyEncodedValue("2020-01", date(2020, 2, 1), 2.0),
    ]
    dates = ["2020-01-06", "2020-02-03"]
    assert np.allclose(m.map_previous_month_values(dates, records), [-1.0, 2.0])


def test_monthly_future_availability_rejected():
    m = load()
    records = [m.MonthlyEncodedValue("2020-01", date(2020, 2, 10), 1.0)]
    with pytest.raises(ValueError, match="not available"):
        m.map_previous_month_values(["2020-02-03"], records)


def test_monthly_missing_month_rejected_not_neutralized():
    m = load()
    with pytest.raises(ValueError, match="missing"):
        m.map_previous_month_values(["2020-02-03"], [])


def test_monthly_injection_changes_only_channel_70():
    m = load(); x = features(batch=1, seq=2)
    dates = np.array([["2020-01-06", "2020-02-03"]], dtype="datetime64[D]")
    records = [
        m.MonthlyEncodedValue("2019-12", date(2020, 1, 1), -1.0),
        m.MonthlyEncodedValue("2020-01", date(2020, 2, 1), 2.0),
    ]
    out = m.inject_monthly_experimental_slot(x, dates, records)
    assert np.array_equal(out[:, :, :70], x[:, :, :70])
    assert np.allclose(out[0, :, 70], [-1.0, 2.0])


def test_design_does_not_claim_formula_identity_or_authorize_fine_stage():
    m = load(); d = m.design_metadata()
    assert d["monthly"]["exact_S_obs_1sigma_formula_recovered"] is False
    assert d["fine_stage"]["status"] == "preregistered_not_authorized"
    assert d["coarse_stage"]["rerun_F_H"] is False


class FakeStore:
    def __init__(self):
        self.calendar = np.arange(np.datetime64("2019-01-01"), np.datetime64("2020-04-01"), dtype="datetime64[D]")
        current = int(np.flatnonzero(self.calendar == np.datetime64("2020-03-15"))[0])
        self.inference_rows = np.array([[current, 0, 2020, 0]], dtype=np.int64)
    def assemble_inputs(self, indices):
        return np.ones((len(indices), 10), dtype=np.float32), features(batch=len(indices), seq=10)


def test_monthly_store_view_uses_sequence_endpoint_months_without_targets():
    m = load(); store = FakeStore()
    needed = set(); day = int(store.inference_rows[0, 0]); offsets = np.arange(-180, 1, 20)
    for d in store.calendar[day + offsets]:
        needed.add(m.previous_calendar_month(d))
    records = []
    for i, key in enumerate(sorted(needed)):
        y, mo = map(int, key.split("-")); ny, nm = (y + 1, 1) if mo == 12 else (y, mo + 1)
        records.append(m.MonthlyEncodedValue(key, date(ny, nm, 1), float(i + 1)))
    view = m.MonthlyConditionStoreView(store, records)
    hist, x = view.assemble_inputs(np.array([0], dtype=np.int64))
    assert hist.shape == (1, 10)
    assert np.array_equal(x[:, :, :70], features(batch=1, seq=10)[:, :, :70])
    assert np.all(np.isfinite(x[:, :, 70]))
    assert np.count_nonzero(x[:, :, 70]) == 10


def test_E_model_intercepts_training_and_keeps_only_exposure_tensor():
    torch = pytest.importorskip("torch"); m = load()
    class Carrier(torch.nn.Module):
        def __init__(self): super().__init__(); self.last = None
        def _encode_and_gate(self, returns, features): self.last = features.detach().clone(); return features.sum(dim=2)
    model = m.x_view_model_class(Carrier, "E")(); x = torch.from_numpy(features(batch=1, seq=9)); r = torch.zeros((1,9))
    out = model._encode_and_gate(r, x)
    assert out.shape == (1,9)
    assert torch.all(model.last[:, :, :28] == 0)
    assert torch.equal(model.last[:, :, 28:70], x[:, :, 28:70])
    assert torch.all(model.last[:, :, 70] == 0)


def test_F_H_E_model_classes_add_no_parameters():
    torch = pytest.importorskip("torch"); m = load()
    class Carrier(torch.nn.Module):
        def __init__(self): super().__init__(); self.w = torch.nn.Parameter(torch.ones(3))
        def _encode_and_gate(self, returns, features): return features[..., :3] * self.w
    counts=[]
    for arm in ("F","E","H"):
        model=m.x_view_model_class(Carrier,arm)(); counts.append(sum(p.numel() for p in model.parameters()))
    assert counts == [3,3,3]
