import { useEffect, useRef, useState, type FormEvent } from "react";
import QRCode from "qrcode";
import { inviteWorker } from "../../../../api/adminWorkers";
import type { WorkerInviteLang, WorkerInviteResult } from "../../../../api/types";
import { useAdminLang } from "../../../../i18n/AdminLangContext";
import "./Workers.css";

type Status = "idle" | "loading" | "error";
type ErrorKind = "duplicate" | "invalid" | "generic";

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
            <button type="button" data-testid="invite-send" disabled title={t("admin.workers.sendComingSoon")}>
              카톡/문자로 보내기
            </button>
          </div>
          <p className="hint">{t("admin.workers.sendComingSoon")}</p>

          <button type="button" data-testid="invite-new" onClick={handleReset}>
            새 근로자 등록
          </button>
        </div>
      )}
    </div>
  );
}
