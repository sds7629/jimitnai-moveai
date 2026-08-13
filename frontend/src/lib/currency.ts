/** 원(KRW) → "###.#억원" 문자열. null이면 "-". */
export function formatKrwToEokwon(value: number | null): string {
  if (value === null) return "-";

  return `${(value / 100_000_000).toFixed(1)}억원`;
}

/** 원(KRW)을 금액 규모에 맞춰 억원·만원·원 단위 문자열로 변환한다. null이면 "-". */
export function formatKrwByScale(value: number | null): string {
  if (value === null) return "-";

  const absoluteValue = Math.abs(value);
  if (absoluteValue >= 100_000_000) {
    return `${(value / 100_000_000).toFixed(1)}억원`;
  }

  if (absoluteValue >= 10_000) {
    return `${(value / 10_000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}만원`;
  }

  return `${value.toLocaleString("ko-KR")}원`;
}
