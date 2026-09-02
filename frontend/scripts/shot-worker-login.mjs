import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const OUT_PNG = path.join(ASSETS_DIR, "v3-2-worker-login.png");
const PORT = 5201;
const VIEWPORT = { width: 390, height: 800 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });
  let failures = 0;

  // 0 — 보호화면(⑪): jwt 없이 /ask 직접 진입 -> /login으로 리다이렉트되는지.
  await page.goto(`http://localhost:${PORT}/ask`);
  await page.waitForURL(/\/login/, { timeout: 5000 }).then(
    () => console.log("PASS: jwt 없이 /ask 진입 -> /login 리다이렉트"),
    () => {
      console.error("FAIL: jwt 없이 /ask 진입인데 /login으로 리다이렉트되지 않음");
      failures++;
    },
  );

  await page.goto(`http://localhost:${PORT}/login`);
  await page.getByTestId("login-emp-no").waitFor({ state: "visible", timeout: 5000 });

  // A — 언어 선택 칩(Invite와 동일 패턴) 렌더 확인.
  const langChips = await page.locator('[data-testid^="login-lang-"]').count();
  console.log("언어 선택 칩 개수:", langChips);
  if (langChips !== 3) {
    console.error("FAIL: 언어 선택 칩이 3개가 아님:", langChips);
    failures++;
  } else {
    console.log("PASS: 언어 선택 칩(vi/ko/in) 렌더 확인");
  }
  // 초기값 = 저장값 없으면 기본 vi(LangContext.tsx 그대로) — 새 컨텍스트라 저장값 없음.
  const viActiveInitially = await page.getByTestId("login-lang-vi").getAttribute("aria-checked");
  console.log("초기 활성 언어(vi 기대):", viActiveInitially);
  if (viActiveInitially !== "true") {
    console.error("FAIL: 저장값 없을 때 초기 언어가 vi가 아님:", viActiveInitially);
    failures++;
  } else {
    console.log("PASS: 저장값 없을 때 기본 vi 확인");
  }
  // 칩 클릭 -> 실제 전환(setLang) 확인.
  await page.getByTestId("login-lang-ko").click();
  const koActiveAfterClick = await page.getByTestId("login-lang-ko").getAttribute("aria-checked");
  const titleAfterClick = await page.locator("h1").textContent();
  console.log("ko 클릭 후 aria-checked:", koActiveAfterClick, "/ title:", titleAfterClick);
  if (koActiveAfterClick !== "true" || titleAfterClick !== "로그인") {
    console.error("FAIL: 언어 칩 클릭이 실제로 반영되지 않음");
    failures++;
  } else {
    console.log("PASS: 언어 칩 클릭 시 화면 문구까지 전환 확인");
  }
  await page.getByTestId("login-lang-vi").click(); // 이후 테스트를 위해 vi로 되돌림

  // B — PIN 4자리 미만이면 제출 버튼 비활성(★4자리 이상만 제출).
  await page.getByTestId("login-emp-no").fill("EMP-ACTIVE");
  await page.getByTestId("login-pin").fill("123");
  const submitDisabledShort = await page.getByTestId("login-submit").isDisabled();
  console.log("PIN 3자리일 때 제출 버튼 disabled:", submitDisabledShort);
  if (!submitDisabledShort) {
    console.error("FAIL: PIN이 4자리 미만인데 제출 버튼이 활성화됨");
    failures++;
  } else {
    console.log("PASS: PIN 4자리 미만이면 제출 버튼 비활성 확인");
  }

  // C — 401: 잘못된 사번/PIN 조합 -> 단일 안내 문구.
  await page.getByTestId("login-pin").fill("0000");
  const submitEnabledForWrong = await page.getByTestId("login-submit").isEnabled();
  if (!submitEnabledForWrong) {
    console.error("FAIL: PIN 4자리인데도 제출 버튼이 비활성 상태");
    failures++;
  }
  await page.getByTestId("login-submit").click();
  await page.getByTestId("login-invalid").waitFor({ state: "visible", timeout: 5000 }).then(
    () => console.log("PASS: 잘못된 사번/PIN -> login-invalid 안내 렌더"),
    () => {
      console.error("FAIL: 401 응답인데 login-invalid 안내가 렌더되지 않음");
      failures++;
    },
  );
  const stillOnLogin = page.url().includes("/login");
  if (!stillOnLogin) {
    console.error("FAIL: 401인데 /login에서 벗어남:", page.url());
    failures++;
  }

  await page.screenshot({ path: OUT_PNG, fullPage: true });
  console.log(`saved ${OUT_PNG}`);

  // D — 성공: 올바른 사번/PIN -> setToken -> /ask 이동(보호화면 정상 통과).
  await page.getByTestId("login-emp-no").fill("EMP-ACTIVE");
  await page.getByTestId("login-pin").fill("1234");
  await page.getByTestId("login-submit").click();
  await page.waitForURL(/\/ask/, { timeout: 5000 }).then(
    () => console.log("PASS: 올바른 사번/PIN -> /ask 이동(로그인 성공)"),
    () => {
      console.error("FAIL: 올바른 사번/PIN인데 /ask로 이동하지 않음:", page.url());
      failures++;
    },
  );

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
