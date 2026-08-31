import { useEffect, useState } from "react";
import { getDashboard } from "../../../../api/dashboard";
import type { DashboardSummary } from "../../../../api/types";
import "./Dashboard.css";

export default function AdminDashboardScreen() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboard()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>불러오는 중...</p>;

  const maxTrend = Math.max(...data.reports_today_hourly.map((p) => p.count), 1);
  const citationPct =
    data.citation_rate.rate === null ? "—" : `${Math.round(data.citation_rate.rate * 100)}%`;

  return (
    <div className="admin-dashboard" data-testid="admin-dashboard-screen">
      <h1>대시보드</h1>

      <div className="kpi-grid" data-testid="kpi-grid">
        <div className="kpi-card kpi-card-alert" data-testid="kpi-open-reports">
          <span className="kpi-label">① 미확인 위험보고</span>
          <span className="kpi-value">{data.open_reports}</span>
        </div>

        <div className="kpi-card kpi-card-triple" data-testid="kpi-status-counts">
          <span className="kpi-label">② 위험보고 상태별</span>
          <div className="triple-row">
            <div className="triple-cell">
              <span className="triple-value">{data.reports_by_status.submitted}</span>
              <span className="triple-label">접수</span>
            </div>
            <div className="triple-cell">
              <span className="triple-value">{data.reports_by_status.acknowledged}</span>
              <span className="triple-label">확인됨</span>
            </div>
            <div className="triple-cell">
              <span className="triple-value">{data.reports_by_status.resolved}</span>
              <span className="triple-label">해결됨</span>
            </div>
          </div>
        </div>

        <div className="kpi-card" data-testid="kpi-ungrounded">
          <span className="kpi-label">③ 무근거 질의 대기</span>
          <span className="kpi-value">{data.unanswered_open}</span>
        </div>

        <div className="kpi-card" data-testid="kpi-grounded-rate">
          <span className="kpi-label">④ 근거 인용률</span>
          <span className="kpi-value">{citationPct}</span>
        </div>
      </div>

      <section>
        <h2>오늘 시간대별 보고 건수</h2>
        <div className="trend-bars" data-testid="trend-chart">
          {data.reports_today_hourly.map((p) => (
            <div key={p.hour} className="trend-col">
              <div className="trend-bar" style={{ height: `${(p.count / maxTrend) * 100}px` }} />
              <span className="trend-val">{p.count}</span>
              <span className="trend-date">{new Date(p.hour).getHours()}시</span>
            </div>
          ))}
        </div>
      </section>

      {(data.per_worker?.length || data.per_module?.length) && (
        <section className="secondary-section" data-testid="secondary-section">
          <p className="secondary-note">
            아래는 보조 지표입니다 — 퀴즈 실데이터 연동 전이라 mock 값입니다.
          </p>

          {!!data.per_worker?.length && (
            <>
              <h2>근로자별 이해도 (mock)</h2>
              <ul className="per-worker-list" data-testid="per-worker-list">
                {data.per_worker.map((w) => (
                  <li key={w.worker_id}>
                    <span className={`badge badge-label-${w.label}`}>{w.label}</span>
                    <span className="pw-name">{w.name}</span>
                    <span className="pw-score">{w.comprehension}점</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {!!data.per_module?.length && (
            <>
              <h2>모듈별 완주율 (mock)</h2>
              <ul className="per-module-list" data-testid="per-module-list">
                {data.per_module.map((m) => (
                  <li key={m.module}>
                    <span className="pm-name">{m.module}</span>
                    <div className="pm-bar-track">
                      <div className="pm-bar-fill" style={{ width: `${m.completion_rate}%` }} />
                    </div>
                    <span className="pm-pct">{m.completion_rate}%</span>
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
