import type { LearnCardsResponse, QuizSet, QuizSubmitResult } from "./types";
import { getCardsMock, getQuizSetMock, submitQuizMock } from "./fixtures/learn.fixtures";
import { getToken } from "../auth/AuthContext";

// Mock 경계 단일 진입점 (skeleton-v3 §7). 워커 API라 reports.ts/ask.ts와 동일하게 Bearer 부착.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// GET /learn/quiz/{set_id}?lang= — §3 M-38 확정. 서버가 lang 기준으로 q·choices를
// 이미 localize해 내려주므로 화면은 그대로 렌더한다(클라측 폴백 로직 없음).
export async function getQuizSet(setId: number, lang: string): Promise<QuizSet> {
  if (USE_MOCK) {
    await delay(200);
    return getQuizSetMock(setId, lang);
  }
  const res = await fetch(`/api/v1/learn/quiz/${setId}?lang=${encodeURIComponent(lang)}`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    throw new Error(`quiz set fetch failed: ${res.status}`);
  }
  return (await res.json()) as QuizSet;
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

// GET /learn/cards?module=&lang= — M-42 SB 확정, 실백엔드는 착수중·미착륙(learn.py:27-29
// 스텁) — mock 경계로 동작한다. 퀴즈 GET과 동형으로 인증 optional: 토큰 있으면 부착하되
// 없어도 401 아님(서버가 lang 쿼리 우선, 없으면 Bearer의 근로자 lang, 둘 다 없으면 ko).
export async function getCards(module: "safety" | "learning", lang: string): Promise<LearnCardsResponse> {
  if (USE_MOCK) {
    await delay(200);
    return getCardsMock(module, lang);
  }
  const res = await fetch(`/api/v1/learn/cards?module=${encodeURIComponent(module)}&lang=${encodeURIComponent(lang)}`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    throw new Error(`learn cards fetch failed: ${res.status}`);
  }
  return (await res.json()) as LearnCardsResponse;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
