import { NavLink, Outlet } from "react-router-dom";
import { useLang } from "../../i18n/LangContext";
import "./WorkerLayout.css";

// SPA 내부 라우팅(NavLink)으로만 이동 — AdminLayout과 동일 이유(mock 모듈 상태 유지, D-3).
export default function WorkerLayout() {
  const { t } = useLang();

  return (
    <div className="worker-layout">
      <div className="worker-content">
        <Outlet />
      </div>
      <nav className="worker-tabbar" data-testid="worker-tabbar">
        <NavLink
          to="/ask"
          data-testid="tab-ask"
          className={({ isActive }) => (isActive ? "worker-tab active" : "worker-tab")}
        >
          {t("worker.nav.ask")}
        </NavLink>
        <NavLink
          to="/report"
          data-testid="tab-report"
          className={({ isActive }) => (isActive ? "worker-tab active" : "worker-tab")}
        >
          {t("worker.nav.report")}
        </NavLink>
      </nav>
    </div>
  );
}
