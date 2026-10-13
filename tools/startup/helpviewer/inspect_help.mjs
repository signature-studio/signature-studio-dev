// FL 実 Help (素材 fl-win64) の全 HTML ページに prepareHelpPage を通し、安全性・資源・リンクを実測する。
//   FL_WIN64_DIR=... node tools/startup/helpviewer/inspect_help.mjs [--json out.json]
// 失敗条件: ピンした 56 ファイルのどれかが素材に無い / 変換後に unsafeFindings が残る / ネガコンが通る / error-offline 差替えが FL の内容を含む。
import { writeFileSync } from "node:fs";
import { buildNoticeSrcdoc, classifyShellExecute, filesFromMap, prepareHelpPage, resolveLink, classifyTarget } from "../../../src/runtime/help_viewer.ts";
import { loadFixture, unsafeFindings } from "./lib.mjs";

const flDir = process.env.FL_WIN64_DIR;
if (!flDir) throw new Error("FL_WIN64_DIR が未設定 (tools/startup/helpviewer/env.sh を source する)");
const jsonOut = process.argv.includes("--json") ? process.argv[process.argv.indexOf("--json") + 1] : null;
const fail = [];
const check = (ok, msg) => { if (!ok) fail.push(msg); return ok; };

const fx = loadFixture(flDir);
check(fx.missing.length === 0 && fx.found === 56, `ピン 56 件のうち素材に無い: ${fx.missing.join(", ")}`);
const files = filesFromMap(fx.help);
const decode = (b) => new TextDecoder().decode(b);
const ROOT = "C:\\Program Files\\Image-Line\\FL Studio 2026";

const pages = [...fx.help.keys()].filter((p) => /\.html?$/i.test(p)).sort();
const rows = [];
let seq = 0;
const rand = () => `n${(seq++).toString(16).padStart(6, "0")}`;
for (const p of pages) {
  const raw = fx.help.get(p);
  const nonce = `n${seq.toString(16).padStart(6, "0")}`;
  const t0 = performance.now();
  const r = await prepareHelpPage(files, p, { rand });
  const ms = performance.now() - t0;
  const rawHtml = decode(raw);
  const hrefs = [...rawHtml.matchAll(/<a\b[^>]*\shref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi)].map((m) => m[1] ?? m[2] ?? m[3]);
  const kinds = { internal: 0, internalMissing: 0, fragment: 0, external: 0, other: 0 };
  for (const h of hrefs) {
    const t = resolveLink(p, h);
    if (h.trim().startsWith("#")) kinds.fragment++;
    else if (t.kind === "external") kinds.external++;
    else if (t.kind === "help") { kinds.internal++; if (!fx.help.has(t.path) && ![...fx.help.keys()].some((k) => k.toLowerCase() === t.path.toLowerCase())) kinds.internalMissing++; }
    else kinds.other++;
  }
  const finds = unsafeFindings(r.srcdoc, nonce);
  check(finds.length === 0, `${p}: unsafeFindings ${finds.join(",")}`);
  const rawFinds = unsafeFindings(rawHtml, nonce);
  rows.push({
    page: p, rawBytes: raw.length, outBytes: r.stats.bytes, ms: Math.round(ms * 10) / 10, title: r.title, refresh: r.refresh,
    inlined: r.stats.inlinedResources, missing: r.stats.missingResources, skippedLarge: r.stats.skippedLarge,
    scriptsRemoved: r.stats.scriptsRemoved, embedsRemoved: r.stats.embedsRemoved, externalRefsBlocked: r.stats.externalRefsBlocked,
    links: kinds, rawFindings: rawFinds.length, findings: finds.length,
  });
}

// ネガコン: 無加工の FL ページは検査に引っかかる (検査自体が効いている)。index_offline.html は script / iframe / 外部リンクを持つ
const idx = rows.find((r) => r.page === "index_offline.html");
check(idx && idx.rawFindings >= 4, `ネガコン: 無加工 index_offline.html の検出数 ${idx?.rawFindings} (期待 >= 4)`);
const neg = unsafeFindings(decode(fx.help.get("index_offline.html")), "x");
const negFindings = neg.length;

// index_offline.html の期待構造
if (check(idx, "index_offline.html が無い")) {
  check(idx.title === "FL Studio Offline Manual", `title=${idx.title}`);
  check(idx.scriptsRemoved === 2 && idx.embedsRemoved === 2, `script/embeds = ${idx.scriptsRemoved}/${idx.embedsRemoved} (期待 2/2: scripts.js + inline, leftFrame + YouTube iframe)`);
  const IMG_GLOB = ["img_glob/external_link.svg", "img_glob/global_kbd.svg", "img_glob/listbullet2.gif", "img_glob/listbullet3.gif"];
  check(idx.inlined === 3 && JSON.stringify([...idx.missing].sort()) === JSON.stringify(IMG_GLOB), `inlined=${idx.inlined} missing=${idx.missing} (期待: flstudio.css + woff + ttf の 3 件・欠落は基本インストールに無い img_glob 4 件のみ)`);
}

// error-offline.html の差替え: FL のファイルを読まず、自前ページは FL の内容を含まない
const eo = decode(fx.errorOffline);
check(!/<script/i.test(eo), "error-offline.html に script がある (想定外)");
const dec = classifyShellExecute(null, `${ROOT}\\System\\Internet\\error-offline.html`);
check(dec.action === "help" && dec.target.kind === "offline-notice" && dec.result === 33, "error-offline.html が offline-notice に分類されない");
const font = /base64,([A-Za-z0-9+/]{64})/.exec(eo)?.[1];
const notices = ["offline", "not-found", "no-files", "external-blocked", "unsupported"].flatMap((k) => ["en", "ja"].map((l) => buildNoticeSrcdoc(k, l)));
check(font && notices.every((s) => !s.includes(font) && !/gilroy|FL Cloud needs/i.test(s)), "自前ページに FL の内容 (埋込フォント / 文言) が混入");
check(classifyTarget(`${ROOT}\\Help\\index_offline.html`).kind === "help", "index_offline.html が help に分類されない");

const sum = (k) => rows.reduce((a, r) => a + r[k], 0);
const out = {
  fl: "26.1.7.5653", pinned: 56, found: fx.found, pages: rows.length,
  totals: { rawBytes: sum("rawBytes"), outBytes: sum("outBytes"), inlined: sum("inlined"), missing: rows.flatMap((r) => r.missing.map((m) => `${r.page}→${m}`)).length, externalRefsBlocked: sum("externalRefsBlocked"), scriptsRemoved: sum("scriptsRemoved"), embedsRemoved: sum("embedsRemoved") },
  negativeControl: { rawIndexOfflineFindings: negFindings }, errorOffline: { bytes: fx.errorOffline.length, scripts: 0 },
  rows,
};
if (jsonOut) writeFileSync(jsonOut, JSON.stringify(out, null, 1));
console.log(`pages ${rows.length} / pinned ${fx.found}/56 / unsafe findings after prepare: ${rows.reduce((a, r) => a + r.findings, 0)} / negative control (raw index_offline.html): ${negFindings} findings`);
for (const r of rows) console.log(`  ${r.page.padEnd(52)} ${String(r.rawBytes).padStart(7)}→${String(r.outBytes).padStart(7)} B  ${String(r.ms).padStart(6)} ms  inl ${r.inlined} miss ${r.missing.length} ext ${r.externalRefsBlocked} scr ${r.scriptsRemoved} emb ${r.embedsRemoved}  links int ${r.links.internal}(miss ${r.links.internalMissing}) frag ${r.links.fragment} ext ${r.links.external} oth ${r.links.other}${r.refresh ? `  refresh→${r.refresh}` : ""}`);
if (fail.length) { console.error("FAIL:\n  " + fail.join("\n  ")); process.exit(1); }
console.log("inspect_help: PASS");
