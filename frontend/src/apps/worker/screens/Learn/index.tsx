import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useLang } from "../../../../i18n/LangContext";
import { getCards } from "../../../../api/learn";
import type { LearnCardsResponse } from "../../../../api/types";
import "./Learn.css";

type Module = "safety" | "learning";
type LoadStatus = "loading" | "loaded" | "error";

const MODULES: Module[] = ["safety", "learning"];
const MODULE_LABEL_KEY: Record<Module, string> = {
  safety: "worker.learn.moduleSafety",
  learning: "worker.learn.moduleLearning",
};

export default function LearnScreen() {
  const { lang, t } = useLang();
  const [module, setModule] = useState<Module>("safety");
  const [data, setData] = useState<LearnCardsResponse | null>(null);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");

  async function load() {
    setLoadStatus("loading");
    try {
      const res = await getCards(module, lang);
      setData(res);
      setLoadStatus("loaded");
    } catch {
      setLoadStatus("error");
    }
  }

  useEffect(() => {
    load();
    // module·lang이 바뀌면 서버가 다시 localize한 카드를 새로 받아야 한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module, lang]);

  return (
    <div className="learn-screen" data-testid="learn-screen">
      <h1>{t("worker.learn.title")}</h1>

      <div className="learn-module-tabs" role="tablist" data-testid="learn-module-tabs">
        {MODULES.map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={m === module}
            data-testid={`learn-module-${m}`}
            className={m === module ? "learn-module-tab active" : "learn-module-tab"}
            onClick={() => setModule(m)}
          >
            {t(MODULE_LABEL_KEY[m])}
          </button>
        ))}
      </div>

      {loadStatus === "loading" && <p>{t("worker.learn.loading")}</p>}

      {loadStatus === "error" && (
        <div className="learn-error" data-testid="learn-load-error">
          <p>{t("worker.learn.loadError")}</p>
          <button type="button" onClick={load}>
            {t("worker.learn.retry")}
          </button>
        </div>
      )}

      {loadStatus === "loaded" && data && data.cards.length === 0 && (
        <p data-testid="learn-empty">{t("worker.learn.empty")}</p>
      )}

      {loadStatus === "loaded" && data && data.cards.length > 0 && (
        <>
          <ul className="learn-card-list" data-testid="learn-card-list">
            {data.cards.map((card) => (
              <li
                key={card.id}
                className={
                  card.kind === "phrase" && card.high_risk ? "learn-card learn-card-high-risk" : "learn-card"
                }
                data-testid="learn-card"
              >
                {card.kind === "phrase" && card.high_risk && (
                  <span className="learn-high-risk-badge" data-testid="learn-high-risk-badge">
                    {t("worker.learn.highRisk")}
                  </span>
                )}
                <p className="learn-card-text">{card.text}</p>
                <p className="learn-card-text-ko">{card.text_ko}</p>
                {card.note_ko && (
                  <p className="learn-card-note" data-testid="learn-card-note">
                    {card.note_ko}
                  </p>
                )}
                {card.src && (
                  <p className="learn-card-src" data-testid="learn-card-src">
                    {t("worker.learn.srcLabel")}: {card.src}
                  </p>
                )}
              </li>
            ))}
          </ul>

          <div className="learn-quiz-cta">
            {data.quiz_set_id != null ? (
              <Link
                to={`/quiz?set_id=${data.quiz_set_id}`}
                className="learn-quiz-link"
                data-testid="learn-quiz-link"
              >
                {t("worker.learn.takeQuiz")}
              </Link>
            ) : (
              <>
                <button type="button" disabled data-testid="learn-quiz-pending-button">
                  {t("worker.learn.takeQuiz")}
                </button>
                <p className="learn-quiz-pending-note" data-testid="learn-quiz-pending">
                  {t("worker.learn.quizPending")}
                </p>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
