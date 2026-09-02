import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-admin-events.png");
const PORT = 5189;
const VIEWPORT = { width: 1024, height: 900 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });
  let failures = 0;

  // A — 첫 submitted 보고 ack (감사 로그에 report_acknowledged 기록되어야 함)
  await page.goto(`http://localhost:${PORT}/admin/reports`);
  await page.getByTestId("report-row").first().waitFor({ state: "visible", timeout: 5000 });
  const firstAck = page
    .locator('[data-testid="report-row"]')
    .filter({ has: page.locator('[data-testid="ack-btn"]') })
    .first();
  await firstAck.getByTestId("ack-btn").click();
  await page.waitForTimeout(300);
  // 세부 버튼도 눌러서 original_viewed 도 같이 기록
  await firstAck.getByTestId("detail-btn").click();
  await page.getByTestId("report-detail").waitFor({ state: "visible", timeout: 5000 });
  await page.waitForTimeout(300);

  // C — 첫 draft 용어 승인 (glossary_approved 기록되어야 함).
  // SPA nav 링크로 이동해야 mock 모듈 상태가 유지된다 — goto()는 풀 리로드라 store 가 리셋된다.
  await page.getByRole("link", { name: "승인큐" }).click();
  await page.getByTestId("term-row").first().waitFor({ state: "visible", timeout: 5000 });
  await page.locator('[data-testid="term-row"]').first().getByTestId("approve-btn").click();
  await page.waitForTimeout(300);

  // 감사 로그 — 방금 두 행위가 오늘 날짜로 잡히는지 확인
  await page.getByRole("link", { name: "감사 로그" }).click();
  await page.getByTestId("event-table").waitFor({ state: "visible", timeout: 5000 });
  await page.waitForTimeout(300);

  const count = await page.getByTestId("event-count").textContent();
  const rows = await page.getByTestId("event-row").allTextContents();
  console.log("event count:", count);
  rows.forEach((r) => console.log("row:", r.replace(/\s+/g, " ").trim()));

  // i18n 배선 확인 — ko(기본) -> vi -> ko 토글 시 라벨이 실제로 바뀌는지(admin i18n 신규 배선).
  const h1Ko = await page.locator("h1").textContent();
  const thTimeKo = await page.locator("th").first().textContent();
  await page.getByTestId("admin-lang-vi").click();
  await page.waitForTimeout(50);
  const h1Vi = await page.locator("h1").textContent();
  const thTimeVi = await page.locator("th").first().textContent();
  console.log("h1 ko:", h1Ko, "/ h1 vi:", h1Vi, "/ th[0] ko:", thTimeKo, "/ th[0] vi:", thTimeVi);
  if (h1Ko === h1Vi || thTimeKo === thTimeVi) {
    console.error("FAIL: admin-lang-vi 토글 후 h1/표 헤더 라벨이 바뀌지 않음 — i18n 배선 미동작 의심");
    failures++;
  } else {
    console.log("PASS: vi 토글 시 h1·표 헤더 라벨 변경 확인");
  }
  await page.getByTestId("admin-lang-ko").click();
  await page.waitForTimeout(50);
  const h1Back = await page.locator("h1").textContent();
  if (h1Back !== h1Ko) {
    console.error("FAIL: ko로 되돌린 후 라벨이 원래대로 복귀하지 않음");
    failures++;
  } else {
    console.log("PASS: ko 복귀 확인");
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
