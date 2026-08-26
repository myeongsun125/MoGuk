import type { AskResponse } from "../types";

// backend/app/fixtures/ask.json 과 동일 형태 (§7 Mock 경계) — 실연동 전 값 동기화 유지.
export const ASK_FIXTURE_GROUNDED: AskResponse = {
  answer:
    "Trước khi vận hành máy ép, hãy kiểm tra nút dừng khẩn cấp và đảm bảo tấm chắn an toàn đã đóng.",
  sources: [
    { document_id: 1, chunk_id: 12, title: "프레스 작업 안전수칙", category: "safety" },
  ],
  verify: { score: 0.93, passed: true, gated: false },
  trace_id: "mock-trace-0001",
};

// 무근거/게이트 케이스 — verify.gated=true 시 화면은 답변 대신 폴백 메시지를 보여야 한다 (BLUEPRINT §4-2).
export const ASK_FIXTURE_GATED: AskResponse = {
  answer: "",
  sources: [],
  verify: { score: 0.41, passed: false, gated: true },
  trace_id: "mock-trace-0002",
};
