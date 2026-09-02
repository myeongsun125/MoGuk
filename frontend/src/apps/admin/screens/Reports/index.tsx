import { useEffect, useState } from "react";
import {
  TransitionConflictError,
  ackReport,
  getReportDetail,
  listReports,
  resolveReport,
} from "../../../../api/adminReports";
import type { AdminReportDetail, AdminReportListItem } from "../../../../api/types";
import { formatKst } from "../../../../utils/formatKst";
import { useAdminLang } from "../../../../i18n/AdminLangContext";
import "./Reports.css";

export default function AdminReportsScreen() {
  const { t } = useAdminLang();
  const STATUS_LABEL: Record<string, string> = {
    submitted: t("admin.reports.statusSubmitted"),
    acknowledged: t("admin.reports.statusAcknowledged"),
    resolved: t("admin.reports.statusResolved"),
  };
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
    const msg =
      e instanceof TransitionConflictError
        ? t("admin.reports.alreadyProcessed")
        : e instanceof Error
          ? e.message
          : String(e);
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
      <h1>{t("admin.reports.title")}</h1>
      <div className="unconfirmed-badge" data-testid="unconfirmed-count">
        {t("admin.reports.unconfirmedLabel")}: {unconfirmedCount}
        {t("admin.reports.countUnit")}
      </div>

      {loading && <p>{t("admin.reports.loading")}</p>}
      {listError && <p className="error">{listError}</p>}

      <ul className="report-list" data-testid="report-list">
        {reports.map((r) => (
          <li key={r.id} className="report-row" data-testid="report-row" data-report-id={r.id}>
            <div className="report-row-main">
              <span className={`badge badge-status-${r.status}`}>{STATUS_LABEL[r.status]}</span>
              {r.severity && <span className={`badge badge-severity-${r.severity}`}>{r.severity}</span>}
              {r.reporter_confirmed && (
                <span className="badge badge-confirmed">{t("admin.reports.reporterConfirmed")}</span>
              )}
              <span className="summary">
                {r.processing_state === "failed"
                  ? t("admin.reports.summaryFailed")
                  : r.ko_summary ?? t("admin.reports.summaryPendingRow")}
              </span>
            </div>
            <div className="report-row-actions">
              {r.status === "submitted" && (
                <button data-testid="ack-btn" onClick={() => handleAck(r.id)}>
                  {t("admin.reports.ackButton")}
                </button>
              )}
              {r.status === "acknowledged" && (
                <button data-testid="resolve-btn" onClick={() => handleResolve(r.id)}>
                  {t("admin.reports.resolveButton")}
                </button>
              )}
              <button data-testid="detail-btn" onClick={() => openDetail(r.id)}>
                {t("admin.reports.detailButton")}
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

      {detailLoading && <p>{t("admin.reports.detailLoading")}</p>}

      {detail && (
        <div className="report-detail" data-testid="report-detail">
          <button className="close-btn" onClick={closeDetail}>
            {t("admin.reports.closeButton")}
          </button>
          <h2>
            {t("admin.reports.detailTitlePrefix")}
            {detail.id} {t("admin.reports.detailTitleSuffix")}
          </h2>
          <dl>
            <dt>{t("admin.reports.dtOriginal")}</dt>
            <dd data-testid="detail-original">{detail.original_text ?? "—"}</dd>
            <dt>{t("admin.reports.dtSummary")}</dt>
            <dd>
              {detail.processing_state === "failed"
                ? t("admin.reports.summaryFailed")
                : detail.ko_summary ?? t("admin.reports.summaryPendingDetail")}
            </dd>
            <dt>{t("admin.reports.dtStatus")}</dt>
            <dd>{STATUS_LABEL[detail.status]}</dd>
            <dt>{t("admin.reports.reporterConfirmed")}</dt>
            <dd>{detail.reporter_confirmed ? t("admin.reports.confirmedYes") : "-"}</dd>
            <dt>{t("admin.reports.dtAckedBy")}</dt>
            <dd data-testid="detail-acked-by">{detail.acked_by ?? t("admin.reports.authPending")}</dd>
            <dt>{t("admin.reports.dtResolvedBy")}</dt>
            <dd data-testid="detail-resolved-by">{detail.resolved_by ?? t("admin.reports.authPending")}</dd>
            <dt>{t("admin.reports.dtNote")}</dt>
            <dd>{detail.resolution_note ?? "—"}</dd>
          </dl>

          {detail.status === "acknowledged" && (
            <div className="resolve-form">
              <input
                data-testid="resolve-note"
                placeholder={t("admin.reports.notePlaceholder")}
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
              />
              <button data-testid="resolve-btn-detail" onClick={() => handleResolve(detail.id)}>
                {t("admin.reports.resolveButton")}
              </button>
            </div>
          )}

          <h3>{t("admin.reports.historyTitle")}</h3>
          <div className="table-scroll">
            <ul className="event-list" data-testid="event-list">
              {detail.events.map((ev) => (
                <li key={ev.id}>
                  <span className="ev-action">{ev.action}</span>
                  <span className="ev-actor">{ev.actor ?? "-"}</span>
                  <span className="ev-time">{formatKst(ev.created_at)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
