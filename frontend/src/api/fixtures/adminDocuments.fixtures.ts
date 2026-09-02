import type { DocumentCategory, DocumentListItem, DocumentUploadRequest, DocumentUploadResult } from "../types";

// 001 documents 테이블 category CHECK 그대로(76행) — docs/ms-m41: text 빈 값·category
// 밖은 422. mock도 동일 순서(category → text)로 재현한다.
const CATEGORY_VALUES: readonly DocumentCategory[] = ["process", "instruction", "safety", "equipment"];

// mock 저장소 — 모듈 상태(SPA 내부 라우팅으로만 이동해야 유지, AdminLayout 주석과 동일 전제).
// _pollsSeen/_textLen은 폴링 시뮬용 내부 필드 — DocumentListItem에는 없는 값이라 응답
// 직전에 벗겨낸다. wall-clock(Date.now() 델타) 대신 폴링 횟수로 진행시킨다 — 실행 환경의
// 타이머 지연/스로틀링에 흔들리지 않고 "폴링 1회 이상 관측 후 done" 동작을 결정적으로 재현.
interface MockDoc extends DocumentListItem {
  _pollsSeen: number;
  _textLen: number;
}

let nextId = 101;
let nextJobId = 5001;

const STORE: MockDoc[] = [
  {
    id: 1,
    title: "선반 작업 안전 수칙",
    category: "safety",
    origin: "seed",
    source: "seed:safety_lathe_1",
    created_at: "2026-08-20T09:00:00",
    chunk_count: 6,
    job_status: "done",
    _pollsSeen: 0,
    _textLen: 0,
  },
  {
    id: 2,
    title: "프레스 작업 표준",
    category: "instruction",
    origin: "seed",
    source: "seed:instruction_press_1",
    created_at: "2026-08-21T10:30:00",
    chunk_count: 4,
    job_status: "done",
    _pollsSeen: 0,
    _textLen: 0,
  },
];

// 업로드 직후 첫 조회(handleSubmit의 즉시 refresh())까지는 running, 그 다음 조회(5초
// 간격 폴링 1회차)에 done으로 전환 — 폴링이 실제로 동작해야만(2번째 listDocuments 호출)
// done이 보이게 하기 위함.
const POLLS_UNTIL_DONE = 2;

function strip(doc: MockDoc): DocumentListItem {
  const { _pollsSeen, _textLen, ...pub } = doc;
  void _pollsSeen;
  void _textLen;
  return pub;
}

export function uploadMock(body: DocumentUploadRequest): DocumentUploadResult {
  if (!(CATEGORY_VALUES as readonly string[]).includes(body.category)) {
    throw Object.assign(new Error(`category 는 ${JSON.stringify(CATEGORY_VALUES)} 중 하나여야 합니다`), {
      status: 422,
    });
  }
  if (!body.text || !body.text.trim()) {
    throw Object.assign(new Error("text 는 필수입니다"), { status: 422 });
  }

  const id = nextId++;
  const jobId = nextJobId++;
  STORE.unshift({
    id,
    title: body.title,
    category: body.category,
    origin: "upload",
    source: `upload:${body.filename}`,
    created_at: new Date().toISOString(),
    chunk_count: 0,
    job_status: "running",
    _pollsSeen: 0,
    _textLen: body.text.length,
  });
  return { id, job_id: jobId };
}

export function listMock(): DocumentListItem[] {
  for (const doc of STORE) {
    if (doc.job_status !== "running") continue;
    doc._pollsSeen += 1;
    if (doc._pollsSeen >= POLLS_UNTIL_DONE) {
      doc.job_status = "done";
      // 청킹 ≤800자 규칙(docs/ms-m41) 그대로 흉내 — 최소 1청크.
      doc.chunk_count = Math.max(1, Math.ceil(doc._textLen / 800));
    }
  }
  return STORE.map(strip);
}
