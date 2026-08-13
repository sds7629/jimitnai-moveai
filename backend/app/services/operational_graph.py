"""Core operational-graph logic (agents/operational-graph.md).

Builds the "지금 이 사건이 재고·생산·운송에 어떻게 퍼지는가" picture for a
validated incident: a fixed-point-in-time `OperationalSnapshot` plus the
Impact DAG rooted at it.

Two hard rules from the persona doc, enforced here:
  1. append-only — a "recalculation" is always a new snapshot (+ new DAG)
     row set, never an UPDATE of an existing one (repositories used here
     have no update() method at all — see app/repositories/base.py).
  2. lazy-create — there is no separate "create snapshot" endpoint in this
     system (see agents/operational-graph.md work item and API list).
     `ensure_snapshot_and_dag` is the single entry point: if a snapshot
     already exists for the incident it is returned unchanged; a new one is
     only ever built when none exists yet, or when the caller explicitly
     asks for a recompute (`force_recompute=True` — driven by the
     orchestration agent per simulation-supply-chain-tool.md §3.3's
     "동적 변수가 유의미하게 바뀌면 다시 계산").

Scenario handling (ARCHITECTURE.md §5 / agents/operational-graph.md work
item #3): the DAG is a single common 4-node linear skeleton
(trigger -> secondary disruption -> inventory_depletion -> production
halt/impact). Only the *trigger node's* content and a handful of
scenario-specific labels/durations come from `SCENARIO_TEMPLATES` — there is
deliberately no per-scenario DAG-building function.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.models.operational_snapshot import OperationalSnapshot
from app.repositories.impact_dag import ImpactDagEdgeRepository, ImpactDagNodeRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository

# Only incidents that have passed incident-intake's duplicate/false-positive
# gate are snapshot targets (agents/operational-graph.md: "status='유효'인
# 사건만 스냅샷 대상으로 삼아라"). 중복/오탐 사건은 스냅샷을 만들지 않는다.
ELIGIBLE_STATUS = "유효"

# The 3 operational-state/DAG categories the business spec treats as the
# "필수" data for a normal-quality analysis (simulation-supply-chain-tool.md
# §3.3): enough to place a part in the inventory node, a production order in
# the production node, and a container in the transport node. `customers` is
# tracked by incident-intake but isn't itself part of the
# inventory/production/transport triad this module owns, so it is not part
# of this gate.
REQUIRED_AFFECTED_TARGET_KEYS: tuple[str, ...] = ("parts", "production_orders", "containers")


class IncidentNotFoundError(LookupError):
    """No incident with the given id exists."""


class IncidentNotEligibleError(ValueError):
    """Incident exists but is not status='유효' (e.g. 중복/오탐/종료) — not a
    snapshot target per agents/operational-graph.md."""


@dataclass(frozen=True)
class ScenarioTemplate:
    """Everything that varies between the 3 seed scenarios (+ the generic
    fallback for incident types that don't match any of them). Feeds the one
    common DAG-building routine below — see module docstring."""

    scenario_slug: str  # english slug used in scenario_version, mirrors db/init/003-seed-scenarios.sql
    trigger_label: str
    trigger_basis: str
    trigger_responsible_party: str
    trigger_uncertainty: str

    secondary_node_key: str
    secondary_label: str
    secondary_basis: str
    secondary_responsible_party: str
    secondary_uncertainty: str
    secondary_offset_hours: float

    production_node_key: str  # "production_halt" | "production_impact"
    production_label: str
    production_uncertainty: str
    production_buffer_hours: float

    edge1_basis: str
    edge2_basis: str
    edge3_basis: str

    default_line: str
    default_part_qty: int
    default_hourly_consumption: int
    default_safety_stock: int
    default_capacity_per_hour: int
    transport_status_label: str


SCENARIO_TEMPLATES: dict[str, ScenarioTemplate] = {
    "적체": ScenarioTemplate(
        scenario_slug="congestion",
        trigger_label="항만 하역 지연",
        trigger_basis="항만공사 하역지연 공지",
        trigger_responsible_party="항만운영팀",
        trigger_uncertainty="low",
        secondary_node_key="container_release_delay",
        secondary_label="컨테이너 반출 지연",
        secondary_basis="하역 지연 공지 기준 반출 슬롯 재배정 지연 산정",
        secondary_responsible_party="항만운영팀",
        secondary_uncertainty="medium",
        secondary_offset_hours=12,
        production_node_key="production_halt",
        production_label="생산라인 중단",
        production_uncertainty="high",
        production_buffer_hours=6,
        edge1_basis="하역 지연 발생 시 반출 슬롯 재배정으로 반출 지연",
        edge2_basis="반출 지연 누적 시 신규 입고 중단으로 재고 소진 가속",
        edge3_basis="안전재고 소진 시점 도달 시 라인 가동 불가",
        default_line="L2",
        default_part_qty=480,
        default_hourly_consumption=20,
        default_safety_stock=200,
        default_capacity_per_hour=15,
        transport_status_label="반출대기",
    ),
    "파업": ScenarioTemplate(
        scenario_slug="strike",
        trigger_label="항만/운송 노동 파업",
        trigger_basis="노조 파업 공지",
        trigger_responsible_party="항만운영팀",
        trigger_uncertainty="low",
        secondary_node_key="handling_customs_halt",
        secondary_label="하역·통관 전면 중단 (컨테이너 반출 불가)",
        secondary_basis="파업 공지 즉시 전면 중단 발효",
        secondary_responsible_party="항만운영팀",
        secondary_uncertainty="low",
        secondary_offset_hours=2,
        production_node_key="production_halt",
        production_label="생산라인 중단",
        production_uncertainty="high",
        production_buffer_hours=4,
        edge1_basis="파업 발효 시 하역·통관 업무 즉시 전면 중단",
        edge2_basis="반출 불가로 신규 입고가 전면 중단되어 재고 소진 가속",
        edge3_basis="안전재고 소진 시점 도달 시 라인 가동 불가",
        default_line="L1",
        default_part_qty=300,
        default_hourly_consumption=25,
        default_safety_stock=150,
        default_capacity_per_hour=12,
        transport_status_label="하역중단",
    ),
    "관세": ScenarioTemplate(
        scenario_slug="tariff",
        trigger_label="관세·통관 규정 변경",
        trigger_basis="관세청 규정 변경 공지",
        trigger_responsible_party="통관담당팀",
        trigger_uncertainty="low",
        secondary_node_key="customs_clearance_delay",
        secondary_label="통관 지연 및 추가 서류 요구 (반출 지연)",
        secondary_basis="신규 규정상 추가 서류 준비 소요시간 기준 산정",
        secondary_responsible_party="통관담당팀",
        secondary_uncertainty="medium",
        secondary_offset_hours=48,
        production_node_key="production_impact",
        production_label="생산 영향 (감산 또는 라인 중단)",
        production_uncertainty="high",
        production_buffer_hours=6,
        edge1_basis="규정 변경 발효 시 통관 절차에 추가 서류 요구 반영",
        edge2_basis="통관 지연 누적 시 신규 입고 지연으로 재고 소진 가속",
        edge3_basis="안전재고 소진 시점 도달 시 감산 또는 라인 중단 불가피",
        default_line="L3",
        default_part_qty=600,
        default_hourly_consumption=10,
        default_safety_stock=300,
        default_capacity_per_hour=8,
        transport_status_label="통관대기",
    ),
    # Fallback for incident types that are not one of the 3 known scenarios.
    # ARCHITECTURE.md §6 excludes real-time port/inventory/production
    # integration entirely — for any incident outside the 3 seeded scenario
    # families there is no real operational data source at all, so this path
    # is inherently placeholder-based and always forced into 'limited' mode
    # (see _quality_gate below).
    "기타": ScenarioTemplate(
        scenario_slug="generic",
        trigger_label="사건 발생",
        trigger_basis="사건 접수 정보(유형/위치/발생시각) 기준 — 시드 시나리오와 매칭되지 않아 표준 템플릿 적용",
        trigger_responsible_party="상황관리팀",
        trigger_uncertainty="medium",
        secondary_node_key="operational_disruption",
        secondary_label="운영 차질 (반출/처리 지연 추정)",
        secondary_basis="시드 시나리오 미매칭 — 표준 지연시간 가정치 적용",
        secondary_responsible_party="상황관리팀",
        secondary_uncertainty="high",
        secondary_offset_hours=24,
        production_node_key="production_impact",
        production_label="생산 영향 (감산 또는 라인 중단 추정)",
        production_uncertainty="high",
        production_buffer_hours=6,
        edge1_basis="사건 발생 시 관련 운영 차질 발생 가정",
        edge2_basis="운영 차질 지속 시 재고 소진 가속 가정",
        edge3_basis="안전재고 소진 시점 도달 시 생산 영향 발생 가정",
        default_line="L0",
        default_part_qty=300,
        default_hourly_consumption=15,
        default_safety_stock=150,
        default_capacity_per_hour=10,
        transport_status_label="상태미상",
    ),
}


def classify_scenario(incident_type: str) -> str:
    """Maps an incident's free-text `type` to one of the 3 seed scenario
    families by substring match (matches both the seed rows' exact types —
    '항만 적체'/'항만 파업'/'관세 규정 변경' — and free-form variants like
    incident-intake's test payloads), or '기타' if none match."""

    if "적체" in incident_type:
        return "적체"
    if "파업" in incident_type:
        return "파업"
    if "관세" in incident_type:
        return "관세"
    return "기타"


def _quality_gate(incident: Incident, scenario_key: str) -> tuple[str, float, list[str]]:
    """§3.3 데이터 품질 게이트. Returns (quality_mode, coverage_ratio, notes).

    coverage_ratio = fraction of REQUIRED_AFFECTED_TARGET_KEYS present on the
    incident. quality_mode is 'normal' only when coverage is complete *and*
    the incident type matches a known seed scenario (see 기타 fallback
    docstring above for why unmatched types are always limited)."""

    affected = incident.affected_targets or {}
    present = [key for key in REQUIRED_AFFECTED_TARGET_KEYS if affected.get(key)]
    coverage_ratio = round(len(present) / len(REQUIRED_AFFECTED_TARGET_KEYS), 4)

    notes: list[str] = []
    is_known_scenario = scenario_key != "기타"
    if not is_known_scenario:
        notes.append(
            "ASSUMPTION: 사건 유형이 시드 시나리오(적체/파업/관세)와 매칭되지 않아 "
            "일반 대응 템플릿과 플레이스홀더 운영 수치를 사용함"
        )
    missing = [key for key in REQUIRED_AFFECTED_TARGET_KEYS if key not in present]
    for key in missing:
        notes.append(f"ASSUMPTION: 필수 운영 데이터 항목 affected_targets.{key} 누락 — 제한 모드로 진행")

    quality_mode = "normal" if is_known_scenario and not missing else "limited"
    return quality_mode, coverage_ratio, notes


def _create_snapshot_and_dag(db: Session, incident: Incident) -> OperationalSnapshot:
    """The one common DAG-building routine (ARCHITECTURE.md §5 / work item
    #3): every scenario — known or not — goes through this exact same
    4-node/3-edge linear construction. Only the field values pulled from
    `SCENARIO_TEMPLATES[scenario_key]` differ."""

    snapshot_repo = OperationalSnapshotRepository(db)
    node_repo = ImpactDagNodeRepository(db)
    edge_repo = ImpactDagEdgeRepository(db)

    scenario_key = classify_scenario(incident.type)
    template = SCENARIO_TEMPLATES[scenario_key]
    quality_mode, coverage_ratio, quality_notes = _quality_gate(incident, scenario_key)

    now = datetime.now(timezone.utc)

    affected = incident.affected_targets or {}
    parts = list(affected.get("parts") or [])
    production_orders = list(affected.get("production_orders") or [])
    containers = list(affected.get("containers") or [])

    part_id = parts[0] if parts else f"UNKNOWN-PART-INC{incident.id}"
    po_id = production_orders[0] if production_orders else f"UNKNOWN-PO-INC{incident.id}"
    container_ids = containers if containers else [f"UNKNOWN-CTN-INC{incident.id}"]

    qty = template.default_part_qty
    consumption = template.default_hourly_consumption
    safety_stock = template.default_safety_stock

    hours_to_deplete = max(qty - safety_stock, 0) / consumption
    inventory_expected_time = now + timedelta(hours=hours_to_deplete)
    production_expected_time = inventory_expected_time + timedelta(hours=template.production_buffer_hours)
    secondary_expected_time = now + timedelta(hours=template.secondary_offset_hours)

    operational_state = {
        "inventory": {
            part_id: {
                "qty": qty,
                "unit": "ea",
                "hourly_consumption": consumption,
                "safety_stock": safety_stock,
            }
        },
        "production": {
            po_id: {
                "line": template.default_line,
                "status": "정상가동",
                "capacity_per_hour": template.default_capacity_per_hour,
            }
        },
        "transport": {
            cid: {"status": template.transport_status_label, "eta": None} for cid in container_ids
        },
    }

    # incident.assumptions (incident-intake's "ASSUMPTION: ..." strings) must
    # always be carried forward — losing them would silently drop context
    # that later response-design/simulation comparisons depend on.
    assumptions = list(incident.assumptions or []) + quality_notes
    assumptions.append(
        "ASSUMPTION: 실시간 항만/재고/생산 시스템 연동 없음(ARCHITECTURE.md §6) — "
        f"{scenario_key} 시나리오 표준 소비율 {consumption}ea/h, 안전재고 {safety_stock}ea, "
        f"현재 재고 {qty}ea 가정치를 적용함"
    )

    revision = len(snapshot_repo.history_for_incident(incident.id)) + 1
    data_version = f"v{revision}"
    scenario_version = f"scenario-{template.scenario_slug}-v{revision}"

    snapshot = snapshot_repo.add(
        incident_id=incident.id,
        data_version=data_version,
        scenario_version=scenario_version,
        assumptions=assumptions,
        operational_state=operational_state,
        quality_mode=quality_mode,
        freshness_seconds=max(int((now - incident.occurred_at).total_seconds()), 0),
        coverage_ratio=coverage_ratio,
    )

    n1 = node_repo.add(
        snapshot_id=snapshot.id,
        node_key="trigger",
        label=template.trigger_label,
        affected_target=incident.location,
        expected_time=now,
        basis=template.trigger_basis,
        responsible_party=template.trigger_responsible_party,
        uncertainty=template.trigger_uncertainty,
    )
    n2 = node_repo.add(
        snapshot_id=snapshot.id,
        node_key=template.secondary_node_key,
        label=template.secondary_label,
        affected_target=",".join(container_ids),
        expected_time=secondary_expected_time,
        basis=template.secondary_basis,
        responsible_party=template.secondary_responsible_party,
        uncertainty=template.secondary_uncertainty,
    )
    n3 = node_repo.add(
        snapshot_id=snapshot.id,
        node_key="inventory_depletion",
        label="부품 안전재고 소진",
        affected_target=part_id,
        expected_time=inventory_expected_time,
        basis=(
            f"현재 재고 {qty}ea / 시간당 소비 {consumption}ea, 안전재고 {safety_stock}ea 기준 역산 "
            f"(소진까지 약 {hours_to_deplete:.1f}시간)"
        ),
        responsible_party="생산관리팀",
        uncertainty="medium",
    )
    n4 = node_repo.add(
        snapshot_id=snapshot.id,
        node_key=template.production_node_key,
        label=template.production_label,
        affected_target=f"{po_id} / {template.default_line}",
        expected_time=production_expected_time,
        basis="안전재고 소진 예상시각 이후 잔여 공정 처리 완료 시 라인정지/감산 가정",
        responsible_party="생산관리팀",
        uncertainty=template.production_uncertainty,
    )

    edge_repo.add(snapshot_id=snapshot.id, from_node_id=n1.id, to_node_id=n2.id, basis=template.edge1_basis)
    edge_repo.add(snapshot_id=snapshot.id, from_node_id=n2.id, to_node_id=n3.id, basis=template.edge2_basis)
    edge_repo.add(snapshot_id=snapshot.id, from_node_id=n3.id, to_node_id=n4.id, basis=template.edge3_basis)

    return snapshot


def ensure_snapshot_and_dag(
    db: Session, incident_id: int, force_recompute: bool = False
) -> OperationalSnapshot:
    """Lazy-create entry point — the only way a snapshot/DAG gets built in
    this system (there is no separate POST endpoint, per
    agents/operational-graph.md).

    - If a snapshot already exists for `incident_id` and `force_recompute`
      is False, the latest one is returned as-is (no DB write at all).
    - Otherwise a brand-new snapshot + DAG is appended (never an UPDATE of
      the old one — old rows are left exactly as they were, satisfying the
      baseline-immutability requirement even across recomputation).

    Raises IncidentNotFoundError / IncidentNotEligibleError for callers
    (the API layer) to translate into 404 / 409 respectively.
    """

    incident_repo = IncidentRepository(db)
    incident = incident_repo.get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    if incident.status != ELIGIBLE_STATUS:
        raise IncidentNotEligibleError(
            f"incident {incident_id} has status {incident.status!r}, not "
            f"{ELIGIBLE_STATUS!r} — 중복/오탐 사건은 스냅샷 대상이 아님"
        )

    snapshot_repo = OperationalSnapshotRepository(db)
    if not force_recompute:
        existing = snapshot_repo.latest_for_incident(incident_id)
        if existing is not None:
            return existing

    return _create_snapshot_and_dag(db, incident)
