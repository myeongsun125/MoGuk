import { useEffect, useState } from "react";
import { getAdminEvents } from "../../../../api/adminEvents";
import type { AdminEvent } from "../../../../api/types";
import { formatKst } from "../../../../utils/formatKst";
import { useAdminLang } from "../../../../i18n/AdminLangContext";
import "./AuditLog.css";

function todayLocal(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export default function AdminAuditLogScreen() {
  const { t } = useAdminLang();
  const [date, setDate] = useState(todayLocal());
  const [events, setEvents] = useState<AdminEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh(d: string) {
    setLoading(true);
    try {
      setEvents(await getAdminEvents(d));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh(date);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleDateChange(v: string) {
    setDate(v);
    refresh(v);
  }

  return (
    <div className="admin-audit-log" data-testid="admin-audit-log-screen">
      <h1>{t("admin.auditlog.title")}</h1>

      <div className="filter-row">
        <label htmlFor="date-filter">{t("admin.auditlog.dateLabel")}</label>
        <input
          id="date-filter"
          data-testid="date-filter"
          type="date"
          value={date}
          onChange={(e) => handleDateChange(e.target.value)}
        />
        <span className="count-label" data-testid="event-count">
          {events.length}
          {t("admin.auditlog.countUnit")}
        </span>
      </div>

      {loading && <p>{t("admin.auditlog.loading")}</p>}
      {error && <p className="error">{error}</p>}

      <div className="table-scroll">
        <table className="event-table" data-testid="event-table">
          <thead>
            <tr>
              <th>{t("admin.auditlog.thTime")}</th>
              <th>{t("admin.auditlog.thActor")}</th>
              <th>{t("admin.auditlog.thTarget")}</th>
              <th>action</th>
              <th>{t("admin.auditlog.thTransition")}</th>
              <th>{t("admin.auditlog.thDetail")}</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev) => (
              // M-36: id는 target_type별 시퀀스(admin_events·risk_report_events)라 유일하지
              // 않다 — target_type+id로 합성해야 병합 시 충돌하지 않는다.
              <tr key={`${ev.target_type}-${ev.id}`} data-testid="event-row">
                <td className="col-time">{formatKst(ev.created_at)}</td>
                <td>{ev.actor ?? "-"}</td>
                <td>
                  {ev.target_type} #{ev.target_id}
                </td>
                <td className="col-action">{ev.action}</td>
                <td>
                  {ev.from_state || ev.to_state ? `${ev.from_state ?? "-"} → ${ev.to_state ?? "-"}` : "-"}
                </td>
                <td className="col-detail">{ev.detail ?? "-"}</td>
              </tr>
            ))}
            {!loading && events.length === 0 && (
              <tr>
                <td colSpan={6} className="empty-row">
                  {t("admin.auditlog.emptyRow")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
