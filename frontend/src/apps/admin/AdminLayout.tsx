import { NavLink, Outlet } from "react-router-dom";
import { AdminLangProvider, useAdminLang } from "../../i18n/AdminLangContext";
import type { Lang } from "../../api/types";
import "./AdminLayout.css";

const LINKS = [
  { to: "/admin/reports", label: "위험보고" },
  { to: "/admin/dashboard", label: "대시보드" },
  { to: "/admin/glossary", label: "승인큐" },
  { to: "/admin/events", label: "감사 로그" },
  { to: "/admin/unanswered", label: "무근거 질의" },
  { to: "/admin/workers", label: "근로자 등록" },
];

// endonym(자기표기) 고정 상수 — WorkerLayout과 동일 관례(#61). i18n 대상 아님.
const LANG_CODES: Lang[] = ["vi", "in", "ko"];
const LANG_ENDONYM: Record<Lang, string> = {
  vi: "Tiếng Việt",
  in: "Bahasa Indonesia",
  ko: "한국어",
};

// SPA 내부 라우팅(Link)으로만 이동해야 mock 모듈 상태가 유지된다 — 실API 붙으면
// 상태가 서버 DB에 있어 무관해지지만, 지금은 이 nav가 mock 데모의 전제조건이다.
function AdminLayoutInner() {
  const { lang, setLang } = useAdminLang();

  return (
    <div className="admin-layout">
      <div className="admin-header" data-testid="admin-header">
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
        <div className="admin-lang-toggle" role="radiogroup" aria-label="admin language">
          {LANG_CODES.map((code) => (
            <button
              key={code}
              type="button"
              role="radio"
              aria-checked={code === lang}
              data-testid={`admin-lang-${code}`}
              className={code === lang ? "admin-lang-btn active" : "admin-lang-btn"}
              onClick={() => setLang(code)}
            >
              {LANG_ENDONYM[code]}
            </button>
          ))}
        </div>
      </div>
      <Outlet />
    </div>
  );
}

// 관리자 로케일(moguk_admin_lang)은 워커 로케일(moguk_lang, i18n/LangContext)과 별개 —
// AdminLangProvider가 /admin 하위 라우트에만 스코프된다(#63).
export default function AdminLayout() {
  return (
    <AdminLangProvider>
      <AdminLayoutInner />
    </AdminLangProvider>
  );
}
