import { useEffect, useState } from "react";

export type Theme = "dark" | "light";

/**
 * 테마 선택을 저장하는 localStorage 키.
 *
 * localStorage를 쓰는 이유(다음에 이 코드를 보는 사람을 위한 메모):
 * - 이건 순수 클라이언트 렌더링 취향(preference)이고 서버는 이 값을 전혀 필요로 하지 않는다.
 *   그래서 매 요청마다 서버로 전송되는 쿠키는 아무 의미 없는 네트워크 오버헤드만 추가한다.
 * - sessionStorage는 탭/브라우저를 닫으면 사라지므로 "한번 결정하면 유지된다"는 요구사항(재실행/재시작
 *   후에도 유지)을 만족하지 못한다.
 * - localStorage는 브라우저 재시작·새 탭에서도 살아남고, 순수 클라이언트 상태라 서버 왕복이 필요 없다.
 *   그래서 이 세 가지 중 localStorage가 유일하게 요구사항을 만족한다.
 */
const THEME_STORAGE_KEY = "moveai-theme";

function isValidTheme(value: unknown): value is Theme {
  return value === "dark" || value === "light";
}

function readStoredTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isValidTheme(stored) ? stored : null;
  } catch {
    // localStorage를 쓸 수 없는 환경(프라이버시 모드, 잠긴 환경 등)이면 조용히 무시하고
    // 저장된 값이 없는 것처럼 취급한다 — 앱이 죽을 이유는 아니다.
    return null;
  }
}

function writeStoredTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // 쓰기 실패도 마찬가지로 무시한다 — 테마 전환 자체(화면 반영)는 계속 동작해야 한다.
  }
}

/**
 * 앱 전역에서 공유하는 라이트/다크 테마 훅.
 *
 * localStorage에 저장된 선택을 최초 렌더에서 읽어 시작값으로 쓰고, 아직 저장된 값이 없으면
 * `initial` 파라미터(각 호출부가 원하는 기본값, 예: IncidentDashboard의 `theme` prop)로,
 * 그것도 없으면 앱의 기존 기본값인 "dark"로 떨어진다. 이후 `theme`이 바뀔 때마다 localStorage에
 * 다시 써서, 어느 화면에서 토글하든 같은 선택이 새로고침ㆍ다른 페이지ㆍ새 탭에도 유지된다.
 */
export function useTheme(initial?: Theme): { theme: Theme; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>(() => readStoredTheme() ?? initial ?? "dark");

  useEffect(() => {
    writeStoredTheme(theme);
  }, [theme]);

  const toggleTheme = () => setTheme((current) => (current === "dark" ? "light" : "dark"));

  return { theme, toggleTheme };
}
