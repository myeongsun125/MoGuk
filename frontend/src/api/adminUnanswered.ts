import type { UnansweredItem } from "./types";
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

// POST /admin/unanswered/{question_id}/answer — 응답 스키마 미확정(backend 스텁, #74 미착륙,
// admin.py:198-201 NotImplementedError). 성공 여부(res.ok)만 확인하고 바디는 소비하지 않는다 —
// 화면은 성공 시 목록을 재조회(listUnanswered)해 상태 진실원본을 GET에서 가져온다.
// #74 착륙 후 실제 응답 필드가 필요해지면 그때 타입을 추가해 반환값을 정의할 것.
export async function answerUnanswered(questionId: number, text: string): Promise<void> {
  if (USE_MOCK) {
    await delay(150);
    const u = answerMock(questionId, text);
    if (!u) throw new Error(`question ${questionId} not found`);
    return;
  }
  const res = await fetch(`/api/v1/admin/unanswered/${questionId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`answer failed: ${res.status}`);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
