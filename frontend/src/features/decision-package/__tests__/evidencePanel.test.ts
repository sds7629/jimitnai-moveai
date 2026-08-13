import { describe, expect, it } from "vitest";
import { buildEvidenceCandidateRows } from "../evidencePanel";
import type { DataAndDocumentsUsedSection, FactInferenceAssumptionSection } from "../types";

describe("buildEvidenceCandidateRows — 정상 시나리오(happy path)", () => {
  it("후보 id를 기준으로 참고 문서와 FACT/INFERENCE/ASSUMPTION을 병합한다", () => {
    const docs: DataAndDocumentsUsedSection = {
      operational_assumptions: [],
      data_version: "v1",
      scenario_version: "s1",
      reference_document_ids_by_candidate: { "1": ["doc-a", "doc-b"] },
    };
    const fia: FactInferenceAssumptionSection = {
      "1": {
        fact: { port_status: "폐쇄" },
        inference: { delay_days: 3 },
        assumption: { reopen_date: "미정" },
      },
    };

    const rows = buildEvidenceCandidateRows(docs, fia);

    expect(rows).toHaveLength(1);
    expect(rows[0].candidateId).toBe("1");
    expect(rows[0].referenceDocumentIds).toEqual(["doc-a", "doc-b"]);
    expect(rows[0].fact).toEqual([{ key: "port_status", value: "폐쇄" }]);
    expect(rows[0].inference).toEqual([{ key: "delay_days", value: "3" }]);
    expect(rows[0].assumption).toEqual([{ key: "reopen_date", value: "미정" }]);
  });

  it("값이 객체/배열이면 JSON 문자열로 변환한다", () => {
    const docs: DataAndDocumentsUsedSection = {
      operational_assumptions: [],
      data_version: "v1",
      scenario_version: "s1",
      reference_document_ids_by_candidate: {},
    };
    const fia: FactInferenceAssumptionSection = {
      "1": { fact: { list: [1, 2] }, inference: {}, assumption: {} },
    };

    const rows = buildEvidenceCandidateRows(docs, fia);

    expect(rows[0].fact).toEqual([{ key: "list", value: "[1,2]" }]);
  });
});

describe("buildEvidenceCandidateRows — 경계값(문서만 있고 fact/inference/assumption 없음)", () => {
  it("한쪽 섹션에만 있는 후보 id도 빠뜨리지 않고 병합한다", () => {
    const docs: DataAndDocumentsUsedSection = {
      operational_assumptions: [],
      data_version: "v1",
      scenario_version: "s1",
      reference_document_ids_by_candidate: { "2": ["doc-c"] },
    };
    const fia: FactInferenceAssumptionSection = {};

    const rows = buildEvidenceCandidateRows(docs, fia);

    expect(rows).toHaveLength(1);
    expect(rows[0].candidateId).toBe("2");
    expect(rows[0].referenceDocumentIds).toEqual(["doc-c"]);
    expect(rows[0].fact).toEqual([]);
  });
});

describe("buildEvidenceCandidateRows — 실패 시나리오(둘 다 비어 있음)", () => {
  it("후보 id가 하나도 없으면 빈 배열을 반환한다", () => {
    const docs: DataAndDocumentsUsedSection = {
      operational_assumptions: [],
      data_version: "v1",
      scenario_version: "s1",
      reference_document_ids_by_candidate: {},
    };
    expect(buildEvidenceCandidateRows(docs, {})).toEqual([]);
  });
});
