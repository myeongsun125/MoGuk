import type { AnswerResult, UnansweredItem } from "./types";
import { answerMock, listMock } from "./fixtures/unanswered.fixtures";

// Mock 경계 (skeleton-v3 §7). glossary.ts 구조 템플릿 — 어드민 API는 IP 화이트리스트로
// 보호되어 Bearer를 붙이지 않는다(워커 api/*.ts의 authHeaders()와 다름, 의도적).
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export async function listUnanswered(status = "open"): Promise<UnansweredItem[]> {
  if (USE_MOCK) {
    await delay(150);
    return listMock(status || undefined);
  }
  const res = await fetch(`/api/v1/admin/unanswered?status=${encodeURIComponent(status)}`);
  if (!res.ok) throw new Error(`list_unanswered failed: ${res.status}`);
  return (await res.json()) as UnansweredItem[];
}

// POST /admin/unanswered/{question_id}/answer — #74 확정 응답(types.ts AnswerResult 참고).
// 에러는 status를 Error에 실어 던진다(reports.ts confirmReport의 401 관례와 동일) — 화면이
// 404(대상 없음)·422(open 아님/text 공백)를 구분해 문구를 나눌 수 있게.
export async function answerUnanswered(questionId: number, text: string): Promise<AnswerResult> {
  if (USE_MOCK) {
    await delay(150);
    return answerMock(questionId, text);
  }
  const res = await fetch(`/api/v1/admin/unanswered/${questionId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    throw Object.assign(new Error(`answer failed: ${res.status}`), { status: res.status });
  }
  return (await res.json()) as AnswerResult;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
