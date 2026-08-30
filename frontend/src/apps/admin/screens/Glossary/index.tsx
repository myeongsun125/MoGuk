import { useEffect, useState } from "react";
import { approveGlossary, listGlossary, rejectGlossary } from "../../../../api/glossary";
import type { GlossaryTerm } from "../../../../api/types";
import "./Glossary.css";

export default function AdminGlossaryScreen() {
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  async function handleReject(id: number) {
    await rejectGlossary(id);
    await refresh();
  }

  return (
    <div className="admin-glossary" data-testid="admin-glossary-screen">
      <h1>용어 승인큐</h1>
      <div className="pending-badge" data-testid="pending-count">
        승인 대기: {terms.length}건
      </div>

      {loading && <p>불러오는 중...</p>}
      {error && <p className="error">{error}</p>}

      <ul className="term-list" data-testid="term-list">
        {terms.map((t) => (
          <li key={t.id} className="term-row" data-testid="term-row" data-term-id={t.id}>
            <div className="term-main">
              <span className="term-ko">{t.term_ko}</span>
              <span className="term-tr">vi: {t.term_vi ?? "—"}</span>
              <span className="term-tr">in: {t.term_in ?? "—"}</span>
              {t.note && <span className="term-note">{t.note}</span>}
            </div>
            <div className="term-actions">
              <button data-testid="approve-btn" onClick={() => handleApprove(t.id)}>
                승인
              </button>
              <button data-testid="reject-btn" onClick={() => handleReject(t.id)}>
                반려
              </button>
            </div>
          </li>
        ))}
        {!loading && terms.length === 0 && <li className="term-empty">대기 중인 용어가 없습니다.</li>}
      </ul>
    </div>
  );
}
