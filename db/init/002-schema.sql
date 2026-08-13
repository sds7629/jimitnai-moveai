-- platform-infra: full schema for the supply-chain crisis decision platform
-- See ARCHITECTURE.md §2 (data layer) for the table inventory and
-- agents/*.md for per-persona column requirements.
--
-- Design notes:
--  * All primary keys are BIGSERIAL — no extra extension needed beyond
--    pgvector (001-init-extensions.sql).
--  * `operational_snapshots`, `simulation_results`, `approvals` and
--    `audit_log` are append-only by design (baseline immutability
--    requirement, ARCHITECTURE.md §2 / simulation-supply-chain-tool.md §9).
--    This is enforced two ways:
--      1. The application repository layer never defines an UPDATE method
--         for these tables (backend/app/repositories/*.py).
--      2. The `moveai_app` DB role (used by the backend at runtime) is
--         granted SELECT/INSERT only on these tables — see
--         004-permissions.sql. UPDATE/DELETE are never granted.
--  * `incidents`, `response_candidates`, `documents`/`document_chunks`,
--    `impact_dag_nodes/edges` and `decision_packages` allow in-place field
--    updates for fields that are legitimately mutable state (e.g. incident
--    status, candidate validation_status) — those go through
--    MutableRepository in the app layer.

-- ============================================================
-- incidents
-- ============================================================
CREATE TABLE incidents (
    id                          BIGSERIAL PRIMARY KEY,
    type                        TEXT NOT NULL,
    location                    TEXT NOT NULL,
    occurred_at                 TIMESTAMPTZ NOT NULL,
    status                      TEXT NOT NULL DEFAULT '신규'
                                    CHECK (status IN ('신규','중복','오탐','유효','처리중','승인','종료')),
    duplicate_of_incident_id    BIGINT REFERENCES incidents(id),
    affected_targets            JSONB NOT NULL DEFAULT '{}'::jsonb,
    assumptions                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_incidents_status ON incidents(status);
CREATE INDEX idx_incidents_type_location ON incidents(type, location);

COMMENT ON TABLE incidents IS
  '사건 정의/상태. append-only 대상 아님 - 상태 전이는 audit_log에도 기록.';

-- ============================================================
-- audit_log (append-only)
-- ============================================================
CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    incident_id   BIGINT REFERENCES incidents(id),
    event_type    TEXT NOT NULL,
    actor         TEXT NOT NULL,
    reason        TEXT,
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_log_incident ON audit_log(incident_id);
CREATE INDEX idx_audit_log_event_type ON audit_log(event_type);

COMMENT ON TABLE audit_log IS
  '모든 상태전이/승인/발송/수신 이벤트. append-only.';

-- ============================================================
-- operational_snapshots (append-only)
-- ============================================================
CREATE TABLE operational_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    incident_id         BIGINT NOT NULL REFERENCES incidents(id),
    data_version        TEXT NOT NULL,
    scenario_version    TEXT NOT NULL,
    assumptions         JSONB NOT NULL DEFAULT '[]'::jsonb,
    operational_state   JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_mode        TEXT NOT NULL DEFAULT 'normal' CHECK (quality_mode IN ('normal','limited')),
    freshness_seconds   INTEGER,
    coverage_ratio      NUMERIC(5,4),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_snapshots_incident ON operational_snapshots(incident_id, created_at DESC);

COMMENT ON TABLE operational_snapshots IS
  'baseline 불변성 요구. append-only, UPDATE 금지 (새 버전은 새 행으로 추가).';

-- ============================================================
-- impact_dag_nodes / impact_dag_edges
-- ============================================================
CREATE TABLE impact_dag_nodes (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_id         BIGINT NOT NULL REFERENCES operational_snapshots(id),
    node_key            TEXT NOT NULL,
    label               TEXT NOT NULL,
    affected_target     TEXT,
    expected_time       TIMESTAMPTZ,
    basis               TEXT,
    responsible_party   TEXT,
    uncertainty         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, node_key)
);
CREATE INDEX idx_dag_nodes_snapshot ON impact_dag_nodes(snapshot_id);

CREATE TABLE impact_dag_edges (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES operational_snapshots(id),
    from_node_id    BIGINT NOT NULL REFERENCES impact_dag_nodes(id),
    to_node_id      BIGINT NOT NULL REFERENCES impact_dag_nodes(id),
    basis           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_dag_edges_snapshot ON impact_dag_edges(snapshot_id);

-- ============================================================
-- response_candidates
-- ============================================================
CREATE TABLE response_candidates (
    id                          BIGSERIAL PRIMARY KEY,
    incident_id                 BIGINT NOT NULL REFERENCES incidents(id),
    snapshot_id                 BIGINT NOT NULL REFERENCES operational_snapshots(id),
    candidate_type               TEXT NOT NULL CHECK (candidate_type IN ('단일','복합','baseline')),
    description                  TEXT NOT NULL,
    reference_document_ids       JSONB NOT NULL DEFAULT '[]'::jsonb,
    preconditions                JSONB NOT NULL DEFAULT '[]'::jsonb,
    start_time_variant           TEXT,
    validation_status            TEXT NOT NULL DEFAULT '미검증'
                                     CHECK (validation_status IN ('가능','조건부','불가능','미검증')),
    exclusion_category            TEXT,
    exclusion_detail              TEXT,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_candidates_incident ON response_candidates(incident_id);

COMMENT ON TABLE response_candidates IS
  '대응안 후보. validation_status/exclusion_*는 제약검증 단계에서 in-place 갱신 (append-only 아님).';

-- ============================================================
-- simulation_results (append-only)
-- ============================================================
CREATE TABLE simulation_results (
    id                       BIGSERIAL PRIMARY KEY,
    candidate_id             BIGINT NOT NULL REFERENCES response_candidates(id),
    incident_id              BIGINT NOT NULL REFERENCES incidents(id),
    expected_loss            NUMERIC,
    p90                      NUMERIC,
    cvar                     NUMERIC,
    sensitivity_variables    JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence               NUMERIC,
    fact                     JSONB NOT NULL DEFAULT '{}'::jsonb,
    inference                JSONB NOT NULL DEFAULT '{}'::jsonb,
    assumption               JSONB NOT NULL DEFAULT '{}'::jsonb,
    data_version             TEXT NOT NULL,
    scenario_version         TEXT NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sim_results_candidate ON simulation_results(candidate_id, created_at DESC);
CREATE INDEX idx_sim_results_incident ON simulation_results(incident_id);

COMMENT ON TABLE simulation_results IS
  'LLM 산출 예측 결과. append-only, UPDATE 금지 (재시뮬레이션은 새 행).';

-- ============================================================
-- candidate_reviews (append-only)
-- ============================================================
-- 다중 관점 교차검증 (agents/response-optimization.md, simulation-supply-
-- chain-tool.md §7.1 대응 최적화 에이전트, Level 2). 시뮬레이션 결과가 있는
-- 후보마다 비용(cost)/실행가능성(feasibility)/리스크(risk) 3개의 독립된
-- LLM 호출이 각자의 행을 남긴다 -- 재검토도 기존 행을 고치지 않고 새 행을
-- 추가한다 (simulation_results와 동일한 append-only 근거).
CREATE TABLE candidate_reviews (
    id                    BIGSERIAL PRIMARY KEY,
    candidate_id          BIGINT NOT NULL REFERENCES response_candidates(id),
    incident_id           BIGINT NOT NULL REFERENCES incidents(id),
    simulation_result_id  BIGINT REFERENCES simulation_results(id),
    lens                  TEXT NOT NULL CHECK (lens IN ('cost','feasibility','risk')),
    concern_level         TEXT NOT NULL CHECK (concern_level IN ('low','medium','high')),
    comment               TEXT NOT NULL,
    flags                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_candidate_reviews_candidate ON candidate_reviews(candidate_id);

COMMENT ON TABLE candidate_reviews IS
  '다중 관점(비용/실행가능성/리스크) 교차검증 결과. append-only, UPDATE 금지 (재검토는 새 행).';

-- ============================================================
-- decision_packages
-- ============================================================
CREATE TABLE decision_packages (
    id                       BIGSERIAL PRIMARY KEY,
    incident_id              BIGINT NOT NULL REFERENCES incidents(id),
    package                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    recommended_deadline     TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_decision_packages_incident ON decision_packages(incident_id, created_at DESC);

COMMENT ON TABLE decision_packages IS
  '`package` JSONB는 업무명세 §5.1의 10개 항목(기대손실/P90/CVaR, 지금·6시간후·무대응 비교, '
  '원인경로, 사용 데이터/문서, FACT/INFERENCE/ASSUMPTION, freshness/coverage, 민감도 변수, '
  '실행가능성/제외사유, 신뢰도/불확실성, 권고결정기한)을 구조화해 담는다. '
  '재계산 시 새 행을 추가하는 append-only 취급을 권장(리포지토리에 update 없음).';

-- ============================================================
-- approvals (append-only)
-- ============================================================
CREATE TABLE approvals (
    id                       BIGSERIAL PRIMARY KEY,
    incident_id              BIGINT NOT NULL REFERENCES incidents(id),
    decision_type            TEXT NOT NULL CHECK (decision_type IN ('승인','조건부승인','수정요청','반려','기한초과')),
    reason                   TEXT NOT NULL,
    approver                 TEXT NOT NULL,
    decided_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_version_ref         TEXT,
    scenario_version_ref     TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_approvals_incident ON approvals(incident_id);

COMMENT ON TABLE approvals IS
  '승인/반려/조건부승인/수정요청/기한초과 이력. append-only.';

-- ============================================================
-- documents / document_chunks (RAG)
-- ============================================================
CREATE TABLE documents (
    id             BIGSERIAL PRIMARY KEY,
    doc_type       TEXT NOT NULL CHECK (doc_type IN ('사고','SOP','계약','플레이북')),
    title          TEXT NOT NULL,
    source         TEXT,
    valid_from     TIMESTAMPTZ,
    valid_until    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_documents_type ON documents(doc_type);

-- Embedding dimension fixed at 768 to match Gemini text-embedding-004
-- (`gemini-embedding` family). Adjust here + any ivfflat/hnsw index if the
-- embedding model changes.
CREATE TABLE document_chunks (
    id             BIGSERIAL PRIMARY KEY,
    document_id    BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_text     TEXT NOT NULL,
    chunk_type     TEXT NOT NULL,
    embedding      vector(768),
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chunks_document ON document_chunks(document_id);

COMMENT ON COLUMN document_chunks.chunk_type IS
  '문서유형별 청킹 단위: 계약=조항, SOP=절차, 사고=사건(원인->대응->결과), 플레이북=대응패턴.';

-- ============================================================
-- seed_scenarios
-- ============================================================
CREATE TABLE seed_scenarios (
    id                BIGSERIAL PRIMARY KEY,
    scenario_key      TEXT NOT NULL UNIQUE CHECK (scenario_key IN ('적체','파업','관세')),
    description       TEXT,
    seed_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    incident_id       BIGINT REFERENCES incidents(id),
    snapshot_id       BIGINT REFERENCES operational_snapshots(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE seed_scenarios IS
  '적체/파업/관세 3종 시드 시나리오 참조 레코드. seed_payload에 트리거/영향경로 요약을 저장하고, '
  'incident_id/snapshot_id로 003-seed-scenarios.sql이 실제로 만든 레코드를 가리킨다.';
