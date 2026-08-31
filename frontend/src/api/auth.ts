import type { ActivateResponse, Lang } from "./types";

// Mock 경계 (skeleton-v3 §7) — backend auth.activate 는 SB V3-2 전까지 NotImplementedError.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

// "__lang_<code>__" 포함 토큰으로 응답 lang 유무 두 경로를 재현(로컬 스모크용, 계약 필드 아님).
const LANG_MARKER = /__lang_(ko|vi|in)__/;

export async function activate(token: string, pin: string): Promise<ActivateResponse> {
  if (USE_MOCK) {
    await delay(200);
    const match = token.match(LANG_MARKER);
    const lang = match ? (match[1] as Lang) : undefined;
    return { jwt: "mock-jwt-token", refresh: "mock-refresh-token", ...(lang ? { lang } : {}) };
  }
  const res = await fetch("/api/v1/auth/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, pin }),
  });
  if (!res.ok) {
    throw new Error(`activate failed: ${res.status}`);
  }
  return (await res.json()) as ActivateResponse;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
