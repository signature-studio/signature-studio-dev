// フォールバック/クロスチェック用ドライバ: puppeteer-core + 既存 /usr/bin/google-chrome (CDP)。
// agent-browser と同一インターフェース。E2E_DRIVER=puppeteer で選択。
import puppeteer from "puppeteer-core";

export async function createDriver({ chrome = "/usr/bin/google-chrome", headers }) {
  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: true,
    args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"],
    defaultViewport: { width: 1280, height: 720 },
  });
  const page = await browser.newPage();
  const consoleMsgs = [];
  const errors = [];
  page.on("console", (m) =>
    consoleMsgs.push({ type: m.type(), text: m.text(), url: m.location()?.url ?? "" }),
  );
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  if (headers) await page.setExtraHTTPHeaders(headers);

  return {
    name: "puppeteer-core",
    version: `puppeteer-core ${await browser.version()}`,
    async open(url) {
      await page.goto(url, { waitUntil: "load" });
    },
    async eval(expr) {
      return page.evaluate(expr);
    },
    async click(selector) {
      await page.click(selector);
    },
    async upload(selector, files) {
      const el = await page.$(selector);
      if (!el) throw new Error(`upload: ${selector} が見つからない`);
      await el.uploadFile(...files);
    },
    async waitFn(expr, timeoutMs = 15000) {
      try {
        await page.waitForFunction(expr, { timeout: timeoutMs, polling: 100 });
        return true;
      } catch (e) {
        if (e?.name === "TimeoutError") return false;
        throw e;
      }
    },
    async mouse(action, x, y) {
      if (action === "move") await page.mouse.move(x, y);
      else if (action === "down") await page.mouse.down({ button: "left" });
      else if (action === "up") await page.mouse.up({ button: "left" });
      else throw new Error(`mouse: 未知の action ${action}`);
    },
    async press(key) {
      await page.keyboard.press(key);
    },
    async setViewport(w, h) {
      await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
    },
    async screenshot(file) {
      await page.screenshot({ path: file });
    },
    async consoleMessages() {
      return consoleMsgs.slice();
    },
    async pageErrors() {
      return errors.slice();
    },
    async close() {
      await browser.close();
    },
  };
}
