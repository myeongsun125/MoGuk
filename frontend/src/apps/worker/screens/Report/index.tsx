import { useState, type FormEvent } from "react";
import { useLang } from "../../../../i18n/LangContext";
import { confirmReport, submitReport } from "../../../../api/reports";
import type { ConfirmResponse, ConfirmResult, ReportSubmitResponse } from "../../../../api/types";
import "./Report.css";

type SubmitStatus = "idle" | "loading" | "error";
type ConfirmStatus = "idle" | "loading" | "done" | "error";

export default function ReportScreen() {
  const { lang, t } = useLang();
  const [text, setText] = useState("");
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [submitted, setSubmitted] = useState<ReportSubmitResponse | null>(null);
  const [confirmStatus, setConfirmStatus] = useState<ConfirmStatus>("idle");
  const [confirmResponse, setConfirmResponse] = useState<ConfirmResponse | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setStatus("loading");
    try {
      const res = await submitReport({ original_text: text, lang, source: "text" });
      setSubmitted(res);
      setConfirmStatus("idle");
      setConfirmResponse(null);
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  }

  async function handleConfirm(result: ConfirmResult) {
    if (!submitted) return;
    setConfirmStatus("loading");
    try {
      const res = await confirmReport(submitted.id, { result });
      setConfirmResponse(res);
      setConfirmStatus("done");
    } catch {
      setConfirmStatus("error");
    }
  }

  return (
    <div className="report-screen" data-testid="report-screen">
      <h1>{t("worker.report.title")}</h1>

      <form onSubmit={handleSubmit}>
        <textarea
          data-testid="report-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("worker.report.placeholder")}
        />
        <button data-testid="report-submit" type="submit" disabled={status === "loading"}>
          {status === "loading" ? t("worker.report.submitting") : t("worker.report.submit")}
        </button>
        {status === "error" && (
          <p className="error" data-testid="report-error">
            {t("worker.report.error")}
          </p>
        )}
      </form>

      {submitted && (
        <div className="report-submitted" data-testid="report-submitted">
          <p>
            {t("worker.report.acceptedLabel")}: #{submitted.id} ({submitted.status})
          </p>

          {confirmStatus !== "done" && (
            <div className="confirm-actions" data-testid="confirm-actions">
              <p>{t("worker.report.confirmPrompt")}</p>
              <button
                type="button"
                data-testid="confirm-yes"
                disabled={confirmStatus === "loading"}
                onClick={() => handleConfirm("confirmed")}
              >
                {t("worker.report.confirmYes")}
              </button>
              <button
                type="button"
                data-testid="confirm-no"
                disabled={confirmStatus === "loading"}
                onClick={() => handleConfirm("corrected")}
              >
                {t("worker.report.confirmNo")}
              </button>
              {confirmStatus === "error" && (
                <p className="error" data-testid="confirm-error">
                  {t("worker.report.confirmError")}
                </p>
              )}
            </div>
          )}

          {confirmStatus === "done" && confirmResponse?.result === "local_failed" && (
            <div className="confirm-failed" data-testid="confirm-failed">
              <p>{confirmResponse.message ?? t("worker.report.summaryFailed")}</p>
              {confirmResponse.original_text && (
                <p className="confirm-echo" data-testid="confirm-failed-echo">
                  {t("worker.report.echoLabel")}: {confirmResponse.original_text}
                </p>
              )}
            </div>
          )}

          {confirmStatus === "done" && confirmResponse && confirmResponse.result !== "local_failed" && (
            <p className="confirm-done" data-testid="confirm-done">
              {confirmResponse.result === "confirmed"
                ? t("worker.report.confirmedDone")
                : t("worker.report.correctedDone")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
