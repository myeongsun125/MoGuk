import { useEffect, useState } from "react";
import {
  TransitionConflictError,
  ackReport,
  getReportDetail,
  listReports,
  resolveReport,
} from "../../../../api/adminReports";
import type { AdminReportDetail, AdminReportListItem } from "../../../../api/types";
import "./Reports.css";

const STATUS_LABEL: Record<string, string> = {
  submitted: "접수",
  acknowledged: "확인됨",
  resolved: "해결됨",
};

export default function AdminReportsScreen() {
  const [reports, setReports] = useState<AdminReportListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminReportDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<Record<number, string>>({});
  const [noteDraft, setNoteDraft] = useState("");

  async function refresh() {
    setLoading(true);
    try {
      setReports(await listReports());
      setListError(null);
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const unconfirmedCount = reports.filter((r) => r.status === "submitted").length;

  // 세부 버튼 클릭 시에만 호출 — 목록 로드 시 미리 부르지 않는다(원문 열람 감사 = 실제 열람).
  async function openDetail(id: number) {
    setDetailLoading(true);
    try {
      setDetail(await getReportDetail(id));
    } catch (e) {
      setActionMsg((m) => ({ ...m, [id]: e instanceof Error ? e.message : String(e) }));
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDetail() {
    setDetail(null);
    setNoteDraft("");
  }

  function describeError(id: number, e: unknown) {
    const msg = e instanceof TransitionConflictError ? "이미 처리됨" : e instanceof Error ? e.message : String(e);
    setActionMsg((m) => ({ ...m, [id]: msg }));
  }

  async function handleAck(id: number) {
    setActionMsg((m) => ({ ...m, [id]: "" }));
    try {
      await ackReport(id);
      await refresh();
      if (detail?.id === id) await openDetail(id);
    } catch (e) {
      describeError(id, e);
    }
  }

  async function handleResolve(id: number) {
    setActionMsg((m) => ({ ...m, [id]: "" }));
    try {
      await resolveReport(id, noteDraft || undefined);
      setNoteDraft("");
      await refresh();
      if (detail?.id === id) await openDetail(id);
    } catch (e) {
      describeError(id, e);
    }
  }

  return (
    <div className="admin-reports" data-testid="admin-reports-screen">
      <h1>위험보고 관리</h1>
      <div className="unconfirmed-badge" data-testid="unconfirmed-count">
        미확인 위험보고: {unconfirmedCount}건
      </div>

      {loading && <p>불러오는 중...</p>}
      {listError && <p className="error">{listError}</p>}

      <ul className="report-list" data-testid="report-list">
        {reports.map((r) => (
          <li key={r.id} className="report-row" data-testid="report-row" data-report-id={r.id}>
            <div className="report-row-main">
              <span className={`badge badge-status-${r.status}`}>{STATUS_LABEL[r.status]}</span>
              {r.severity && <span className={`badge badge-severity-${r.severity}`}>{r.severity}</span>}
              {r.reporter_confirmed && <span className="badge badge-confirmed">보고자 확인</span>}
              <span className="summary">
                {r.processing_state === "failed" ? "요약 실패 — 원문 직접 확인" : r.ko_summary ?? "(요약 대기 중)"}
              </span>
            </div>
            <div className="report-row-actions">
              {r.status === "submitted" && (
                <button data-testid="ack-btn" onClick={() => handleAck(r.id)}>
                  확인(ack)
                </button>
              )}
              {r.status === "acknowledged" && (
                <button data-testid="resolve-btn" onClick={() => handleResolve(r.id)}>
                  해결(resolve)
                </button>
              )}
              <button data-testid="detail-btn" onClick={() => openDetail(r.id)}>
                세부
              </button>
            </div>
            {actionMsg[r.id] && (
              <div className="action-msg" data-testid="action-msg">
                {actionMsg[r.id]}
              </div>
            )}
          </li>
        ))}
      </ul>

      {detailLoading && <p>상세 불러오는 중...</p>}

      {detail && (
        <div className="report-detail" data-testid="report-detail">
          <button className="close-btn" onClick={closeDetail}>
            닫기
          </button>
          <h2>보고 #{detail.id} 상세</h2>
          <dl>
            <dt>원문</dt>
            <dd data-testid="detail-original">{detail.original_text ?? "—"}</dd>
            <dt>요약</dt>
            <dd>
              {detail.processing_state === "failed" ? "요약 실패 — 원문 직접 확인" : detail.ko_summary ?? "(대기 중)"}
            </dd>
            <dt>상태</dt>
            <dd>{STATUS_LABEL[detail.status]}</dd>
            <dt>보고자 확인</dt>
            <dd>{detail.reporter_confirmed ? "확인함" : "-"}</dd>
            <dt>확인자(ack)</dt>
            <dd data-testid="detail-acked-by">{detail.acked_by ?? "— (인증 도입 예정)"}</dd>
            <dt>해결자(resolve)</dt>
            <dd data-testid="detail-resolved-by">{detail.resolved_by ?? "— (인증 도입 예정)"}</dd>
            <dt>비고</dt>
            <dd>{detail.resolution_note ?? "—"}</dd>
          </dl>

          {detail.status === "acknowledged" && (
            <div className="resolve-form">
              <input
                data-testid="resolve-note"
                placeholder="처리 메모(선택)"
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
              />
              <button data-testid="resolve-btn-detail" onClick={() => handleResolve(detail.id)}>
                해결(resolve)
              </button>
            </div>
          )}

          <h3>이력</h3>
          <ul className="event-list" data-testid="event-list">
            {detail.events.map((ev) => (
              <li key={ev.id}>
                <span className="ev-action">{ev.action}</span>
                <span className="ev-actor">{ev.actor ?? "-"}</span>
                <span className="ev-time">{ev.created_at}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
