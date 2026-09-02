import type { LearnCard, LearnCardsResponse, QuizItem, QuizSet, QuizSubmitResult, QuizTermHint } from "../types";

// §3 M-38 확정 계약(GET /learn/quiz/{set_id}?lang=) 시뮬레이션 — 서버가 lang 기준으로
// q·choices·term_hints를 이미 localize해 내려주는 동작을 mock에서 재현한다. 원본 문항
// 콘텐츠는 data/seed/quiz/quiz_learning_1.json·quiz_safety_1.json 그대로(ko+vi만 있음),
// in은 서버 폴백을 흉내내 ko 문구를 그대로 준다.
interface RawItem {
  id: number;
  q_ko: string;
  q_vi: string;
  choices_ko: string[];
  choices_vi: string[];
  answer_idx: number;
  // [term_ko, term_vi] 쌍 — in 요청 시에도 vi 대신 ko로 폴백(서버 책임 시뮬).
  terms: [string, string][];
}

function localizeItem(raw: RawItem, lang: string): QuizItem {
  const vi = lang === "vi";
  const term_hints: QuizTermHint[] = raw.terms.map(([term_ko, term_vi]) => ({
    term_ko,
    term_lang: vi ? term_vi : term_ko, // in은 vi 대역이 없어 ko로 폴백(서버 시뮬)
  }));
  return {
    id: raw.id,
    q: vi ? raw.q_vi : raw.q_ko,
    choices: vi ? raw.choices_vi : raw.choices_ko,
    term_hints,
  };
}

const LEARNING_ITEMS: RawItem[] = [
  {
    id: 1,
    q_ko: "선반에서 공작물을 척에 고정할 때 안전하게 작업하려면 척 조에서 얼마나 물려야 합니까?",
    q_vi: "Khi kẹp phôi vào mâm cặp máy tiện, phải kẹp sâu vào chấu cặp bao nhiêu để làm việc an toàn?",
    choices_ko: ["5 mm 이상", "10 mm 이상", "20 mm 이상", "50 mm 이상"],
    choices_vi: ["Từ 5 mm trở lên", "Từ 10 mm trở lên", "Từ 20 mm trở lên", "Từ 50 mm trở lên"],
    answer_idx: 2,
    terms: [["척", "mâm cặp"]],
  },
  {
    id: 2,
    q_ko: "바이트를 공구대에 고정할 때 바이트 날 끝의 높이는 어디에 맞춥니까?",
    q_vi: "Khi gá dao tiện lên đài dao, chiều cao mũi dao phải khớp với vị trí nào?",
    choices_ko: ["공작물의 중심", "공구대의 윗면", "베드의 높이", "심압대의 밑면"],
    choices_vi: ["Tâm phôi", "Mặt trên đài dao", "Độ cao băng máy", "Mặt dưới ụ động"],
    answer_idx: 0,
    terms: [
      ["바이트", "dao tiện"],
      ["심압대", "ụ động"],
    ],
  },
  {
    id: 3,
    q_ko: "프레스에서 다이하이트란 무엇입니까?",
    q_vi: "Trong máy dập, chiều cao khuôn (die height) là gì?",
    choices_ko: [
      "볼스터 상면부터 슬라이드 하면까지의 높이",
      "금형의 총중량",
      "슬라이드가 1행정에 움직이는 거리",
      "플라이휠의 지름",
    ],
    choices_vi: [
      "Chiều cao từ mặt trên bàn máy đến mặt dưới đầu trượt",
      "Tổng khối lượng khuôn",
      "Quãng đường đầu trượt di chuyển trong một hành trình",
      "Đường kính bánh đà",
    ],
    answer_idx: 0,
    terms: [["볼스터", "bàn máy"]],
  },
  {
    id: 4,
    q_ko: "광전자식 방호장치는 어떤 원리로 기계를 정지시킵니까?",
    q_vi: "Thiết bị bảo vệ quang điện dừng máy theo nguyên lý nào?",
    choices_ko: [
      "신체의 일부가 광선을 차단하면 급정지시킨다",
      "양손 버튼을 놓으면 정지시킨다",
      "가드가 열리면 정지시킨다",
      "발 스위치를 밟으면 정지시킨다",
    ],
    choices_vi: [
      "Dừng khẩn cấp khi một phần cơ thể chắn tia sáng",
      "Dừng khi buông nút hai tay",
      "Dừng khi tấm chắn mở ra",
      "Dừng khi đạp công tắc chân",
    ],
    answer_idx: 0,
    terms: [["광전자식 방호장치", "thiết bị bảo vệ quang điện"]],
  },
  {
    id: 5,
    q_ko: "프레스 양산 작업에서 발 스위치를 사용할 때 지켜야 하는 것은 무엇입니까?",
    q_vi: "Khi dùng công tắc chân trong sản xuất hàng loạt trên máy dập, phải tuân thủ điều gì?",
    choices_ko: ["1회마다 스위치에서 발을 뗀다", "발을 계속 올려 둔다", "두 발로 동시에 밟는다", "덮개를 떼어 낸다"],
    choices_vi: [
      "Nhấc chân khỏi công tắc sau mỗi lần dập",
      "Giữ chân trên công tắc liên tục",
      "Đạp bằng hai chân cùng lúc",
      "Tháo nắp che ra",
    ],
    answer_idx: 0,
    terms: [["발 스위치", "công tắc chân"]],
  },
];

const SAFETY_ITEMS: RawItem[] = [
  {
    id: 1,
    q_ko: "선반 작업에서 장갑에 대한 규정으로 옳은 것은 무엇입니까?",
    q_vi: "Quy định nào sau đây về găng tay khi làm việc trên máy tiện là đúng?",
    choices_ko: ["장갑 착용을 금한다", "반드시 면장갑을 낀다", "두꺼운 장갑만 낀다", "한 손만 낀다"],
    choices_vi: ["Cấm đeo găng tay", "Bắt buộc đeo găng vải", "Chỉ đeo găng dày", "Chỉ đeo một tay"],
    answer_idx: 0,
    terms: [["면장갑", "găng vải"]],
  },
  {
    id: 2,
    q_ko: "프레스 금형을 부착·해체·조정할 때 슬라이드가 갑자기 작동하는 위험을 막기 위해 반드시 사용해야 하는 것은 무엇입니까?",
    q_vi: "Khi lắp, tháo hoặc điều chỉnh khuôn máy dập, phải dùng gì để ngăn nguy cơ đầu trượt bất ngờ hoạt động?",
    choices_ko: ["안전블록", "발 스위치", "면장갑", "테이프"],
    choices_vi: ["Khối chèn an toàn", "Công tắc chân", "Găng vải", "Băng dính"],
    answer_idx: 0,
    terms: [["안전블록", "khối chèn an toàn"]],
  },
  {
    id: 3,
    q_ko: "정비·청소를 위해 기계의 운전을 정지한 뒤, 다른 사람이 기계를 운전하는 것을 막기 위한 조치는 무엇입니까?",
    q_vi: "Sau khi dừng máy để bảo dưỡng, vệ sinh, cần biện pháp gì để ngăn người khác vận hành máy?",
    choices_ko: [
      "기동장치에 잠금장치를 하고 열쇠를 별도 관리하거나 표지판을 설치한다",
      "기계 옆에 서서 지킨다",
      "전원을 켜 둔 채 빨리 끝낸다",
      "방호장치를 떼어 낸다",
    ],
    choices_vi: [
      "Khóa thiết bị khởi động, quản lý riêng chìa khóa hoặc đặt biển báo",
      "Đứng cạnh máy canh chừng",
      "Để nguồn bật và làm nhanh",
      "Tháo thiết bị bảo vệ ra",
    ],
    answer_idx: 0,
    terms: [["기동장치", "thiết bị khởi động"]],
  },
  {
    id: 4,
    q_ko: "선반에서 칩을 제거할 때 올바른 방법은 무엇입니까?",
    q_vi: "Cách đúng để loại bỏ phoi trên máy tiện là gì?",
    choices_ko: ["솔이나 갈고리, 에어 컴프레서를 사용한다", "맨손으로 잡아 뺀다", "면장갑을 끼고 턴다", "기계를 돌리면서 입으로 분다"],
    choices_vi: [
      "Dùng chổi, móc hoặc máy nén khí",
      "Dùng tay trần kéo ra",
      "Đeo găng vải rồi phủi",
      "Thổi bằng miệng khi máy đang chạy",
    ],
    answer_idx: 0,
    terms: [["칩", "phoi"]],
  },
  {
    id: 5,
    q_ko: "양수조작식 방호장치의 설명으로 옳은 것은 무엇입니까?",
    q_vi: "Mô tả nào về thiết bị bảo vệ điều khiển hai tay là đúng?",
    choices_ko: [
      "양손으로 동시에 조작해야 동작하고 한 손이라도 떼면 정지한다",
      "한 손으로 조작해도 동작한다",
      "버튼을 테이프로 고정하면 더 안전하다",
      "발로 조작하는 장치이다",
    ],
    choices_vi: [
      "Chỉ hoạt động khi thao tác đồng thời bằng hai tay và dừng khi buông một tay",
      "Vẫn hoạt động khi thao tác bằng một tay",
      "Dán băng dính cố định nút thì an toàn hơn",
      "Là thiết bị điều khiển bằng chân",
    ],
    answer_idx: 0,
    terms: [["양수조작식 방호장치", "thiết bị bảo vệ điều khiển hai tay"]],
  },
];

// set_id ↔ 시드 매핑은 mock 전용 임시값(1=learning_1, 2=safety_1) — 실경로는 서버가 결정.
// status: learning_1(draft, review_note 원문상 실제로도 draft)·safety_1(published, 라벨
// 배너 미노출 대조군 — 실seed는 둘 다 draft지만 배너 조건부 렌더 확인을 위해 mock에서 구분).
const QUIZ_SET_META: Record<number, { module: string; title: string; status: string; raw: RawItem[] }> = {
  1: { module: "learning", title: "선반·프레스 장비 이해", status: "draft", raw: LEARNING_ITEMS },
  2: { module: "safety", title: "선반·프레스 안전 수칙", status: "published", raw: SAFETY_ITEMS },
};
const ANSWER_KEY: Record<number, number[]> = {
  1: LEARNING_ITEMS.map((i) => i.answer_idx),
  2: SAFETY_ITEMS.map((i) => i.answer_idx),
};

export function getQuizSetMock(setId: number, lang: string): QuizSet {
  const meta = QUIZ_SET_META[setId];
  if (!meta) {
    return { set_id: setId, module: "", title: "", status: "unknown", items: [] };
  }
  return {
    set_id: setId,
    module: meta.module,
    title: meta.title,
    status: meta.status,
    items: meta.raw.map((raw) => localizeItem(raw, lang)),
  };
}

// tenant threshold 판정(M-01)은 백엔드 스텁이라 실값 없음 — mock은 정답률 기준 자체 판정으로
// 대체(60% 이상 통과, 3구간 라벨). label 값("red"|"yellow"|"green")은 SB 미확정 임시 정의
// (types.ts QuizSubmitResult 주석 참고) — 실계약 확정 시 이 판정 로직 전체가 서버로 넘어간다.
export function submitQuizMock(setId: number, answers: number[]): QuizSubmitResult {
  const key = ANSWER_KEY[setId] ?? [];
  const total = key.length || 1;
  const correct = key.reduce((acc, answerIdx, i) => acc + (answers[i] === answerIdx ? 1 : 0), 0);
  const score = Math.round((correct / total) * 100);
  const passed = score >= 60;
  const label = score >= 80 ? "green" : score >= 60 ? "yellow" : "red";
  return { score, passed, label };
}

// M-42 학습카드 mock — GET /learn/cards?module=&lang= (§3 확정, learn.py:27-29 백엔드 스텁이라
// mock 경계). vi/in 문구는 기계번역 draft — 원어민 검수 후속(커밋 메시지 명기).
interface RawPhrase {
  id: number;
  ko: string;
  vi: string;
  high_risk: boolean;
  note_ko?: string;
  src?: string;
}

// safety=phrase 10건 — 선반·프레스 안전수칙(퀴즈 SAFETY_ITEMS와 같은 소재 계열, 문항이
// 아니라 그대로 게시하는 경고 문구). note_ko/src는 일부만(방어 검증용 — 카드 3·6·9는 둘 다
// 없음, 카드 5·10은 note_ko만).
const SAFETY_PHRASES: RawPhrase[] = [
  {
    id: 1,
    ko: "선반 작업 중 장갑 착용을 금한다",
    vi: "Cấm đeo găng tay khi vận hành máy tiện",
    high_risk: true,
    note_ko: "회전체에 장갑이 말려 들어가는 사고 위험",
    src: "안전 수칙 3조",
  },
  {
    id: 2,
    ko: "프레스 금형을 부착·해체·조정할 때 안전블록을 사용한다",
    vi: "Dùng khối chèn an toàn khi lắp, tháo, điều chỉnh khuôn máy dập",
    high_risk: true,
    note_ko: "슬라이드 갑작스런 낙하·작동 방지",
    src: "안전 수칙 7조",
  },
  {
    id: 3,
    ko: "정비·청소 전 전원을 차단하고 잠금장치를 건다",
    vi: "Ngắt nguồn và khóa thiết bị trước khi bảo dưỡng, vệ sinh",
    high_risk: true,
  },
  {
    id: 4,
    ko: "칩은 맨손으로 만지지 않는다",
    vi: "Không dùng tay trần chạm vào phoi",
    high_risk: true,
    src: "안전 수칙 5조",
  },
  {
    id: 5,
    ko: "기계 회전 중에는 청소하지 않는다",
    vi: "Không vệ sinh khi máy đang quay",
    high_risk: true,
    note_ko: "회전부 접촉 시 즉시 중상 위험",
  },
  {
    id: 6,
    ko: "비상정지 버튼 위치를 작업 전 확인한다",
    vi: "Kiểm tra vị trí nút dừng khẩn cấp trước khi làm việc",
    high_risk: false,
  },
  {
    id: 7,
    ko: "작업장 통로에 물건을 적재하지 않는다",
    vi: "Không chất đồ vật trên lối đi trong xưởng",
    high_risk: false,
    src: "안전 수칙 12조",
  },
  {
    id: 8,
    ko: "인화성 물질 근처에서 화기를 사용하지 않는다",
    vi: "Không dùng lửa gần vật liệu dễ cháy",
    high_risk: true,
  },
  {
    id: 9,
    ko: "소음이 심한 구역에서는 귀마개를 착용한다",
    vi: "Đeo nút tai ở khu vực có tiếng ồn lớn",
    high_risk: false,
  },
  {
    id: 10,
    ko: "보호구 미착용 시 작업을 시작하지 않는다",
    vi: "Không bắt đầu làm việc nếu chưa mang đủ đồ bảo hộ",
    high_risk: false,
    note_ko: "보안경·안전화 등 기본 보호구 포함",
  },
];

// learning=term 용어집 — 퀴즈 term_hints와 같은 용어 풀이(척·바이트 등)를 카드로도 노출.
// high_risk는 term에서 항상 false(계약 그대로).
interface RawTerm {
  id: number;
  term_ko: string;
  term_vi: string;
  note_ko?: string;
}

const LEARNING_TERMS: RawTerm[] = [
  { id: 1, term_ko: "척", term_vi: "mâm cặp", note_ko: "공작물을 고정하는 선반의 회전 부품" },
  { id: 2, term_ko: "바이트", term_vi: "dao tiện", note_ko: "선반에서 절삭에 쓰이는 공구" },
  { id: 3, term_ko: "심압대", term_vi: "ụ động" },
  { id: 4, term_ko: "볼스터", term_vi: "bàn máy", note_ko: "프레스 하부의 금형 받침대" },
  { id: 5, term_ko: "광전자식 방호장치", term_vi: "thiết bị bảo vệ quang điện", note_ko: "광선 차단으로 기계를 급정지시키는 장치" },
  { id: 6, term_ko: "발 스위치", term_vi: "công tắc chân" },
  { id: 7, term_ko: "안전블록", term_vi: "khối chèn an toàn" },
  { id: 8, term_ko: "기동장치", term_vi: "thiết bị khởi động" },
];

function localizePhrase(raw: RawPhrase, lang: string): LearnCard {
  const vi = lang === "vi";
  return {
    id: raw.id,
    kind: "phrase",
    text: vi ? raw.vi : raw.ko, // in은 vi 대역이 없어 ko로 폴백(서버 폴백 시뮬 — Quiz mock과 동일 관례)
    text_ko: raw.ko,
    high_risk: raw.high_risk,
    ...(raw.note_ko ? { note_ko: raw.note_ko } : {}),
    ...(raw.src ? { src: raw.src } : {}),
  };
}

function localizeTerm(raw: RawTerm, lang: string): LearnCard {
  const vi = lang === "vi";
  return {
    id: raw.id,
    kind: "term",
    text: vi ? raw.term_vi : raw.term_ko,
    text_ko: raw.term_ko,
    high_risk: false, // 계약 그대로 — term은 항상 false
    ...(raw.note_ko ? { note_ko: raw.note_ko } : {}),
  };
}

export function getCardsMock(module: "safety" | "learning", lang: string): LearnCardsResponse {
  if (module === "safety") {
    return {
      module: "safety",
      quiz_set_id: null, // 안전문구 카드는 아직 연결된 퀴즈 세트 없음 — "퀴즈 준비 중" 케이스
      cards: SAFETY_PHRASES.map((raw) => localizePhrase(raw, lang)),
    };
  }
  return {
    module: "learning",
    quiz_set_id: 1, // QUIZ_SET_META[1]=learning_1과 동일 세트 — "퀴즈 풀기" 링크 있는 케이스
    cards: LEARNING_TERMS.map((raw) => localizeTerm(raw, lang)),
  };
}
