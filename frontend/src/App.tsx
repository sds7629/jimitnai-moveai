import { BrowserRouter, Route, Routes } from "react-router-dom";
import { IncidentListPage } from "./pages/IncidentListPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { PostReportPage } from "./pages/PostReportPage";
import { RoiPage } from "./pages/RoiPage";

/**
 * 라우팅 골격.
 * `/incidents/:id`는 Phase 2부터 실제 API로 연동됐다(Phase 10까지: DAG/스냅샷/대응안/의사결정근거/
 * 승인/SOP발송/실행추적). `/incidents/:id/post-report`는 Phase 11에서 분리한 별도 라우트 —
 * 진행 중 대시보드와 관심사가 달라(사후 정산) 한 화면에 얹지 않았다. `/reports/roi`는 Phase 12 —
 * 사건에 종속되지 않는 전역 계산이라 사건 목록과 나란한 최상위 라우트다.
 */
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<IncidentListPage />} />
        <Route path="/incidents/:id" element={<IncidentDetailPage />} />
        <Route path="/incidents/:id/post-report" element={<PostReportPage />} />
        <Route path="/reports/roi" element={<RoiPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
