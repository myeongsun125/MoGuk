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

// quiz_learning_1 5문항의 정답 인덱스(learn.fixtures.ts QUIZ_LEARNING_1과 동일 순서) —
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
  return { resultLabel, resultStatus };
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
    console.log("PASS: 5/5 -> green + 통과");
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
      console.log("PASS: 3/5 -> yellow + 통과");
    } catch (e) {
      console.error("FAIL:", e.message);
      failures++;
    }
    await p.close();
  }

  // red(0/5=0%, failed)
  {
    const p = await browser.newPage({ viewport: VIEWPORT });
    await activate(p);
    try {
      const r = await runQuiz(p, 0, "red");
      if (r.resultStatus !== "미통과") throw new Error(`expected failed, got ${r.resultStatus}`);
      console.log("PASS: 0/5 -> red + 미통과");
    } catch (e) {
      console.error("FAIL:", e.message);
      failures++;
    }
    await p.close();
  }

  // 회귀: term-hint 자리(disabled) 확인.
  {
    const p = await browser.newPage({ viewport: VIEWPORT });
    await activate(p);
    await p.locator('[data-testid="tab-quiz"]').click();
    await p.getByTestId("quiz-item").first().waitFor({ state: "visible", timeout: 5000 });
    const hintDisabled = await p.getByTestId("term-hint").first().isDisabled();
    console.log("term-hint disabled (자리만):", hintDisabled);
    if (!hintDisabled) {
      console.error("FAIL: term-hint should stay disabled(자리만) — 데이터 연결 금지");
      failures++;
    }
    await p.close();
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
