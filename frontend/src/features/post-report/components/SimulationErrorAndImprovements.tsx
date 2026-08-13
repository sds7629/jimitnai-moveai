import type {
  FutureImprovementsSection,
  SimulationErrorCandidateApi,
  SimulationErrorSection,
} from "../types";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

/** 백엔드 confidence는 0~1 실수라 화면에서는 %로 바꿔 보여준다 (ExpectedProgressAndChanges.tsx와 동일 규칙) */
function formatConfidence(confidence: number | null): string | null {
  if (confidence == null) return null;
  return `${Math.round(confidence * 100)}%`;
}

function SimulationErrorCandidateCard({ candidate }: { candidate: SimulationErrorCandidateApi }) {
  const confidence = formatConfidence(candidate.confidence);
  const assumptionEntries = Object.entries(candidate.assumption);

  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10.5px] font-bold text-[var(--text-secondary-strong)]">{candidate.candidate_type}</span>
        {confidence !== null && (
          <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
            신뢰도 {confidence}
          </span>
        )}
      </div>
      <div className="mt-1 text-[10.5px] text-[var(--text-tertiary)]">
        데이터 {candidate.data_version} · 시나리오 {candidate.scenario_version} · {formatDateTime(candidate.calculated_at)}
      </div>

      {candidate.sensitivity_variables.length > 0 && (
        <div className="mt-1.5">
          <div className="text-[10.5px] font-bold text-[var(--text-secondary-strong)]">민감 변수</div>
          <ul className="list-disc pl-4 text-[10.5px] text-[var(--text-secondary)]">
            {candidate.sensitivity_variables.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        </div>
      )}

      {assumptionEntries.length > 0 && (
        <div className="mt-1.5 text-[10.5px] text-[var(--text-secondary)]">
          {assumptionEntries.map(([key, value]) => (
            <div key={key}>
              ㆍ{key}: {Array.isArray(value) ? value.join(", ") : String(value)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FutureImprovementCard({ category, description }: { category: string; description: string }) {
  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-2.5">
      <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
        {category}
      </span>
      <div className="mt-1.5 text-[10.5px] text-[var(--text-secondary)]">{description}</div>
    </div>
  );
}

interface SimulationErrorAndImprovementsProps {
  simulationError: SimulationErrorSection;
  improvements: FutureImprovementsSection;
}

/**
 * 사후보고서 Phase 24 — sections["10_시뮬레이션_오차와_가정의_영향"] +
 * sections["12_향후_SOP_모델_데이터_개선사항"]을 리스트 UI로 렌더링한다
 * (frontend/docs/FEATURE_PHASES.md Phase 24).
 *
 * 섹션 10의 error_calculable은 이 시스템 스코프상 항상 false다(실적 데이터 입력 메커니즘이
 * 없어 오차 계산 불가) — reason을 화면에서 숨기지 않는다. 섹션 12는 다른 섹션들과 달리
 * object가 아니라 배열 자체다(_section_12_future_improvements가 list[dict]를 직접 반환).
 */
export function SimulationErrorAndImprovements({
  simulationError,
  improvements,
}: SimulationErrorAndImprovementsProps) {
  return (
    <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-3 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">
        시뮬레이션 오차와 가정의 영향 · 향후 개선사항
      </div>

      <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-2 text-[10.5px] text-[var(--text-secondary)]">
        {simulationError.reason}
      </div>

      <div className="mt-3">
        {simulationError.candidates.length === 0 ? (
          <div className="text-[10.5px] text-[var(--text-secondary)]">시뮬레이션 결과가 있는 후보가 없습니다.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {simulationError.candidates.map((candidate) => (
              <SimulationErrorCandidateCard key={candidate.candidate_id} candidate={candidate} />
            ))}
          </div>
        )}
      </div>

      <div className="mt-3 border-t border-[var(--border)] pt-2.5">
        <div className="mb-1.5 text-[10.5px] font-bold text-[var(--text-secondary-strong)]">향후 SOP·모델·데이터 개선사항</div>
        {improvements.length === 0 ? (
          <div className="text-[10.5px] text-[var(--text-secondary)]">개선사항 없음.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {improvements.map((item) => (
              <FutureImprovementCard key={item.category} category={item.category} description={item.description} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
