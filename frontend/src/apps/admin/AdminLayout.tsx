import { NavLink, Outlet } from "react-router-dom";
import "./AdminLayout.css";

const LINKS = [
  { to: "/admin/reports", label: "위험보고" },
  { to: "/admin/dashboard", label: "대시보드" },
  { to: "/admin/glossary", label: "승인큐" },
  { to: "/admin/events", label: "감사 로그" },
];

// SPA 내부 라우팅(Link)으로만 이동해야 mock 모듈 상태가 유지된다 — 실API 붙으면
// 상태가 서버 DB에 있어 무관해지지만, 지금은 이 nav가 mock 데모의 전제조건이다.
export default function AdminLayout() {
  return (
    <div className="admin-layout">
      <nav className="admin-nav" data-testid="admin-nav">
        {LINKS.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            className={({ isActive }) => (isActive ? "admin-nav-link active" : "admin-nav-link")}
          >
            {l.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
