// help_viewer.ts の純ロジック単体テスト (合成フィクスチャのみ。FL 由来ファイルは使わない)。
//   node --test tools/startup/helpviewer/test/
import test from "node:test";
import assert from "node:assert/strict";
import {
  FL_INSTALL_ROOT, buildNoticeSrcdoc, classifyShellExecute, classifyTarget, filesFromMap, prepareHelpPage, resolveLink,
} from "../../../../src/runtime/help_viewer.ts";
import { unsafeFindings } from "../lib.mjs";

const ROOT = "C:\\Program Files\\Image-Line\\FL Studio 2026";
const enc = (s) => new TextEncoder().encode(s);
const PNG = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);
const det = () => { let n = 0; return () => `r${(n++).toString(16).padStart(4, "0")}`; };

test("classifyTarget: Windows パス / file: URL / 大文字小文字 / フラグメント", () => {
  assert.deepEqual(classifyTarget(`${ROOT}\\Help\\index_offline.html`), { kind: "help", path: "index_offline.html", fragment: "" });
  assert.deepEqual(classifyTarget(`c:\\program files\\image-line\\fl studio 2026\\HELP\\html\\a\\B.htm#sec`), { kind: "help", path: "html/a/B.htm", fragment: "sec" });
  assert.deepEqual(classifyTarget(`${ROOT}\\Help\\`), { kind: "help", path: "index_offline.html", fragment: "" });
  assert.deepEqual(classifyTarget("file:///C:/Program%20Files/Image-Line/FL%20Studio%202026/Help/WhatsNew.htm#x"), { kind: "help", path: "WhatsNew.htm", fragment: "x" });
  assert.deepEqual(classifyTarget("file://localhost/C:/Program%20Files/Image-Line/FL%20Studio%202026/Help/a%20b.html"), { kind: "help", path: "a b.html", fragment: "" });
  assert.equal(FL_INSTALL_ROOT, "C:/Program Files/Image-Line/FL Studio 2026");
});

test("classifyTarget: error-offline.html は自前ページへ差替え / 外部 URL / 拒否", () => {
  assert.deepEqual(classifyTarget(`${ROOT}\\System\\Internet\\error-offline.html`), { kind: "offline-notice" });
  assert.deepEqual(classifyTarget("file:///C:/Program%20Files/Image-Line/FL%20Studio%202026/System/Internet/error-offline.html"), { kind: "offline-notice" });
  assert.equal(classifyTarget("https://support.image-line.com/redirect/x").kind, "external");
  for (const bad of [
    "", "   ", "a\0b", "relative/page.html", "javascript:alert(1)", "data:text/html,x", "ftp://x/y",
    `${ROOT}\\Help\\..\\..\\Windows\\win.ini`, `${ROOT}\\Help\\..\\Plugins\\x.html`, `${ROOT}\\System\\Languages\\ja.moe`,
    "D:\\Program Files\\Image-Line\\FL Studio 2026\\Help\\index_offline.html", "C:\\Other\\Help\\index_offline.html",
    "file://server/share/Help/x.html", "file:///C:/Program%20Files/Image-Line/FL%20Studio%202026/Help/%E0%A4%A.html",
    "file:///C:/Program%20Files/Image-Line/FL%20Studio%202026/Help/%2e%2e/%2e%2e/x.html",
  ]) assert.equal(classifyTarget(bad).kind, "unsupported", bad);
});

test("resolveLink: 相対 / .. / フラグメントのみ / ルート相対 / 脱出拒否 / 外部", () => {
  assert.deepEqual(resolveLink("html/FD/web/index.html", "documents/info.html#a"), { kind: "help", path: "html/FD/web/documents/info.html", fragment: "a" });
  assert.deepEqual(resolveLink("html/FD/web/documents/info.html", "../../../../flstudio.css"), { kind: "help", path: "flstudio.css", fragment: "" });
  assert.deepEqual(resolveLink("html/x.html", "#top"), { kind: "help", path: "html/x.html", fragment: "top" });
  assert.deepEqual(resolveLink("html/x.html", "/html/y.htm"), { kind: "help", path: "html/y.htm", fragment: "" });
  assert.deepEqual(resolveLink("a.html", "dir%20x/b.html?q=1"), { kind: "help", path: "dir x/b.html", fragment: "" });
  assert.equal(resolveLink("a.html", "../x.html").kind, "unsupported");
  assert.equal(resolveLink("html/a.html", "%2e%2e/%2e%2e/x.html").kind, "unsupported");
  assert.equal(resolveLink("a.html", "..%5c..%5cx.html").kind, "unsupported");
  assert.equal(resolveLink("a.html", "x:y.html").kind, "unsupported");
  assert.deepEqual(resolveLink("a.html", "//cdn.example/x.js"), { kind: "external", url: "https://cdn.example/x.js" });
  assert.equal(resolveLink("a.html", "mailto:x@y").kind, "unsupported");
  assert.equal(resolveLink("a.html", "").kind, "unsupported");
});

test("classifyShellExecute: verb NULL は open / 他 verb は pass / http(s) は 33 の no-op", () => {
  const h = `${ROOT}\\Help\\index_offline.html`;
  for (const v of [null, "", "open", "OPEN"]) {
    const d = classifyShellExecute(v, h);
    assert.equal(d.action, "help");
    assert.equal(d.result, 33);
  }
  assert.deepEqual(classifyShellExecute("open", "https://www.image-line.com/x"), { action: "external-noop", url: "https://www.image-line.com/x", result: 33 });
  assert.equal(classifyShellExecute(null, "https://x.test").action, "external-noop");
  assert.equal(classifyShellExecute("runas", h).action, "pass");
  assert.equal(classifyShellExecute("explore", h).action, "pass");
  assert.equal(classifyShellExecute(null, `${ROOT}\\Plugins\\tool.exe`).action, "pass");
  assert.equal(classifyShellExecute(null, `${ROOT}\\System\\Internet\\error-offline.html`).action, "help");
});

test("filesFromMap: 大文字小文字を無視して引く", async () => {
  const f = filesFromMap(new Map([["Html/A.htm", enc("x")]]));
  assert.equal((await f.read("html/a.htm")).length, 1);
  assert.equal(await f.read("html/b.htm"), null);
});

const FIXTURE = {
  "index.html": `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Fixture &amp; Co</title>
<meta http-equiv="Content-Security-Policy" content="default-src *">
<meta http-equiv="refresh" content="0; url=documents/next.html#frag">
<base href="https://evil.example/">
<link rel="stylesheet" href="css/site.css"><link rel="stylesheet" href="https://evil.example/x.css"><link rel="icon" href="favicon.ico">
<script src="evil.js"></script><script>alert(1)</script>
<style>body{background:url(img/bg.png)} @import url(https://evil.example/y.css);</style></head>
<body onload="steal()" background="img/bg.png">
<h1 id="top" onclick="x()">Hello</h1>
<img src="img/a.png" alt="a"><img src="img/missing.png" alt="m"><img src="https://evil.example/t.gif" alt="t">
<div style="background:url('img/a.png')">s</div>
<a href="documents/next.html" target="_blank">int</a> <a href="https://evil.example/">ext</a> <a href="#top">frag</a>
<iframe src="https://www.youtube.com/embed/x"></iframe><iframe src="a"></iframe>text-after
<object data="x"><param name="a" value="b"></object><embed src="y"><form action="https://evil.example/"><input type="image" src="img/a.png"></form>
</body></html>`,
  "css/site.css": `@font-face{font-family:g;src:url('../fonts/g.woff') format('woff'),url(../fonts/none.ttf)}
.b{background:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'/>")} .c{background:url(https://evil.example/z.png)}`,
  "img/a.png": PNG, "img/bg.png": PNG, "fonts/g.woff": Uint8Array.from([1, 2, 3]),
};
const fixtureFiles = (extra = {}) => filesFromMap(new Map(Object.entries({ ...FIXTURE, ...extra }).map(([k, v]) => [k, typeof v === "string" ? enc(v) : v])));

test("prepareHelpPage: 安全化 + 資源の埋込み + 統計", async () => {
  const rand = det();
  const p = await prepareHelpPage(fixtureFiles(), "index.html", { rand, fragment: "top" });
  assert.ok(p);
  const nonce = "r0000";
  assert.equal(p.token, "r0001");
  assert.deepEqual(unsafeFindings(p.srcdoc, nonce), []);
  assert.equal(p.title, "Fixture & Co");
  assert.equal(p.refresh, "documents/next.html#frag");
  assert.deepEqual(p.stats.missingResources.sort(), ["fonts/none.ttf", "img/missing.png"]);
  assert.equal(p.stats.scriptsRemoved, 2);
  assert.equal(p.stats.embedsRemoved, 5); // iframe×2 + object (本体の param は object ごと) + embed + base
  assert.ok(p.stats.externalRefsBlocked >= 4);
  assert.equal(p.stats.inlinedResources, 6); // site.css + a.png(img) + bg.png(<style>) + a.png(style attr) + g.woff + a.png(input)
  assert.ok(p.srcdoc.includes("data:image/png;base64,iVBORwECAw=="));
  assert.ok(p.srcdoc.includes("data:font/woff;base64,AQID"));
  assert.ok(!p.srcdoc.includes('target="_blank"'));
  assert.ok(p.srcdoc.includes('href="documents/next.html"')); // 内部リンクは bridge が拾う
  assert.ok(p.srcdoc.includes("text-after"));
  assert.ok(p.srcdoc.includes(`<script nonce="${nonce}">`));
  assert.ok(p.srcdoc.includes('go("top")'));
  assert.ok(p.srcdoc.includes(`script-src 'nonce-${nonce}'`) && p.srcdoc.includes("default-src 'none'"));
});

test("ネガコン: 無加工の HTML は unsafeFindings が検出する (検査自体が効いている)", () => {
  const raw = FIXTURE["index.html"];
  const found = unsafeFindings(raw, "r0000");
  for (const k of ["script without nonce", "embedding/base/form tag", "event handler attribute", "external reference", "@import", "CSP is not the first element"]) assert.ok(found.includes(k), k);
});

test("prepareHelpPage: フラグメント経由の </script> 注入を JS 文字列内で無害化", async () => {
  const f = filesFromMap(new Map([["a.html", enc("<p>x</p>")]]));
  const p = await prepareHelpPage(f, "a.html", { rand: det(), fragment: '"</script><img src=x onerror=alert(1)>' });
  assert.equal([...p.srcdoc.matchAll(/<script\b/gi)].length, 1);
  assert.ok(!/<\/script><img/i.test(p.srcdoc));
  assert.ok(p.srcdoc.includes("\\u003c/script>"));
});

test("prepareHelpPage: 無い / 巨大資源 / 文字コード", async () => {
  assert.equal(await prepareHelpPage(fixtureFiles(), "nope.html"), null);
  const big = await prepareHelpPage(fixtureFiles(), "index.html", { rand: det(), maxResourceBytes: 5 });
  assert.ok(big.stats.skippedLarge.includes("img/a.png") && !big.srcdoc.includes("iVBORwEC"));
  const sj = await prepareHelpPage(filesFromMap(new Map([["s.html", Uint8Array.from([...enc('<meta charset="shift_jis"><p>'), 0x82, 0xa0, ...enc("</p>")])]])), "s.html", { rand: det() });
  assert.ok(sj.srcdoc.includes("あ"));
});

test("prepareHelpPage: 自己終了 script / 大文字タグ / コメント内タグ", async () => {
  const f = filesFromMap(new Map([["a.html", enc('<SCRIPT SRC="x"/><P>keep</P><!-- <script>bad()</script> --><SCRIPT>alert(1)</SCRIPT><STYLE>p{color:red}</STYLE>')]]));
  const p = await prepareHelpPage(f, "a.html", { rand: det() });
  assert.deepEqual(unsafeFindings(p.srcdoc, "r0000"), []);
  assert.ok(p.srcdoc.includes("<P>keep</P>") && p.srcdoc.includes("<style>p{color:red}</style>"));
  assert.ok(!p.srcdoc.includes("bad()") || p.srcdoc.includes("<!--") === false);
});

test("buildNoticeSrcdoc: script なし・detail はエスケープ・FL 由来物なし", () => {
  for (const kind of ["offline", "not-found", "no-files", "external-blocked", "unsupported"]) for (const lang of ["en", "ja"]) {
    const s = buildNoticeSrcdoc(kind, lang, '<img src=x onerror=alert(1)>');
    assert.ok(!/<script|<img|base64|@font-face/i.test(s), `${kind}/${lang}`);
    assert.ok(s.includes("default-src 'none'") && s.includes("&lt;img"));
  }
  assert.ok(buildNoticeSrcdoc("offline", "ja").includes("オフライン"));
});
