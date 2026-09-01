import { useEffect, useState } from "react";
import { answerUnanswered, listUnanswered } from "../../../../api/adminUnanswered";
import type { UnansweredItem } from "../../../../api/types";
import { useAdminLang } from "../../../../i18n/AdminLangContext";
import { formatKst } from "../../../../utils/formatKst";
import "./Unanswered.css";

const STATUS_LABEL: Record<string, string> = {
  open: "대기",
  answered: "답변됨",
};

export default function AdminUnansweredScreen() {
  const { t } = useAdminLang();
  const [items, setItems] = useState<UnansweredItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [submittingId, setSubmittingId] = useState<number | null>(null);
  const [rowError, setRowError] = useState<Record<number, string>>({});

  // POST 응답 스키마 미확정(#74 스텁)이라 성공 여부만 보고 목록을 재조회한다 —
  // status=open 재조회가 진실원본이므로 방금 답변한 항목은 자연히 빠진다.
  async function refresh() {
    setLoading(true);
    try {
      setItems(await listUnanswered("open"));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleSubmit(item: UnansweredItem) {
    const text = (drafts[item.question_id] ?? "").trim();
    if (!text) return;
    setSubmittingId(item.question_id);
    setRowError((m) => ({ ...m, [item.question_id]: "" }));
    try {
      await answerUnanswered(item.question_id, text);
      setDrafts((d) => ({ ...d, [item.question_id]: "" }));
      await refresh();
    } catch {
      setRowError((m) => ({ ...m, [item.question_id]: t("admin.unanswered.answerError") }));
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <div className="admin-unanswered" data-testid="admin-unanswered-screen">
      <h1>무근거 질의 대기열</h1>
      <div className="pending-badge" data-testid="unanswered-count">
        대기 중: {items.length}건
      </div>

      {loading && <p>불러오는 중...</p>}
      {error && <p className="error">{error}</p>}

      <div className="table-scroll">
        <table className="unanswered-table" data-testid="unanswered-table">
          <thead>
            <tr>
              <th>질문</th>
              <th>언어</th>
              <th>등록일</th>
              <th>상태</th>
              <th>답변</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} data-testid="unanswered-row" data-question-id={item.question_id}>
                <td className="col-question">{item.question ?? "—"}</td>
                <td>{item.lang ?? "-"}</td>
                <td className="col-time">{formatKst(item.question_created_at)}</td>
                <td>{STATUS_LABEL[item.status] ?? item.status}</td>
                <td className="col-answer">
                  <div className="answer-form">
                    <textarea
                      data-testid="answer-input"
                      placeholder={t("admin.unanswered.answerPlaceholder")}
                      value={drafts[item.question_id] ?? ""}
                      onChange={(e) => setDrafts((d) => ({ ...d, [item.question_id]: e.target.value }))}
                      disabled={submittingId === item.question_id}
                    />
                    <button
                      type="button"
                      data-testid="answer-submit"
                      disabled={submittingId === item.question_id || !(drafts[item.question_id] ?? "").trim()}
                      onClick={() => handleSubmit(item)}
                    >
                      {submittingId === item.question_id
                        ? t("admin.unanswered.answerSubmitting")
                        : t("admin.unanswered.answerSubmit")}
                    </button>
                    {rowError[item.question_id] && (
                      <p className="error" data-testid="answer-error">
                        {rowError[item.question_id]}
                      </p>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={5} className="empty-row">
                  대기 중인 질문이 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
