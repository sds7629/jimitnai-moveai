import { BrowserRouter, Route, Routes } from "react-router-dom";
import { IncidentListPage } from "./pages/IncidentListPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";

/**
 * 라우팅 골격.
 * `/incidents/:id`는 Phase 2부터 실제 Impact DAG API로 연동됐다 — 대응안 랭킹/SOP/승인 패널만
 * 아직 목업(frontend/docs/FEATURE_PHASES.md Phase 5 이후)이다.
 */
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<IncidentListPage />} />
        <Route path="/incidents/:id" element={<IncidentDetailPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
