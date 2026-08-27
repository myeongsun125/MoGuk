import { chromium } from "playwright";
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const OUT_PATH = path.resolve(FRONTEND_ROOT, "..", "docs", "assets", "v2-1-ask-390.png");
const PORT = 5183;

async function main() {
  const server = await createServer({
    root: FRONTEND_ROOT,
    server: { port: PORT, strictPort: true },
  });
  await server.listen();

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(`http://localhost:${PORT}/ask`);
    await page.getByTestId("ask-input").fill("연차는 어떻게 신청하나요?");
    await page.getByTestId("ask-submit").click();
    await page.getByTestId("ask-result").waitFor({ state: "visible", timeout: 5000 });

    await mkdir(path.dirname(OUT_PATH), { recursive: true });
    await page.screenshot({ path: OUT_PATH });
    console.log(`saved ${OUT_PATH}`);
  } finally {
    await browser.close();
    await server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
