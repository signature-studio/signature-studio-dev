// text_e2e.mjs — GUI-13 (#615) headless Chrome でのテキスト描画 e2e。
//   usage: node text_e2e.mjs <oracle.ppm> <oracle.tsv> <fontdir> <wasmdir> [<baseline wasmdir = GUI_NO_FT=1 の従来ビルド>]
//   wasm (test/text_wasm_app.c + shim + gui_ft.c + libfreetype wasm32) をブラウザで走らせ、フォントを host call で遅延取得 (sha256 検証) →
//   GDI テキストを描画 → OffscreenCanvas 読み戻し / CDP スクリーンショット / metrics 表を、独立オラクル (golden/ft_oracle.c = native FreeType 直叩き) と全一致で判定する。
//   ネガティブコントロール (どれも「不一致で拒否」しなければ FAIL = exit 1):
//     N1 face 未登録 (内蔵 8x8)  N2 manifest の sha256 が不正 (検証で拒否 → 8x8)  N3 manifest・配信とも別フォント (sha256 は一致するが画素が不一致)  N4 オラクルの 1 画素 + 1 metrics セルを破壊
//   exit 0 = 全 PASS / 1 = 判定 FAIL / 2 = 実行エラー / 3 = watchdog
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { startServer, launchChrome, decodePNG } from "./cdp_lib.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, "..");
const [ORACLE_PPM, ORACLE_TSV, FONTDIR, WASMDIR, BASE_WASMDIR] = process.argv.slice(2).map((p) => path.resolve(p));
let wasmDir = WASMDIR;
const OUT = path.join(ROOT, "build", "text_e2e"); fs.mkdirSync(OUT, { recursive: true });
const W = 320, H = 120;
const CHROME = process.env.CHROME || "google-chrome";
const failures = [];
const need = (c, m) => { if (!c) { failures.push(m); console.error("[text-e2e] FAIL:", m); } };
const log = (...a) => console.log("[text-e2e]", ...a);
const wd = setTimeout(() => { console.error("[text-e2e] WATCHDOG timeout"); process.exit(3); }, Number(process.env.E2E_TIMEOUT_MS || 180000));

const ledger = fs.readFileSync(path.join(ROOT, "test", "fonts.tsv"), "utf8").split("\n").filter(Boolean).map((l) => { const [file, url, sha256, name] = l.split("\t"); return { file, url, sha256, name }; });
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
for (const e of ledger) need(sha(fs.readFileSync(path.join(FONTDIR, e.file))) === e.sha256, `font ${e.file}: on-disk sha256 != ledger (run test/fetch_fonts.sh)`);

function readPPM(file) { const b = fs.readFileSync(file); const m = /^P6\s+(\d+)\s+(\d+)\s+255\s/.exec(b.toString("latin1", 0, 32)); return { w: +m[1], h: +m[2], data: Buffer.from(b.subarray(m[0].length)) }; }
const oracle = readPPM(ORACLE_PPM); const oracleTsv = fs.readFileSync(ORACLE_TSV, "utf8").split("\n").filter(Boolean);
need(oracle.w === W && oracle.h === H, "oracle size");
const BG = [32, 32, 48];
const fgCount = (rgb) => { let n = 0; for (let i = 0; i < rgb.length; i += 3) if (rgb[i] !== BG[0] || rgb[i + 1] !== BG[1] || rgb[i + 2] !== BG[2]) n++; return n; };
const diffRGB = (a, b) => { let d = 0, first = null; for (let i = 0; i < a.length; i += 3) if (a[i] !== b[i] || a[i + 1] !== b[i + 1] || a[i + 2] !== b[i + 2]) { d++; first ??= { x: (i / 3) % W, y: Math.floor(i / 3 / W) }; } return { d, first }; };
const rgbaToRgb = (buf, bpp) => { const o = Buffer.alloc(W * H * 3); for (let p = 0; p < W * H; p++) { o[p * 3] = buf[p * bpp]; o[p * 3 + 1] = buf[p * bpp + 1]; o[p * 3 + 2] = buf[p * bpp + 2]; } return o; };

// ---- 配信 (case ごとに差し替え) ----
let cfg = { manifest: [], files: {} };
const routes = [["/wasm/", WASMDIR], ["/js/", path.join(ROOT, "build", "js")], ["/e2e/", HERE]];
const { srv, port } = await startServer(routes, (url) => {
  if (url === "/") return { type: "text/html", body: fs.readFileSync(path.join(HERE, "text_index.html")) };
  if (url === "/fonts.json") return { type: "application/json", body: JSON.stringify(cfg.manifest) };
  if (url.startsWith("/fonts/") && cfg.files[url.slice(7)]) return { type: "font/ttf", body: cfg.files[url.slice(7)] };
  return null;
});
const udd = fs.mkdtempSync(path.join(process.env.OPENCODE_TMP || os.tmpdir(), "gui-text-chrome-"));
const br = await launchChrome(CHROME, udd, 480, 360);
const cleanup = () => { br.close(); srv.close(); };

const goodFiles = Object.fromEntries(ledger.map((e) => [e.file, fs.readFileSync(path.join(FONTDIR, e.file))]));
const goodManifest = ledger.map((e) => ({ name: e.name, url: `/fonts/${e.file}`, sha256: e.sha256, file: e.file }));

async function runCase(mode, manifest, files, label) {
  cfg = { manifest, files };
  const { cdp } = br; const consoleLines = [];
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const S = (m, p) => cdp.send(m, p, sessionId);
  const h = (m) => { if (m.sessionId !== sessionId) return; if (m.method === "Runtime.consoleAPICalled") consoleLines.push(m.params.args.map((a) => a.value ?? a.description).join(" ")); if (m.method === "Runtime.exceptionThrown") consoleLines.push("EXC " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text)); };
  cdp.on(h);
  await S("Runtime.enable"); await S("Page.enable");
  await S("Emulation.setDeviceMetricsOverride", { width: 480, height: 360, deviceScaleFactor: 1, mobile: false });
  await S("Page.bringToFront");
  const E = async (expr) => { const r = await S("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error("eval failed: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text) + "\n  console tail: " + consoleLines.slice(-15).join(" | ")); return r.result.value; };
  const loaded = new Promise((res) => cdp.on((m) => { if (m.sessionId === sessionId && m.method === "Page.loadEventFired") res(); }));
  await S("Page.navigate", { url: `http://127.0.0.1:${port}/?mode=${mode}` });
  await loaded;
  const boot = await E("window.__ready");
  need(boot.crossOriginIsolated === true && boot.sab === true, `${label}: crossOriginIsolated/SAB`);
  const r = await E("window.__run()");
  const rbuf = Buffer.from(r.b64, "base64");
  const rb = rgbaToRgb(rbuf, 4);
  fs.writeFileSync(path.join(OUT, `${label}.rgba`), rbuf);
  const shot = await S("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: W, height: H, scale: 1 } });
  fs.writeFileSync(path.join(OUT, `${label}.png`), Buffer.from(shot.data, "base64"));
  const png = decodePNG(Buffer.from(shot.data, "base64"));
  const sc = rgbaToRgb(png.data, png.bpp);
  need(r.w === W && r.h === H && png.w === W && png.h === H, `${label}: size ${r.w}x${r.h} / screenshot ${png.w}x${png.h}`);
  need(r.presentSeq === r.presentDone && r.presentSeq > 0, `${label}: present not caught up (${r.presentSeq}/${r.presentDone})`);
  await cdp.send("Target.closeTarget", { targetId });
  return { r, rb, sc, consoleLines };
}

async function main() {
  // ---- 本番: フォント取得 (sha256 検証) → FreeType 描画 → オラクルと全一致 ----
  const t0 = Date.now();
  const A = await runCase("normal", goodManifest, goodFiles, "normal");
  const dRb = diffRGB(A.rb, oracle.data), dSc = diffRGB(A.sc, oracle.data);
  const fg = fgCount(oracle.data);
  const tmDiff = A.r.tm.length === oracleTsv.length ? A.r.tm.filter((l, i) => l !== oracleTsv[i]).length : -1;
  log(`normal: readback vs oracle ${dRb.d} px differ / screenshot ${dSc.d} px differ (of ${W * H}; oracle fg ${fg} px); metrics ${A.r.tm.length} rows, ${tmDiff} differing; ${Date.now() - t0} ms`);
  log("host events:", JSON.stringify(A.r.events));
  need(fg >= 800, `oracle has too few foreground pixels (${fg})`);
  need(dRb.d === 0, `OffscreenCanvas readback != oracle: ${dRb.d} px, first=${JSON.stringify(dRb.first)}`);
  need(dSc.d === 0, `screenshot != oracle: ${dSc.d} px, first=${JSON.stringify(dSc.first)}`);
  need(A.r.tm.length === 30 && tmDiff === 0, `metrics rows ${A.r.tm.length} (want 30), differing ${tmDiff}`);
  need(A.r.events.filter((e) => /sha256 ok/.test(e)).length === 2, "expected 2 fonts loaded with sha256 ok (lazy fetch via host call)");
  need(!A.r.logs.some((l) => l.includes("unavailable")), "shim reported a font fallback in the normal run");
  const diffs = [];
  // ---- N1: face 未登録 = 内蔵 8x8 ----
  { const N = await runCase("nofont", goodManifest, goodFiles, "neg1_nofont"); const d = diffRGB(N.rb, oracle.data).d, m = N.r.tm.filter((l, i) => l !== oracleTsv[i]).length + Math.abs(N.r.tm.length - oracleTsv.length);
    need(fgCount(N.rb) > 100, "N1: 8x8 run drew nothing (invalid control)"); need(d > 0 && m > 0, `N1 NEGCTL FAIL: 8x8 fallback accepted (px ${d}, metrics ${m})`); diffs.push(`N1 8x8 fallback: ${d} px / ${m} metrics rows differ -> rejected`); }
  // ---- N2: manifest の sha256 が不正 → 検証で拒否 → 8x8 フォールバック ----
  { const bad = goodManifest.map((m, i) => (i === 0 ? { ...m, sha256: "0".repeat(64) } : m)); const N = await runCase("normal", bad, goodFiles, "neg2_badsha");
    const d = diffRGB(N.rb, oracle.data).d; need(N.r.events.some((e) => /sha256 mismatch/.test(e)), "N2: no 'sha256 mismatch' event"); need(N.r.logs.some((l) => l.includes("unavailable")), "N2: shim did not report the font fallback");
    need(d > 0, `N2 NEGCTL FAIL: wrong-sha256 font accepted (${d} px)`); diffs.push(`N2 bad sha256: ${d} px differ, 'sha256 mismatch' event + shim fallback log seen -> rejected`); }
  // ---- N3: 別フォントを配信 (manifest の sha256 もそれに合わせる) → 検証は通るが画素がオラクルと不一致 ----
  { const swap = { ...goodFiles, [ledger[1].file]: goodFiles[ledger[0].file] }; const m = goodManifest.map((x, i) => (i === 1 ? { ...x, sha256: sha(goodFiles[ledger[0].file]) } : x));
    const N = await runCase("normal", m, swap, "neg3_swapfont"); const d = diffRGB(N.rb, oracle.data).d; need(N.r.events.filter((e) => /sha256 ok/.test(e)).length === 2, "N3: control invalid (fonts not loaded)");
    need(d > 0, `N3 NEGCTL FAIL: wrong font accepted (${d} px)`); diffs.push(`N3 wrong font file (sha256 consistent): ${d} px differ -> rejected`); }
  // ---- N4: オラクル側の 1 画素 + 1 metrics セルを破壊 ----
  { const o2 = Buffer.from(oracle.data); o2[(40 * W + 10) * 3] ^= 0x10; const t2 = oracleTsv.slice(); t2[7] = t2[7].replace("\t", "\t9");
    const d = diffRGB(A.rb, o2).d, m = A.r.tm.filter((l, i) => l !== t2[i]).length; need(d === 1 && m === 1, `N4 NEGCTL FAIL: tampered oracle not rejected exactly (px ${d}, metrics ${m})`); diffs.push(`N4 tampered oracle: ${d} px / ${m} metrics row differ -> rejected`); }
  // ---- 回帰: face 未登録 (8x8) の描画が、FT 未組込みの従来ビルド (GUI_NO_FT=1) と画素一致 ----
  if (BASE_WASMDIR) {
    const N = await runCase("nofont", goodManifest, goodFiles, "neg1_nofont");
    routes[0][1] = BASE_WASMDIR;
    const Bz = await runCase("nofont", goodManifest, goodFiles, "baseline_noft_nofont");
    const d = diffRGB(N.rb, Bz.rb).d, d2 = diffRGB(N.sc, Bz.sc).d;
    need(fgCount(Bz.rb) > 100, "baseline 8x8 run drew nothing (invalid control)");
    need(d === 0 && d2 === 0 && N.r.tm.join("\n") === Bz.r.tm.join("\n"), `8x8 regression: FT-linked build (no face) != baseline build: readback ${d} px / screenshot ${d2} px`);
    log(`regression OK: 8x8 path with FT linked (no face registered) == baseline GUI_NO_FT=1 build: readback ${d} px / screenshot ${d2} px differ (fg ${fgCount(Bz.rb)} px), metrics rows equal (${Bz.r.tm.length})`);
    // 回帰検査のネガコン: 本番 (FreeType) 出力を 8x8 基準と比べれば不一致になる
    const dn = diffRGB(A.rb, Bz.rb).d; need(dn > 0, "regression negctl FAIL: FreeType output equals the 8x8 baseline"); log(`negctl OK: N5 FreeType output vs 8x8 baseline: ${dn} px differ -> distinguishable`);
  }
  for (const l of diffs) log("negctl OK:", l);
}

main().then(() => { clearTimeout(wd); cleanup(); if (failures.length) { console.error(`[text-e2e] FAILED (${failures.length})`); process.exit(1); } console.log("[text-e2e] PASS"); process.exit(0); })
  .catch((e) => { clearTimeout(wd); console.error("[text-e2e] ERROR", e); cleanup(); process.exit(2); });
