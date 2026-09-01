import type { UnansweredItem } from "../types";

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

// POST 응답 스키마 미확정(#74 스텁)이라 반환값은 갱신된 항목 자체 — 실API 착륙 후
// 실제 응답과 다르면 adminUnanswered.ts 소비부만 맞추면 된다(화면은 이 반환값을 쓰지 않는다).
export function answerMock(questionId: number, text: string): UnansweredItem | undefined {
  const u = store.find((x) => x.question_id === questionId);
  if (!u) return undefined;
  u.status = "answered";
  u.admin_answer = text;
  u.answered_at = new Date().toISOString();
  return u;
}
