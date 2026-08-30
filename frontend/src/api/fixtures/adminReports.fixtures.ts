import type { AdminReportDetail, ReportEvent } from "../types";

// 관리자 위험보고 mock 저장소 — §3 계약과 필드 동일. 전이(ack/resolve)가 상태를 바꿔야
// DoD("ack 클릭 후 카운트 감소")를 mock만으로 재현할 수 있어 모듈 내 mutable store로 둔다.
let seq = 1;

function mkEvent(action: string, fromState: string | null, toState: string | null): ReportEvent {
  return {
    id: seq++,
    actor: action === "report_submitted" ? "worker:1001" : "admin:unauthenticated",
    action,
    from_state: fromState,
    to_state: toState,
    detail: null,
    created_at: new Date().toISOString(),
  };
}

function mkReport(over: Partial<AdminReportDetail>): AdminReportDetail {
  return {
    id: 0,
    source: "text",
    original_text: "원문 예시",
    lang: "vi",
    ko_summary: null,
    severity: null,
    status: "submitted",
    processing_state: "queued",
    reporter_confirmed: false,
    acked_by: null,
    acked_at: null,
    resolved_by: null,
    resolved_at: null,
    resolution_note: null,
    created_at: new Date().toISOString(),
    processed_at: null,
    events: [],
    ...over,
  };
}

let store: AdminReportDetail[] = [
  mkReport({
    id: 1,
    original_text: "3층 프레스기 방호장치가 떨어져 있습니다.",
    ko_summary: "3층 프레스기 방호장치 이탈",
    severity: "high",
    status: "submitted",
    processing_state: "done",
    events: [mkEvent("report_submitted", null, "submitted"), mkEvent("summary_done", null, null)],
  }),
  mkReport({
    id: 2,
    original_text: "지게차 경적이 고장난 것 같습니다.",
    ko_summary: "지게차 경적 고장 의심",
    severity: "medium",
    status: "submitted",
    processing_state: "done",
    reporter_confirmed: true,
    events: [
      mkEvent("report_submitted", null, "submitted"),
      mkEvent("summary_done", null, null),
      mkEvent("reporter_confirmed", null, null),
    ],
  }),
  mkReport({
    id: 3,
    original_text: "창고 바닥에 기름이 흘러 있습니다.",
    ko_summary: "창고 바닥 기름 유출",
    severity: "low",
    status: "submitted",
    processing_state: "done",
    events: [mkEvent("report_submitted", null, "submitted"), mkEvent("summary_done", null, null)],
  }),
  mkReport({
    id: 4,
    original_text: "환기구에서 이상한 냄새가 납니다. 확인 부탁드립니다.",
    ko_summary: null,
    severity: null,
    status: "submitted",
    processing_state: "failed",
    events: [mkEvent("report_submitted", null, "submitted"), mkEvent("summary_failed", null, null)],
  }),
  mkReport({
    id: 5,
    original_text: "안전모 재고가 부족합니다.",
    ko_summary: "안전모 재고 부족",
    severity: "low",
    status: "acknowledged",
    processing_state: "done",
    acked_at: new Date(Date.now() - 3600_000).toISOString(),
    events: [
      mkEvent("report_submitted", null, "submitted"),
      mkEvent("summary_done", null, null),
      mkEvent("report_acknowledged", "submitted", "acknowledged"),
    ],
  }),
];

export function listMock(status?: string): AdminReportDetail[] {
  return status ? store.filter((r) => r.status === status) : store;
}

export function getMock(id: number): AdminReportDetail | undefined {
  return store.find((r) => r.id === id);
}

export function ackMock(id: number): { id: number; status: string } | "conflict" | "not_found" {
  const r = store.find((x) => x.id === id);
  if (!r) return "not_found";
  if (r.status !== "submitted") return "conflict";
  r.status = "acknowledged";
  r.acked_at = new Date().toISOString();
  r.events = [...r.events, mkEvent("report_acknowledged", "submitted", "acknowledged")];
  return { id, status: r.status };
}

export function resolveMock(
  id: number,
  note?: string,
): { id: number; status: string } | "conflict" | "not_found" {
  const r = store.find((x) => x.id === id);
  if (!r) return "not_found";
  if (r.status !== "acknowledged") return "conflict";
  r.status = "resolved";
  r.resolved_at = new Date().toISOString();
  r.resolution_note = note ?? null;
  r.events = [...r.events, mkEvent("report_resolved", "acknowledged", "resolved")];
  return { id, status: r.status };
}

// 대시보드(B) KPI①② 소스 — A와 같은 mock 저장소를 직접 집계한다(총괄 지시: "A 화면과
// 동일 소스"). 실API 전환 시에도 둘 다 같은 risk_reports 테이블이라 자연히 일치.
export function statusCounts(): { submitted: number; acknowledged: number; resolved: number } {
  return {
    submitted: store.filter((r) => r.status === "submitted").length,
    acknowledged: store.filter((r) => r.status === "acknowledged").length,
    resolved: store.filter((r) => r.status === "resolved").length,
  };
}
