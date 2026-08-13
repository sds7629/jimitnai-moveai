-- platform-infra: seed data for the 3 demo scenarios (적체 / 파업 / 관세)
-- ARCHITECTURE.md §5. Each scenario gets: 1 incident, 1 operational
-- snapshot, a 4-node/3-edge Impact DAG, and 2 response candidates
-- (baseline + one active candidate). All three share the same schema —
-- only the trigger point and initial nodes differ (§5's requirement).
--
-- This file is also the frontend's mock data source (ARCHITECTURE.md §7.3):
-- the seeded rows must be shaped exactly like what the real API will
-- return, since other personas' fixtures / early frontend work will read
-- directly from these rows via GET endpoints.

-- ============================================================
-- Scenario 1: 항만 적체 (port congestion)
-- 항만 하역 지연 -> 컨테이너 반출 지연 -> 부품 재고 소진 -> 생산라인 중단
-- -> 완성차 출고 지연 -> 딜러 납기 위반
-- ============================================================
WITH inc AS (
  INSERT INTO incidents (type, location, occurred_at, status, affected_targets, assumptions)
  VALUES (
    '항만 적체', '부산항 3부두', now() - interval '6 hours', '유효',
    '{"containers": ["CTN-1001", "CTN-1002"], "parts": ["PT-ENGINE-01"], "production_orders": ["PO-2026-1001"], "customers": ["Dealer-Seoul-01", "Dealer-Busan-02"]}'::jsonb,
    '["하역 지연의 근본 원인(장비 고장/기상)은 미확정이며 3일 지속을 가정"]'::jsonb
  )
  RETURNING id
), snap AS (
  INSERT INTO operational_snapshots (incident_id, data_version, scenario_version, assumptions, operational_state, quality_mode, freshness_seconds, coverage_ratio)
  SELECT inc.id, 'v1', 'scenario-congestion-v1',
    '["부품 시간당 소비량은 최근 7일 평균으로 가정", "대체항 가용 용량은 평시 30% 수준으로 가정"]'::jsonb,
    '{
       "inventory": {"PT-ENGINE-01": {"qty": 480, "unit": "ea", "hourly_consumption": 20, "safety_stock": 200}},
       "production": {"PO-2026-1001": {"line": "L2", "status": "정상가동", "capacity_per_hour": 15}},
       "transport": {"CTN-1001": {"status": "반출대기", "eta": null}, "CTN-1002": {"status": "하역중", "eta": null}}
     }'::jsonb,
    'normal', 3600, 0.9500
  FROM inc
  RETURNING id, incident_id
), n1 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'trigger', '항만 하역 지연', '부산항 3부두', now(), '항만공사 하역지연 공지', '항만운영팀', 'low' FROM snap
  RETURNING id, snapshot_id
), n2 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'container_release_delay', '컨테이너 반출 지연', 'CTN-1001,CTN-1002', now() + interval '12 hours', '하역 지연 공지 기준 반출 슬롯 재배정 지연 산정', '항만운영팀', 'medium' FROM snap
  RETURNING id, snapshot_id
), n3 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'inventory_depletion', '부품 안전재고 소진', 'PT-ENGINE-01', now() + interval '24 hours', '현재 재고 480ea / 시간당 소비 20ea, 안전재고 200ea 기준 역산', '생산관리팀', 'medium' FROM snap
  RETURNING id, snapshot_id
), n4 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'production_halt', '생산라인 중단', 'PO-2026-1001 / L2', now() + interval '30 hours', '안전재고 소진 예상시각 이후 즉시 라인정지 가정', '생산관리팀', 'high' FROM snap
  RETURNING id, snapshot_id
), e1 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n1.id, n2.id, '하역 지연 발생 시 반출 슬롯 재배정으로 반출 지연' FROM snap, n1, n2
  RETURNING id
), e2 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n2.id, n3.id, '반출 지연 누적 시 신규 입고 중단으로 재고 소진 가속' FROM snap, n2, n3
  RETURNING id
), e3 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n3.id, n4.id, '안전재고 소진 시점 도달 시 라인 가동 불가' FROM snap, n3, n4
  RETURNING id
), cand_baseline AS (
  INSERT INTO response_candidates (incident_id, snapshot_id, candidate_type, description, reference_document_ids, preconditions, start_time_variant, validation_status)
  SELECT snap.incident_id, snap.id, 'baseline', '무대응 - 현재 계획대로 진행하며 재고 소진 시 자연 라인정지 수용', '[]'::jsonb, '[]'::jsonb, '즉시', '가능'
  FROM snap
  RETURNING id
), cand_active AS (
  INSERT INTO response_candidates (incident_id, snapshot_id, candidate_type, description, reference_document_ids, preconditions, start_time_variant, validation_status)
  SELECT snap.incident_id, snap.id, '단일', '컨테이너 우선 반출 - PT-ENGINE-01 포함 컨테이너 긴급 반출 슬롯 확보', '[]'::jsonb, '["항만 측 우선반출 승인 필요"]'::jsonb, '즉시', '미검증'
  FROM snap
  RETURNING id
)
INSERT INTO seed_scenarios (scenario_key, description, seed_payload, incident_id, snapshot_id)
SELECT
  '적체',
  '항만 하역 지연으로 컨테이너 반출이 지연되어 부품 재고가 소진되고 생산라인 중단으로 이어지는 시나리오',
  jsonb_build_object(
    'trigger', '항만 하역 지연',
    'path', ARRAY['컨테이너 반출 지연','부품 재고 소진','생산라인 중단','완성차 출고 지연','딜러 납기 위반']
  ),
  snap.incident_id, snap.id
FROM snap;

-- ============================================================
-- Scenario 2: 파업 (labor strike)
-- 항만/운송 노동 파업 -> 하역·통관 전면 중단 -> 컨테이너 반출 불가
-- -> 재고 소진 -> 생산라인 중단
-- ============================================================
WITH inc AS (
  INSERT INTO incidents (type, location, occurred_at, status, affected_targets, assumptions)
  VALUES (
    '항만 파업', '부산항', now() - interval '2 hours', '유효',
    '{"containers": ["CTN-2001", "CTN-2002"], "parts": ["PT-BATTERY-01"], "production_orders": ["PO-2026-2001"], "customers": ["Dealer-Incheon-01"]}'::jsonb,
    '["파업 지속기간은 노조 공지 기준 5일을 가정하며 조기 종료 가능성은 배제"]'::jsonb
  )
  RETURNING id
), snap AS (
  INSERT INTO operational_snapshots (incident_id, data_version, scenario_version, assumptions, operational_state, quality_mode, freshness_seconds, coverage_ratio)
  SELECT inc.id, 'v1', 'scenario-strike-v1',
    '["파업 기간 중 대체 인력 투입 가능성은 없다고 가정", "긴급운송 수단 확보는 평시 대비 50% 리드타임 증가로 가정"]'::jsonb,
    '{
       "inventory": {"PT-BATTERY-01": {"qty": 300, "unit": "ea", "hourly_consumption": 25, "safety_stock": 150}},
       "production": {"PO-2026-2001": {"line": "L1", "status": "정상가동", "capacity_per_hour": 12}},
       "transport": {"CTN-2001": {"status": "하역중단", "eta": null}, "CTN-2002": {"status": "하역중단", "eta": null}}
     }'::jsonb,
    'normal', 1800, 0.9000
  FROM inc
  RETURNING id, incident_id
), n1 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'trigger', '항만/운송 노동 파업', '부산항 전체', now(), '노조 파업 공지', '항만운영팀', 'low' FROM snap
  RETURNING id, snapshot_id
), n2 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'handling_customs_halt', '하역·통관 전면 중단 (컨테이너 반출 불가)', 'CTN-2001,CTN-2002', now() + interval '2 hours', '파업 공지 즉시 전면 중단 발효', '항만운영팀', 'low' FROM snap
  RETURNING id, snapshot_id
), n3 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'inventory_depletion', '부품 안전재고 소진', 'PT-BATTERY-01', now() + interval '6 hours', '현재 재고 300ea / 시간당 소비 25ea, 안전재고 150ea 기준 역산', '생산관리팀', 'medium' FROM snap
  RETURNING id, snapshot_id
), n4 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'production_halt', '생산라인 중단', 'PO-2026-2001 / L1', now() + interval '10 hours', '안전재고 소진 예상시각 이후 즉시 라인정지 가정', '생산관리팀', 'high' FROM snap
  RETURNING id, snapshot_id
), e1 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n1.id, n2.id, '파업 발효 시 하역·통관 업무 즉시 전면 중단' FROM snap, n1, n2
  RETURNING id
), e2 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n2.id, n3.id, '반출 불가로 신규 입고가 전면 중단되어 재고 소진 가속' FROM snap, n2, n3
  RETURNING id
), e3 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n3.id, n4.id, '안전재고 소진 시점 도달 시 라인 가동 불가' FROM snap, n3, n4
  RETURNING id
), cand_baseline AS (
  INSERT INTO response_candidates (incident_id, snapshot_id, candidate_type, description, reference_document_ids, preconditions, start_time_variant, validation_status)
  SELECT snap.incident_id, snap.id, 'baseline', '무대응 - 파업 종료까지 대기하며 재고 소진 시 자연 라인정지 수용', '[]'::jsonb, '[]'::jsonb, '즉시', '가능'
  FROM snap
  RETURNING id
), cand_active AS (
  INSERT INTO response_candidates (incident_id, snapshot_id, candidate_type, description, reference_document_ids, preconditions, start_time_variant, validation_status)
  SELECT snap.incident_id, snap.id, '복합', '대체항 활용 + 긴급 항공/육상 운송으로 PT-BATTERY-01 우회 조달', '[]'::jsonb, '["대체항 슬롯 확보 필요", "긴급운송 예산 승인 필요"]'::jsonb, '즉시', '미검증'
  FROM snap
  RETURNING id
)
INSERT INTO seed_scenarios (scenario_key, description, seed_payload, incident_id, snapshot_id)
SELECT
  '파업',
  '항만/운송 노동 파업으로 하역·통관이 전면 중단되어 컨테이너 반출이 불가능해지고 재고 소진 후 생산라인이 중단되는 시나리오',
  jsonb_build_object(
    'trigger', '항만/운송 노동 파업',
    'path', ARRAY['하역·통관 전면 중단','컨테이너 반출 불가','재고 소진','생산라인 중단']
  ),
  snap.incident_id, snap.id
FROM snap;

-- ============================================================
-- Scenario 3: 관세 (tariff / customs rule change)
-- 관세·통관 규정 변경 -> 통관 지연/추가 서류 요구 -> 반출 지연
-- -> 재고 소진 -> 생산 영향
-- ============================================================
WITH inc AS (
  INSERT INTO incidents (type, location, occurred_at, status, affected_targets, assumptions)
  VALUES (
    '관세 규정 변경', '인천세관', now() - interval '4 hours', '유효',
    '{"containers": ["CTN-3001"], "parts": ["PT-CHIP-01"], "production_orders": ["PO-2026-3001"], "customers": ["Dealer-Daegu-01"]}'::jsonb,
    '["신규 규정에 따른 추가 서류 요구 항목은 세관 공지 기준이며 개별 품목별 예외 가능성은 배제"]'::jsonb
  )
  RETURNING id
), snap AS (
  INSERT INTO operational_snapshots (incident_id, data_version, scenario_version, assumptions, operational_state, quality_mode, freshness_seconds, coverage_ratio)
  SELECT inc.id, 'v1', 'scenario-tariff-v1',
    '["추가 서류 준비 소요시간은 평균 통관사례 기준 48시간으로 가정"]'::jsonb,
    '{
       "inventory": {"PT-CHIP-01": {"qty": 600, "unit": "ea", "hourly_consumption": 10, "safety_stock": 300}},
       "production": {"PO-2026-3001": {"line": "L3", "status": "정상가동", "capacity_per_hour": 8}},
       "transport": {"CTN-3001": {"status": "통관대기", "eta": null}}
     }'::jsonb,
    'limited', 7200, 0.7500
  FROM inc
  RETURNING id, incident_id
), n1 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'trigger', '관세·통관 규정 변경', '인천세관', now(), '관세청 규정 변경 공지', '통관담당팀', 'low' FROM snap
  RETURNING id, snapshot_id
), n2 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'customs_clearance_delay', '통관 지연 및 추가 서류 요구 (반출 지연)', 'CTN-3001', now() + interval '48 hours', '신규 규정상 추가 서류 준비 소요시간 48시간 산정', '통관담당팀', 'medium' FROM snap
  RETURNING id, snapshot_id
), n3 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'inventory_depletion', '부품 안전재고 소진', 'PT-CHIP-01', now() + interval '30 hours', '현재 재고 600ea / 시간당 소비 10ea, 안전재고 300ea 기준 역산', '생산관리팀', 'medium' FROM snap
  RETURNING id, snapshot_id
), n4 AS (
  INSERT INTO impact_dag_nodes (snapshot_id, node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty)
  SELECT snap.id, 'production_impact', '생산 영향 (감산 또는 라인 중단)', 'PO-2026-3001 / L3', now() + interval '36 hours', '안전재고 소진 이후 감산 운영 가정', '생산관리팀', 'high' FROM snap
  RETURNING id, snapshot_id
), e1 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n1.id, n2.id, '규정 변경 발효 시 통관 절차에 추가 서류 요구 반영' FROM snap, n1, n2
  RETURNING id
), e2 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n2.id, n3.id, '통관 지연 누적 시 신규 입고 지연으로 재고 소진 가속' FROM snap, n2, n3
  RETURNING id
), e3 AS (
  INSERT INTO impact_dag_edges (snapshot_id, from_node_id, to_node_id, basis)
  SELECT snap.id, n3.id, n4.id, '안전재고 소진 시점 도달 시 감산 또는 라인 중단 불가피' FROM snap, n3, n4
  RETURNING id
), cand_baseline AS (
  INSERT INTO response_candidates (incident_id, snapshot_id, candidate_type, description, reference_document_ids, preconditions, start_time_variant, validation_status)
  SELECT snap.incident_id, snap.id, 'baseline', '무대응 - 통관 절차 정상 진행 대기 및 재고 소진 시 감산 수용', '[]'::jsonb, '[]'::jsonb, '즉시', '가능'
  FROM snap
  RETURNING id
), cand_active AS (
  INSERT INTO response_candidates (incident_id, snapshot_id, candidate_type, description, reference_document_ids, preconditions, start_time_variant, validation_status)
  SELECT snap.incident_id, snap.id, '단일', '통관 서류 사전 준비 및 대체 통관경로(타 세관) 확보', '[]'::jsonb, '["세관 사전 협의 필요", "대체 통관경로 물류비 승인 필요"]'::jsonb, '즉시', '미검증'
  FROM snap
  RETURNING id
)
INSERT INTO seed_scenarios (scenario_key, description, seed_payload, incident_id, snapshot_id)
SELECT
  '관세',
  '관세·통관 규정 변경으로 통관이 지연되고 추가 서류가 요구되어 반출이 지연되고, 재고 소진 후 생산에 영향을 주는 시나리오',
  jsonb_build_object(
    'trigger', '관세·통관 규정 변경',
    'path', ARRAY['통관 지연/추가 서류 요구','반출 지연','재고 소진','생산 영향']
  ),
  snap.incident_id, snap.id
FROM snap;
