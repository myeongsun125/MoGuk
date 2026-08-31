import type { ConfirmResponse, ReportSubmitResponse } from "../types";

// 로컬 벽시계 문자열 — toISOString() UTC 시프트로 두 번 버그가 난 전례(dashboard/adminEvents)와
// 동일한 이유로 쓰지 않는다.
function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function localTimestamp(): string {
  const now = new Date();
  const d = `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
  const t = `${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`;
  return `${d}T${t}`;
}

let mockIdSeq = 1001;

export function buildSubmitMock(): ReportSubmitResponse {
  return {
    id: mockIdSeq++,
    status: "submitted",
    created_at: localTimestamp(),
  };
}

export function buildConfirmMock(id: number, result: "confirmed" | "corrected"): ConfirmResponse {
  if (result === "confirmed") {
    return { id, result: "confirmed", reporter_confirmed: true };
  }
  return { id, result: "corrected", requeued_job_id: 900 + id, reporter_confirmed: false };
}
