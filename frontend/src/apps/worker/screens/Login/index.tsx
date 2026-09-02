import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useLang } from "../../../../i18n/LangContext";
import { useAuth } from "../../../../auth/AuthContext";
import { login } from "../../../../api/auth";
import type { Lang } from "../../../../api/types";
import "./Login.css";

const LANG_CODES: Lang[] = ["vi", "ko", "in"];
const LANG_KEY: Record<Lang, string> = {
  vi: "worker.login.langVi",
  ko: "worker.login.langKo",
  in: "worker.login.langIn",
};

export default function LoginScreen() {
  // lang은 useLang이 이미 저장값(getStoredLang()) 우선·없으면 기본 vi로 초기화해준다(SB a안,
  // LangContext.tsx 그대로) — 로그인 응답엔 lang이 없어서(SB 확정) 화면은 그 값을 그대로
  // 쓰고, 사용자가 칩으로 바꾸면 setLang이 저장값을 갱신한다(SB b안). 로그인 성공 후 별도
  // 처리 불필요 — 이미 반영된 lang이 그대로 유지된다.
  const { lang, setLang, t } = useLang();
  const { jwt, setToken } = useAuth();
  const [empNo, setEmpNo] = useState("");
  const [pin, setPin] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const navigate = useNavigate();

  if (jwt) {
    return <Navigate to="/ask" replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("loading");
    try {
      const res = await login(empNo, pin);
      setToken(res.jwt, res.refresh);
      navigate("/ask");
    } catch {
      // 계정 미존재·PIN 불일치를 구분하지 않는 단일 401(auth.py) — 안내도 단일 문구.
      setStatus("error");
    }
  }

  const canSubmit = empNo.trim() !== "" && pin.length >= 4 && status !== "loading";

  return (
    <div className="login-screen">
      <h1>{t("worker.login.title")}</h1>

      <div className="lang-select" role="radiogroup" aria-label={t("worker.login.langLabel")}>
        {LANG_CODES.map((code) => (
          <button
            key={code}
            type="button"
            role="radio"
            aria-checked={code === lang}
            data-testid={`login-lang-${code}`}
            className={code === lang ? "lang-btn active" : "lang-btn"}
            onClick={() => setLang(code)}
          >
            {t(LANG_KEY[code])}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit}>
        <label htmlFor="login-emp-no">{t("worker.login.empNoLabel")}</label>
        <input
          id="login-emp-no"
          data-testid="login-emp-no"
          value={empNo}
          onChange={(e) => setEmpNo(e.target.value)}
          placeholder={t("worker.login.empNoPlaceholder")}
          required
        />

        <label htmlFor="login-pin">{t("worker.login.pinLabel")}</label>
        <input
          id="login-pin"
          data-testid="login-pin"
          type="password"
          inputMode="numeric"
          placeholder={t("worker.login.pinPlaceholder")}
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          required
        />

        <button type="submit" data-testid="login-submit" disabled={!canSubmit}>
          {status === "loading" ? t("worker.login.loggingIn") : t("worker.login.submit")}
        </button>
        {status === "error" && (
          <p className="error" data-testid="login-invalid">
            {t("worker.login.invalidCreds")}
          </p>
        )}
      </form>
    </div>
  );
}
