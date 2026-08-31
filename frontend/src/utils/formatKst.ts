// Asia/Seoul(KST) 표시 전용 — 값 자체는 바꾸지 않고 렌더링만 바꾼다(D-7).
// 실API(admin_events·risk_reports)는 tz-aware timestamptz를 isoformat()해 오프셋을
// 포함한다("+00:00" 등) — 그 경우만 KST로 변환한다. mock(로컬 벽시계, 오프셋 없는
// 문자열 — dashboard/adminEvents fixtures 관례)은 이미 로컬(=KST 가정) 표기라 그대로 둔다.
// 오프셋 유무로 분기하지 않으면 mock 문자열을 "UTC로 잘못 해석해 재변환"하는 사고가 난다
// (이 프로젝트에서 이미 두 번 겪은 toISOString() 버그와 같은 계열).
const HAS_OFFSET = /(Z|[+-]\d{2}:\d{2})$/;

const KST_FORMATTER = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function formatKst(iso: string): string {
  if (!HAS_OFFSET.test(iso)) {
    return `${iso.replace("T", " ").slice(0, 19)} KST`;
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${KST_FORMATTER.format(date)} KST`;
}
