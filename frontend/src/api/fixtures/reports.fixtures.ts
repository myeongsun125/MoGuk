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

// "__local_failed__" 포함 원문으로 요약 실패(G-1a, processing_state=failed) 분기를 재현
// (ask.ts의 "__gated__" 관례와 동일 — 로컬 스모크용, 계약 필드 아님).
const failedReportIds = new Set<number>();

export function buildSubmitMock(originalText: string): ReportSubmitResponse {
  const id = mockIdSeq++;
  if (originalText.includes("__local_failed__")) {
    failedReportIds.add(id);
  }
  return {
    id,
    status: "submitted",
    created_at: localTimestamp(),
  };
}

export function buildConfirmMock(id: number, result: "confirmed" | "corrected"): ConfirmResponse {
  if (failedReportIds.has(id)) {
    // services/risk_reports.py:429-436 local_failed 분기와 동일 형태(요청 result 무관하게 고정).
    return {
      id,
      result: "local_failed",
      original_text: "(mock) 요약 실패 원문",
      message: "요약 생성에 실패했습니다. 신고는 정상 접수되었으며 관리자가 원문을 직접 확인합니다.",
    };
  }
  if (result === "confirmed") {
    return { id, result: "confirmed", reporter_confirmed: true };
  }
  return { id, result: "corrected", requeued_job_id: 900 + id, reporter_confirmed: false };
}
