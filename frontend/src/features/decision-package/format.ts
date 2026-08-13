export interface DeadlineSummary {
  label: string;
  overdue: boolean;
}

/**
 * recommended_deadline(ISO 문자열 또는 null)을 표시용 문구로 변환한다.
 * backend/app/services/response_optimization.py의 compute_recommended_deadline은 Impact DAG에
 * "돌이킬 수 없는 지점" 직전 노드의 expected_time을 역산한 값이거나, 계산할 수 없으면 null이다.
 */
export function summarizeDeadline(deadlineIso: string | null, now: Date = new Date()): DeadlineSummary {
  if (!deadlineIso) return { label: "미산정", overdue: false };

  const diffMs = new Date(deadlineIso).getTime() - now.getTime();
  if (diffMs <= 0) return { label: "초과", overdue: true };

  const diffMinutes = Math.floor(diffMs / 60_000);
  if (diffMinutes < 60) return { label: `${diffMinutes}분 후`, overdue: false };

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return { label: `${diffHours}시간 후`, overdue: false };

  const diffDays = Math.floor(diffHours / 24);
  return { label: `${diffDays}일 후`, overdue: false };
}
