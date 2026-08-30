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

  const maxTrend = Math.max(...data.weekly_trend.map((p) => p.avg_comprehension), 1);

  return (
    <div className="admin-dashboard" data-testid="admin-dashboard-screen">
      <h1>대시보드</h1>

      <div className="kpi-grid" data-testid="kpi-grid">
        <div className="kpi-card">
          <span className="kpi-label">등록 근로자</span>
          <span className="kpi-value">{data.workers}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">평균 이해도</span>
          <span className="kpi-value">{data.avg_comprehension}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">완주율</span>
          <span className="kpi-value">{data.completion_rate}%</span>
        </div>
        <div className="kpi-card kpi-card-alert" data-testid="kpi-open-reports">
          <span className="kpi-label">미확인 위험보고</span>
          <span className="kpi-value">{data.open_reports}</span>
        </div>
      </div>

      <section>
        <h2>주간 이해도 추이</h2>
        <div className="trend-bars" data-testid="trend-chart">
          {data.weekly_trend.map((p) => (
            <div key={p.date} className="trend-col">
              <div className="trend-bar" style={{ height: `${(p.avg_comprehension / maxTrend) * 100}px` }} />
              <span className="trend-val">{p.avg_comprehension}</span>
              <span className="trend-date">{p.date}</span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2>근로자별 이해도</h2>
        <ul className="per-worker-list" data-testid="per-worker-list">
          {data.per_worker.map((w) => (
            <li key={w.worker_id}>
              <span className={`badge badge-label-${w.label}`}>{w.label}</span>
              <span className="pw-name">{w.name}</span>
              <span className="pw-score">{w.comprehension}점</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>모듈별 완주율</h2>
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
      </section>
    </div>
  );
}
