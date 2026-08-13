import { BrowserRouter, Route, Routes } from "react-router-dom";
import { IncidentListPage } from "./pages/IncidentListPage";
import { IncidentDashboard } from "./features/incident-dashboard/IncidentDashboard";
import { strikeScenarioMock } from "./features/incident-dashboard/mockData";

/**
 * 라우팅 골격 (frontend/docs/FEATURE_PHASES.md Phase 1).
 * `/incidents/:id`는 아직 Phase 2(Impact DAG 실연동)가 끝나기 전까지 목업 데이터를 그대로 쓴다 —
 * 사건 목록에서 어떤 사건을 클릭해도 지금은 같은 "파업" 시나리오 목업이 보인다는 뜻이다.
 */
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<IncidentListPage />} />
        <Route path="/incidents/:id" element={<IncidentDashboard data={strikeScenarioMock} />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
