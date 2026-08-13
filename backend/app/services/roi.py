"""연간 ROI 산출 (agents/post-report.md work item #4,
simulation-supply-chain-tool.md §10).

개별 사고의 절감액이 아니라, 연간 사고 빈도와 대응 가능성을 적용해 연간
투자효과로 환산한다. 공식은 그대로 파라미터화한다 (하드코딩 금지):

    연간 방어 가능 기대손실 = 연간 발생 빈도 x 사고당 기대손실 x 개입 가능 비율
    연간 실현 절감액       = 연간 방어 가능 기대손실 x 대응 실행률 x 실제 손실 감소율
    투자 회수기간(일)      = 총 구축·운영비 / 연간 실현 절감액 x 365

이 함수는 incident_id와 무관한 전역 계산이다 (GET /reports/roi). LLM 호출도
블로킹 I/O도 없는 순수 산술이라 동기(`def`)로 남긴다.

**단일 확정 수치처럼 제시하지 않는다** -- 낙관/기준/보수 3개 시나리오를 함께
반환한다. §10은 실제 관측치가 아니라 "공개 통계와 보수적 가정으로 만든
사업성 시나리오"라고 명시하므로, 반환값에는 그 사실 자체(공개 통계 원문 미확보,
실제 운영 데이터 적용 전 검증 필요 등)도 함께 담아 단일 확정 성과처럼 보이지
않게 한다.
"""

from __future__ import annotations

from typing import Any

__all__ = ["compute_roi", "DEFAULT_ROI_INPUTS"]

# ------------------------------------------------------------------
# §10 예시 가정을 그대로 기본값으로 채택하되, 전부 함수 파라미터로 노출한다.
# 이 5개 기본값의 산출 근거 (코드 주석으로 명시 -- 실제 공개 통계 원문은 이번
# 스코프에 연결돼 있지 않다는 것 자체가 판단값):
#
#   연간 발생 빈도(20건) x 사고당 기대손실(50억원) x 개입 가능 비율(0.5)
#     = 연간 방어 가능 기대손실 500억원  (§10 예시 "약 500억 원"과 일치)
#   대응 실행률(0.6) x 실제 손실 감소율(0.5) = 실제 방어율 0.3 (§10 예시 "30%")
#   총 구축·운영비(4.9억원)를 위 실현 절감액(150억원)으로 나누고 x365 하면
#     약 11.9일 -- §10 예시 "약 12일"과 일치.
#
# 20건/50억원/0.5/0.6/0.5/4.9억원 각각의 실측 근거는 없다 -- §10 자체가
# "공개 통계와 보수적 가정으로 만든 사업성 시나리오"라고 명시하는 예시값을
# 역산해 채운 것이며, 호출자가 실제 운영 데이터로 언제든 교체할 수 있도록
# 전부 파라미터로 노출한다.
DEFAULT_ROI_INPUTS: dict[str, float] = {
    "annual_incident_frequency": 20.0,
    "expected_loss_per_incident": 5_000_000_000.0,
    "intervention_ratio": 0.5,
    "execution_rate": 0.6,
    "loss_reduction_rate": 0.5,
    "total_investment": 490_000_000.0,
}

# 낙관/보수 시나리오 조정폭. intervention_ratio/execution_rate/
# loss_reduction_rate 3개만 조정한다 -- 이 3개는 "이 시스템이 실제로 얼마나
# 잘 개입/실행/손실감소에 성공하는가"라는, 아직 실적 데이터가 없어 가장
# 불확실한 항목들이다. annual_incident_frequency/expected_loss_per_incident/
# total_investment는 상대적으로 더 외생적인(사고 발생 통계, 투자비 견적)
# 값이라 시나리오별로 흔들지 않는다 -- 이 구분 자체가 이번 스코프의 판단이다.
#
# ±20%라는 폭 자체의 근거: 실측 데이터가 전혀 없는 상태에서 사업성 시나리오에
# 흔히 쓰이는 대칭적 밴드를 채택한 것으로, 더 정교한(비대칭적이거나 다른 폭의)
# 조정을 정당화할 근거 데이터가 이번 스코프에는 없다는 것을 그대로 반영한다.
OPTIMISTIC_FACTOR = 1.2
CONSERVATIVE_FACTOR = 0.8


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _scenario(
    *,
    annual_incident_frequency: float,
    expected_loss_per_incident: float,
    intervention_ratio: float,
    execution_rate: float,
    loss_reduction_rate: float,
    total_investment: float,
    factor: float,
) -> dict[str, Any]:
    adjusted_intervention_ratio = _clamp01(intervention_ratio * factor)
    adjusted_execution_rate = _clamp01(execution_rate * factor)
    adjusted_loss_reduction_rate = _clamp01(loss_reduction_rate * factor)

    annual_defendable_expected_loss = (
        annual_incident_frequency * expected_loss_per_incident * adjusted_intervention_ratio
    )
    annual_realized_savings = (
        annual_defendable_expected_loss * adjusted_execution_rate * adjusted_loss_reduction_rate
    )

    if annual_realized_savings > 0:
        payback_period_days: float | None = total_investment / annual_realized_savings * 365
        payback_note = None
    else:
        payback_period_days = None
        payback_note = (
            "연간 실현 절감액이 0이어서 투자 회수기간을 계산할 수 없음 "
            "(조정된 대응 실행률 또는 손실 감소율이 0이 되는 극단적인 보수 가정)"
        )

    return {
        "adjusted_intervention_ratio": adjusted_intervention_ratio,
        "adjusted_execution_rate": adjusted_execution_rate,
        "adjusted_loss_reduction_rate": adjusted_loss_reduction_rate,
        "annual_defendable_expected_loss": annual_defendable_expected_loss,
        "annual_realized_savings": annual_realized_savings,
        "payback_period_days": payback_period_days,
        "payback_note": payback_note,
    }


def compute_roi(
    annual_incident_frequency: float = DEFAULT_ROI_INPUTS["annual_incident_frequency"],
    expected_loss_per_incident: float = DEFAULT_ROI_INPUTS["expected_loss_per_incident"],
    intervention_ratio: float = DEFAULT_ROI_INPUTS["intervention_ratio"],
    execution_rate: float = DEFAULT_ROI_INPUTS["execution_rate"],
    loss_reduction_rate: float = DEFAULT_ROI_INPUTS["loss_reduction_rate"],
    total_investment: float = DEFAULT_ROI_INPUTS["total_investment"],
) -> dict[str, Any]:
    """GET /reports/roi의 서비스 로직 -- 낙관/기준/보수 3개 시나리오를 반환한다.

    6개 입력 전부 파라미터로 노출되어 있으며, 기본값은 DEFAULT_ROI_INPUTS
    (simulation-supply-chain-tool.md §10 예시값)이다."""

    kwargs = dict(
        annual_incident_frequency=annual_incident_frequency,
        expected_loss_per_incident=expected_loss_per_incident,
        intervention_ratio=intervention_ratio,
        execution_rate=execution_rate,
        loss_reduction_rate=loss_reduction_rate,
        total_investment=total_investment,
    )

    scenarios = {
        "낙관": _scenario(**kwargs, factor=OPTIMISTIC_FACTOR),
        "기준": _scenario(**kwargs, factor=1.0),
        "보수": _scenario(**kwargs, factor=CONSERVATIVE_FACTOR),
    }

    return {
        "inputs": kwargs,
        "scenarios": scenarios,
        # simulation-supply-chain-tool.md §10이 "최종 자료에 반드시 함께
        # 표시하라"고 명시한 항목들 -- 이 스코프에는 실제 공개 통계/사건별 귀속
        # 집계가 없으므로, 없는 것은 "미확보"로 정직하게 표기한다(지어내지 않음).
        "disclosure": {
            "public_statistics_source": (
                "미확보 -- 위 기본값은 §10 예시 가정을 코드 파라미터로 옮긴 것이며, "
                "실제 공개 통계 원문과 기준연도는 이번 스코프에 연결되어 있지 않습니다."
            ),
            "frequency_and_loss_basis": (
                "미확보 -- 사고 유형별 연간 발생 빈도/사고당 기대손실의 실측 산출 근거 데이터가 "
                "없습니다. 호출자가 실제 값으로 파라미터를 교체할 수 있습니다."
            ),
            "direct_vs_customer_avoidance": (
                "이 엔드포인트는 총 절감액만 계산합니다. 직접 손익 효과 vs 고객 회피비용 구분은 "
                "사건 단위로 GET /incidents/{id}/cost-attribution에서 제공하며, 연간 ROI는 "
                "사건별 귀속 결과를 집계하지 않습니다."
            ),
            "included_excluded_cost_items": (
                "포함: total_investment(총 구축·운영비) 단일 합계 전체. 제외: 인프라/인건비/"
                "라이선스 등 세부 항목별 분해는 이번 스코프에서 하나의 파라미터로만 노출됩니다."
            ),
            "scenario_adjustment_basis": (
                f"낙관 = 기준 x {OPTIMISTIC_FACTOR}, 보수 = 기준 x {CONSERVATIVE_FACTOR} "
                "(intervention_ratio/execution_rate/loss_reduction_rate 3개에만 적용, "
                "0~1로 clamp). 근거: 실측 데이터가 없는 상태에서 채택한 대칭적 예시 밴드입니다."
            ),
            "validation_required_before_real_data": True,
        },
    }
