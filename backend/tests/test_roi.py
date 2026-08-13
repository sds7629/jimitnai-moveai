"""Tests for annual ROI computation (agents/post-report.md work item #4,
simulation-supply-chain-tool.md §10) -- app/services/roi.py +
GET /reports/roi.

Covers the DoD's minimum case:
  3. ROI가 3개 시나리오(낙관/기준/보수)로 표시됨.

Plus: the base scenario reproduces §10's own worked example (~150억원 실현
절감액, ~12일 회수기간), scenarios are properly ordered (더 나은 가정일수록
회수기간이 짧음), zero-effectiveness edge case doesn't raise
ZeroDivisionError, every input is a real parameter (not hardcoded) and the
GET endpoint validates its ratio bounds.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.roi import DEFAULT_ROI_INPUTS, compute_roi

client = TestClient(app)


# ============================================================
# DoD case 3: 3개 시나리오 표시
# ============================================================
def test_compute_roi_returns_three_scenarios_with_required_keys():
    result = compute_roi()
    assert set(result["scenarios"].keys()) == {"낙관", "기준", "보수"}
    for scenario in result["scenarios"].values():
        assert "annual_defendable_expected_loss" in scenario
        assert "annual_realized_savings" in scenario
        assert "payback_period_days" in scenario


def test_compute_roi_base_scenario_matches_documented_example():
    """simulation-supply-chain-tool.md §10 예시: 연간 방어 가능 기대손실 약
    500억, 실현 절감액 약 150억, 회수기간 약 12일."""

    result = compute_roi()
    base = result["scenarios"]["기준"]
    assert base["annual_defendable_expected_loss"] == pytest.approx(50_000_000_000, rel=0.01)
    assert base["annual_realized_savings"] == pytest.approx(15_000_000_000, rel=0.01)
    assert base["payback_period_days"] == pytest.approx(12, abs=1)


def test_compute_roi_optimistic_has_shorter_payback_than_conservative():
    result = compute_roi()
    optimistic = result["scenarios"]["낙관"]["payback_period_days"]
    base = result["scenarios"]["기준"]["payback_period_days"]
    conservative = result["scenarios"]["보수"]["payback_period_days"]
    assert optimistic < base < conservative


def test_compute_roi_zero_execution_rate_returns_none_payback_not_raising():
    result = compute_roi(execution_rate=0.0)
    for scenario in result["scenarios"].values():
        assert scenario["annual_realized_savings"] == 0.0
        assert scenario["payback_period_days"] is None
        assert scenario["payback_note"] is not None


# ============================================================
# 파라미터화 -- 하드코딩 아님을 확인
# ============================================================
def test_compute_roi_custom_inputs_change_the_result():
    default_result = compute_roi()
    custom_result = compute_roi(
        annual_incident_frequency=1,
        expected_loss_per_incident=1_000_000,
        intervention_ratio=1.0,
        execution_rate=1.0,
        loss_reduction_rate=1.0,
        total_investment=1_000_000,
    )
    assert custom_result["scenarios"]["기준"]["annual_defendable_expected_loss"] == pytest.approx(1_000_000)
    assert custom_result["scenarios"]["기준"]["annual_realized_savings"] == pytest.approx(1_000_000)
    assert custom_result != default_result
    assert custom_result["inputs"]["annual_incident_frequency"] == 1


def test_compute_roi_doubling_investment_roughly_doubles_payback():
    base = compute_roi()
    doubled = compute_roi(total_investment=DEFAULT_ROI_INPUTS["total_investment"] * 2)
    assert doubled["scenarios"]["기준"]["payback_period_days"] == pytest.approx(
        base["scenarios"]["기준"]["payback_period_days"] * 2, rel=0.01
    )


def test_compute_roi_disclosure_flags_missing_public_statistics():
    result = compute_roi()
    disclosure = result["disclosure"]
    assert disclosure["validation_required_before_real_data"] is True
    assert "미확보" in disclosure["public_statistics_source"]


# ============================================================
# API
# ============================================================
def test_get_roi_api_default_matches_service():
    resp = client.get("/reports/roi")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["scenarios"].keys()) == {"낙관", "기준", "보수"}
    assert body["inputs"]["annual_incident_frequency"] == DEFAULT_ROI_INPUTS["annual_incident_frequency"]


def test_get_roi_api_accepts_custom_query_params():
    resp = client.get(
        "/reports/roi",
        params={
            "annual_incident_frequency": 10,
            "expected_loss_per_incident": 2_000_000_000,
            "intervention_ratio": 0.4,
            "execution_rate": 0.5,
            "loss_reduction_rate": 0.5,
            "total_investment": 100_000_000,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inputs"]["annual_incident_frequency"] == 10
    assert body["scenarios"]["기준"]["annual_defendable_expected_loss"] == pytest.approx(
        10 * 2_000_000_000 * 0.4
    )


def test_get_roi_api_rejects_ratio_out_of_bounds():
    resp = client.get("/reports/roi", params={"intervention_ratio": 1.5})
    assert resp.status_code == 422
