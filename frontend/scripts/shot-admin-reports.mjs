import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const BEFORE_PNG = path.join(ASSETS_DIR, "v3-2-admin-reports-before-ack.png");
const AFTER_PNG = path.join(ASSETS_DIR, "v3-2-admin-reports-after-ack.png");
const DETAIL_PNG = path.join(ASSETS_DIR, "v3-2-admin-reports-detail.png");
const PORT = 5186;
const VIEWPORT = { width: 1024, height: 900 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });

  const server = await createServer({
    root: FRONTEND_ROOT,
    server: { port: PORT, strictPort: true },
  });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });
  let failures = 0;

  await page.goto(`http://localhost:${PORT}/admin/reports`);
  await page.getByTestId("admin-reports-screen").waitFor({ state: "visible", timeout: 5000 });
  await page.getByTestId("report-row").first().waitFor({ state: "visible", timeout: 5000 });

  // i18n 배선 확인 — ko(기본) -> vi -> ko 토글 시 라벨이 실제로 바뀌는지(admin i18n 신규 배선).
  const h1Ko = await page.locator("h1").textContent();
  await page.getByTestId("admin-lang-vi").click();
  await page.waitForTimeout(50);
  const h1Vi = await page.locator("h1").textContent();
  console.log("h1 ko:", h1Ko, "/ h1 vi:", h1Vi);
  if (h1Ko === h1Vi) {
    console.error("FAIL: admin-lang-vi 토글 후 h1 라벨이 바뀌지 않음 — i18n 배선 미동작 의심");
    failures++;
  } else {
    console.log("PASS: vi 토글 시 라벨 변경 확인");
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

  const before = await page.getByTestId("unconfirmed-count").textContent();
  console.log("before:", before);
  await page.screenshot({ path: BEFORE_PNG });

  // 첫 번째 submitted 행의 ack 버튼 클릭 — 이후 이 행은 acknowledged 로 바뀌어 다음
  // 행이 "첫 ack-btn"이 되므로, id 로 고정한 locator 로 같은 행을 계속 참조한다.
  const firstAck = page.locator('[data-testid="report-row"]').filter({ has: page.locator('[data-testid="ack-btn"]') }).first();
  const reportId = await firstAck.getAttribute("data-report-id");
  const targetRow = page.locator(`[data-testid="report-row"][data-report-id="${reportId}"]`);
  await targetRow.getByTestId("ack-btn").click();

  await page.waitForTimeout(400); // mock delay(150) + refresh 왕복
  const after = await page.getByTestId("unconfirmed-count").textContent();
  console.log("after ack on report", reportId, ":", after);
  await page.screenshot({ path: AFTER_PNG });

  // 세부 버튼 — 상세(원문 열람 시점에만 호출) + acked_by=null 표시 확인. 방금 ack 한 그 행.
  await targetRow.getByTestId("detail-btn").click();
  await page.getByTestId("report-detail").waitFor({ state: "visible", timeout: 5000 });
  const ackedBy = await page.getByTestId("detail-acked-by").textContent();
  console.log("acked_by display:", ackedBy);
  await page.screenshot({ path: DETAIL_PNG });

  await browser.close();
  await server.close();

  console.log(`saved ${BEFORE_PNG}`);
  console.log(`saved ${AFTER_PNG}`);
  console.log(`saved ${DETAIL_PNG}`);

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
