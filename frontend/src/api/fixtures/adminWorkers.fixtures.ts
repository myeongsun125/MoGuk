import type { WorkerInviteRequest, WorkerInviteResult } from "../types";
import { appendEvent } from "./adminEvents.fixtures";

// invites.py:88-98 _validate와 동일 순서(emp_no → name → lang) + :118 WorkerAlreadyActive —
// emp_no="EMP-ACTIVE"는 이미 활성화된 워커로 미리 심어 409 케이스를 결정적으로 재현한다.
const activeEmpNos = new Set<string>(["EMP-ACTIVE"]);
const LANG_VALUES = ["vi", "in"] as const;

let workerIdSeq = 9001;
let tokenSeq = 1;

export function inviteMock(body: WorkerInviteRequest): WorkerInviteResult {
  const empNo = (body.emp_no ?? "").trim();
  const name = (body.name ?? "").trim();
  if (!empNo) {
    throw Object.assign(new Error("emp_no 는 필수입니다"), { status: 422 });
  }
  if (!name) {
    throw Object.assign(new Error("name 은 필수입니다"), { status: 422 });
  }
  if (!(LANG_VALUES as readonly string[]).includes(body.lang)) {
    throw Object.assign(new Error(`lang 은 ${JSON.stringify(LANG_VALUES)} 중 하나여야 합니다`), { status: 422 });
  }
  if (activeEmpNos.has(empNo)) {
    throw Object.assign(new Error(`emp_no=${empNo} 는 이미 활성화된 워커입니다`), { status: 409 });
  }

  const workerId = workerIdSeq++;
  const token = `mock-invite-token-${tokenSeq++}`;
  // invites.py:56 build_invite_url(token) 형태 그대로("{BASE_URL}/activate?token=") — mock은
  // 현재 origin을 BASE_URL 대용으로 써서 QA 로컬 환경에서도 QR이 실제로 스캔 가능하게 한다.
  const inviteUrl = `${window.location.origin}/activate?token=${token}`;

  // invites.py:126-131 admin_events.record와 동일 배선(target_type='worker',
  // action='worker_invited', detail=emp_no) — AuditLog mock 검증 parity.
  appendEvent({
    actor: "admin:unauthenticated",
    target_type: "worker",
    target_id: workerId,
    action: "worker_invited",
    from_state: null,
    to_state: null,
    detail: empNo,
  });

  return { invite_url: inviteUrl };
}
