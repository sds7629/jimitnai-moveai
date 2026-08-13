import type { AiStatus } from "../types";
import { ThemeToggleButton } from "../../../components/ThemeToggleButton";

const AI_STATUS_LABEL: Record<AiStatus, { label: string; colorVar: string }> = {
  live: { label: "AI: 정상", colorVar: "rgba(45,212,191,.6)" },
  cache_fallback: { label: "AI: 캐시 폴백", colorVar: "rgba(201,154,63,.6)" },
  degraded: { label: "AI: 성능저하", colorVar: "rgba(245,69,94,.6)" },
};

interface HeaderProps {
  aiStatus: AiStatus;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

/** 상단 헤더: 제품명/브랜딩 + AI(LLM) 파이프라인 상태 뱃지 + 우상단 테마 토글 */
export function Header({ aiStatus, theme, onToggleTheme }: HeaderProps) {
  const ai = AI_STATUS_LABEL[aiStatus];

  return (
    <div className="flex items-center justify-between border-b border-[var(--border)] px-7 py-[18px]">
      <div className="flex items-center gap-3.5">
        <div className="h-3.5 w-3.5 rounded-[3px] bg-[var(--text-body)]" aria-hidden />
        <div className="text-[19px] font-bold text-[var(--text-primary)]">도미노 시뮬레이터</div>
        <div className="rounded-full border border-[var(--border-mid)] px-2.5 py-1 text-[11.5px] text-[var(--text-secondary)]">
          GVIS 확장ㆍ의사결정 타이밍 엔진
        </div>
        <div className="text-[12.5px] text-[var(--text-tertiary)]">
          결론이 아니라{" "}
          <span className="font-semibold text-[var(--text-secondary-strong)]">근거ㆍ신뢰도</span>를 제공합니다
        </div>
      </div>
      <div className="flex items-center gap-2.5">
        <div
          className="rounded-full border px-3 py-1 text-[11.5px]"
          style={{ borderColor: ai.colorVar, color: ai.colorVar }}
        >
          {ai.label}
        </div>
        <ThemeToggleButton theme={theme} onToggleTheme={onToggleTheme} />
      </div>
    </div>
  );
}
