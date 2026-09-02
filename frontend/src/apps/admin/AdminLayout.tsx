import { NavLink, Outlet } from "react-router-dom";
import { AdminLangProvider, useAdminLang } from "../../i18n/AdminLangContext";
import type { Lang } from "../../api/types";
import "./AdminLayout.css";

// labelKey가 있으면 i18n 배선 대상(7차: 승인큐·무근거 질의) — 나머지는 스코프 밖 무접촉.
const LINKS: { to: string; label?: string; labelKey?: string }[] = [
  { to: "/admin/reports", label: "위험보고" },
  { to: "/admin/dashboard", label: "대시보드" },
  { to: "/admin/glossary", labelKey: "admin.glossary.nav" },
  { to: "/admin/events", label: "감사 로그" },
  { to: "/admin/unanswered", labelKey: "admin.unanswered.nav" },
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
  const { lang, setLang, t } = useAdminLang();
  // ①(M-41) 문서 등록 + 7차(승인큐·무근거 질의)만 i18n 키로 — 나머지 3개는 스코프 밖(무접촉).
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
