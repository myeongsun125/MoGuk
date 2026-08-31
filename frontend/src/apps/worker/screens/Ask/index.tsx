import { useState, type FormEvent } from "react";
import { useLang } from "../../../../i18n/LangContext";
import { askQuestion } from "../../../../api/ask";
import type { AskResponse } from "../../../../api/types";
import "./Ask.css";

type Status = "idle" | "loading" | "error";

export default function AskScreen() {
  const { lang, t } = useLang();
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<AskResponse | null>(null);

  async function submit(q: string) {
    setStatus("loading");
    try {
      const res = await askQuestion({ question: q, lang });
      setResult(res);
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setResult(null);
    submit(question);
  }

  return (
    <div className="ask-screen" data-testid="ask-screen">
      <h1>{t("worker.ask.title")}</h1>

      <form onSubmit={handleSubmit}>
        <input
          data-testid="ask-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={t("worker.ask.placeholder")}
        />
        <button data-testid="ask-submit" type="submit" disabled={status === "loading"}>
          {status === "loading" ? t("worker.ask.loading") : t("worker.ask.submit")}
        </button>
      </form>

      {status === "error" && (
        <div className="ask-error" data-testid="ask-error">
          <p>{t("worker.ask.error")}</p>
          <button type="button" onClick={() => submit(question)}>
            {t("worker.ask.retry")}
          </button>
        </div>
      )}

      {result && (
        <div className="ask-result" data-testid="ask-result">
          {result.verify.gated ? (
            <p className="gated" data-testid="ask-gated">
              {t("worker.ask.gatedMessage")}
            </p>
          ) : (
            <p className="answer" data-testid="ask-answer">
              {result.answer}
            </p>
          )}

          <div className="sources" data-testid="ask-sources">
            <span className="sources-label">{t("worker.ask.sourcesLabel")}</span>
            {result.sources.length === 0 ? (
              <span className="badge badge-none" data-testid="source-none">
                {t("worker.ask.noSources")}
              </span>
            ) : (
              result.sources.map((s) => (
                <span
                  key={`${s.document_id}-${s.chunk_id}`}
                  className={s.category === "safety" ? "badge badge-safety" : "badge"}
                  data-testid="source-badge"
                >
                  {s.title} · {s.category}
                </span>
              ))
            )}
          </div>

          <div className="trace-id" data-testid="ask-trace">
            {t("worker.ask.traceLabel")}: {result.trace_id}
          </div>
        </div>
      )}
    </div>
  );
}
