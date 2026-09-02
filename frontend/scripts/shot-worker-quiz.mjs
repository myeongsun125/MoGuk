import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-worker-quiz.png");
const PORT = 5196;
const VIEWPORT = { width: 390, height: 900 };

// quiz_learning_1 5문항의 정답 인덱스(learn.fixtures.ts LEARNING_ITEMS와 동일 순서) —
// 3색 라벨(green/yellow/red)을 결정적으로 재현하려고 정답 개수를 고정한다.
const ANSWER_IDX = [2, 0, 0, 0, 0];

async function activate(page) {
  await page.goto(`http://localhost:${PORT}/activate?token=t1`);
  const pinInput = page.locator("#pin");
  if (await pinInput.count()) {
    await pinInput.fill("1234");
    await page.locator('form button[type="submit"]').click();
  }
  await page.waitForURL(/\/ask/, { timeout: 5000 }).catch(() => {});
  // 기본 lang=vi라 결과 문구가 베트남어로 뜬다 — 이 스크립트의 문자열 비교는 ko 기준이므로
  // 헤더 토글로 ko로 바꿔둔다(워커 lang 전환 자체는 #61 기존 기능, 회귀 아님).
  await page.locator('[data-testid="worker-lang-ko"]').click();
}

async function runQuiz(page, correctCount, label) {
  await page.locator('[data-testid="tab-quiz"]').click();
  await page.getByTestId("quiz-item").first().waitFor({ state: "visible", timeout: 5000 });

  const items = await page.getByTestId("quiz-item").count();
  if (items !== ANSWER_IDX.length) {
    throw new Error(`expected ${ANSWER_IDX.length} quiz items, got ${items}`);
  }

  for (let i = 0; i < items; i++) {
    const choiceIdx = i < correctCount ? ANSWER_IDX[i] : (ANSWER_IDX[i] + 1) % 4; // 오답으로 강제
    await page.getByTestId(`quiz-choice-${i}-${choiceIdx}`).check();
  }

  const submit = page.getByTestId("quiz-submit");
  if (await submit.isDisabled()) {
    throw new Error("submit stayed disabled after answering all items");
  }
  await submit.click();
  await page.getByTestId("quiz-result").waitFor({ state: "visible", timeout: 5000 });

  const score = await page.getByTestId("quiz-result").textContent();
  const resultLabel = await page.getByTestId("quiz-result-label").textContent();
  const resultStatus = await page.getByTestId("quiz-result-status").textContent();
  console.log(`[${label}] result text:`, score?.replace(/\s+/g, " ").trim());
  console.log(`[${label}] label=${resultLabel} status=${resultStatus}`);
  if (resultLabel !== label) {
    throw new Error(`expected label=${label}, got ${resultLabel}`);
  }
  const retryLearnVisible = await page.getByTestId("quiz-retry-learn").isVisible().catch(() => false);
  return { resultLabel, resultStatus, retryLearnVisible };
}

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  let failures = 0;

  // green(5/5=100%, passed) — 첫 페이지에서 활성화 후 그대로 스크린샷용으로 남긴다.
  const page = await browser.newPage({ viewport: VIEWPORT });
  await activate(page);
  try {
    const r = await runQuiz(page, 5, "green");
    if (r.resultStatus !== "통과") throw new Error(`expected passed, got ${r.resultStatus}`);
    if (r.retryLearnVisible) throw new Error("passed=true인데 '다시 학습' 링크가 렌더됨");
    console.log("PASS: 5/5 -> green + 통과, 다시 학습 링크 미표시");
  } catch (e) {
    console.error("FAIL:", e.message);
    failures++;
  }
  await page.screenshot({ path: OUT_PNG, fullPage: true });
  console.log(`saved ${OUT_PNG}`);
  await page.close();

  // yellow(3/5=60%, passed)
  {
    const p = await browser.newPage({ viewport: VIEWPORT });
    await activate(p);
    try {
      const r = await runQuiz(p, 3, "yellow");
      if (r.resultStatus !== "통과") throw new Error(`expected passed, got ${r.resultStatus}`);
      if (r.retryLearnVisible) throw new Error("passed=true인데 '다시 학습' 링크가 렌더됨");
      console.log("PASS: 3/5 -> yellow + 통과, 다시 학습 링크 미표시");
    } catch (e) {
      console.error("FAIL:", e.message);
      failures++;
    }
    await p.close();
  }

  // red(0/5=0%, failed) — #94: passed=false -> "다시 학습" 링크(/learn?module=learning,
  // set_id=1(기본값, 미지정) -> QUIZ_SET_META[1].module="learning") 렌더 확인.
  {
    const p = await browser.newPage({ viewport: VIEWPORT });
    await activate(p);
    try {
      const r = await runQuiz(p, 0, "red");
      if (r.resultStatus !== "미통과") throw new Error(`expected failed, got ${r.resultStatus}`);
      if (!r.retryLearnVisible) throw new Error("passed=false인데 '다시 학습' 링크가 렌더되지 않음");
      const href = await p.getByTestId("quiz-retry-learn").getAttribute("href");
      console.log("다시 학습 링크 href:", href);
      if (href !== "/learn?module=learning") throw new Error(`다시 학습 링크 href 불일치: ${href}`);
      console.log("PASS: 0/5 -> red + 미통과 + 다시 학습 링크(/learn?module=learning)");
    } catch (e) {
      console.error("FAIL:", e.message);
      failures++;
    }
    await p.close();
  }

  // #94: /quiz?set_id=2(safety_1, published) 직접 진입 -> set_id 쿼리 소비 확인.
  // 퀴즈 GET 자체는 인증 optional이지만, ⑪로 WorkerLayout이 jwt 없으면 /login으로 보내는
  // 보호화면이 됐다 — 진입 전 세션을 심어둔다(moguk_jwt/moguk_refresh, AuthContext.tsx 키).
  {
    const p = await browser.newPage({ viewport: VIEWPORT });
    await p.goto(`http://localhost:${PORT}/activate`);
    await p.evaluate(() => {
      localStorage.setItem("moguk_jwt", "fake.jwt.token");
      localStorage.setItem("moguk_refresh", "fake.refresh.token");
    });
    await p.goto(`http://localhost:${PORT}/quiz?set_id=2`);
    await p.getByTestId("quiz-item").first().waitFor({ state: "visible", timeout: 5000 });
    const draftBanner = await p.getByTestId("quiz-draft-banner").isVisible().catch(() => false);
    const itemCount = await p.getByTestId("quiz-item").count();
    console.log("set_id=2 진입 -> draft 배너:", draftBanner, "문항 수:", itemCount);
    if (draftBanner) {
      console.error("FAIL: set_id=2(safety_1, published)인데 draft 배너가 렌더됨 — set_id 쿼리가 무시된 것으로 의심");
      failures++;
    } else if (itemCount !== 5) {
      console.error("FAIL: set_id=2 문항 수가 5가 아님(safety_1 기대):", itemCount);
      failures++;
    } else {
      console.log("PASS: /quiz?set_id=2 -> safety_1 로드(set_id 쿼리 소비 확인)");
    }
    await p.close();
  }

  // M-38: q/choices 직접 렌더(서버 localize 시뮬) + draft 배너 + term_hints 칩 확인.
  {
    const p = await browser.newPage({ viewport: VIEWPORT });
    await activate(p);
    await p.locator('[data-testid="tab-quiz"]').click();
    await p.getByTestId("quiz-item").first().waitFor({ state: "visible", timeout: 5000 });

    const firstQuestion = await p.locator('[data-testid="quiz-item"]').first().locator(".quiz-question").textContent();
    console.log("first question (ko, server-localized 시뮬):", firstQuestion);
    if (!firstQuestion || !firstQuestion.includes("척 조에서")) {
      console.error("FAIL: item.q 렌더 불일치 — q_ko/q_vi 선택 로직이 남아있을 가능성");
      failures++;
    } else {
      console.log("PASS: item.q 직접 렌더 확인");
    }

    const draftBanner = await p.getByTestId("quiz-draft-banner").isVisible().catch(() => false);
    console.log("draft banner visible (set_id=1 status=draft):", draftBanner);
    if (!draftBanner) {
      console.error("FAIL: status='draft' 배너가 렌더되지 않음");
      failures++;
    } else {
      console.log("PASS: draft 배너 렌더 확인");
    }

    const hintChips = await p.getByTestId("term-hint-chip").allTextContents();
    console.log("term hint chips:", hintChips);
    if (hintChips.length === 0 || !hintChips[0].includes("→")) {
      console.error("FAIL: term_hints 칩이 렌더되지 않음(용어: term_ko → term_lang 형식)");
      failures++;
    } else {
      console.log("PASS: term_hints 칩 렌더 확인");
    }

    await p.close();
  }

  // 대조군: safety_1(set_id=2)은 status='published' — draft 배너가 뜨지 않아야 한다.
  // (이 화면은 set_id=1 고정이라 fixtures 레벨에서 간접 확인 — getQuizSetMock 직접 호출,
  // 이미 떠 있는 dev server의 ssrLoadModule 재사용)
  {
    const mod = await server.ssrLoadModule("/src/api/fixtures/learn.fixtures.ts");
    const set2 = mod.getQuizSetMock(2, "ko");
    console.log("set_id=2 status (대조군, published 기대):", set2.status);
    if (set2.status === "draft") {
      console.error("FAIL: 대조군(set 2)도 draft — 배너 조건부 렌더 검증 무의미");
      failures++;
    } else {
      console.log("PASS: 대조군 status !== draft 확인");
    }
  }

  await browser.close();
  await server.close();

  if (failures > 0) {
    console.error(`\n${failures} CHECK(S) FAILED`);
    process.exit(1);
  }
  console.log("\nALL CHECKS PASSED");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
