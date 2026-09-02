import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
// v3-2-admin-dashboard.png는 61a8197(감사 로그 화면, 0830)에서 이미 트래킹 중인 별개 파일 —
// 이름 충돌 방지로 -kpi 접미사를 붙인다(M-41 학습 KPI 렌더 스크린샷).
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-admin-dashboard-kpi.png");
const PORT = 5198;
const VIEWPORT = { width: 1024, height: 1100 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });
  let failures = 0;

  await page.goto(`http://localhost:${PORT}/admin/dashboard`);
  await page.getByTestId("kpi-grid").waitFor({ state: "visible", timeout: 5000 });

  // "(mock)" 라벨 제거 확인 — M-41 전엔 근로자별/모듈별 제목에 "(mock)"이 붙어 있었다.
  const bodyText = await page.textContent("body");
  if (bodyText?.includes("(mock)")) {
    console.error("FAIL: 화면에 '(mock)' 라벨이 남아있음");
    failures++;
  } else {
    console.log("PASS: '(mock)' 라벨 제거 확인");
  }

  // 신규 KPI 카드 — 평균 이해도·학습 완료율(mock avg_comprehension=84.8, completion_rate.rate=0.625).
  const avgCompText = await page.getByTestId("kpi-avg-comprehension").textContent().catch(() => null);
  console.log("avg-comprehension card:", avgCompText);
  if (!avgCompText || !avgCompText.includes("85점")) {
    console.error("FAIL: 평균 이해도 KPI 카드 값이 예상과 다름(반올림 85점 기대):", avgCompText);
    failures++;
  } else {
    console.log("PASS: 평균 이해도 KPI 카드 렌더 확인");
  }

  const completionText = await page.getByTestId("kpi-completion-rate").textContent().catch(() => null);
  console.log("completion-rate card:", completionText);
  if (!completionText || !completionText.includes("63%")) {
    console.error("FAIL: 학습 완료율 KPI 카드 값이 예상과 다름(반올림 63% 기대):", completionText);
    failures++;
  } else {
    console.log("PASS: 학습 완료율 KPI 카드 렌더 확인");
  }

  // 근로자별 이해도 3색(red/yellow/green) — mock PER_WORKER: green/yellow/red/green/yellow.
  await page.getByTestId("per-worker-list").waitFor({ state: "visible", timeout: 5000 });
  const badgeClasses = await page
    .locator('[data-testid="per-worker-list"] .badge')
    .evaluateAll((els) => els.map((el) => el.className));
  console.log("per-worker badges:", badgeClasses);
  const colors = ["red", "yellow", "green"];
  const seen = new Set(colors.filter((c) => badgeClasses.some((cls) => cls.includes(`badge-label-${c}`))));
  if (seen.size !== 3) {
    console.error("FAIL: 근로자별 이해도 3색(red/yellow/green)이 모두 나타나지 않음:", [...seen]);
    failures++;
  } else {
    console.log("PASS: 근로자별 이해도 3색 전부 렌더 확인");
  }

  // quiz_set_id·score 렌더 확인(옛 name/comprehension 필드가 아님).
  const firstWorkerRow = await page.locator('[data-testid="per-worker-list"] li').first().textContent();
  console.log("first per-worker row:", firstWorkerRow);
  if (!firstWorkerRow?.includes("세트") || !firstWorkerRow?.includes("점")) {
    console.error("FAIL: per-worker 행에 세트(quiz_set_id)·점수(score) 표기가 없음:", firstWorkerRow);
    failures++;
  } else {
    console.log("PASS: per-worker 행에 quiz_set_id·score 표기 확인");
  }

  // 모듈별 평균(avg_score·n) 렌더 확인.
  const firstModuleRow = await page.locator('[data-testid="per-module-list"] li').first().textContent();
  console.log("first per-module row:", firstModuleRow);
  if (!firstModuleRow?.includes("명")) {
    console.error("FAIL: per-module 행에 인원수(n)가 표기되지 않음:", firstModuleRow);
    failures++;
  } else {
    console.log("PASS: per-module 행에 avg_score·n 표기 확인");
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
