import type { SendInviteResult, WorkerInviteRequest, WorkerInviteResult } from "./types";
import { inviteMock, sendInviteMock } from "./fixtures/adminWorkers.fixtures";

// Mock 경계 (skeleton-v3 §7). glossary.ts·adminUnanswered.ts 구조 템플릿 — 어드민 API는
// IP 화이트리스트로 보호되어 Bearer를 붙이지 않는다.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

// 본문은 반드시 {name, emp_no, lang} 3필드만(types.ts WorkerInviteRequest 주석 참고) —
// phone은 이 함수 시그니처에 없다(호출부가 실수로도 실을 수 없게).
// 에러는 status를 Error에 실어 던진다(adminUnanswered.ts 관례와 동일) — 409(활성 워커
// 중복)·422(검증 실패)를 화면이 구분해 문구를 나눌 수 있게.
export async function inviteWorker(body: WorkerInviteRequest): Promise<WorkerInviteResult> {
  if (USE_MOCK) {
    await delay(150);
    return inviteMock(body);
  }
  const res = await fetch("/api/v1/admin/workers/invite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw Object.assign(new Error(`invite failed: ${res.status}`), { status: res.status });
  }
  return (await res.json()) as WorkerInviteResult;
}

// {id}=worker_id(경로), body {channel} — SB #87 파트1 확정. Bearer 미부착(invite와 동일).
// 에러는 status를 Error에 실어 던진다(inviteWorker와 동일 관례).
export async function sendInvite(
  workerId: number,
  channel: "kakao_link" = "kakao_link",
): Promise<SendInviteResult> {
  if (USE_MOCK) {
    await delay(150);
    return sendInviteMock(workerId, channel);
  }
  const res = await fetch(`/api/v1/admin/workers/${workerId}/send-invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel }),
  });
  if (!res.ok) {
    throw Object.assign(new Error(`send-invite failed: ${res.status}`), { status: res.status });
  }
  return (await res.json()) as SendInviteResult;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
