import type { ActivateResponse, Lang, LoginResult } from "./types";

// Mock 경계 (skeleton-v3 §7) — backend auth.activate 는 SB V3-2 전까지 NotImplementedError.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

// "__lang_<code>__" 포함 토큰으로 응답 lang 유무 두 경로를 재현(로컬 스모크용, 계약 필드 아님).
const LANG_MARKER = /__lang_(ko|vi|in)__/;
// "__invalid__" 포함 토큰으로 활성화 실패(실API 401, auth.py:13 uniform) 경로를 재현.
const INVALID_MARKER = "__invalid__";

export async function activate(token: string, pin: string): Promise<ActivateResponse> {
  if (USE_MOCK) {
    await delay(200);
    if (token.includes(INVALID_MARKER)) {
      throw new Error("activate failed: 401");
    }
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

// 재로그인 — POST /auth/login {emp_no,pin} → {jwt,refresh}(SB 실물, auth.py:106-113).
// 계정 미존재·PIN 불일치를 구분하지 않는 단일 401 — mock도 동일하게 하나의 실패 경로로 재현.
const LOGIN_VALID_EMP_NO = "EMP-ACTIVE";
const LOGIN_VALID_PIN = "1234";

export async function login(empNo: string, pin: string): Promise<LoginResult> {
  if (USE_MOCK) {
    await delay(200);
    if (empNo !== LOGIN_VALID_EMP_NO || pin !== LOGIN_VALID_PIN) {
      throw Object.assign(new Error("login failed: 401"), { status: 401 });
    }
    return { jwt: "mock-jwt-login", refresh: "mock-refresh-login" };
  }
  const res = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ emp_no: empNo, pin }),
  });
  if (!res.ok) {
    throw Object.assign(new Error(`login failed: ${res.status}`), { status: res.status });
  }
  return (await res.json()) as LoginResult;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
