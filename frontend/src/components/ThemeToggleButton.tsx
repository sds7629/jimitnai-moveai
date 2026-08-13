import type { Theme } from "../lib/useTheme";

interface ThemeToggleButtonProps {
  theme: Theme;
  onToggleTheme: () => void;
  className?: string;
}

/**
 * 라이트/다크 테마 전환 버튼 — 원래 incident-dashboard의 Header 안에만 있던 토글을 여러 화면
 * (Header, 사후보고서 페이지 등)에서 재사용할 수 있도록 뽑아낸 공용 UI 컴포넌트.
 * 다크 모드일 때 ☀️(라이트로 전환), 라이트 모드일 때 🌙(다크로 전환)를 보여준다.
 */
export function ThemeToggleButton({ theme, onToggleTheme, className = "" }: ThemeToggleButtonProps) {
  return (
    <button
      type="button"
      onClick={onToggleTheme}
      aria-label="테마 전환"
      title={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
      className={`flex h-7 w-7 items-center justify-center rounded-full border border-[var(--border-btn)] text-[13px] text-[var(--text-secondary)] ${className}`}
    >
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  );
}
