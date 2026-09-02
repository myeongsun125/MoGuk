import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const ASSETS_DIR = path.resolve(FRONTEND_ROOT, "..", "docs", "assets");
const DASHBOARD_PNG = path.join(ASSETS_DIR, "v3-2-admin-dashboard.png");
const GLOSSARY_BEFORE_PNG = path.join(ASSETS_DIR, "v3-2-admin-glossary-before.png");
const GLOSSARY_AFTER_PNG = path.join(ASSETS_DIR, "v3-2-admin-glossary-after.png");
const PORT = 5187;
const VIEWPORT = { width: 1024, height: 900 };

async function main() {
  await mkdir(ASSETS_DIR, { recursive: true });
  const server = await createServer({ root: FRONTEND_ROOT, server: { port: PORT, strictPort: true } });
  await server.listen();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });
  let failures = 0;

  // B — 대시보드
  await page.goto(`http://localhost:${PORT}/admin/dashboard`);
  await page.getByTestId("kpi-grid").waitFor({ state: "visible", timeout: 5000 });
  await page.getByTestId("per-worker-list").waitFor({ state: "visible", timeout: 5000 });
  await page.screenshot({ path: DASHBOARD_PNG, fullPage: true });
  console.log(`saved ${DASHBOARD_PNG}`);

  // C — 승인큐
  await page.goto(`http://localhost:${PORT}/admin/glossary`);
  await page.getByTestId("term-list").waitFor({ state: "visible", timeout: 5000 });

  // 7차: 승인큐 nav 라벨·화면 제목 i18n 배선 확인 — ko -> vi -> ko 토글 시 실제로 바뀌는지.
  const navKo = await page.getByRole("link", { name: "승인큐" }).count();
  const h1Ko = await page.locator("h1").textContent();
  const navTextsKo = await page.locator('[data-testid="admin-nav"] a').allTextContents();
  console.log("nav texts (ko):", navTextsKo);

  await page.getByTestId("admin-lang-vi").click();
  await page.waitForTimeout(50);
  const h1Vi = await page.locator("h1").textContent();
  const navViCount = await page.locator('[data-testid="admin-nav"] a', { hasText: "Hàng chờ duyệt" }).count();
  console.log("glossary h1 ko:", h1Ko, "/ vi:", h1Vi, "/ nav(ko exists):", navKo, "/ nav(vi count):", navViCount);
  if (h1Ko === h1Vi || navViCount === 0) {
    console.error("FAIL: 승인큐 화면 제목/nav 라벨이 vi 토글 후 바뀌지 않음");
    failures++;
  } else {
    console.log("PASS: 승인큐 제목·nav 라벨 vi 토글 확인");
  }

  // #100 후속 — nav 6개 전 항목이 vi 토글 후 한글이 하나도 안 남는지(전부 labelKey 배선됐는지).
  const navTextsVi = await page.locator('[data-testid="admin-nav"] a').allTextContents();
  console.log("nav texts (vi):", navTextsVi);
  const hangulRe = /[가-힣]/;
  const stillKorean = navTextsVi.filter((t) => hangulRe.test(t));
  if (stillKorean.length > 0) {
    console.error("FAIL: vi 토글 후에도 한글이 남아있는 nav 항목:", stillKorean);
    failures++;
  } else if (navTextsVi.length !== navTextsKo.length) {
    console.error("FAIL: vi 토글 후 nav 항목 개수가 달라짐:", navTextsKo.length, "->", navTextsVi.length);
    failures++;
  } else {
    console.log("PASS: nav 전 항목(", navTextsVi.length, "개)이 vi 토글 후 한글 잔여 없음");
  }

  await page.getByTestId("admin-lang-ko").click();
  await page.waitForTimeout(50);
  const h1Back = await page.locator("h1").textContent();
  if (h1Back !== h1Ko) {
    console.error("FAIL: 승인큐 ko 복귀 후 제목이 원래대로 돌아오지 않음");
    failures++;
  } else {
    console.log("PASS: 승인큐 ko 복귀 확인");
  }
  const navTextsBack = await page.locator('[data-testid="admin-nav"] a').allTextContents();
  if (JSON.stringify(navTextsBack) !== JSON.stringify(navTextsKo)) {
    console.error("FAIL: ko 복귀 후 nav 텍스트가 원래와 다름:", navTextsBack);
    failures++;
  } else {
    console.log("PASS: ko 복귀 후 nav 텍스트 전부 원상 복구 확인");
  }

  const before = await page.getByTestId("pending-count").textContent();
  console.log("glossary before:", before);
  await page.screenshot({ path: GLOSSARY_BEFORE_PNG });

  await page.locator('[data-testid="term-row"]').first().getByTestId("approve-btn").click();
  await page.waitForTimeout(400);
  const after = await page.getByTestId("pending-count").textContent();
  console.log("glossary after approve:", after);
  await page.screenshot({ path: GLOSSARY_AFTER_PNG });

  await browser.close();
  await server.close();
  console.log(`saved ${GLOSSARY_BEFORE_PNG}`);
  console.log(`saved ${GLOSSARY_AFTER_PNG}`);

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
