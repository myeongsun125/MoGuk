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

  // 첫 open 항목에 답변 제출 (mock: 성공 시 answerMock이 AnswerResult{status:'answered',...}를
  // 돌려주고, handleSubmit이 그 값을 해당 행에 먼저 반영한 뒤(짧게 "답변됨" 노출) 재조회로
  // status=open 목록에서 자연히 빠진다).
  const firstRow = page.locator('[data-testid="unanswered-row"]').first();
  const firstQid = await firstRow.getAttribute("data-question-id");
  await firstRow.getByTestId("answer-input").fill("정착지원팀 문의처: 내선 1234");
  await firstRow.getByTestId("answer-submit").click();

  // 재조회로 사라지기 전, AnswerResult.status가 먼저 그 행에 반영되는 짧은 창을 폴링으로 포착.
  let sawAnswered = false;
  for (let i = 0; i < 15; i++) {
    const row = page.locator(`[data-testid="unanswered-row"][data-question-id="${firstQid}"]`);
    if ((await row.count()) === 0) break; // 이미 재조회로 빠짐(창을 놓침 — 타이밍 문제일 뿐 실패 아님)
    const text = await row.textContent().catch(() => "");
    if (text?.includes("답변됨")) {
      sawAnswered = true;
      break;
    }
    await page.waitForTimeout(20);
  }
  console.log(sawAnswered ? "PASS: row reflected status='answered' before refetch" : "note: answered-state window not captured (refetch too fast — not a failure)");

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

  // 감사 로그 화면이 target_type='unanswered'·action='unanswered_answered' 행을 필터 없이
  // 그대로 노출하는지 확인(코드 변경 없이 기존 병합 조회로 되는지 — SPA nav로 이동해야
  // mock 모듈 상태 유지, goto()는 풀 리로드라 store가 리셋된다).
  await page.getByRole("link", { name: "감사 로그" }).click();
  await page.getByTestId("event-row").first().waitFor({ state: "visible", timeout: 5000 });
  const eventRows = await page.getByTestId("event-row").allTextContents();
  const unansweredRow = eventRows.find((r) => r.includes("unanswered_answered"));
  if (!unansweredRow) {
    console.error("FAIL: AuditLog does not show unanswered_answered event row", eventRows);
    await browser.close();
    await server.close();
    process.exit(1);
  }
  console.log("PASS: AuditLog shows unanswered_answered row ->", unansweredRow.replace(/\s+/g, " ").trim());

  await page.screenshot({ path: OUT_PNG, fullPage: true });
  console.log(`saved ${OUT_PNG}`);

  await browser.close();
  await server.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
