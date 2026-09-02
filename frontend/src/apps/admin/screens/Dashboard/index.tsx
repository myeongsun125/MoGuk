import { useEffect, useState } from "react";
import { getDashboard } from "../../../../api/dashboard";
import type { DashboardSummary } from "../../../../api/types";
import { useAdminLang } from "../../../../i18n/AdminLangContext";
import "./Dashboard.css";

export default function AdminDashboardScreen() {
  const { t } = useAdminLang();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboard()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>{t("admin.dashboard.loading")}</p>;

  const maxTrend = Math.max(...data.reports_today_hourly.map((p) => p.count), 1);
  const citationPct =
    data.citation_rate.rate === null ? "—" : `${Math.round(data.citation_rate.rate * 100)}%`;

  return (
    <div className="admin-dashboard" data-testid="admin-dashboard-screen">
      <h1>{t("admin.dashboard.title")}</h1>

      <div className="kpi-grid" data-testid="kpi-grid">
        <div className="kpi-card kpi-card-alert" data-testid="kpi-open-reports">
          <span className="kpi-label">{t("admin.dashboard.kpiOpenReports")}</span>
          <span className="kpi-value">{data.open_reports}</span>
        </div>

        <div className="kpi-card kpi-card-triple" data-testid="kpi-status-counts">
          <span className="kpi-label">{t("admin.dashboard.kpiStatusCounts")}</span>
          <div className="triple-row">
            <div className="triple-cell">
              <span className="triple-value">{data.reports_by_status.submitted}</span>
              <span className="triple-label">{t("admin.dashboard.statusSubmitted")}</span>
            </div>
            <div className="triple-cell">
              <span className="triple-value">{data.reports_by_status.acknowledged}</span>
              <span className="triple-label">{t("admin.dashboard.statusAcknowledged")}</span>
            </div>
            <div className="triple-cell">
              <span className="triple-value">{data.reports_by_status.resolved}</span>
              <span className="triple-label">{t("admin.dashboard.statusResolved")}</span>
            </div>
          </div>
        </div>

        <div className="kpi-card" data-testid="kpi-ungrounded">
          <span className="kpi-label">{t("admin.dashboard.kpiUnanswered")}</span>
          <span className="kpi-value">{data.unanswered_open}</span>
        </div>

        <div className="kpi-card" data-testid="kpi-grounded-rate">
          <span className="kpi-label">{t("admin.dashboard.kpiCitationRate")}</span>
          <span className="kpi-value">{citationPct}</span>
        </div>

        {data.avg_comprehension != null && (
          <div className="kpi-card" data-testid="kpi-avg-comprehension">
            <span className="kpi-label">{t("admin.dashboard.kpiAvgComprehension")}</span>
            <span className="kpi-value">
              {Math.round(data.avg_comprehension)}
              {t("admin.dashboard.pointUnit")}
            </span>
          </div>
        )}

        {data.completion_rate && (
          <div className="kpi-card" data-testid="kpi-completion-rate">
            <span className="kpi-label">{t("admin.dashboard.kpiCompletionRate")}</span>
            <span className="kpi-value">
              {data.completion_rate.rate === null
                ? "—"
                : `${Math.round(data.completion_rate.rate * 100)}%`}
            </span>
          </div>
        )}
      </div>

      <section>
        <h2>{t("admin.dashboard.trendTitle")}</h2>
        <div className="trend-bars" data-testid="trend-chart">
          {data.reports_today_hourly.map((p) => (
            <div key={p.hour} className="trend-col">
              <div className="trend-bar" style={{ height: `${(p.count / maxTrend) * 100}px` }} />
              <span className="trend-val">{p.count}</span>
              <span className="trend-date">
                {new Date(p.hour).getHours()}
                {t("admin.dashboard.hourUnit")}
              </span>
            </div>
          ))}
        </div>
      </section>

      {(data.per_worker?.length || data.per_module?.length) && (
        <section className="secondary-section" data-testid="secondary-section">
          <p className="secondary-note">{t("admin.dashboard.secondaryNote")}</p>

          {!!data.per_worker?.length && (
            <>
              <h2>{t("admin.dashboard.perWorkerTitle")}</h2>
              <ul className="per-worker-list" data-testid="per-worker-list">
                {data.per_worker.map((w) => (
                  <li key={`${w.worker_id}-${w.quiz_set_id}`}>
                    <span className={`badge badge-label-${w.label}`}>{w.label}</span>
                    <span className="pw-name">
                      {t("admin.dashboard.workerLabel")} #{w.worker_id} · {t("admin.dashboard.setLabel")}{" "}
                      {w.quiz_set_id}
                    </span>
                    <span className="pw-score">
                      {w.score}
                      {t("admin.dashboard.pointUnit")}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {!!data.per_module?.length && (
            <>
              <h2>{t("admin.dashboard.perModuleTitle")}</h2>
              <ul className="per-module-list" data-testid="per-module-list">
                {data.per_module.map((m) => (
                  <li key={m.module}>
                    <span className="pm-name">{m.module}</span>
                    <div className="pm-bar-track">
                      <div className="pm-bar-fill" style={{ width: `${m.avg_score}%` }} />
                    </div>
                    <span className="pm-pct">
                      {m.avg_score}
                      {t("admin.dashboard.pointUnit")} ({m.n}
                      {t("admin.dashboard.peopleUnit")})
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}
    </div>
  );
}
