import type { ConfirmRequest, ConfirmResponse, ReportSubmitRequest, ReportSubmitResponse } from "./types";
import { buildConfirmMock, buildSubmitMock } from "./fixtures/reports.fixtures";
import { getToken } from "../auth/AuthContext";

// Mock 경계 단일 진입점 (skeleton-v3 §7). PR-3 — 워커 위험보고 제출/확인.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function submitReport(req: ReportSubmitRequest): Promise<ReportSubmitResponse> {
  if (USE_MOCK) {
    await delay(250);
    return buildSubmitMock(req.original_text);
  }
  const res = await fetch("/api/v1/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`report submit failed: ${res.status}`);
  }
  return (await res.json()) as ReportSubmitResponse;
}

export async function confirmReport(id: number, body: ConfirmRequest): Promise<ConfirmResponse> {
  if (USE_MOCK) {
    await delay(200);
    return buildConfirmMock(id, body.result);
  }
  const res = await fetch(`/api/v1/reports/${id}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // status를 실어 보낸다 — 화면이 401(재인증 필요)과 그 외 오류를 구분해야 한다(#61 이월 ⑤).
    throw Object.assign(new Error(`confirm failed: ${res.status}`), { status: res.status });
  }
  return (await res.json()) as ConfirmResponse;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
