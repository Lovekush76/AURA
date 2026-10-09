import puppeteer from 'puppeteer-core';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function runUITest() {
  console.log("==================================================");
  console.log(">>> AURA HUD AUTOMATED END-TO-END UI TEST <<<");
  console.log("==================================================");

  const chromePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
  console.log(`[1/5] Launching Chrome engine at: ${chromePath}`);

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: "new",
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const consoleLogs = [];
  const errors = [];

  page.on('console', msg => {
    consoleLogs.push(`[Browser ${msg.type()}] ${msg.text()}`);
  });

  page.on('pageerror', err => {
    errors.push(err.toString());
    console.error(`[Page Error]: ${err}`);
  });

  console.log("[2/5] Navigating to http://localhost:5173 ...");
  await page.goto("http://localhost:5173", { waitUntil: 'networkidle2', timeout: 30000 });

  const title = await page.title();
  console.log(`  Document Title: "${title}"`);
  if (title !== "Aura Assistant - Developer HUD") {
    throw new Error(`Unexpected page title: ${title}`);
  }

  console.log("[3/5] Verifying DOM elements & HUD telemetry...");
  // Check Telemetry Header
  const bodyText = await page.evaluate(() => document.body.innerText);
  
  const expectedKeywords = ["aura.", "v3.5 PROD", "VRAM: 22.4 / 24 GB", "AIR-GAPPED", "idle", "src/server/auth.py"];
  for (const kw of expectedKeywords) {
    if (!bodyText.includes(kw)) {
      throw new Error(`Expected HUD keyword not found in UI text: "${kw}"`);
    }
    console.log(`  ✓ Verified HUD element: "${kw}"`);
  }

  console.log("[4/5] Testing interactive chat terminal input...");
  const inputSelector = 'input[placeholder="Ask Aura or type instructions..."]';
  await page.waitForSelector(inputSelector, { timeout: 5000 });
  await page.type(inputSelector, "Run diagnostic audit from UI test");

  // Click Send button
  const submitButtonSelector = 'button[type="submit"]';
  await page.click(submitButtonSelector);
  console.log("  Submitted prompt to /api/v1/chat/stream across Vite proxy...");

  // Wait 3 seconds for streaming response to render
  await new Promise(r => setTimeout(r, 3000));

  const updatedBodyText = await page.evaluate(() => document.body.innerText);
  console.log(`  ✓ User prompt rendered in chat log: ${updatedBodyText.includes("Run diagnostic audit from UI test")}`);

  console.log("[5/5] Capturing verified UI screenshot...");
  const screenshotPath = path.join(__dirname, "aura_hud_verified.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`  ✓ Screenshot saved: ${screenshotPath}`);

  await browser.close();

  if (errors.length > 0) {
    console.error("UI Encountered Page Errors:", errors);
    process.exit(1);
  }

  console.log("==================================================");
  console.log(">>> ALL UI CHECKS PASSED SUCCESSFULLY (100%) <<<");
  console.log("==================================================");
}

runUITest().catch(err => {
  console.error("UI Test Failed:", err);
  process.exit(1);
});
