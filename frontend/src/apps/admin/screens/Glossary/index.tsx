import { useEffect, useState } from "react";
import { approveGlossary, listGlossary, rejectGlossary } from "../../../../api/glossary";
import type { GlossaryTerm } from "../../../../api/types";
import { useAdminLang } from "../../../../i18n/AdminLangContext";
import "./Glossary.css";

export default function AdminGlossaryScreen() {
  const { t } = useAdminLang();
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejectDraftId, setRejectDraftId] = useState<number | null>(null);
  const [rejectNote, setRejectNote] = useState("");

  async function refresh() {
    setLoading(true);
    try {
      setTerms(await listGlossary("draft"));
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

  async function handleApprove(id: number) {
    await approveGlossary(id);
    await refresh();
  }

  function openRejectDraft(id: number) {
    setRejectDraftId(id);
    setRejectNote("");
  }

  function cancelRejectDraft() {
    setRejectDraftId(null);
    setRejectNote("");
  }

  async function submitReject(id: number) {
    await rejectGlossary(id, rejectNote.trim() || undefined);
    setRejectDraftId(null);
    setRejectNote("");
    await refresh();
  }

  return (
    <div className="admin-glossary" data-testid="admin-glossary-screen">
      <h1>{t("admin.glossary.title")}</h1>
      <div className="pending-badge" data-testid="pending-count">
        승인 대기: {terms.length}건
      </div>

      {loading && <p>불러오는 중...</p>}
      {error && <p className="error">{error}</p>}

      <ul className="term-list" data-testid="term-list">
        {terms.map((term) => (
          <li key={term.id} className="term-row" data-testid="term-row" data-term-id={term.id}>
            <div className="term-main">
              <span className="term-ko">{term.term_ko}</span>
              <span className="term-tr">vi: {term.term_vi ?? "—"}</span>
              <span className="term-tr">in: {term.term_in ?? "—"}</span>
              {term.note && <span className="term-note">{term.note}</span>}
            </div>
            <div className="term-actions">
              <button data-testid="approve-btn" onClick={() => handleApprove(term.id)}>
                승인
              </button>
              {rejectDraftId === term.id ? (
                <div className="reject-draft" data-testid="reject-draft">
                  <input
                    data-testid="reject-note-input"
                    placeholder={t("admin.glossary.rejectNotePlaceholder")}
                    value={rejectNote}
                    onChange={(e) => setRejectNote(e.target.value)}
                  />
                  <button data-testid="reject-confirm-btn" onClick={() => submitReject(term.id)}>
                    {t("admin.glossary.rejectConfirm")}
                  </button>
                  <button data-testid="reject-cancel-btn" onClick={cancelRejectDraft}>
                    {t("admin.glossary.rejectCancel")}
                  </button>
                </div>
              ) : (
                <button data-testid="reject-btn" onClick={() => openRejectDraft(term.id)}>
                  반려
                </button>
              )}
            </div>
          </li>
        ))}
        {!loading && terms.length === 0 && <li className="term-empty">대기 중인 용어가 없습니다.</li>}
      </ul>
    </div>
  );
}
