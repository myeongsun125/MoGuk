import type { AskRequest, AskResponse } from "./types";
import { ASK_FIXTURE_GATED, ASK_FIXTURE_GROUNDED } from "./fixtures/ask.fixtures";

// Mock 경계 단일 진입점 (skeleton-v3 §7). 실연동(SB V2-2) cutover 시 이 파일만 교체.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export async function askQuestion(req: AskRequest): Promise<AskResponse> {
  if (USE_MOCK) {
    return mockAsk(req);
  }
  const res = await fetch("/api/v1/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`ask failed: ${res.status}`);
  }
  return (await res.json()) as AskResponse;
}

async function mockAsk(req: AskRequest): Promise<AskResponse> {
  await delay(300);
  // "__gated__" 포함 질문으로 게이트 폴백 케이스를 재현(로컬 스모크용, 계약 필드 아님).
  if (req.question.includes("__gated__")) {
    return ASK_FIXTURE_GATED;
  }
  return ASK_FIXTURE_GROUNDED;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
