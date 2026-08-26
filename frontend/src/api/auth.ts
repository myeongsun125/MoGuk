import type { ActivateResponse } from "./types";

// Mock 경계 (skeleton-v3 §7) — backend auth.activate 는 SB V3-2 전까지 NotImplementedError.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export async function activate(token: string, pin: string): Promise<ActivateResponse> {
  if (USE_MOCK) {
    await delay(200);
    return { jwt: "mock-jwt-token", refresh: "mock-refresh-token" };
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
