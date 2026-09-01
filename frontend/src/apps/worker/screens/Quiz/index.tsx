import { useEffect, useState } from "react";
import { useLang } from "../../../../i18n/LangContext";
import { getQuizItems, submitQuiz } from "../../../../api/learn";
import type { QuizItem, QuizSubmitResult } from "../../../../api/types";
import "./Quiz.css";

// GET 문항 경로가 SB 미확정이라 set_id는 이 화면의 임시 고정값(mock 매핑,
// api/fixtures/learn.fixtures.ts QUIZ_SETS[1]=learning_1) — 실경로 확정되면
// 세트 선택 UI(모듈별 목록 등)로 대체될 수 있다.
const SET_ID = 1;

type LoadStatus = "loading" | "loaded" | "error";
type SubmitStatus = "idle" | "loading" | "error" | "done";

const LABEL_CLASS: Record<string, string> = {
  red: "badge-label-red",
  yellow: "badge-label-yellow",
  green: "badge-label-green",
};

// q_in·choices_in 시드 콘텐츠가 없다(★vi만 있음) — in은 ko로 폴백한다.
// TODO(MS): in 퀴즈 콘텐츠 시드 부재
function pickQuestion(item: QuizItem, lang: string): string {
  return lang === "vi" ? item.q_vi : item.q_ko;
}
function pickChoices(item: QuizItem, lang: string): string[] {
  return lang === "vi" ? item.choices_vi : item.choices;
}

export default function QuizScreen() {
  const { lang, t } = useLang();
  const [items, setItems] = useState<QuizItem[]>([]);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [submitStatus, setSubmitStatus] = useState<SubmitStatus>("idle");
  const [result, setResult] = useState<QuizSubmitResult | null>(null);

  async function load() {
    setLoadStatus("loading");
    try {
      const data = await getQuizItems(SET_ID);
      setItems(data);
      setAnswers(new Array(data.length).fill(null));
      setLoadStatus("loaded");
    } catch {
      setLoadStatus("error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectAnswer(itemIdx: number, choiceIdx: number) {
    setAnswers((a) => a.map((v, i) => (i === itemIdx ? choiceIdx : v)));
  }

  async function handleSubmit() {
    setSubmitStatus("loading");
    try {
      // 미응답 문항은 -1(어떤 choice와도 매칭되지 않는 값)로 채워 서버가 오답으로만 처리하게 한다.
      const res = await submitQuiz(SET_ID, answers.map((a) => a ?? -1));
      setResult(res);
      setSubmitStatus("done");
    } catch {
      setSubmitStatus("error");
    }
  }

  const allAnswered = answers.length > 0 && answers.every((a) => a !== null);

  return (
    <div className="quiz-screen" data-testid="quiz-screen">
      <h1>{t("worker.quiz.title")}</h1>

      {loadStatus === "loading" && <p>{t("worker.quiz.loadingItems")}</p>}

      {loadStatus === "error" && (
        <div className="quiz-error" data-testid="quiz-load-error">
          <p>{t("worker.quiz.loadError")}</p>
          <button type="button" onClick={load}>
            {t("worker.quiz.retry")}
          </button>
        </div>
      )}

      {loadStatus === "loaded" && (
        <>
          <ul className="quiz-item-list" data-testid="quiz-item-list">
            {items.map((item, itemIdx) => (
              <li key={itemIdx} className="quiz-item" data-testid="quiz-item">
                <div className="quiz-item-head">
                  <p className="quiz-question">{pickQuestion(item, lang)}</p>
                  {/* 용어 힌트 — 자리만, 데이터 연결은 후속 */}
                  <button type="button" className="term-hint" data-testid="term-hint" disabled>
                    {t("worker.quiz.termHint")} ({t("worker.quiz.termHintComingSoon")})
                  </button>
                </div>
                <div className="quiz-choices" role="radiogroup">
                  {pickChoices(item, lang).map((choice, choiceIdx) => (
                    <label key={choiceIdx} className="quiz-choice">
                      <input
                        type="radio"
                        name={`quiz-item-${itemIdx}`}
                        data-testid={`quiz-choice-${itemIdx}-${choiceIdx}`}
                        checked={answers[itemIdx] === choiceIdx}
                        onChange={() => selectAnswer(itemIdx, choiceIdx)}
                        disabled={submitStatus === "loading" || submitStatus === "done"}
                      />
                      {choice}
                    </label>
                  ))}
                </div>
              </li>
            ))}
          </ul>

          {submitStatus !== "done" && (
            <button
              type="button"
              data-testid="quiz-submit"
              disabled={!allAnswered || submitStatus === "loading"}
              onClick={handleSubmit}
            >
              {submitStatus === "loading" ? t("worker.quiz.submitting") : t("worker.quiz.submit")}
            </button>
          )}

          {submitStatus === "error" && (
            <p className="error" data-testid="quiz-submit-error">
              {t("worker.quiz.submitError")}
            </p>
          )}

          {submitStatus === "done" && result && (
            <div className="quiz-result" data-testid="quiz-result">
              <h2>{t("worker.quiz.resultTitle")}</h2>
              <p>
                {t("worker.quiz.scoreLabel")}: {result.score}
              </p>
              <span
                className={`badge ${LABEL_CLASS[result.label] ?? "badge-label-neutral"}`}
                data-testid="quiz-result-label"
              >
                {result.label}
              </span>
              <p className={result.passed ? "quiz-passed" : "quiz-failed"} data-testid="quiz-result-status">
                {result.passed ? t("worker.quiz.passed") : t("worker.quiz.failed")}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
