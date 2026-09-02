import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-worker-invite.png");
const PORT = 5200;
const VIEWPORT = { width: 390, height: 800 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });
  let failures = 0;

  // 사전 조건 세팅용 — 빈 페이지를 한 번 띄워 origin을 잡은 뒤 localStorage에 기존 jwt를
  // 심는다(AuthContext.tsx STORAGE_KEY_JWT="moguk_jwt"/REFRESH="moguk_refresh" 그대로).
  await page.goto(`http://localhost:${PORT}/activate`);
  await page.evaluate(() => {
    localStorage.setItem("moguk_jwt", "fake.existing.jwt");
    localStorage.setItem("moguk_refresh", "fake.existing.refresh");
  });

  // A — 회귀 확인: 기존 jwt + URL에 token 없음 -> 여전히 /ask로 리다이렉트(기존 동작 무변경).
  await page.goto(`http://localhost:${PORT}/activate`);
  await page.waitForURL(/\/ask/, { timeout: 5000 }).then(
    () => console.log("PASS: 기존 jwt + token 없음 -> /ask 리다이렉트(기존 동작 유지)"),
    () => {
      console.error("FAIL: 기존 jwt + token 없음인데 /ask로 리다이렉트되지 않음(회귀)");
      failures++;
    },
  );

  // B — 본 수정 확인: 기존 jwt + URL에 token 있음 -> 리다이렉트하지 않고 PIN 화면 노출
  // (삼성 인터넷 등에서 새 초대 QR을 스캔해도 PIN이 안 보이던 버그의 재현·수정 확인).
  await page.goto(`http://localhost:${PORT}/activate?token=new-invite-token-1`);
  const pinInput = page.locator("#pin");
  await pinInput.waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: 기존 jwt + token 있음 -> PIN 입력 화면 노출(리다이렉트 안 함)"),
    () => {
      console.error("FAIL: 기존 jwt + token 있는데도 PIN 화면이 렌더되지 않음(리다이렉트된 것으로 의심)");
      failures++;
    },
  );
  const currentUrl = page.url();
  console.log("현재 URL:", currentUrl);
  if (!currentUrl.includes("/activate")) {
    console.error("FAIL: token 있는데도 /activate에서 다른 경로로 이동함:", currentUrl);
    failures++;
  }
  const langSelectVisible = await page.locator(".lang-select").isVisible().catch(() => false);
  if (!langSelectVisible) {
    console.error("FAIL: 언어 선택 영역이 렌더되지 않음");
    failures++;
  } else {
    console.log("PASS: 언어 선택 영역도 함께 렌더됨");
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
