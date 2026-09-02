import { NavLink, Outlet } from "react-router-dom";
import { AdminLangProvider, useAdminLang } from "../../i18n/AdminLangContext";
import type { Lang } from "../../api/types";
import "./AdminLayout.css";

// #100 후속 — 전 항목 labelKey로 통일(문서 등록만 아래 별도 append 그대로).
// 대시보드·감사 로그·근로자 등록은 화면 제목과 nav 텍스트가 동일해 #97 title 키를
// 그대로 재사용, 위험보고만 제목("위험보고 관리")과 nav 텍스트가 달라 전용 키 신규.
const LINKS: { to: string; label?: string; labelKey?: string }[] = [
  { to: "/admin/reports", labelKey: "admin.reports.nav" },
  { to: "/admin/dashboard", labelKey: "admin.dashboard.title" },
  { to: "/admin/glossary", labelKey: "admin.glossary.nav" },
  { to: "/admin/events", labelKey: "admin.auditlog.title" },
  { to: "/admin/unanswered", labelKey: "admin.unanswered.nav" },
  { to: "/admin/workers", labelKey: "admin.workers.title" },
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
  const { lang, setLang, t } = useAdminLang();
  // #100 후속으로 LINKS 6개 전부 labelKey — 문서 등록만 기존 방식(별도 append) 그대로.
  const links = [...LINKS, { to: "/admin/documents", label: t("admin.documents.nav") }];

  return (
    <div className="admin-layout">
      <div className="admin-header" data-testid="admin-header">
        <nav className="admin-nav" data-testid="admin-nav">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) => (isActive ? "admin-nav-link active" : "admin-nav-link")}
            >
              {l.labelKey ? t(l.labelKey) : l.label}
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
