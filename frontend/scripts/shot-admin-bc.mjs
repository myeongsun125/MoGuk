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

  // B — 대시보드
  await page.goto(`http://localhost:${PORT}/admin/dashboard`);
  await page.getByTestId("kpi-grid").waitFor({ state: "visible", timeout: 5000 });
  await page.getByTestId("per-worker-list").waitFor({ state: "visible", timeout: 5000 });
  await page.screenshot({ path: DASHBOARD_PNG, fullPage: true });
  console.log(`saved ${DASHBOARD_PNG}`);

  // C — 승인큐
  await page.goto(`http://localhost:${PORT}/admin/glossary`);
  await page.getByTestId("term-list").waitFor({ state: "visible", timeout: 5000 });
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
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
