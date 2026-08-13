import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvidencePanel } from "../EvidencePanel";
import type {
  DataAndDocumentsUsedSection,
  FactInferenceAssumptionSection,
  FreshnessAndCoverageSection,
} from "../../../decision-package/types";

const dataAndDocuments: DataAndDocumentsUsedSection = {
  operational_assumptions: ["항만 재개방 시점 미확정"],
  data_version: "v1",
  scenario_version: "strike-v1",
  reference_document_ids_by_candidate: { "1": ["doc-a"] },
};
const factInferenceAssumption: FactInferenceAssumptionSection = {
  "1": { fact: { port_status: "폐쇄" }, inference: { delay_days: 3 }, assumption: {} },
};
const freshnessAndCoverage: FreshnessAndCoverageSection = {
  quality_mode: "normal",
  freshness_seconds: 120,
  coverage_ratio: 0.8,
};

describe("EvidencePanel — 정상 시나리오(happy path)", () => {
  it("가정·문서 버전·freshness/coverage 뱃지·후보별 FACT/INFERENCE를 모두 표시한다", () => {
    render(
      <EvidencePanel
        dataAndDocuments={dataAndDocuments}
        factInferenceAssumption={factInferenceAssumption}
        freshnessAndCoverage={freshnessAndCoverage}
      />,
    );

    expect(screen.getByText("항만 재개방 시점 미확정")).toBeInTheDocument();
    expect(screen.getByText(/v1/)).toBeInTheDocument();
    expect(screen.getByText("정상")).toBeInTheDocument();
    expect(screen.getByText(/80%/)).toBeInTheDocument();
    expect(screen.getByText("doc-a")).toBeInTheDocument();
    expect(screen.getByText(/port_status/)).toBeInTheDocument();
    expect(screen.getByText(/폐쇄/)).toBeInTheDocument();
  });
});

describe("EvidencePanel — 경계값(가정·문서 없음)", () => {
  it("가정과 참고 문서가 없어도 오류 없이 렌더링된다", () => {
    render(
      <EvidencePanel
        dataAndDocuments={{ ...dataAndDocuments, operational_assumptions: [], reference_document_ids_by_candidate: {} }}
        factInferenceAssumption={{}}
        freshnessAndCoverage={freshnessAndCoverage}
      />,
    );
    expect(screen.getByText("등록된 가정이 없습니다.")).toBeInTheDocument();
  });
});

describe("EvidencePanel — 실패 시나리오(freshness/coverage 값 없음)", () => {
  it("freshness_seconds/coverage_ratio가 null이면 '-'을 표시한다", () => {
    render(
      <EvidencePanel
        dataAndDocuments={dataAndDocuments}
        factInferenceAssumption={factInferenceAssumption}
        freshnessAndCoverage={{ quality_mode: "limited", freshness_seconds: null, coverage_ratio: null }}
      />,
    );
    expect(screen.getByText(/최신성\s*-/)).toBeInTheDocument();
    expect(screen.getByText(/커버리지\s*-/)).toBeInTheDocument();
    expect(screen.getByText("제한 모드")).toBeInTheDocument();
  });
});
