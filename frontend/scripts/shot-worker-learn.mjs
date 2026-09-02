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

  // safety 모듈은 quiz_set_id=null -> 퀴즈 버튼 영역 자체가 렌더되지 않는다(#94 추가,
  // 총괄 승인 0902 — 이전엔 비활성 버튼+안내 문구였으나 렌더 안 함으로 변경).
  await page.waitForTimeout(300); // 카드 로딩과 별개로 버튼 영역 부재를 확정하기 위한 여유
  const linkVisibleOnSafety = await page.getByTestId("learn-quiz-link").isVisible().catch(() => false);
  const ctaCountOnSafety = await page.locator(".learn-quiz-cta").count();
  console.log("safety: 퀴즈 링크 표시:", linkVisibleOnSafety, "/ CTA 영역 개수:", ctaCountOnSafety);
  if (linkVisibleOnSafety || ctaCountOnSafety !== 0) {
    console.error("FAIL: quiz_set_id=null인데 퀴즈 버튼/CTA 영역이 렌더됨");
    failures++;
  } else {
    console.log("PASS: quiz_set_id=null -> 퀴즈 버튼 영역 자체가 렌더되지 않음");
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
  const ctaCountOnLearning = await page.locator(".learn-quiz-cta").count();
  if (ctaCountOnLearning !== 1) {
    console.error("FAIL: quiz_set_id가 있는데 CTA 영역이 정확히 1개가 아님:", ctaCountOnLearning);
    failures++;
  }

  await page.screenshot({ path: OUT_PNG, fullPage: true });
  console.log(`saved ${OUT_PNG}`);

  // C — #94: /learn?module=learning 쿼리로 초기 선택 모듈 지정(Quiz "다시 학습" 링크가
  // 사용). 새 페이지의 첫 goto()이므로 SPA 상태 리셋 문제 없음.
  {
    const p = await browser.newPage({ viewport: VIEWPORT });
    await p.goto(`http://localhost:${PORT}/learn?module=learning`);
    await p.getByTestId("learn-card-list").waitFor({ state: "visible", timeout: 5000 });

    const learningTabSelected = await p.getByTestId("learn-module-learning").getAttribute("aria-selected");
    console.log("module=learning 쿼리 -> learning 탭 aria-selected:", learningTabSelected);
    if (learningTabSelected !== "true") {
      console.error("FAIL: module=learning 쿼리인데 learning 탭이 초기 선택되지 않음");
      failures++;
    } else {
      console.log("PASS: module 쿼리로 초기 선택 모듈 지정 확인(learning)");
    }

    const cardText = await p.getByTestId("learn-card").first().locator(".learn-card-text-ko").textContent();
    console.log("첫 카드(ko):", cardText);
    if (cardText !== "척") {
      console.error("FAIL: module=learning 쿼리인데 렌더된 카드가 learning(용어집) 세트가 아님:", cardText);
      failures++;
    } else {
      console.log("PASS: module 쿼리로 지정한 모듈의 카드가 실제로 로드됨");
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
