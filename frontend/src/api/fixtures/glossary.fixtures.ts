import type { GlossaryTerm, GlossaryTransitionResult } from "../types";
import { appendEvent } from "./adminEvents.fixtures";

// approve/reject가 상태를 바꿔야 승인큐에서 항목이 빠지는 걸 mock으로 재현할 수 있어
// adminReports.fixtures 와 동일하게 모듈 내 mutable store로 둔다.
let store: GlossaryTerm[] = [
  {
    id: 1,
    term_ko: "방호장치",
    term_vi: "thiết bị bảo vệ",
    term_in: "perangkat pelindung",
    note: null,
    status: "draft",
    source_question_id: 101,
    approved_by: null,
    approved_at: null,
  },
  {
    id: 2,
    term_ko: "지게차",
    term_vi: "xe nâng",
    term_in: "forklift",
    note: null,
    status: "draft",
    source_question_id: 102,
    approved_by: null,
    approved_at: null,
  },
  {
    id: 3,
    term_ko: "연차",
    term_vi: "phép năm",
    term_in: "cuti tahunan",
    note: "정착지원 질의에서 반복 등장",
    status: "draft",
    source_question_id: 103,
    approved_by: null,
    approved_at: null,
  },
];

export function listMock(status: string): GlossaryTerm[] {
  return store.filter((t) => t.status === status);
}

export function approveMock(id: number): GlossaryTransitionResult | undefined {
  const t = store.find((x) => x.id === id);
  if (!t) return undefined;
  const from = t.status;
  t.status = "approved";
  t.approved_at = new Date().toISOString();
  appendEvent({
    actor: "admin:unauthenticated",
    target_type: "glossary", // approval.py:101 TARGET_GLOSSARY — "glossary_term" 아님(정정)
    target_id: id,
    action: "glossary_approved",
    from_state: from,
    to_state: "approved",
    detail: null, // _transition(...,None) — approve는 detail 없음(approval.py:157)
  });
  return { id: t.id, status: t.status };
}

export function rejectMock(id: number, note?: string): GlossaryTransitionResult | undefined {
  const t = store.find((x) => x.id === id);
  if (!t) return undefined;
  const from = t.status;
  t.status = "rejected";
  appendEvent({
    actor: "admin:unauthenticated",
    target_type: "glossary", // approval.py:101 TARGET_GLOSSARY — "glossary_term" 아님(정정)
    target_id: id,
    action: "glossary_rejected",
    from_state: from,
    to_state: "rejected",
    detail: note ?? null, // detail=note(approval.py:161-162) — 용어명 아님(정정)
  });
  return { id: t.id, status: t.status };
}
