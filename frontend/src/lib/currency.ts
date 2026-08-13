/** 원(KRW) → "###.#억원" 문자열. null이면 "-". features/candidates/mapping.ts와 post-report 화면이 공유한다 */
export function formatKrwToEokwon(value: number | null): string {
  if (value === null) return "-";
  return `${(value / 100_000_000).toFixed(1)}억원`;
}
