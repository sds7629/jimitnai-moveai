import "@testing-library/jest-dom/vitest";

// jsdom의 localStorage는 테스트 파일 하나 안의 여러 it() 사이에서, 그리고 (같은 워커에서 실행되면)
// 파일 간에도 그대로 유지된다. frontend/src/lib/useTheme.ts가 "moveai-theme" 키로 테마 선택을
// localStorage에 저장하므로, 정리해주지 않으면 어떤 테스트가 먼저 테마를 바꿔놓았는지에 따라
// 그 뒤에 도는 테마 관련 테스트(예: IncidentDashboard.test.tsx의 "기본은 다크 테마이다" 케이스)가
// 실행 순서에 따라 통과/실패가 갈릴 수 있다 — 매 테스트 뒤에 비워서 이 상태 오염을 막는다.
afterEach(() => {
  window.localStorage.clear();
});
