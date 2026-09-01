import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-admin-workers.png");
const PORT = 5194;
const VIEWPORT = { width: 1024, height: 900 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT, acceptDownloads: true });
  let failures = 0;

  await page.goto(`http://localhost:${PORT}/admin/workers`);
  await page.getByTestId("invite-form").waitFor({ state: "visible", timeout: 5000 });

  // A — 422: 공백뿐인 이름(name)으로 제출 → invites.py _validate와 동일 422 경로.
  await page.getByTestId("invite-name").fill("   ");
  await page.getByTestId("invite-emp-no").fill("EMP-NEW-001");
  await page.getByTestId("invite-submit").click();
  await page.getByTestId("invite-error-invalid").waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: 422(name 공백) -> invite-error-invalid"),
    () => {
      console.error("FAIL: 422 branch did not render invite-error-invalid");
      failures++;
    },
  );

  // B — 409: 미리 심어둔 활성 사번(EMP-ACTIVE)으로 제출.
  await page.getByTestId("invite-name").fill("김철수");
  await page.getByTestId("invite-emp-no").fill("EMP-ACTIVE");
  await page.getByTestId("invite-submit").click();
  await page.getByTestId("invite-error-duplicate").waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: 409(활성 워커 중복) -> invite-error-duplicate"),
    () => {
      console.error("FAIL: 409 branch did not render invite-error-duplicate");
      failures++;
    },
  );

  // C — 정상 발급 → invite_url 표시 + QR 캔버스 렌더 + 이미지 저장 다운로드 왕복.
  await page.getByTestId("invite-name").fill("김철수");
  await page.getByTestId("invite-emp-no").fill("EMP-NEW-001");
  await page.getByTestId("invite-lang").selectOption("in");
  await page.getByTestId("invite-submit").click();
  await page.getByTestId("invite-result").waitFor({ state: "visible", timeout: 5000 });

  const inviteUrl = await page.getByTestId("invite-url").textContent();
  console.log("invite_url:", inviteUrl);
  if (!inviteUrl || !inviteUrl.includes("/activate?token=")) {
    console.error("FAIL: invite_url shape unexpected");
    failures++;
  }

  const canvasSize = await page.evaluate(() => {
    const c = document.querySelector('[data-testid="invite-qr-canvas"]');
    return c ? { width: c.width, height: c.height, dataLen: c.toDataURL().length } : null;
  });
  console.log("QR canvas:", canvasSize);
  if (!canvasSize || canvasSize.width === 0 || canvasSize.dataLen < 500) {
    console.error("FAIL: QR canvas not rendered (blank/zero-size)");
    failures++;
  } else {
    console.log("PASS: QR canvas rendered with non-trivial content");
  }

  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 5000 }),
    page.getByTestId("invite-save-image").click(),
  ]);
  const suggested = download.suggestedFilename();
  const savedPath = path.join(ASSETS_DIR, `_qa-${suggested}`);
  await download.saveAs(savedPath);
  console.log("PASS: '이미지 저장' download ->", suggested, "saved to", savedPath);

  // 발송 버튼은 자리만 — disabled 확인.
  const sendDisabled = await page.getByTestId("invite-send").isDisabled();
  console.log("send button disabled (자리만, 연결 금지):", sendDisabled);
  if (!sendDisabled) {
    console.error("FAIL: '카톡/문자로 보내기' should stay disabled — API 연결 금지 지시 위반");
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
