import { IncidentDashboard } from "./features/incident-dashboard/IncidentDashboard";
import { strikeScenarioMock } from "./features/incident-dashboard/mockData";

/**
 * 앱 진입점.
 * 현재는 "파업" 시드 시나리오 목업으로 인시던트 대시보드를 바로 렌더링한다.
 * 라우팅(React Router)·실제 API 연동(TanStack Query)은 백엔드 계약 확정 후 연결한다
 * (FRONTEND_ARCHITECTURE.md §3, §4).
 */
function App() {
  return <IncidentDashboard data={strikeScenarioMock} />;
}

export default App;
