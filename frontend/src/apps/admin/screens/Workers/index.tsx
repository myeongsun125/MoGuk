import { useEffect, useRef, useState, type FormEvent } from "react";
import QRCode from "qrcode";
import { inviteWorker, sendInvite } from "../../../../api/adminWorkers";
import type { WorkerInviteLang, WorkerInviteResult } from "../../../../api/types";
import { useAdminLang } from "../../../../i18n/AdminLangContext";
import "./Workers.css";

type Status = "idle" | "loading" | "error";
type ErrorKind = "duplicate" | "invalid" | "generic";
type SendStatus = "idle" | "loading" | "error";

function errorStatus(e: unknown): number | undefined {
  return e && typeof e === "object" && "status" in e ? (e as { status?: number }).status : undefined;
}

export default function AdminWorkersScreen() {
  const { t } = useAdminLang();
  const [name, setName] = useState("");
  const [empNo, setEmpNo] = useState("");
  const [lang, setLang] = useState<WorkerInviteLang>("vi");
  // phone은 ④ 발송(카톡/문자) 연결 전까지 화면 상태로만 보관 — POST 본문에 절대 싣지 않는다
  // (backend InviteRequest는 {name,emp_no,lang} 3필드뿐, phone은 이 계약에 없음).
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorKind, setErrorKind] = useState<ErrorKind>("generic");
  const [result, setResult] = useState<WorkerInviteResult | null>(null);
  const [sendStatus, setSendStatus] = useState<SendStatus>("idle");
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!result || !canvasRef.current) return;
    QRCode.toCanvas(canvasRef.current, result.invite_url, { width: 220, margin: 1 }).catch((e) => {
      console.error("QR render failed", e);
    });
  }, [result]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // 완전 빈값은 input required가 막는다 — 공백만 있는 값 등은 여기서 걸러내지 않고
    // 그대로 보내 invites.py _validate(94-98)와 동일한 422 응답 경로를 실제로 타게 한다
    // (프론트에서 미리 막아버리면 422 분기가 죽은 코드가 된다).
    setStatus("loading");
    try {
      // ★본문은 반드시 이 3필드만 — phone 미포함. trim()도 하지 않는다(서버 판정 그대로 반영).
      const res = await inviteWorker({ name, emp_no: empNo, lang });
      setResult(res);
      setStatus("idle");
    } catch (err) {
      const s = errorStatus(err);
      setErrorKind(s === 409 ? "duplicate" : s === 422 ? "invalid" : "generic");
      setStatus("error");
    }
  }

  function handleReset() {
    setResult(null);
    setName("");
    setEmpNo("");
    setPhone("");
    setStatus("idle");
    setSendStatus("idle");
    setShareUrl(null);
    setCopied(false);
  }

  // ⑤ SB #87 파트1 확정: {channel:'kakao_link'} → {share_url}. worker_id는 파트2 전 실
  // 백엔드가 아직 안 채우므로 result.worker_id 없으면 버튼 자체가 disabled(아래 렌더).
  async function handleSendKakao() {
    if (!result?.worker_id) return;
    setSendStatus("loading");
    setCopied(false);
    setShareUrl(null);
    try {
      const { share_url } = await sendInvite(result.worker_id, "kakao_link");
      let nativeShared = false;
      if (typeof navigator.share === "function") {
        try {
          await navigator.share({ url: share_url });
          nativeShared = true;
        } catch (e) {
          // 사용자가 공유 시트를 취소한 것은 에러가 아니다 — 그대로 종료(클립보드 폴백 없음).
          if (e instanceof Error && e.name === "AbortError") {
            nativeShared = true;
          }
        }
      }
      if (!nativeShared) {
        // navigator.share 미지원이거나 취소가 아닌 사유로 실패 — 링크를 화면에 항상 노출하고
        // 클립보드 복사까지 시도한다(복사도 실패하면 노출된 텍스트로 수동 복사).
        setShareUrl(share_url);
        try {
          await navigator.clipboard.writeText(share_url);
          setCopied(true);
        } catch {
          // 복사 실패 — shareUrl 텍스트 노출만으로 수동 복사 유도.
        }
      }
      setSendStatus("idle");
    } catch {
      setSendStatus("error");
    }
  }

  function handleSaveImage() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const url = canvas.toDataURL("image/png");
    const a = document.createElement("a");
    a.href = url;
    a.download = `invite-qr-${empNo || "worker"}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  return (
    <div className="admin-workers" data-testid="admin-workers-screen">
      <h1>근로자 등록</h1>

      {!result && (
        <form className="invite-form" onSubmit={handleSubmit} data-testid="invite-form">
          <label>
            이름
            <input
              data-testid="invite-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("admin.workers.namePlaceholder")}
              required
            />
          </label>
          <label>
            사번
            <input
              data-testid="invite-emp-no"
              value={empNo}
              onChange={(e) => setEmpNo(e.target.value)}
              placeholder={t("admin.workers.empNoPlaceholder")}
              required
            />
          </label>
          <label>
            언어
            <select data-testid="invite-lang" value={lang} onChange={(e) => setLang(e.target.value as WorkerInviteLang)}>
              <option value="vi">Tiếng Việt</option>
              <option value="in">Bahasa Indonesia</option>
            </select>
          </label>
          <label>
            휴대폰 번호 <span className="hint">(발송 연결 전 임시 보관용, 서버 전송 안 함)</span>
            <input
              data-testid="invite-phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder={t("admin.workers.phonePlaceholder")}
            />
          </label>

          <button type="submit" data-testid="invite-submit" disabled={status === "loading"}>
            {status === "loading" ? t("admin.workers.submitting") : t("admin.workers.submit")}
          </button>

          {status === "error" && errorKind === "duplicate" && (
            <p className="error" data-testid="invite-error-duplicate">
              {t("admin.workers.errorDuplicate")}
            </p>
          )}
          {status === "error" && errorKind === "invalid" && (
            <p className="error" data-testid="invite-error-invalid">
              {t("admin.workers.errorInvalid")}
            </p>
          )}
          {status === "error" && errorKind === "generic" && (
            <p className="error" data-testid="invite-error-generic">
              {t("admin.workers.errorGeneric")}
            </p>
          )}
        </form>
      )}

      {result && (
        <div className="invite-result" data-testid="invite-result">
          <p className="invite-url" data-testid="invite-url">
            {result.invite_url}
          </p>

          <canvas ref={canvasRef} data-testid="invite-qr-canvas" />

          <div className="invite-actions">
            <button type="button" data-testid="invite-save-image" onClick={handleSaveImage}>
              이미지 저장
            </button>
            <button
              type="button"
              data-testid="invite-send"
              disabled={!result.worker_id || sendStatus === "loading"}
              onClick={handleSendKakao}
            >
              {sendStatus === "loading" ? t("admin.workers.submitting") : t("admin.workers.sendKakao")}
            </button>
          </div>

          {!result.worker_id && (
            <p className="hint" data-testid="send-no-worker-id">
              실백엔드가 아직 worker_id를 내려주지 않습니다(SB #87 파트2 예정) — 발급 응답에
              worker_id가 있어야 발송 버튼이 활성화됩니다.
            </p>
          )}
          {sendStatus === "error" && (
            <p className="error" data-testid="send-error">
              {t("admin.workers.sendError")}
            </p>
          )}
          {copied && (
            <p data-testid="send-copied">{t("admin.workers.sendCopied")}</p>
          )}
          {shareUrl && (
            <p className="share-url-text" data-testid="share-url-text">
              {shareUrl}
            </p>
          )}

          <button type="button" data-testid="invite-new" onClick={handleReset}>
            새 근로자 등록
          </button>
        </div>
      )}
    </div>
  );
}
