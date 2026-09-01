import type { QuizItem, QuizSubmitResult } from "../types";

// data/seed/quiz/quiz_learning_1.json·quiz_safety_1.json 실물 구조·문구 그대로 전사
// (items[]만 — _meta는 화면이 쓰지 않아 옮기지 않음). GET 문항 경로가 SB 미확정이라
// set_id ↔ 시드 매핑은 이 파일의 가정(1=learning_1, 2=safety_1) — 실경로 확정되면
// 서버가 이 매핑을 대신하므로 여기 상수는 mock 전용으로만 남는다.
const QUIZ_LEARNING_1: QuizItem[] = [
  {
    q_ko: "선반에서 공작물을 척에 고정할 때 안전하게 작업하려면 척 조에서 얼마나 물려야 합니까?",
    q_vi: "Khi kẹp phôi vào mâm cặp máy tiện, phải kẹp sâu vào chấu cặp bao nhiêu để làm việc an toàn?",
    choices: ["5 mm 이상", "10 mm 이상", "20 mm 이상", "50 mm 이상"],
    choices_vi: ["Từ 5 mm trở lên", "Từ 10 mm trở lên", "Từ 20 mm trở lên", "Từ 50 mm trở lên"],
    answer_idx: 2,
    explain_ko: "공작물은 척 조에서 20 mm 이상 물려야 안전하게 작업할 수 있습니다. (선반 매뉴얼 §3.2)",
    source: "cnc_lathe_manual.md §3.2",
    src: "NCS-LATHE-2 p.32",
  },
  {
    q_ko: "바이트를 공구대에 고정할 때 바이트 날 끝의 높이는 어디에 맞춥니까?",
    q_vi: "Khi gá dao tiện lên đài dao, chiều cao mũi dao phải khớp với vị trí nào?",
    choices: ["공작물의 중심", "공구대의 윗면", "베드의 높이", "심압대의 밑면"],
    choices_vi: ["Tâm phôi", "Mặt trên đài dao", "Độ cao băng máy", "Mặt dưới ụ động"],
    answer_idx: 0,
    explain_ko:
      "받침판으로 바이트 날 끝을 공작물 중심과 일치시킵니다. 중심이 맞지 않으면 단면 가운데가 깎이지 않는 현상이 생깁니다. (선반 매뉴얼 §3.3)",
    source: "cnc_lathe_manual.md §3.3",
    src: "NCS-LATHE-2 p.30; NCS-LATHE-2 p.31",
  },
  {
    q_ko: "프레스에서 다이하이트란 무엇입니까?",
    q_vi: "Trong máy dập, chiều cao khuôn (die height) là gì?",
    choices: [
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
    explain_ko: "다이하이트는 슬라이드 조절이 최상 위치이고 하사점 상태에서 볼스터 상면부터 슬라이드 하면까지의 높이입니다. (프레스 매뉴얼 §1.2)",
    source: "press_manual.md §1.2",
    src: "KOSHA-PRESS-4 3.(1)(사)",
  },
  {
    q_ko: "광전자식 방호장치는 어떤 원리로 기계를 정지시킵니까?",
    q_vi: "Thiết bị bảo vệ quang điện dừng máy theo nguyên lý nào?",
    choices: [
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
    explain_ko: "광전자식 방호장치는 투광부·수광부·컨트롤 부분으로 구성되며, 신체의 일부가 광선을 차단하면 기계를 급정지시킵니다. (프레스 매뉴얼 §1.3)",
    source: "press_manual.md §1.3",
    src: "KOSHA-PRESS p.2",
    quote: "투광부, 수광부, 컨트롤 부분으로 구성된 것으로서 신체의 일부가 광선을 차단하면 기계를 급정지시키는 방호장치",
  },
  {
    q_ko: "프레스 양산 작업에서 발 스위치를 사용할 때 지켜야 하는 것은 무엇입니까?",
    q_vi: "Khi dùng công tắc chân trong sản xuất hàng loạt trên máy dập, phải tuân thủ điều gì?",
    choices: ["1회마다 스위치에서 발을 뗀다", "발을 계속 올려 둔다", "두 발로 동시에 밟는다", "덮개를 떼어 낸다"],
    choices_vi: [
      "Nhấc chân khỏi công tắc sau mỗi lần dập",
      "Giữ chân trên công tắc liên tục",
      "Đạp bằng hai chân cùng lúc",
      "Tháo nắp che ra",
    ],
    answer_idx: 0,
    explain_ko: "발 스위치를 사용할 때는 1회마다 스위치에서 발을 뗍니다. 발 조작용 페달은 덮개를 가진 것이어야 합니다. (프레스 매뉴얼 §3.4, §4.2)",
    source: "press_manual.md §3.4",
    src: "NCS-COMMON p.35; KOSHA-PRESS p.4",
    quote: "발 조작용 페달은 덮개를 가진 것이어야 하며, 발은 한쪽 방향에서만 접근 가능하고 페달은 미끄럼을 방지할 수 있는 구조",
  },
];

const QUIZ_SAFETY_1: QuizItem[] = [
  {
    q_ko: "선반 작업에서 장갑에 대한 규정으로 옳은 것은 무엇입니까?",
    q_vi: "Quy định nào sau đây về găng tay khi làm việc trên máy tiện là đúng?",
    choices: ["장갑 착용을 금한다", "반드시 면장갑을 낀다", "두꺼운 장갑만 낀다", "한 손만 낀다"],
    choices_vi: ["Cấm đeo găng tay", "Bắt buộc đeo găng vải", "Chỉ đeo găng dày", "Chỉ đeo một tay"],
    answer_idx: 0,
    explain_ko: "선반 작업에서는 장갑 착용을 금합니다. 손이 말릴 위험이 있는 면장갑 등은 사용 금지입니다. (선반 매뉴얼 §4.3)",
    source: "cnc_lathe_manual.md §4.3",
    src: "NCS-LATHE p.42; KOSHA-COMMON-1 p.6",
    quote: "손이 말릴 위험이 있는 면장갑 등의 사용 금지",
  },
  {
    q_ko: "프레스 금형을 부착·해체·조정할 때 슬라이드가 갑자기 작동하는 위험을 막기 위해 반드시 사용해야 하는 것은 무엇입니까?",
    q_vi: "Khi lắp, tháo hoặc điều chỉnh khuôn máy dập, phải dùng gì để ngăn nguy cơ đầu trượt bất ngờ hoạt động?",
    choices: ["안전블록", "발 스위치", "면장갑", "테이프"],
    choices_vi: ["Khối chèn an toàn", "Công tắc chân", "Găng vải", "Băng dính"],
    answer_idx: 0,
    explain_ko: "금형을 부착·해체 또는 조정하는 작업에서 근로자의 신체가 위험한계 내에 있는 경우 안전블록을 사용하여야 합니다. (프레스 매뉴얼 §4.3)",
    source: "press_manual.md §4.3",
    src: "LAW-KOSH-RULE 제104조; KOSHA-PRESS p.5",
    quote:
      "프레스 등의 금형을 부착·해체·조정 작업 시, 안전블록을 사용하는 등 필요한 조치를 실시하여 작업 근로자가 위험한계 내에 있는 경우 슬라이드 작동 등의 위험을 방지",
  },
  {
    q_ko: "정비·청소를 위해 기계의 운전을 정지한 뒤, 다른 사람이 기계를 운전하는 것을 막기 위한 조치는 무엇입니까?",
    q_vi: "Sau khi dừng máy để bảo dưỡng, vệ sinh, cần biện pháp gì để ngăn người khác vận hành máy?",
    choices: [
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
    explain_ko:
      "운전을 정지한 경우 기동장치에 잠금장치를 하고 그 열쇠를 별도 관리하거나 표지판을 설치하는 등 필요한 방호 조치를 합니다. (프레스 매뉴얼 §4.4, 선반 매뉴얼 §4.4)",
    source: "press_manual.md §4.4",
    src: "LAW-KOSH-RULE 제92조②; KOSHA-COMMON-1 p.4",
    quote: "정비·청소·수리 등의 작업 시 해당 기계의 운전을 정지한 후, 다른 사람이 기계를 운전하는 것을 방지하기 위해 기동장치에 잠금장치를 하고 표지판을 부착",
  },
  {
    q_ko: "선반에서 칩을 제거할 때 올바른 방법은 무엇입니까?",
    q_vi: "Cách đúng để loại bỏ phoi trên máy tiện là gì?",
    choices: ["솔이나 갈고리, 에어 컴프레서를 사용한다", "맨손으로 잡아 뺀다", "면장갑을 끼고 턴다", "기계를 돌리면서 입으로 분다"],
    choices_vi: [
      "Dùng chổi, móc hoặc máy nén khí",
      "Dùng tay trần kéo ra",
      "Đeo găng vải rồi phủi",
      "Thổi bằng miệng khi máy đang chạy",
    ],
    answer_idx: 0,
    explain_ko: "칩은 고열이 나고 날카로우므로 맨손으로 절대 잡아서는 안 되며, 솔이나 갈고리, 에어 컴프레서를 사용합니다. (선반 매뉴얼 §4.2)",
    source: "cnc_lathe_manual.md §4.2",
    src: "NCS-LATHE p.38",
  },
  {
    q_ko: "양수조작식 방호장치의 설명으로 옳은 것은 무엇입니까?",
    q_vi: "Mô tả nào về thiết bị bảo vệ điều khiển hai tay là đúng?",
    choices: [
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
    explain_ko:
      "양수조작식 방호장치는 양손으로 동시에 조작하지 않으면 기계가 동작하지 않으며, 한 손이라도 떼어내면 기계를 정지시킵니다. 버튼을 테이프로 고정하면 방호장치를 무효화하는 것입니다. (프레스 매뉴얼 §1.3, §4.2)",
    source: "press_manual.md §4.2",
    src: "KOSHA-PRESS p.2; LAW-KOSH-RULE 제103조③",
    quote: "양손으로 동시에 조작하지 않으면 기계가 동작하지 않으며, 한손이라도 떼어내면 기계를 정지시키는 방호장치",
  },
];

const QUIZ_SETS: Record<number, QuizItem[]> = {
  1: QUIZ_LEARNING_1,
  2: QUIZ_SAFETY_1,
};

export function listQuizItemsMock(setId: number): QuizItem[] {
  return QUIZ_SETS[setId] ?? [];
}

// tenant threshold 판정(M-01)은 백엔드 스텁이라 실값 없음 — mock은 정답률 기준 자체 판정으로
// 대체(60% 이상 통과, 3구간 라벨). label 값("red"|"yellow"|"green")은 SB 미확정 임시 정의
// (types.ts QuizSubmitResult 주석 참고) — 실계약 확정 시 이 판정 로직 전체가 서버로 넘어간다.
export function submitQuizMock(setId: number, answers: number[]): QuizSubmitResult {
  const items = listQuizItemsMock(setId);
  const total = items.length || 1;
  const correct = items.reduce((acc, item, i) => acc + (answers[i] === item.answer_idx ? 1 : 0), 0);
  const score = Math.round((correct / total) * 100);
  const passed = score >= 60;
  const label = score >= 80 ? "green" : score >= 60 ? "yellow" : "red";
  return { score, passed, label };
}
