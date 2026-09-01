import type { AskResponse } from "../types";

// backend/app/fixtures/ask.json 과 동일 형태 (§7 Mock 경계) — 실연동 전 값 동기화 유지.
export const ASK_FIXTURE_GROUNDED: AskResponse = {
  answer:
    "Trước khi vận hành máy ép, hãy kiểm tra nút dừng khẩn cấp và đảm bảo tấm chắn an toàn đã đóng.",
  sources: [
    { document_id: 1, chunk_id: 12, title: "프레스 작업 안전수칙", category: "safety" },
  ],
  verify: { score: 0.93, passed: true, gated: false, gate_reason: null },
  trace_id: "mock-trace-0001",
};

// 무근거 게이트 케이스 — verify.gated=true 시 화면은 답변 대신 폴백 메시지를 보여야 한다 (BLUEPRINT §4-2).
// gate_reason은 계약 타입엔 남아있지만(§3:222) 근로자 화면은 사유 불문 단일 문구만 쓴다(BLUEPRINT
// §4-1·WORKORDER V4-1) — 값 자체는 실API 그대로 두되 화면 분기는 소비하지 않는다.
export const ASK_FIXTURE_GATED: AskResponse = {
  answer: "",
  sources: [],
  verify: { score: null, passed: false, gated: true, gate_reason: "grounding" },
  trace_id: "mock-trace-0002",
};

// 동일 document_id 청크 다건 + 별도 문서 1건 — 출처 칩 묶음(document_id 기준 1칩·"제목 ×N")
// 회귀용 고정 픽스처.
export const ASK_FIXTURE_MULTISOURCE: AskResponse = {
  answer:
    "Trước khi vận hành máy ép, hãy kiểm tra nút dừng khẩn cấp và đảm bảo tấm chắn an toàn đã đóng.",
  sources: [
    { document_id: 1, chunk_id: 12, title: "프레스 작업 안전수칙", category: "safety" },
    { document_id: 1, chunk_id: 15, title: "프레스 작업 안전수칙", category: "safety" },
    { document_id: 1, chunk_id: 21, title: "프레스 작업 안전수칙", category: "safety" },
    { document_id: 2, chunk_id: 4, title: "지게차 운행 매뉴얼", category: "general" },
  ],
  verify: { score: 0.9, passed: true, gated: false, gate_reason: null },
  trace_id: "mock-trace-0003",
};
