import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-worker-learn.png");
const PORT = 5199;
const VIEWPORT = { width: 420, height: 900 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });
  let failures = 0;

  await page.goto(`http://localhost:${PORT}/learn`);
  await page.getByTestId("learn-card-list").waitFor({ state: "visible", timeout: 5000 });

  // A — safety(phrase) 모듈: 카드 렌더, high_risk 빨간 강조, note_ko/src 옵셔널 방어.
  const safetyCards = await page.getByTestId("learn-card").count();
  console.log("safety cards:", safetyCards);
  if (safetyCards < 5) {
    console.error("FAIL: safety 카드가 5건 미만(10건 기대)", safetyCards);
    failures++;
  } else {
    console.log("PASS: safety 카드 렌더(", safetyCards, "건)");
  }

  const highRiskCount = await page.locator(".learn-card-high-risk").count();
  console.log("high_risk 카드:", highRiskCount);
  if (highRiskCount === 0) {
    console.error("FAIL: high_risk 빨간 강조 카드가 하나도 없음");
    failures++;
  } else if (highRiskCount === safetyCards) {
    console.error("FAIL: 모든 카드가 high_risk — 대조군(false) 없음");
    failures++;
  } else {
    console.log("PASS: high_risk 강조가 일부 카드에만 적용됨(", highRiskCount, "/", safetyCards, ")");
  }

  const noteCount = await page.getByTestId("learn-card-note").count();
  const srcCount = await page.getByTestId("learn-card-src").count();
  console.log("note_ko 있는 카드:", noteCount, "/ src 있는 카드:", srcCount, "/ 전체:", safetyCards);
  if (noteCount === 0 || srcCount === 0) {
    console.error("FAIL: note_ko/src가 있는 카드가 렌더되지 않음");
    failures++;
  } else if (noteCount === safetyCards && srcCount === safetyCards) {
    console.error("FAIL: 모든 카드에 note_ko/src가 있음 — 누락(옵셔널 방어) 케이스가 검증되지 않음");
    failures++;
  } else {
    console.log("PASS: note_ko/src 옵셔널 렌더 + 누락 카드도 에러 없이 렌더됨");
  }

  // safety 모듈은 quiz_set_id=null -> 퀴즈 버튼 비활성 + 안내, 링크 없음.
  await page.getByTestId("learn-quiz-pending").waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: quiz_set_id=null -> '퀴즈 준비 중' 안내 렌더"),
    () => {
      console.error("FAIL: quiz_set_id=null인데 '퀴즈 준비 중' 안내가 렌더되지 않음");
      failures++;
    },
  );
  const pendingButtonDisabled = await page.getByTestId("learn-quiz-pending-button").isDisabled();
  if (!pendingButtonDisabled) {
    console.error("FAIL: quiz_set_id=null인데 퀴즈 버튼이 활성화됨");
    failures++;
  } else {
    console.log("PASS: quiz_set_id=null -> 퀴즈 버튼 비활성화 확인");
  }
  const linkVisibleOnSafety = await page.getByTestId("learn-quiz-link").isVisible().catch(() => false);
  if (linkVisibleOnSafety) {
    console.error("FAIL: quiz_set_id=null인데 퀴즈 링크가 렌더됨");
    failures++;
  }

  // B — learning(term) 모듈: high_risk 항상 false, quiz_set_id 있음 -> 링크 렌더.
  await page.getByTestId("learn-module-learning").click();
  await page.waitForTimeout(300); // mock delay(200) 여유
  await page.getByTestId("learn-card-list").waitFor({ state: "visible", timeout: 5000 });

  const learningCards = await page.getByTestId("learn-card").count();
  console.log("learning cards:", learningCards);
  if (learningCards < 3) {
    console.error("FAIL: learning 카드가 3건 미만", learningCards);
    failures++;
  } else {
    console.log("PASS: learning 카드 렌더(", learningCards, "건)");
  }

  const learningHighRisk = await page.locator(".learn-card-high-risk").count();
  if (learningHighRisk !== 0) {
    console.error("FAIL: learning(term) 카드에 high_risk 강조가 있음(계약상 term은 항상 false)");
    failures++;
  } else {
    console.log("PASS: learning(term) 카드는 high_risk 강조 없음(계약 준수)");
  }

  const quizLink = page.getByTestId("learn-quiz-link");
  await quizLink.waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: quiz_set_id 있음 -> 퀴즈 링크 렌더"),
    () => {
      console.error("FAIL: quiz_set_id가 있는데 퀴즈 링크가 렌더되지 않음");
      failures++;
    },
  );
  const href = await quizLink.getAttribute("href").catch(() => null);
  console.log("퀴즈 링크 href:", href);
  if (!href || !href.includes("/quiz")) {
    console.error("FAIL: 퀴즈 링크 href가 /quiz를 포함하지 않음:", href);
    failures++;
  }
  const pendingVisibleOnLearning = await page.getByTestId("learn-quiz-pending").isVisible().catch(() => false);
  if (pendingVisibleOnLearning) {
    console.error("FAIL: quiz_set_id가 있는데 '퀴즈 준비 중' 안내가 남아있음");
    failures++;
  }

  await page.screenshot({ path: OUT_PNG, fullPage: true });
  console.log(`saved ${OUT_PNG}`);

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
