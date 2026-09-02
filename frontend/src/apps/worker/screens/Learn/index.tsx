import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
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

function isModule(value: string | null): value is Module {
  return value === "safety" || value === "learning";
}

export default function LearnScreen() {
  const { lang, t } = useLang();
  // #94 보강 — /learn?module=safety|learning 쿼리로 초기 선택 모듈을 지정할 수 있다
  // (Quiz 화면의 "다시 학습" 링크가 사용). 없거나 잘못된 값이면 기존 기본(safety) 그대로.
  // 최초 렌더 시점의 값만 반영 — 이후 탭 클릭으로 자유롭게 전환되는 기존 동작은 무변경.
  const [searchParams] = useSearchParams();
  const moduleParam = searchParams.get("module");
  const [module, setModule] = useState<Module>(isModule(moduleParam) ? moduleParam : "safety");
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

          {/* #94 추가(총괄 승인 0902) — quiz_set_id 없으면 버튼 영역 자체를 렌더하지 않는다
              (이전엔 비활성 버튼+안내 문구였음, 렌더 안 함으로 변경). */}
          {data.quiz_set_id != null && (
            <div className="learn-quiz-cta">
              <Link
                to={`/quiz?set_id=${data.quiz_set_id}`}
                className="learn-quiz-link"
                data-testid="learn-quiz-link"
              >
                {t("worker.learn.takeQuiz")}
              </Link>
            </div>
          )}
        </>
      )}
    </div>
  );
}
