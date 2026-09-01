import type { AnswerResult, UnansweredItem } from "../types";
import { appendEvent } from "./adminEvents.fixtures";

// 답변 제출이 상태를 바꿔야 open 필터에서 항목이 빠지는 걸 mock으로 재현할 수 있어
// adminReports.fixtures·glossary.fixtures와 동일하게 모듈 내 mutable store로 둔다.
let store: UnansweredItem[] = [
  {
    id: 1,
    question_id: 201,
    status: "open",
    question: "연차는 언제부터 쓸 수 있나요?",
    lang: "vi",
    question_created_at: "2026-08-28T09:12:00",
    admin_answer: null,
    answered_at: null,
  },
  {
    id: 2,
    question_id: 202,
    status: "open",
    question: "기숙사 소화기 위치가 어디인가요?",
    lang: "in",
    question_created_at: "2026-08-29T14:03:00",
    admin_answer: null,
    answered_at: null,
  },
  {
    id: 3,
    question_id: 203,
    status: "answered",
    question: "야간 근무 수당은 얼마인가요?",
    lang: "vi",
    question_created_at: "2026-08-25T08:40:00",
    admin_answer: "야간(22시~06시) 근무는 통상임금의 50%를 가산합니다.",
    answered_at: "2026-08-26T10:00:00",
  },
];

// status: "open"(기본)|"answered"|undefined(전체) — approval.py list_unanswered와 동일 필터 규칙.
export function listMock(status?: string): UnansweredItem[] {
  if (!status) return store;
  return store.filter((u) => u.status === status);
}

let jobIdSeq = 5001; // jobs.id(serial) mock — 실DB 시퀀스와 축만 다를 뿐 unanswered.id와 무관.

// approval.py answer_unanswered(205-268)와 동일 규칙: 대상 없음 404·text 공백 422·
// open 아님(이미 answered) 422 — 각각 Error에 status를 실어 던진다(adminUnanswered.ts와 대칭).
export function answerMock(questionId: number, text: string): AnswerResult {
  const body = text.trim();
  const u = store.find((x) => x.question_id === questionId);
  if (!u) {
    throw Object.assign(new Error(`unanswered question not found: ${questionId}`), { status: 404 });
  }
  if (!body) {
    throw Object.assign(new Error("text 는 필수입니다 (공백 불가)"), { status: 422 });
  }
  if (u.status !== "open") {
    throw Object.assign(new Error(`${u.status} → answered 불가 (open 에서만)`), { status: 422 });
  }
  const from = u.status;
  u.status = "answered";
  u.admin_answer = body;
  u.answered_at = new Date().toISOString();
  // approval.py:246-259 admin_events.record와 동일 배선(target_type='unanswered',
  // action='unanswered_answered', target_id=question_id — queue id 아님) — AuditLog
  // 화면이 필터 없이 그대로 노출하는지 mock으로도 확인할 수 있게 parity 유지.
  appendEvent({
    actor: "admin:unauthenticated",
    target_type: "unanswered",
    target_id: questionId,
    action: "unanswered_answered",
    from_state: from,
    to_state: "answered",
    detail: JSON.stringify({ ingested_doc_id: null, text_len: body.length }),
  });
  return { id: u.id, status: "answered", answered_at: u.answered_at, ingest_job_id: jobIdSeq++ };
}
