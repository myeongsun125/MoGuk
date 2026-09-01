import { useState, type FormEvent } from "react";
import { useLang } from "../../../../i18n/LangContext";
import { askQuestion } from "../../../../api/ask";
import type { AskResponse, AskSource } from "../../../../api/types";
import "./Ask.css";

type Status = "idle" | "loading" | "error";

type SourceGroup = {
  document_id: number;
  title: string;
  category: string;
  chunkIds: number[];
};

// 같은 document_id 청크를 1칩으로 묶는다 — ★dedup(버리기)이 아니라 표시 묶음이므로
// 청크 id는 chunkIds에 그대로 유지한다(현재는 title 속성 상세로 노출).
function groupSources(sources: AskSource[]): SourceGroup[] {
  const groups = new Map<number, SourceGroup>();
  for (const s of sources) {
    const g = groups.get(s.document_id);
    if (g) {
      g.chunkIds.push(s.chunk_id);
    } else {
      groups.set(s.document_id, { document_id: s.document_id, title: s.title, category: s.category, chunkIds: [s.chunk_id] });
    }
  }
  return Array.from(groups.values());
}

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
              groupSources(result.sources).map((g) => (
                <span
                  key={g.document_id}
                  className={g.category === "safety" ? "badge badge-safety" : "badge"}
                  data-testid="source-badge"
                  title={`${g.title} · ${g.category} (chunk ${g.chunkIds.join(", ")})`}
                >
                  {g.chunkIds.length > 1 ? `${g.title} ×${g.chunkIds.length}` : `${g.title} · ${g.category}`}
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
