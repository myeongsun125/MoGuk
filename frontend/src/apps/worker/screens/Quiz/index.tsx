import { useEffect, useState } from "react";
import { useLang } from "../../../../i18n/LangContext";
import { getQuizSet, submitQuiz } from "../../../../api/learn";
import type { QuizSet, QuizSubmitResult } from "../../../../api/types";
import "./Quiz.css";

// §3 M-38 확정 계약: GET /learn/quiz/{set_id}?lang=이 q·choices·term_hints를 이미
// localize해 내려준다 — 세트 선택 UI는 아직 없어 이 화면의 임시 고정값(mock 매핑,
// api/fixtures/learn.fixtures.ts QUIZ_SET_META[1]=learning_1).
const SET_ID = 1;

type LoadStatus = "loading" | "loaded" | "error";
type SubmitStatus = "idle" | "loading" | "error" | "done";

const LABEL_CLASS: Record<string, string> = {
  red: "badge-label-red",
  yellow: "badge-label-yellow",
  green: "badge-label-green",
};

export default function QuizScreen() {
  const { lang, t } = useLang();
  const [quizSet, setQuizSet] = useState<QuizSet | null>(null);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [submitStatus, setSubmitStatus] = useState<SubmitStatus>("idle");
  const [result, setResult] = useState<QuizSubmitResult | null>(null);

  async function load() {
    setLoadStatus("loading");
    try {
      const data = await getQuizSet(SET_ID, lang);
      setQuizSet(data);
      setAnswers(new Array(data.items.length).fill(null));
      setSubmitStatus("idle");
      setResult(null);
      setLoadStatus("loaded");
    } catch {
      setLoadStatus("error");
    }
  }

  useEffect(() => {
    load();
    // lang이 바뀌면 서버가 다시 localize한 문항을 새로 받아야 한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

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

      {loadStatus === "loaded" && quizSet && (
        <>
          {quizSet.status === "draft" && (
            <p className="quiz-draft-banner" data-testid="quiz-draft-banner">
              {t("worker.quiz.draftLabel")}
            </p>
          )}

          <ul className="quiz-item-list" data-testid="quiz-item-list">
            {quizSet.items.map((item, itemIdx) => (
              <li key={item.id} className="quiz-item" data-testid="quiz-item">
                <p className="quiz-question">{item.q}</p>
                <div className="quiz-choices" role="radiogroup">
                  {item.choices.map((choice, choiceIdx) => (
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
                {item.term_hints.length > 0 && (
                  <div className="quiz-term-hints" data-testid="quiz-term-hints">
                    {item.term_hints.map((hint, hintIdx) => (
                      <span key={hintIdx} className="term-hint-chip" data-testid="term-hint-chip">
                        {t("worker.quiz.termLabel")}: {hint.term_ko} → {hint.term_lang}
                      </span>
                    ))}
                  </div>
                )}
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
