import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir, rename } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");

// OUT_SUFFIX=<name> npm run rehearse — 탐색/실패 예상 실행이 canonical v4-* 산출물을
// 덮어쓰지 않도록 파일명을 분리한다. 생략하면 기존과 동일한 v4-* 이름 그대로.
const OUT_SUFFIX = process.env.OUT_SUFFIX ? `-${process.env.OUT_SUFFIX}` : "";
const MOCK_PNG = path.join(ASSETS_DIR, `v4-ask-mock-390${OUT_SUFFIX}.png`);
const GATED_PNG = path.join(ASSETS_DIR, `v4-ask-gated-390${OUT_SUFFIX}.png`);
const VIDEO_OUT = path.join(ASSETS_DIR, `v4-rehearsal${OUT_SUFFIX}.webm`);
const PORT = 5184;
const VIEWPORT = { width: 390, height: 844 };

const results = [];

async function step(name, fn) {
  try {
    await fn();
    results.push({ name, status: "PASS" });
    console.log(`[PASS] ${name}`);
  } catch (err) {
    results.push({ name, status: "FAIL", reason: err instanceof Error ? err.message : String(err) });
    console.log(`[FAIL] ${name} — ${err instanceof Error ? err.message : String(err)}`);
  }
}

async function resolveBaseUrl() {
  if (process.env.BASE_URL) {
    return { baseUrl: process.env.BASE_URL.replace(/\/$/, ""), server: null };
  }
  const server = await createServer({
    root: FRONTEND_ROOT,
    server: { port: PORT, strictPort: true },
  });
  await server.listen();
  return { baseUrl: `http://localhost:${PORT}`, server };
}

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });

  const { baseUrl, server } = await resolveBaseUrl();
  console.log(`BASE_URL = ${baseUrl}`);
  console.log(`OUT_SUFFIX = ${OUT_SUFFIX || "(none — canonical v4-* 파일명)"}`);

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: ASSETS_DIR, size: VIEWPORT },
  });
  const page = await context.newPage();

  await step("진입: /activate?token=demo-rehearsal", async () => {
    await page.goto(`${baseUrl}/activate?token=demo-rehearsal`);
    await page.locator("#pin").waitFor({ state: "visible", timeout: 5000 });
  });

  await step("언어 선택: vi (Tiếng Việt)", async () => {
    await page.getByRole("radio", { name: "Tiếng Việt" }).click();
  });

  await step("PIN 입력", async () => {
    await page.locator("#pin").fill("123456");
  });

  await step("활성화 → Ask 화면 이동 (SPA)", async () => {
    await page.locator('button[type="submit"]').click();
    await page.getByTestId("ask-screen").waitFor({ state: "visible", timeout: 5000 });
  });

  await step("정상 질의 → mock 응답 (answer/source/trace)", async () => {
    await page.getByTestId("ask-input").fill("연차는 어떻게 신청하나요?");
    await page.getByTestId("ask-submit").click();
    await page.getByTestId("ask-result").waitFor({ state: "visible", timeout: 5000 });
    await page.getByTestId("ask-answer").waitFor({ state: "visible", timeout: 2000 });
    await page.getByTestId("source-badge").first().waitFor({ state: "visible", timeout: 2000 });
    await page.getByTestId("ask-trace").waitFor({ state: "visible", timeout: 2000 });
    await page.screenshot({ path: MOCK_PNG });
  });

  await step("게이트 폴백 질의 (__gated__)", async () => {
    await page.getByTestId("ask-input").fill("__gated__ 위험 작업 절차");
    await page.getByTestId("ask-submit").click();
    await page.getByTestId("ask-gated").waitFor({ state: "visible", timeout: 5000 });
    await page.screenshot({ path: GATED_PNG });
  });

  await context.close();
  await browser.close();
  if (server) {
    await server.close();
  }

  const recordedPath = await page.video()?.path();
  if (recordedPath) {
    await rename(recordedPath, VIDEO_OUT);
  }

  const failed = results.filter((r) => r.status === "FAIL");
  console.log("\n=== 요약 ===");
  for (const r of results) {
    console.log(`${r.status === "PASS" ? "✓" : "✗"} ${r.name}${r.reason ? ` — ${r.reason}` : ""}`);
  }
  if (failed.length > 0) {
    console.log(`\n${failed.length}개 스텝 실패: ${failed.map((f) => f.name).join(", ")}`);
  } else {
    console.log("\n전 스텝 PASS");
  }
  console.log(`산출물: ${MOCK_PNG}`);
  console.log(`산출물: ${GATED_PNG}`);
  console.log(`산출물: ${VIDEO_OUT}`);

  process.exitCode = failed.length > 0 ? 1 : 0;
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
