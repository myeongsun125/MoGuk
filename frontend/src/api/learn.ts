import type { QuizItem, QuizSubmitResult } from "./types";
import { listQuizItemsMock, submitQuizMock } from "./fixtures/learn.fixtures";
import { getToken } from "../auth/AuthContext";

// Mock 경계 단일 진입점 (skeleton-v3 §7). 워커 API라 reports.ts/ask.ts와 동일하게 Bearer 부착.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// TODO(SB): GET 문항 경로·응답 키 미확정 — 회신 오면 이 함수의 실API 분기 1곳만 교체.
export async function getQuizItems(setId: number): Promise<QuizItem[]> {
  if (USE_MOCK) {
    await delay(200);
    return listQuizItemsMock(setId);
  }
  // 실경로 미확정이라 아직 fetch 배선 없음 — mock만 존재.
  return listQuizItemsMock(setId);
}

export async function submitQuiz(setId: number, answers: number[]): Promise<QuizSubmitResult> {
  if (USE_MOCK) {
    await delay(200);
    return submitQuizMock(setId, answers);
  }
  const res = await fetch(`/api/v1/learn/quiz/${setId}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) {
    throw new Error(`quiz submit failed: ${res.status}`);
  }
  return (await res.json()) as QuizSubmitResult;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
