import { NavLink, Outlet } from "react-router-dom";
import { useLang } from "../../i18n/LangContext";
import type { Lang } from "../../api/types";
import "./WorkerLayout.css";

// endonym(자기표기) 고정 상수 — 언어 자체 이름은 번역 대상이 아니라 i18n 불필요(#61).
const LANG_CODES: Lang[] = ["vi", "in", "ko"];
const LANG_ENDONYM: Record<Lang, string> = {
  vi: "Tiếng Việt",
  in: "Bahasa Indonesia",
  ko: "한국어",
};

// SPA 내부 라우팅(NavLink)으로만 이동 — AdminLayout과 동일 이유(mock 모듈 상태 유지, D-3).
export default function WorkerLayout() {
  const { t, lang, setLang } = useLang();

  return (
    <div className="worker-layout">
      <header className="worker-header" data-testid="worker-header">
        <div className="worker-lang-toggle" role="radiogroup" aria-label="language">
          {LANG_CODES.map((code) => (
            <button
              key={code}
              type="button"
              role="radio"
              aria-checked={code === lang}
              data-testid={`worker-lang-${code}`}
              className={code === lang ? "worker-lang-btn active" : "worker-lang-btn"}
              onClick={() => setLang(code)}
            >
              {LANG_ENDONYM[code]}
            </button>
          ))}
        </div>
      </header>
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
        <NavLink
          to="/quiz"
          data-testid="tab-quiz"
          className={({ isActive }) => (isActive ? "worker-tab active" : "worker-tab")}
        >
          {t("worker.nav.quiz")}
        </NavLink>
      </nav>
    </div>
  );
}
