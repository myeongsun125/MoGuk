import { useEffect, useRef, useState } from "react";
import { listDocuments, uploadDocument } from "../../../../api/adminDocuments";
import type { DocumentCategory, DocumentListItem } from "../../../../api/types";
import { useAdminLang } from "../../../../i18n/AdminLangContext";
import "./Documents.css";

type Status = "idle" | "loading" | "error";

// 001 documents 테이블 category CHECK(76행) 그대로 — mock 임시값 아님, 실 DB 제약값.
const CATEGORY_VALUES: DocumentCategory[] = ["process", "instruction", "safety", "equipment"];
const CATEGORY_KEY: Record<DocumentCategory, string> = {
  process: "admin.documents.categoryProcess",
  instruction: "admin.documents.categoryInstruction",
  safety: "admin.documents.categorySafety",
  equipment: "admin.documents.categoryEquipment",
};

// jobs.status CHECK(001) 그대로 — queued|running|done|failed.
const STATUS_KEY: Record<string, string> = {
  queued: "admin.documents.statusQueued",
  running: "admin.documents.statusRunning",
  done: "admin.documents.statusDone",
  failed: "admin.documents.statusFailed",
};

const POLL_INTERVAL_MS = 5000;

function errorStatus(e: unknown): number | undefined {
  return e && typeof e === "object" && "status" in e ? (e as { status?: number }).status : undefined;
}

function stripExtension(filename: string): string {
  const idx = filename.lastIndexOf(".");
  return idx > 0 ? filename.slice(0, idx) : filename;
}

function isPending(status: string): boolean {
  return status === "queued" || status === "running";
}

export default function AdminDocumentsScreen() {
  const { t } = useAdminLang();
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<DocumentCategory>(CATEGORY_VALUES[0]);
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<DocumentListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // 폴링 setInterval·마운트 StrictMode 이중 호출·제출 직후 refresh()가 겹칠 수 있다 —
  // 나중에 시작됐지만 먼저 응답한 요청이 이후 응답을 덮어쓰지 못하게 "최신 요청만 반영"
  // 가드(요청 시작 시점 시퀀스 번호, 응답 시점에 아직 최신인지 확인).
  const requestSeqRef = useRef(0);

  async function refresh() {
    const seq = ++requestSeqRef.current;
    try {
      const list = await listDocuments();
      if (seq !== requestSeqRef.current) return; // 더 최신 refresh()가 이미 나갔음 — 낡은 응답 폐기
      setItems(list);
      // 목록에 대기 중인 잡이 남아있는 동안만 폴링 유지 — 전부 done/failed면 정지.
      if (list.some((d) => isPending(d.job_status)) ) {
        startPolling();
      } else {
        stopPolling();
      }
    } catch (e) {
      if (seq === requestSeqRef.current) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (seq === requestSeqRef.current) {
        setListLoading(false);
      }
    }
  }

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(refresh, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  useEffect(() => {
    refresh();
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFilename(file.name);
    setTitle(stripExtension(file.name));
    const reader = new FileReader();
    reader.onload = () => {
      setText(typeof reader.result === "string" ? reader.result : "");
    };
    reader.readAsText(file);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setError(null);
    try {
      await uploadDocument({ title, category, text, filename });
      setStatus("idle");
      setTitle("");
      setText("");
      setFilename("");
      await refresh();
    } catch (err) {
      const s = errorStatus(err);
      setError(s === 422 ? t("admin.documents.errorInvalid") : t("admin.documents.errorGeneric"));
      setStatus("error");
    }
  }

  // .trim()으로 미리 막지 않는다 — 공백뿐인 파일 내용도 그대로 보내 서버의 text 빈 값
  // 422 경로를 실제로 타게 한다(Workers 화면 name 공백 관례와 동일, invites.py 대응).
  const canSubmit = title !== "" && text !== "" && filename !== "" && status !== "loading";

  return (
    <div className="admin-documents" data-testid="admin-documents-screen">
      <h1>문서 등록</h1>

      <form className="document-form" onSubmit={handleSubmit} data-testid="document-form">
        <label>
          파일 선택
          <input
            data-testid="document-file"
            type="file"
            accept=".md,.txt"
            onChange={handleFileChange}
          />
          <span className="hint">{t("admin.documents.fileHint")}</span>
        </label>

        <label>
          제목
          <input
            data-testid="document-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t("admin.documents.titlePlaceholder")}
          />
        </label>

        <label>
          분류
          <select
            data-testid="document-category"
            value={category}
            onChange={(e) => setCategory(e.target.value as DocumentCategory)}
          >
            {CATEGORY_VALUES.map((c) => (
              <option key={c} value={c}>
                {t(CATEGORY_KEY[c])}
              </option>
            ))}
          </select>
        </label>

        <button type="submit" data-testid="document-submit" disabled={!canSubmit}>
          {status === "loading" ? t("admin.documents.submitting") : t("admin.documents.submit")}
        </button>

        {status === "error" && error && (
          <p className="error" data-testid="document-error">
            {error}
          </p>
        )}
      </form>

      {listLoading && <p>불러오는 중...</p>}

      <div className="table-scroll">
        <table className="documents-table" data-testid="documents-table">
          <thead>
            <tr>
              <th>제목</th>
              <th>분류</th>
              <th>청크 수</th>
              <th>잡 상태</th>
            </tr>
          </thead>
          <tbody>
            {items.map((doc) => (
              <tr key={doc.id} data-testid="document-row" data-job-status={doc.job_status}>
                <td>{doc.title}</td>
                <td>{t(CATEGORY_KEY[doc.category as DocumentCategory] ?? "") || doc.category}</td>
                <td>{doc.chunk_count}</td>
                <td>
                  <span className={`badge badge-job-${doc.job_status}`}>
                    {t(STATUS_KEY[doc.job_status] ?? "") || doc.job_status}
                  </span>
                </td>
              </tr>
            ))}
            {!listLoading && items.length === 0 && (
              <tr>
                <td colSpan={4} className="empty-row">
                  등록된 문서가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
