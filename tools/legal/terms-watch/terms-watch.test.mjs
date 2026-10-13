// node --test tools/legal/terms-watch/   (素材・外部ネットワーク不要。ローカル http サーバと合成文書を使う)
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { deflateRawSync } from "node:zlib";
import { ackDocs, exitCodeFor, extractSection, htmlToText, loadLedger, locateFlFile, locateNsisLicense, normalizeText, renderLedgerMd, rtfToText, runCheck, SourceError } from "./lib.mjs";
import { NsisError, nsisLicenseCandidates, readNsisHeader } from "./nsis.mjs";

const CLI = path.join(import.meta.dirname, "cli.mjs");
const tmp = mkdtempSync(path.join(process.env.RUNNER_TEMP ?? os.tmpdir(), "tw-test-"));
test.after(() => rmSync(tmp, { recursive: true, force: true }));

const BODY = "The Licensee shall not reverse engineer, decompile or disassemble the Software. ".repeat(40);
const page = ({ nonce = "a", extra = "", body = BODY, charset = "utf-8" } = {}) =>
  `<!doctype html><html><head><meta charset="${charset}"><title>Terms</title><script>var n="${nonce}"</script></head><body>` +
  `<header>Cart ${nonce}</header><nav>menu ${nonce}</nav><main><h1>Terms of Use</h1><p>${body}${extra}</p></main><footer>© ${nonce}</footer></body></html>`;

test("normalizeText: 空白・符号化差は同一、語句の変更は別", () => {
  const a = normalizeText("It’s “ok” — fine…  \n\tdone\u00a0here\u200b.");
  const b = normalizeText("It's \"ok\" - fine...\ndone here.");
  assert.equal(a, b);
  assert.notEqual(normalizeText("shall not"), normalizeText("shall now"));
  assert.notEqual(normalizeText("Reverse"), normalizeText("reverse"));
  assert.equal(normalizeText("Ｔｅｒｍｓ"), "Terms");
});

test("htmlToText: script/style/head 除去・実体参照・chrome 除去", () => {
  const h = "<html><head><title>T</title><style>a{}</style></head><body><nav>NAV</nav><p>a&nbsp;&amp;&#233;&#x41;&rsquo;s</p><script>x()</script><footer>F</footer></body></html>";
  assert.equal(normalizeText(htmlToText(h)), "T NAV a &éA's F");
  assert.equal(normalizeText(htmlToText(h, { stripChrome: true })), "T a &éA's");
});

test("rtfToText: cp1252・\\u・段落・destination 除去・リスト番号", () => {
  const rtf = String.raw`{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}{\colortbl ;\red0;}{\*\generator Riched20}{\pard {\listtext\f1 1.\tab}Caf\'e9 \u8212?dash\bullet x\par next\line two\'92s \~ end\par}}`;
  assert.equal(normalizeText(rtfToText(rtf)), "1. Café -dash•x next two's end");
});

test("extractSection: start/end/last・マーカ欠落は SourceError", () => {
  const t = "nav\nSTART\nbody1\nEND\nbody2\nEND\ntail";
  assert.equal(extractSection(t, { start: "^START$", end: "^END$" }), "START\nbody1\n");
  assert.equal(extractSection(t, { start: "^START$", end: "^END$", endMode: "last", endInclusive: true }), "START\nbody1\nEND\nbody2\nEND");
  assert.throws(() => extractSection(t, { start: "^NOPE$" }), SourceError);
  assert.throws(() => extractSection(t, { start: "^START$", end: "^NOPE$" }), SourceError);
});

test("runCheck(url): NEW → UNCHANGED → CHANGED → PENDING → ack → UNCHANGED、ノイズ/符号化差では変わらず、エラーは台帳不変", async () => {
  let cur = { status: 200, type: "text/html; charset=utf-8", body: Buffer.from(page()) };
  const srv = http.createServer((req, res) => {
    res.writeHead(cur.status, { "content-type": cur.type });
    res.end(cur.body);
  });
  await new Promise((r) => srv.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${srv.address().port}/terms`;
  const src = { id: "t", vendor: "v", title: "t", kind: "url", url, format: "html", start: "^\\s*Terms of Use\\s*$", mustContain: ["reverse engineer"], minChars: 1000, version: "Rev (\\d+)" };
  const ledger = { schema: 1, docs: {} };
  const run = (now) => runCheck({ sources: [src], ledger, ctx: {}, now });
  try {
    let [r] = await run("2026-10-13T00:00:00Z");
    assert.equal(r.status, "NEW");
    const h0 = r.sha256;
    cur.body = Buffer.from(page({ nonce: "zzz" }).replace("<p>", "<p>\n  ").replace(/\. /g, ".\r\n"));
    [r] = await run("2026-10-14T00:00:00Z");
    assert.equal(r.status, "UNCHANGED", "nonce・空白差で変わってはならない");
    cur.type = "text/html; charset=windows-1252";
    cur.body = Buffer.from(page({ charset: "windows-1252", body: BODY.replace("Software", "Softwar&eacute;") }).replace("Softwar&eacute;", "Software"), "latin1");
    [r] = await run("2026-10-14T00:00:00Z");
    assert.equal(r.status, "UNCHANGED", "charset 差で変わってはならない");

    cur = { status: 200, type: "text/html; charset=utf-8", body: Buffer.from(page({ extra: " Rev 2: new clause." })) };
    [r] = await run("2026-11-01T00:00:00Z");
    assert.equal(r.status, "CHANGED");
    assert.equal(r.previous.sha256, h0);
    assert.equal(r.version, "2");
    assert.equal(ledger.docs.t.history.length, 1);
    assert.equal(ledger.docs.t.pendingReview, true);
    assert.equal(exitCodeFor([r]), 1);
    [r] = await run("2026-11-02T00:00:00Z");
    assert.equal(r.status, "PENDING", "未レビューの間は同一内容でも失敗し続ける");
    assert.equal(exitCodeFor([r]), 1);
    assert.deepEqual(ackDocs(ledger, ["all"], "2026-11-03T00:00:00Z"), ["t"]);
    [r] = await run("2026-11-04T00:00:00Z");
    assert.equal(r.status, "UNCHANGED");

    const before = JSON.stringify(ledger);
    for (const bad of [{ status: 404, type: "text/html", body: Buffer.from(page()) }, { status: 200, type: "text/html", body: Buffer.from("<html>Access denied</html>") }, { status: 200, type: "text/html", body: Buffer.from(page({ body: "x".repeat(2000) })) }]) {
      cur = bad;
      [r] = await run("2026-12-01T00:00:00Z");
      assert.equal(r.status, "ERROR", r.detail);
      assert.equal(exitCodeFor([r]), 3);
    }
    assert.equal(JSON.stringify(ledger), before, "エラー時に台帳を汚さない");
    const md = renderLedgerMd(ledger, [src]);
    assert.match(md, /^<!-- 自動生成: pnpm terms-watch/);
    assert.match(md, new RegExp(ledger.docs.t.current.sha256));
  } finally {
    srv.close();
  }
});

test("locateFlFile: 内容署名で探す・曖昧は失敗・dir 無しは skip", () => {
  const d = path.join(tmp, "fl");
  mkdirSync(path.join(d, "extracted"), { recursive: true });
  const eula = `<!DOCTYPE html>\n<title>confirmation - IMAGE LINE SOFTWARE EULA</title><body>${BODY}</body>`;
  writeFileSync(path.join(d, "extracted/block00001_DATA.bin"), "garbage");
  writeFileSync(path.join(d, "extracted/block99999_DATA.bin"), eula);
  const m = { headRegex: "<title>[^<]*IMAGE LINE SOFTWARE EULA" };
  assert.equal(locateFlFile(d, m).name, "block99999_DATA.bin");
  writeFileSync(path.join(d, "extracted/block88888_DATA.bin"), eula + " (dup, 同一内容)");
  assert.throws(() => locateFlFile(d, m), /内容違い/);
  assert.throws(() => locateFlFile(path.join(tmp, "none"), m), (e) => e instanceof SourceError && e.kind === "skip");
  assert.throws(() => locateFlFile(d, { headRegex: "NOSUCH" }), /無い/);
});

test("CLI 終了コード: 0 → 0 → 1 → 1 → ack → 0、素材なし 3 (--allow-skip で 0)、引数不正 2", () => {
  const f = path.join(tmp, "doc.txt");
  const sources = path.join(tmp, "sources.json");
  const ledger = path.join(tmp, "ledger.json");
  const md = path.join(tmp, "ledger.md");
  writeFileSync(f, "The Licensee shall not reverse engineer the Software. ".repeat(30));
  writeFileSync(sources, JSON.stringify([
    { id: "doc", vendor: "V", title: "T", kind: "file", path: f, format: "text", mustContain: ["reverse engineer"], minChars: 500 },
    { id: "opt", vendor: "V", title: "O", kind: "file", pathEnv: "TW_TEST_UNSET", format: "text", minChars: 10 },
  ]));
  const env = { ...process.env, FL_WIN64_DIR: path.join(tmp, "nofl"), TERMS_WATCH_NOW: "2026-10-13T00:00:00Z" };
  delete env.TW_TEST_UNSET;
  const cli = (...a) => spawnSync("node", [CLI, ...a, "--sources", sources, "--ledger", ledger, "--md", md, "--snapshots", path.join(tmp, "snap")], { encoding: "utf8", env });
  assert.equal(cli("check").status, 3, "optional 素材なし = 検証不能");
  assert.equal(cli("check", "--allow-skip").status, 0);
  assert.equal(cli("check", "--only", "doc").status, 0);
  writeFileSync(f, readFileSync(f, "utf8").replace("shall not", "shall now"));
  const changed = cli("check", "--only", "doc");
  assert.equal(changed.status, 1);
  assert.match(changed.stdout, /CHANGED\s+doc/);
  assert.match(changed.stdout, /-The Licensee shall not|-.*shall not/);
  assert.equal(cli("check", "--only", "doc").status, 1, "ack まで失敗し続ける");
  assert.equal(JSON.parse(readFileSync(ledger, "utf8")).docs.doc.history.length, 1);
  assert.equal(cli("ack", "doc").status, 0);
  assert.equal(cli("check", "--only", "doc").status, 0);
  assert.equal(cli("check", "--only", "nosuch").status, 2);
  const sources2 = path.join(tmp, "sources2.json");
  writeFileSync(sources2, JSON.stringify(JSON.parse(readFileSync(sources, "utf8")).map((x) => ({ ...x, optional: true }))));
  const cli2 = (...a) => spawnSync("node", [CLI, ...a, "--sources", sources2, "--ledger", ledger, "--md", md, "--snapshots", path.join(tmp, "snap")], { encoding: "utf8", env });
  assert.equal(cli2("check").status, 0, "optional の素材なしは警告のみ");
  assert.equal(cli2("check", "--strict").status, 3, "--strict では optional も検証不能");
  assert.equal(cli("bogus").status, 2);
  assert.equal(cli("ack").status, 2);
  assert.equal(loadLedger(ledger).docs.doc.pendingReview, false);
});

// 合成 NSIS インストーラ (stub 4096 B + firstheader + raw deflate ヘッダ)。実 makensis での検証は nsis_e2e.sh
function fakeNsis(strings, { align = 4096, deflate = true } = {}) {
  const str = Buffer.from(strings.map((x) => x + "\0").join(""), "utf16le");
  const top = 4 + 64;
  const hdr = Buffer.alloc(top + str.length);
  const blk = (i, off, num) => { hdr.writeInt32LE(off, 4 + i * 8); hdr.writeInt32LE(num, 8 + i * 8); };
  [0, 1, 2].forEach((i) => blk(i, top, 0));
  blk(3, top, strings.length);
  blk(4, top + str.length, 0);
  [5, 6, 7].forEach((i) => blk(i, hdr.length, 0));
  str.copy(hdr, top);
  const body = deflate ? deflateRawSync(hdr) : Buffer.from("not deflate: \xff\xfe\xfd".repeat(20), "latin1");
  const fh = Buffer.alloc(32);
  fh.writeUInt32LE(0xdeadbeef, 4);
  fh.write("NullsoftInst", 8, "latin1");
  fh.writeInt32LE(hdr.length, 20);
  fh.writeInt32LE(body.length + 4, 24);
  fh.writeUInt32LE((body.length | 0x80000000) >>> 0, 28);
  return Buffer.concat([Buffer.alloc(align, 0x90), fh, body, Buffer.alloc(64, 0xcc)]);
}
const LIC = "The Licensee is prohibited from reverse engineering the Software. ".repeat(20);
const RTF = String.raw`{\rtf1\ansi{\fonttbl{\f0 Arial;}}\pard ${LIC.replaceAll(".", ".\\par")}}`;

test("nsis: ライセンス文の抽出 (形式フラグ \\x11=text / \\x12=RTF、短い文字列・フラグ無しは除外)・不正ヘッダは NsisError", () => {
  const d = path.join(tmp, "nsis1");
  mkdirSync(d, { recursive: true });
  writeFileSync(path.join(d, "a.exe"), fakeNsis(["Setup", "\x01\u8000", "\x11" + LIC, "\x12" + RTF, LIC, "short"]));
  const c = nsisLicenseCandidates(path.join(d, "a.exe"));
  assert.deepEqual(c.map((x) => x.fmt), ["text", "rtf"]);
  assert.equal(c[0].body, LIC);
  writeFileSync(path.join(d, "noalign.exe"), fakeNsis(["\x11" + LIC], { align: 1000 }));
  assert.throws(() => readNsisHeader(path.join(d, "noalign.exe")), (e) => e instanceof NsisError && /firstheader/.test(e.message));
  writeFileSync(path.join(d, "lzma.exe"), fakeNsis(["x"], { deflate: false }));
  assert.throws(() => readNsisHeader(path.join(d, "lzma.exe")), (e) => e instanceof NsisError && /deflate/.test(e.message));
  writeFileSync(path.join(d, "plain.exe"), Buffer.alloc(5000, 0x41));
  assert.throws(() => readNsisHeader(path.join(d, "plain.exe")), NsisError);
});

test("locateNsisLicense: dir 探索・RTF と text の同一本文は同一視・内容違い/無し/dir 無しの扱い", () => {
  const m = { containsRegex: ["Licensee", "reverse engineering"] };
  const d = path.join(tmp, "nsis2");
  mkdirSync(path.join(d, "sub/deep"), { recursive: true });
  writeFileSync(path.join(d, "junk.exe"), Buffer.alloc(6000, 0x41));
  writeFileSync(path.join(d, "sub/deep/a.exe"), fakeNsis(["\x11" + LIC]));
  writeFileSync(path.join(d, "sub/b.exe"), fakeNsis(["\x12" + RTF]));
  assert.equal(normalizeText(locateNsisLicense({ dir: d }, m).text), normalizeText(LIC));
  const wrapped = LIC.replaceAll(" reverse engineering", "\r\n  reverse\n engineering");
  writeFileSync(path.join(d, "sub/c.exe"), fakeNsis(["\x11" + wrapped]));
  assert.equal(locateNsisLicense({ dir: d }, m).files, 3, "折返し・空白差があっても署名に一致し、同一内容として扱う");
  writeFileSync(path.join(d, "sub/d.exe"), fakeNsis(["\x11" + LIC.replace("prohibited", "permitted")]));
  assert.throws(() => locateNsisLicense({ dir: d }, m), /内容違いで 2 種/);
  assert.throws(() => locateNsisLicense({ dir: d }, { containsRegex: ["NO SUCH WORD"] }), (e) => e instanceof SourceError && e.kind === "error" && /NSIS として読めたもの 4 件/.test(e.message));
  assert.throws(() => locateNsisLicense({ dir: path.join(tmp, "none") }, m), (e) => e instanceof SourceError && e.kind === "skip");
  assert.throws(() => locateNsisLicense({ file: path.join(tmp, "none.exe") }, m), (e) => e instanceof SourceError && e.kind === "error");
  assert.throws(() => locateNsisLicense({ file: path.join(d, "junk.exe") }, m), /firstheader/);
});

test("runCheck(nsis-license): NEW → UNCHANGED → CHANGED、textEnv の平文は同一本文なら同一ハッシュ", async () => {
  const d = path.join(tmp, "nsis3");
  mkdirSync(d, { recursive: true });
  const exe = path.join(d, "Setup.exe");
  const src = { id: "x", vendor: "V", title: "T", kind: "nsis-license", optional: true, textEnv: "TW_TEST_TEXT", match: { containsRegex: ["Licensee"] }, mustContain: ["reverse engineering"], minChars: 500 };
  const ledger = { schema: 1, docs: {} };
  const ctx = { pluginsDir: d };
  writeFileSync(exe, fakeNsis(["\x11" + LIC]));
  const r1 = (await runCheck({ sources: [src], ledger, ctx, now: "2026-10-13T00:00:00Z" }))[0];
  assert.equal(r1.status, "NEW");
  assert.match(r1.origin, /^nsis:Setup\.exe$/);
  assert.equal((await runCheck({ sources: [src], ledger, ctx }))[0].status, "UNCHANGED");
  writeFileSync(exe, fakeNsis(["\x11" + LIC.replace("prohibited", "permitted")]));
  assert.equal((await runCheck({ sources: [src], ledger, ctx }))[0].status, "CHANGED");
  writeFileSync(exe, fakeNsis(["\x11" + LIC]));
  const txt = path.join(d, "License.txt");
  writeFileSync(txt, LIC.replaceAll(" ", "\r\n"));
  process.env.TW_TEST_TEXT = txt;
  try {
    const r = (await runCheck({ sources: [src], ledger: { schema: 1, docs: {} }, ctx: { pluginsDir: path.join(tmp, "none") } }))[0];
    assert.equal(r.status, "NEW");
    assert.equal(r.sha256, r1.sha256, "平文直指定でも NSIS 経由と同一ハッシュ");
  } finally {
    delete process.env.TW_TEST_TEXT;
  }
});
