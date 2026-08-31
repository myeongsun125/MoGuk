import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useLang } from "../../../../i18n/LangContext";
import { useAuth } from "../../../../auth/AuthContext";
import { activate } from "../../../../api/auth";
import type { Lang } from "../../../../api/types";
import "./Invite.css";

const LANG_CODES: Lang[] = ["vi", "ko", "in"];
const LANG_KEY: Record<Lang, string> = {
  vi: "worker.invite.langVi",
  ko: "worker.invite.langKo",
  in: "worker.invite.langIn",
};

export default function InviteScreen() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const { lang, setLang, t } = useLang();
  const { jwt, setToken } = useAuth();
  const [pin, setPin] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setStatus("loading");
    try {
      const res = await activate(token, pin);
      setToken(res.jwt, res.refresh);
      if (res.lang) setLang(res.lang);
      navigate("/ask");
    } catch {
      setStatus("error");
    }
  }

  // 이미 유효 세션이 있으면(뒤로가기·새로고침) 재활성화 시도 대신 워커 홈으로 —
  // 1회용 초대 토큰을 재소진 시도하다 실패하는 것을 막는다(D-1).
  if (jwt) {
    return <Navigate to="/ask" replace />;
  }

  if (!token) {
    return (
      <div className="invite-screen">
        <p data-testid="invite-no-token">{t("worker.invite.tokenMissing")}</p>
      </div>
    );
  }

  return (
    <div className="invite-screen">
      <h1>{t("worker.invite.title")}</h1>

      <div className="lang-select" role="radiogroup" aria-label={t("worker.invite.langLabel")}>
        {LANG_CODES.map((code) => (
          <button
            key={code}
            type="button"
            role="radio"
            aria-checked={code === lang}
            className={code === lang ? "lang-btn active" : "lang-btn"}
            onClick={() => setLang(code)}
          >
            {t(LANG_KEY[code])}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit}>
        <label htmlFor="pin">{t("worker.invite.pinLabel")}</label>
        <input
          id="pin"
          type="password"
          inputMode="numeric"
          placeholder={t("worker.invite.pinPlaceholder")}
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          required
        />
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? t("worker.invite.activating") : t("worker.invite.submit")}
        </button>
        {status === "error" && <p className="error">{t("worker.invite.error")}</p>}
      </form>
    </div>
  );
}
