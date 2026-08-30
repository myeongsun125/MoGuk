import type { AdminEvent } from "../types";

// M-08d 범용 감사 로그 mock — adminReports.fixtures(A)·glossary.fixtures(C) 양쪽이
// 실제 행위 시 여기 append 한다. 리허설 시나리오 ⑩("방금 수행한 승인·전이가 날짜별로
// 기록된 것 확인")을 mock 단계에서도 실제로 재현하기 위함 — 정적 목록이 아니다.
let seq = 1;
let store: AdminEvent[] = [];

// 로컬 벽시계 문자열 직접 구성 — toISOString()은 UTC로 바꿔버려서 화면의 날짜 필터
// (로컬 날짜 기준)와 어긋난다(dashboard.fixtures 의 동일 버그 참고).
function localTimestamp(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
  );
}

export function appendEvent(entry: Omit<AdminEvent, "id" | "created_at">): AdminEvent {
  const ev: AdminEvent = { id: seq++, created_at: localTimestamp(), ...entry };
  store = [ev, ...store]; // 최신 우선
  return ev;
}

// date: "YYYY-MM-DD" — 지정 시 해당 날짜(로컬 기준)만.
export function listEvents(date?: string): AdminEvent[] {
  if (!date) return store;
  return store.filter((ev) => ev.created_at.slice(0, 10) === date);
}
