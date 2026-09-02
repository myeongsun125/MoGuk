import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-admin-documents.png");
const PORT = 5197;
const VIEWPORT = { width: 1024, height: 900 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });
  let failures = 0;

  // 임시 업로드 파일 2종 — .txt만 지원(accept=".md,.txt"), 실 파일 그대로 setInputFiles.
  const okPath = path.join(tmpdir(), `moguk-qa-doc-${Date.now()}.txt`);
  const okContent = "선반 작업 시 척 조에 공작물을 고정할 때 ".repeat(60); // 800자 초과 -> 2청크 기대
  await writeFile(okPath, okContent, "utf8");

  const blankPath = path.join(tmpdir(), `moguk-qa-doc-blank-${Date.now()}.txt`);
  await writeFile(blankPath, "   \n  ", "utf8"); // 공백뿐 -> text 빈 값 422 경로

  await page.goto(`http://localhost:${PORT}/admin/documents`);
  await page.getByTestId("document-form").waitFor({ state: "visible", timeout: 5000 });
  // 초기 목록(시드 3건) 로딩이 끝날 때까지 기다린다 — 이걸 안 기다리면 이후 "beforeRows"가
  // 마운트 refresh()가 아직 응답하기 전(0건)에 계산돼 모든 뒷단 단언이 어긋난다.
  await page.getByTestId("document-row").nth(2).waitFor({ state: "visible", timeout: 5000 });

  // job_status null(SB 확정, 잡 없는 시드 문서) 방어 — "—"(admin.documents.statusNone) 렌더.
  const noneBadge = page.getByTestId("document-status-none");
  await noneBadge.waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: job_status null -> statusNone(\"—\") 렌더"),
    () => {
      console.error("FAIL: job_status null 문서가 statusNone으로 렌더되지 않음");
      failures++;
    },
  );
  const noneText = await noneBadge.textContent().catch(() => null);
  console.log("null 상태 표시 텍스트:", noneText);
  if (noneText !== "—") {
    console.error("FAIL: null 상태 표시 텍스트가 '—'가 아님:", noneText);
    failures++;
  }
  const noneRow = page.locator('[data-testid="document-row"][data-job-status="none"]');
  if ((await noneRow.count()) !== 1) {
    console.error("FAIL: data-job-status=\"none\" 행이 정확히 1개가 아님");
    failures++;
  } else {
    console.log("PASS: null 문서 행의 data-job-status=\"none\" 확인");
  }

  // A — 정상 업로드: 파일 선택 -> title 자동 채움 확인 -> 제출 -> 202 -> 목록 반영(running).
  await page.getByTestId("document-file").setInputFiles(okPath);
  const autoTitle = await page.getByTestId("document-title").inputValue();
  const expectedTitle = path.basename(okPath, ".txt");
  console.log("auto title:", autoTitle, "expected:", expectedTitle);
  if (autoTitle !== expectedTitle) {
    console.error("FAIL: 파일 선택 시 title 기본값이 파일명(확장자 제거)이 아님");
    failures++;
  } else {
    console.log("PASS: title 기본값 = 파일명(확장자 제거)");
  }

  const categoryOptions = await page.getByTestId("document-category").locator("option").allTextContents();
  console.log("category options:", categoryOptions);
  if (categoryOptions.length !== 4) {
    console.error("FAIL: 분류 select 옵션이 4개가 아님:", categoryOptions);
    failures++;
  } else {
    console.log("PASS: 분류 select 4택 확인");
  }

  const beforeRows = await page.getByTestId("document-row").count();
  const clickedAt = Date.now();
  await page.getByTestId("document-submit").click();

  await page.getByTestId("document-row").nth(beforeRows).waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: 제출 후 목록에 새 행 추가"),
    () => {
      console.error("FAIL: 제출 후 목록에 새 행이 추가되지 않음");
      failures++;
    },
  );

  // B — mock은 폴링 2회차(실 setInterval 5초 간격 1회 경과)에 done으로 전환한다 — "즉시
  // running" 순간은 테스트 자체의 실행 속도에 따라 놓칠 수 있어 단언하지 않는다. 대신
  // (a) 결과적으로 done에 도달하는지, (b) 그게 즉시(=폴링 없이)가 아니라 실제로 폴링
  // 간격만큼 걸렸는지(진짜 폴링이 동작했다는 증거)를 확인한다.
  await page.waitForFunction(
    () => document.querySelector('[data-testid="document-row"]')?.getAttribute("data-job-status") === "done",
    { timeout: 12000 },
  ).then(
    () => console.log("PASS: 폴링으로 job_status가 done으로 전환됨"),
    () => {
      console.error("FAIL: 12초 내 job_status가 done으로 전환되지 않음(폴링 미동작?)");
      failures++;
    },
  );
  const doneElapsedMs = Date.now() - clickedAt;
  console.log("done까지 경과(ms):", doneElapsedMs);
  if (doneElapsedMs < 1000) {
    console.error("FAIL: done 전환이 사실상 즉시 일어남 — 폴링을 거치지 않은 것으로 의심됨");
    failures++;
  } else {
    console.log("PASS: 즉시 완료가 아니라 폴링 간격을 거쳐 done 전환됨(실제 폴링 동작 증거)");
  }

  const chunkCountText = await page.getByTestId("document-row").first().locator("td").nth(2).textContent();
  console.log("chunk_count (done 후):", chunkCountText);
  if (!chunkCountText || Number(chunkCountText) < 1) {
    console.error("FAIL: done 전환 후 chunk_count가 1 미만");
    failures++;
  } else {
    console.log("PASS: done 전환 후 chunk_count 채워짐 ->", chunkCountText);
  }

  // C — 공백뿐인 파일 -> 서버 422(text 빈 값) 경로 재현(클라에서 trim() 선차단 안 함).
  await page.getByTestId("document-file").setInputFiles(blankPath);
  await page.getByTestId("document-submit").click();
  await page.getByTestId("document-error").waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: 공백 텍스트 -> 422 -> document-error 렌더"),
    () => {
      console.error("FAIL: 공백 텍스트 제출이 422/document-error로 이어지지 않음");
      failures++;
    },
  );

  await page.screenshot({ path: OUT_PNG, fullPage: true });
  console.log(`saved ${OUT_PNG}`);

  await browser.close();
  await server.close();
  await rm(okPath, { force: true });
  await rm(blankPath, { force: true });

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
