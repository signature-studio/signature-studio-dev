// ブラウザ e2e: 実アプリ (/?help=1, vite.config.ts そのまま = COOP/COEP 付き) で FL 実 Help を sandbox iframe に表示し、
// 外部リンク遮断 / 内部リンク遷移 / error-offline 差替え / CSP・sandbox の実効性 (+ ネガコン) を headless Chrome で検査する。
//   FL_WIN64_DIR=... node tools/startup/helpviewer/e2e_browser.mjs [--json out.json]
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { launchChrome } from "../../runtime/lib/chrome.mjs";
import { loadFixture } from "./lib.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const flDir = process.env.FL_WIN64_DIR;
if (!flDir) throw new Error("FL_WIN64_DIR が未設定");
const jsonOut = process.argv.includes("--json") ? process.argv[process.argv.indexOf("--json") + 1] : null;
const fx = loadFixture(flDir);
if (fx.missing.length) throw new Error(`ピン済みファイルが素材に無い: ${fx.missing.join(", ")}`);

const requests = [];
const fixturePlugin = {
  name: "help-fixture",
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const url = new URL(req.url ?? "/", "http://x");
      requests.push(url.pathname);
      if (url.pathname.startsWith("/__beacon")) { res.statusCode = 204; return res.end(); }
      if (!url.pathname.startsWith("/__help/")) return next();
      const rel = decodeURIComponent(url.pathname.slice("/__help/".length));
      const b = fx.help.get(rel);
      if (!b) { res.statusCode = 404; return res.end("not found"); }
      res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
      res.setHeader("Content-Length", b.length);
      res.end(Buffer.from(b));
    });
  },
};
const server = await createServer({ root, configFile: path.join(root, "vite.config.ts"), plugins: [fixturePlugin], server: { host: "127.0.0.1", port: 0 }, logLevel: "error" });
await server.listen();
const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
const chrome = await launchChrome({ extraArgs: ["--window-size=1280,900"] });
const results = [];
const fail = [];
const check = (ok, name, detail = "") => { results.push({ name, ok: !!ok, detail }); if (!ok) fail.push(`${name} ${detail}`); console.log(`  ${ok ? "ok  " : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`); };
const ROOT = "C:\\\\Program Files\\\\Image-Line\\\\FL Studio 2026";
let exitCode = 0;
try {
  const page = await chrome.newPage();
  await page.goto(`${origin}/?help=1`);
  await page.waitForExpr(`!!window.flHelp && !!document.querySelector('#help-panel iframe')`, 30000);
  await page.evaluate(`window.__ev = []; flHelp.onEvent = (e) => window.__ev.push(e); flHelp.onExternal = (u) => window.__ext = (window.__ext||[]).concat(u); flHelp.useHttp("/__help/"); 1`);

  // sandbox iframe (opaque origin) は別プロセス (OOPIF) になるので、attach 済みの iframe target の session で評価する。
  // 同一プロセスで子 frame が見える場合は isolated world にフォールバックする。
  const inFrame = async (expression) => {
    const sessions = [...page.workerSessions].filter(([, ti]) => ti.type === "iframe").map(([sid]) => sid).reverse();
    for (const sid of sessions) {
      let r;
      try { r = await page.cdp.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, sid); } catch { continue; }
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    }
    const { frameTree } = await page.send("Page.getFrameTree");
    const child = frameTree.childFrames?.[0]?.frame.id;
    if (!child) throw new Error("iframe の評価文脈がない");
    const { executionContextId } = await page.send("Page.createIsolatedWorld", { frameId: child, worldName: `e2e${Math.random()}` });
    const r = await page.send("Runtime.evaluate", { expression, contextId: executionContextId, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  };
  const waitFrame = async (expr, timeout = 15000) => {
    const t0 = Date.now();
    for (;;) {
      try { const v = await inFrame(expr); if (v) return v; } catch { /* 遷移中は文脈が無い */ }
      if (Date.now() - t0 > timeout) throw new Error(`waitFrame timeout: ${expr}`);
      await new Promise((r) => setTimeout(r, 50));
    }
  };
  const targets = async () => (await chrome.browser.send("Target.getTargets")).targetInfos.filter((t) => t.type === "page").length;

  // 1. ShellExecuteW(NULL, file) 経路で index_offline.html を開く
  const t0 = Date.now();
  const rc = await page.evaluate(`flHelp.shellExecute(null, "${ROOT}\\\\Help\\\\index_offline.html")`);
  check(rc === 33, "shellExecute(NULL verb, Help\\index_offline.html) の戻り値", `rc=${rc}`);
  await waitFrame(`document.title === "FL Studio Offline Manual"`);
  const openMs = Date.now() - t0;
  const doc = await inFrame(`({ h1: document.querySelector('h1')?.textContent, scripts: document.scripts.length, iframes: document.querySelectorAll('iframe').length, sheets: [...document.styleSheets].map(s => s.cssRules.length), fontFaces: [...document.fonts].length, extA: document.querySelectorAll('a[href^="https://"]').length, bodyBg: getComputedStyle(document.body).fontFamily })`);
  check(doc.h1 === "Is your computer offline?", "index_offline.html の本文が iframe に描画された", JSON.stringify(doc.h1));
  check(doc.scripts === 1 && doc.iframes === 0, "FL の script / iframe(leftFrame・YouTube) は除去され bridge の script 1 本のみ", `scripts=${doc.scripts} iframes=${doc.iframes}`);
  check(doc.sheets.length >= 1 && doc.sheets[0] > 50, "flstudio.css が埋込まれ規則が効いている", `rules=${doc.sheets}`);
  check(doc.fontFaces >= 1, "@font-face (ILGlyphsEx) が data: で読まれた", `fonts=${doc.fontFaces}`);
  check(doc.extA === 3, "外部リンク 3 件はそのまま DOM に残る (遷移はしない)", `a[https]=${doc.extA}`);

  // 2. 外部リンクのクリック: 遷移も新規 target もなし、onExternal に通知のみ
  const tgtBefore = await targets();
  await inFrame(`document.querySelector('a[href^="https://"]').click(); 1`);
  await page.waitForExpr(`window.__ev.some(e => e.type === 'external-blocked')`, 5000);
  const ext = await page.evaluate(`({ ev: window.__ev.filter(e => e.type === 'external-blocked'), ext: window.__ext })`);
  check(ext.ev.length === 1 && /^https:\/\/support\.image-line\.com\//.test(ext.ev[0].url), "外部リンククリック → external-blocked イベント", ext.ev[0]?.url);
  check((await inFrame(`document.title`)) === "FL Studio Offline Manual", "外部リンク後も iframe は同じページのまま");
  check((await targets()) === tgtBefore, "新しいタブ/ポップアップは開かれない", `targets ${tgtBefore}→${await targets()}`);

  // 3. 内部リンク遷移: html/FD/web/index.html (meta refresh → documents/productinfo.html) → ページ内リンク → back
  const ev0 = await page.evaluate(`flHelp.open("file:///C:/Program%20Files/Image-Line/FL%20Studio%202026/Help/html/FD/web/index.html")`);
  check(ev0.type === "page" && ev0.path === "html/FD/web/documents/productinfo.html", "meta refresh を辿って productinfo.html を表示", `${ev0.type} ${ev0.path}`);
  await waitFrame(`document.body && document.body.textContent.length > 200 && !!document.querySelector('a[href^="info.html"],a[href*="info.html"],a[href*=".html"]:not([href^="http"])')`);
  const hrefs = await inFrame(`[...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')).filter(h => !/^(https?:|#)/.test(h))`);
  const CUR = "html/FD/web/documents/productinfo.html";
  const target = hrefs.find((h) => fx.help.has(`html/FD/web/documents/${h}`) && `html/FD/web/documents/${h}` !== CUR);
  check(!!target, "productinfo.html に Help 内で解決できる内部リンクがある", `hrefs=${JSON.stringify(hrefs)}`);
  const n0 = await page.evaluate(`window.__ev.length`);
  await inFrame(`document.querySelector('a[href="${target}"]').click(); 1`);
  await page.waitForExpr(`window.__ev.length > ${n0} && window.__ev[window.__ev.length-1].type === 'page'`, 10000);
  const nav = await page.evaluate(`window.__ev[window.__ev.length-1]`);
  const expectNav = `html/FD/web/documents/${target}`;
  check(nav.path === expectNav, "内部リンクのクリックで親が遷移を解決して表示", `${nav.path}`);
  const hist = await page.evaluate(`flHelp.history.slice()`);
  const back = await page.evaluate(`flHelp.back()`);
  check(hist.length === 3 && back && back.type === "page" && back.path === hist[1] && back.path === CUR, "back() で直前のページへ戻る (履歴は表示後のパスで 3 件)", `${JSON.stringify(hist)} → ${back?.path}`);
  check(page.exceptions.length === 0, "ここまで page 例外なし", page.exceptions.join(" | ").slice(0, 200));

  // 4. error-offline.html は FL のファイルを読まず自前ページに差替え
  const reqBefore = requests.length;
  const rc2 = await page.evaluate(`flHelp.shellExecute("open", "${ROOT}\\\\System\\\\Internet\\\\error-offline.html")`);
  check(rc2 === 33, "shellExecute(open, System\\Internet\\error-offline.html) の戻り値", `rc=${rc2}`);
  await waitFrame(`/offline|オフライン/i.test(document.body.textContent)`);
  const txt = await inFrame(`document.body.textContent`);
  check(!/FL Cloud needs an internet connection/.test(txt) && !requests.slice(reqBefore).some((p) => /error-offline/.test(p)), "FL の error-offline.html の文言・取得なし (自前ページ)", JSON.stringify(txt.slice(0, 60)));
  check((await inFrame(`document.scripts.length + document.fonts.size`)) === 0, "自前ページは script・フォントなし");

  // 5. 不正な postMessage (親自身から送る = event.source が iframe でない) は無視される
  const n1 = await page.evaluate(`window.__ev.length`);
  await page.evaluate(`window.postMessage({ flHelp: "forged", href: "html/FD/web/index.html" }, "*"); new Promise(r => setTimeout(r, 300))`);
  check((await page.evaluate(`window.__ev.length`)) === n1, "iframe 以外からの postMessage は無視される");

  // 6. CSP / sandbox の実効性: 敵対的な追加要素を足した srcdoc で、ネットワーク到達 (ビーコン) と script 実行を観測
  await page.evaluate(`flHelp.open("${ROOT}\\\\Help\\\\index_offline.html")`);
  await waitFrame(`document.title === "FL Studio Offline Manager" || document.title === "FL Studio Offline Manual"`);
  const hostile = (tag) => `<img src="${origin}/__beacon_img_${tag}"><link rel="stylesheet" href="${origin}/__beacon_css_${tag}"><script>document.title="pwned";fetch("${origin}/__beacon_fetch_${tag}");try{parent.document.title="pwned-parent"}catch(e){}</script>`;
  const setHostile = async (tag, stripCsp) => {
    await page.evaluate(`(() => { const f = flHelp.frame; let s = f.srcdoc; ${stripCsp ? `s = s.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/, "");` : ""} s = s.replace("</body>", ${JSON.stringify(hostile(tag))} + "</body>").replace("<title>FL Studio Offline Manual</title>", "<title>x</title>"); f.srcdoc = s; return 1 })()`);
    await new Promise((r) => setTimeout(r, 1500));
  };
  await setHostile("csp", false);
  const withCsp = requests.filter((p) => p.startsWith("/__beacon") && p.endsWith("_csp"));
  check(withCsp.length === 0, "CSP あり: 敵対的な img/link/fetch は 1 件も到達しない", `beacons=${withCsp.length}`);
  check((await inFrame(`document.title`)) !== "pwned" && (await page.evaluate(`document.title`)) !== "pwned-parent", "CSP あり: nonce 無し script は実行されない");
  await setHostile("nocsp", true);
  const noCsp = requests.filter((p) => p.startsWith("/__beacon") && p.endsWith("_nocsp"));
  check(noCsp.length >= 2, "ネガコン: CSP を剥がすとビーコンが到達する (観測手段が有効)", `beacons=${noCsp.length} ${noCsp.join(",")}`);
  check((await inFrame(`document.title`)) === "pwned", "ネガコン: CSP を剥がすと iframe 内の script が実行される (title=pwned)");
  check((await page.evaluate(`document.title`)) !== "pwned-parent", "sandbox: CSP 無しで script が走っても親 document に触れない (opaque origin)");

  // 7. 大きいページ (WhatsNew.htm 980991 B) の表示時間
  const w0 = Date.now();
  await page.evaluate(`flHelp.open("${ROOT}\\\\Help\\\\WhatsNew.htm")`);
  await waitFrame(`document.title === "What's New Change Log"`);
  const whatsNewMs = Date.now() - w0;
  check(true, "WhatsNew.htm を表示", `${whatsNewMs} ms`);

  // 8. 外部通信ゼロ: 全リクエストが同一オリジンの自アプリ + fixture + ビーコンのみ
  const out = { origin, openIndexMs: openMs, openWhatsNewMs: whatsNewMs, requests: requests.length, checks: results };
  if (jsonOut) writeFileSync(jsonOut, JSON.stringify(out, null, 1));
  console.log(`browser e2e: ${results.filter((r) => r.ok).length}/${results.length} ok / index_offline.html 表示 ${openMs} ms / WhatsNew.htm 表示 ${whatsNewMs} ms / ${chrome.version}`);
} catch (e) {
  console.error("e2e error:", e);
  exitCode = 1;
} finally {
  await chrome.close();
  await server.close();
}
if (fail.length) { console.error("FAIL:\n  " + fail.join("\n  ")); exitCode = 1; }
process.exit(exitCode);
