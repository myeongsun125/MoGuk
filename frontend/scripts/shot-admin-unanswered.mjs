import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-admin-unanswered.png");
const PORT = 5190;
const VIEWPORT = { width: 1024, height: 900 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });

  await page.goto(`http://localhost:${PORT}/admin/unanswered`);
  await page.getByTestId("unanswered-row").first().waitFor({ state: "visible", timeout: 5000 });

  const beforeCount = await page.getByTestId("unanswered-count").textContent();
  const beforeRows = await page.getByTestId("unanswered-row").count();
  console.log("before:", beforeCount, "rows:", beforeRows);

  // 첫 open 항목에 답변 제출 (mock: 성공 시 answerMock이 status→answered, 재조회로
  // status=open 목록에서 자연히 빠져야 한다).
  const firstRow = page.locator('[data-testid="unanswered-row"]').first();
  await firstRow.getByTestId("answer-input").fill("정착지원팀 문의처: 내선 1234");
  await firstRow.getByTestId("answer-submit").click();

  await page.waitForTimeout(400); // mock delay(150) + refetch delay(150) 여유

  const afterCount = await page.getByTestId("unanswered-count").textContent();
  const afterRows = await page.getByTestId("unanswered-row").count();
  console.log("after:", afterCount, "rows:", afterRows);

  if (afterRows !== beforeRows - 1) {
    console.error(`FAIL: expected ${beforeRows - 1} rows after answer, got ${afterRows}`);
    await browser.close();
    await server.close();
    process.exit(1);
  }
  console.log("PASS: answered item dropped from open list after refetch");

  await page.screenshot({ path: OUT_PNG, fullPage: true });
  console.log(`saved ${OUT_PNG}`);

  await browser.close();
  await server.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
