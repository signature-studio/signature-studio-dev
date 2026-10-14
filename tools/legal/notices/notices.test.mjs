// THIRD_PARTY_NOTICES (LGL-3) 単体テスト。素材 (FL) 不要。実 registry / records の整合 + 合成データでのネガティブコントロール。
//   node --test tools/legal/notices/notices.test.mjs
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import zlib from "node:zlib";
import {
  checkArtifact, checkRegistry, decodeText, validateFontAsset, generate, INCOMPLETE_MARK, loadFonts, loadRecords, loadRegistry, NOTICES_HTML, NOTICES_TXT, REL_LICENSE_NAME, REPO, scanFile, sha256, validateRecord, walk,
} from "./lib.mjs";

const tmp = mkdtempSync(path.join(process.env.RUNNER_TEMP ?? tmpdir(), "notices-test-"));
test.after(() => rmSync(tmp, { recursive: true, force: true }));
const clone = (x) => structuredClone(x);

// ---- 合成データ -------------------------------------------------------------------------------------------------
const LIC = "Permission is hereby granted, free of charge...\n";
function synthRecord(id = "foo-1.0", extra = {}) {
  return {
    schema: 1, id, name: "Foo", version: "1.0", provenance: "build-script",
    upstream: { url: "https://example.invalid/foo-1.0.tar.gz", archive: "foo-1.0.tar.gz", sha256: "a".repeat(64) },
    license: { spdx: "MIT", files: [{ path: "LICENSE", sha256: sha256(LIC), text: LIC }] },
    build: { script: "tools/legal/notices/record.mjs", toolchain: "emcc 6.0.12", targets: ["wasm32"], args: [{ step: "configure", args: "./configure --disable-shared" }], patches: [] },
    ...extra,
  };
}
const FL_TEXT = "FL notice text\n";
const flRaw = (text) => Buffer.from(`\uFEFF${text.replace(/\n/g, "\r\n")}`, "utf8"); // FL 同梱表記は BOM 付き UTF-8 + CRLF
function synthRegistry({ attribution } = {}) {
  return {
    schema: 1, flVersion: "test", forbiddenArgs: ["--enable-gpl"], ignoreLicensePaths: [],
    flTexts: [{ file: "foo.txt", block: "block00001_DATA.bin", size: flRaw(FL_TEXT).length, sha256: sha256(flRaw(FL_TEXT)) }],
    forbidden: [{ id: "gpl-bits", reason: "GPL 系は同梱不可", signatures: ["GPLBITS-MARKER"] }],
    components: [
      { id: "foo", name: "Foo", kind: "rebuilt", bundled: true, license: "MIT", copyleft: "none", records: ["foo-1.0"], flTexts: ["foo.txt"], coveredBy: ["tools/legal/notices"], signatures: ["FOO-MARKER"], ...(attribution ? { attribution } : {}) },
      { id: "bar", name: "Bar", kind: "rebuilt", bundled: false, reason: "PoC のみ", license: "BSD", copyleft: "none", records: [], flTexts: [], coveredBy: [], signatures: ["BAR-MARKER"] },
    ],
  };
}
const synthFonts = () => ({ schema: 1, files: [{ path: "a/x.ttf", size: 10, status: "origin-unverified" }, { path: "b/y.ttf", size: 20, status: "license-text", licenseFile: "OFL.txt" }] });
function flDirWith(text = FL_TEXT) {
  const d = mkdtempSync(path.join(tmp, "fl-"));
  mkdirSync(path.join(d, "extracted"));
  writeFileSync(path.join(d, "extracted", "block00001_DATA.bin"), flRaw(text));
  return d;
}

// ---- 実 registry / records ---------------------------------------------------------------------------------------
test("実 registry / records / fonts は整合している (素材不要の CI 検査と同じ)", () => {
  const r = checkRegistry({ registry: loadRegistry(), records: loadRecords(), fonts: loadFonts() });
  assert.deepEqual(r.problems, []);
});

test("実 registry: tools/shared/oss の build.sh は全て component に紐づく / FreeType の謝辞がある", () => {
  const reg = loadRegistry();
  const ft = reg.components.find((c) => c.id === "freetype");
  assert.match(ft.attribution, /The FreeType Project \(www\.freetype\.org\)/);
  assert.equal(reg.flTexts.length, 15);
});

test("ライセンスファイル名の判定: 実在する名前に一致し、notices の自作ファイルには一致しない", () => {
  for (const f of ["tools/ipp/shim/fft/pffft/LICENSE.pffft.txt", "x/COPYING", "x/COPYING.LGPLv2.1", "x/LICENSE.md", "x/license.txt", "x/NOTICE", "x/OFL.txt", "x/COPYING3"]) assert.match(f, REL_LICENSE_NAME, f);
  for (const f of ["tools/legal/notices/notices.test.mjs", "THIRD_PARTY_NOTICES.txt", "docs/LEGAL.md", "x/licenses.json", "x/noticeboard.ts"]) assert.doesNotMatch(f, REL_LICENSE_NAME, f);
});

test("実 records に GPL 系フラグが無い", () => {
  for (const [id, rec] of loadRecords()) {
    for (const a of rec.build.args) assert.doesNotMatch(a.args, /--enable-(gpl|nonfree|version3)/, id);
  }
});

// ---- validateRecord ----------------------------------------------------------------------------------------------
test("validateRecord: 正常な記録は通る", () => assert.deepEqual(validateRecord(synthRecord(), "foo-1.0"), []));

for (const [name, mutate, re] of [
  ["upstream sha256/commit が無い", (r) => { delete r.upstream.sha256; }, /sha256.*commit/],
  ["ライセンス本文が無い", (r) => { r.license.files = []; }, /license\.files が空/],
  ["ライセンス本文の改ざん", (r) => { r.license.files[0].text = "tampered\n"; }, /sha256 が本文と一致しない/],
  ["configure 引数が空", (r) => { r.build.args = []; }, /build\.args/],
  ["禁止フラグ --enable-gpl", (r) => { r.build.args[0].args += " --enable-gpl"; }, /禁止フラグ --enable-gpl/],
  ["patches 未記載", (r) => { delete r.build.patches; }, /build\.patches/],
  ["toolchain 無し", (r) => { r.build.toolchain = ""; }, /toolchain/],
  ["build.script が repo に無い", (r) => { r.build.script = "no/such/build.sh"; }, /build\.script が repo に無い/],
  ["パッチの sha256 不一致", (r) => { r.build.patches = [{ path: "tools/shared/oss/freetype/ftgrays_lp64.patch", sha256: "0".repeat(64) }]; }, /変わっている/],
]) {
  test(`validateRecord NEG: ${name}`, () => {
    const r = synthRecord();
    mutate(r);
    const p = validateRecord(r, "foo-1.0");
    assert.ok(p.some((m) => re.test(m)), JSON.stringify(p));
  });
}

// ---- checkRegistry のネガティブコントロール -------------------------------------------------------------------------
const ctx = (over = {}) => ({ registry: synthRegistry(), records: new Map([["foo-1.0", synthRecord()]]), fonts: synthFonts(), repoRoot: REPO, tracked: [], buildDirs: [], ...over });

test("checkRegistry: 合成の正常系は通る", () => assert.deepEqual(checkRegistry(ctx()).problems, []));

test("checkRegistry NEG: 記録なしの同梱 OSS (records/<id>.json 欠落)", () => {
  const p = checkRegistry(ctx({ records: new Map() })).problems;
  assert.ok(p.some((m) => /records\/foo-1\.0\.json が無い/.test(m)), JSON.stringify(p));
});

test("checkRegistry NEG: bundled=true の rebuilt に records が無い", () => {
  const reg = synthRegistry();
  reg.components[0].records = [];
  assert.ok(checkRegistry(ctx({ registry: reg })).problems.some((m) => /records が無い/.test(m)));
});

test("checkRegistry NEG: 登録のない OSS 再ビルドスクリプト (tools/shared/oss/newlib/build.sh)", () => {
  const p = checkRegistry(ctx({ buildDirs: ["tools/shared/oss/newlib"] })).problems;
  assert.ok(p.some((m) => /newlib\/build\.sh.*coveredBy に無い/.test(m)), JSON.stringify(p));
});

test("checkRegistry NEG: 登録のない repo 内ライセンスファイル (vendored OSS)", () => {
  const p = checkRegistry(ctx({ tracked: ["third_party/zlib/LICENSE", "tools/legal/notices/x/COPYING"] })).problems;
  assert.ok(p.some((m) => /third_party\/zlib\/LICENSE/.test(m)));
  assert.ok(!p.some((m) => /notices\/x\/COPYING/.test(m)), "coveredBy 配下は許容");
});

test("checkRegistry NEG: 孤児の記録 / bundled=false の reason 欠落 / 不正な font status / FL pin の参照切れ", () => {
  const reg = synthRegistry();
  delete reg.components[1].reason;
  reg.flTexts.push({ file: "orphan.txt", block: "b", size: 1, sha256: "b".repeat(64) });
  const fonts = synthFonts();
  fonts.files[0].status = "ok";
  const p = checkRegistry(ctx({ registry: reg, fonts, records: new Map([["foo-1.0", synthRecord()], ["stray-1", synthRecord("stray-1")]]) })).problems;
  for (const re of [/stray-1.*参照されていない/, /bundled=false には reason/, /status "ok"/, /orphan\.txt.*参照されていない/]) assert.ok(p.some((m) => re.test(m)), String(re));
});

test("checkRegistry NEG: copyleft=strong (GPL) は同梱不可", () => {
  const reg = synthRegistry();
  reg.components[0].copyleft = "strong";
  assert.ok(checkRegistry(ctx({ registry: reg })).problems.some((m) => /同梱不可/.test(m)));
});

test("checkRegistry NEG: fonts.json が無い", () => assert.ok(checkRegistry(ctx({ fonts: null })).problems.some((m) => /fonts\.json が無い/.test(m))));

// ---- decodeText / generate ------------------------------------------------------------------------------------------
test("decodeText: BOM 除去・CRLF 正規化・末尾改行 1 つ", () => assert.equal(decodeText(Buffer.from("\uFEFFa\r\nb\r\n\r\n")), "a\nb\n"));

test("generate: 謝辞・component・upstream の記録・FL 同梱表記が出力され、決定的", () => {
  const att = "Portions of this software are copyright © 2016 The FreeType Project (www.freetype.org).  All rights reserved.";
  const flDir = flDirWith();
  const args = { registry: synthRegistry({ attribution: att }), records: new Map([["foo-1.0", synthRecord()]]), fonts: synthFonts(), flDir, strict: true, repoRoot: REPO };
  const a = generate(args);
  const b = generate(args);
  assert.equal(a.txt, b.txt);
  assert.equal(a.html, b.html);
  assert.ok(a.model.complete);
  for (const needle of [att, "[component:foo]", "sha256:" + "a".repeat(64), "Build [configure]: ./configure --disable-shared", "Patches applied: none", "Permission is hereby granted", FL_TEXT.trim(), "origin unverified", "a/x.ttf"]) {
    assert.ok(a.txt.includes(needle), needle);
  }
  assert.ok(!a.txt.includes("[component:bar]"), "bundled=false は本文に出ない");
  assert.match(a.txt, /bar: Bar — PoC のみ/);
  assert.ok(a.html.includes("<!doctype html>") && a.html.includes("c-foo"));
  assert.ok(!a.txt.includes(INCOMPLETE_MARK));
});

test("generate: LGPL (weak) は差し替え・再ビルドの案内と configure 引数・パッチを出す", () => {
  const reg = synthRegistry();
  reg.components[0].copyleft = "weak";
  const rec = synthRecord("foo-1.0", {});
  rec.build.patches = [{ path: "tools/shared/oss/freetype/ftgrays_lp64.patch", sha256: sha256("x"), summary: "demo patch" }];
  const { txt } = generate({ registry: reg, records: new Map([["foo-1.0", rec]]), fonts: synthFonts(), flDir: flDirWith(), repoRoot: REPO });
  assert.match(txt, /Lesser General Public License/);
  assert.match(txt, /can be rebuilt/);
  assert.match(txt, /ftgrays_lp64\.patch sha256:.*demo patch/);
});

test("generate: FL 素材が無いと不完全 (INCOMPLETE) になり、strict なら例外", () => {
  const args = { registry: synthRegistry(), records: new Map([["foo-1.0", synthRecord()]]), fonts: synthFonts(), flDir: path.join(tmp, "nonexistent"), repoRoot: REPO };
  const r = generate(args);
  assert.equal(r.model.complete, false);
  assert.ok(r.txt.split("\n").some((l) => l.startsWith(INCOMPLETE_MARK)));
  assert.throws(() => generate({ ...args, strict: true }), (e) => e.code === "NOTICES_INCOMPLETE");
});

test("generate NEG: FL 同梱表記の内容が pin と違うと不完全 (FL 更新の検出)", () => {
  const r = generate({ registry: synthRegistry(), records: new Map([["foo-1.0", synthRecord()]]), fonts: synthFonts(), flDir: flDirWith("changed\n"), repoRoot: REPO });
  assert.equal(r.model.complete, false);
  assert.match(r.model.missing.join("\n"), /sha256 mismatch/);
});

// ---- 成果物の走査 -------------------------------------------------------------------------------------------------
function artifact({ registry = synthRegistry(), records = new Map([["foo-1.0", synthRecord()]]), files = {}, notices = true, staleDigest = false } = {}) {
  const d = mkdtempSync(path.join(tmp, "art-"));
  if (notices) {
    const g = generate({ registry, records, fonts: synthFonts(), flDir: flDirWith(), repoRoot: REPO });
    const txt = staleDigest ? g.txt.replace(/Registry digest: sha256:[0-9a-f]+/, `Registry digest: sha256:${"0".repeat(64)}`) : g.txt;
    writeFileSync(path.join(d, NOTICES_TXT), txt);
    writeFileSync(path.join(d, NOTICES_HTML), g.html);
  }
  for (const [k, v] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(d, k)), { recursive: true });
    writeFileSync(path.join(d, k), v);
  }
  return { d, entries: walk(d), registry, records };
}
const check = (a, over = {}) => checkArtifact({ entries: a.entries, registry: a.registry, records: a.records, fonts: synthFonts(), repoRoot: REPO, ...over });

test("checkArtifact: NOTICES があり、記録のある OSS の痕跡だけなら通る", () => {
  const a = artifact({ files: { "wasm/foo.wasm": Buffer.from("xx FOO-MARKER yy") } });
  const r = check(a);
  assert.deepEqual(r.problems, []);
  assert.deepEqual(Object.keys(r.detected), ["foo"]);
});

test("checkArtifact NEG: NOTICES が成果物に無い", () => {
  const a = artifact({ notices: false, files: { "index.html": "<html>" } });
  const p = check(a).problems;
  assert.ok(p.some((m) => m.includes(`${NOTICES_TXT} が成果物に無い`)));
  assert.ok(p.some((m) => m.includes(`${NOTICES_HTML} が成果物に無い`)));
});

test("checkArtifact NEG: NOTICES が不完全 / 古い (registry digest 不一致)", () => {
  const stale = check(artifact({ staleDigest: true }));
  assert.ok(stale.problems.some((m) => /一致しない/.test(m)));
  const reg = synthRegistry();
  const d = mkdtempSync(path.join(tmp, "art-"));
  const g = generate({ registry: reg, records: new Map([["foo-1.0", synthRecord()]]), fonts: synthFonts(), flDir: path.join(tmp, "none"), repoRoot: REPO });
  writeFileSync(path.join(d, NOTICES_TXT), g.txt);
  writeFileSync(path.join(d, NOTICES_HTML), g.html);
  const inc = checkArtifact({ entries: walk(d), registry: reg, records: new Map([["foo-1.0", synthRecord()]]), fonts: synthFonts() });
  assert.ok(inc.problems.some((m) => /不完全/.test(m)), JSON.stringify(inc.problems));
});

test("checkArtifact NEG: 記録なしの同梱 OSS (registry の bundled=false なのに痕跡がある)", () => {
  const p = check(artifact({ files: { "wasm/bar.wasm": Buffer.from("..BAR-MARKER..") } })).problems;
  assert.ok(p.some((m) => /bar の痕跡 "BAR-MARKER".*bundled=false/.test(m)), JSON.stringify(p));
});

test("checkArtifact NEG: bundled=true でも再ビルド記録が無い/無効だと失敗", () => {
  const a = artifact({ files: { "w.wasm": Buffer.from("FOO-MARKER") } });
  const noRec = check(a, { records: new Map() });
  assert.ok(noRec.problems.some((m) => /foo.*再ビルド記録 foo-1\.0 が無効/.test(m)), JSON.stringify(noRec.problems));
  const bad = synthRecord();
  bad.build.args = [];
  const badRec = check(a, { records: new Map([["foo-1.0", bad]]) });
  assert.ok(badRec.problems.some((m) => /無効/.test(m)));
});

test("checkArtifact NEG: 同梱禁止 (GPL 系) の痕跡", () => {
  const p = check(artifact({ files: { "x/lame.wasm": Buffer.from("....GPLBITS-MARKER....") } })).problems;
  assert.ok(p.some((m) => /同梱禁止の部品 gpl-bits/.test(m)), JSON.stringify(p));
});

test("scanFile: 圧縮 (.br / .gz) は展開後を走査し、chunk 境界を跨ぐ signature も検出", () => {
  const d = mkdtempSync(path.join(tmp, "scan-"));
  const sigs = [{ id: "foo", sig: "FOO-MARKER" }];
  writeFileSync(path.join(d, "a.br"), zlib.brotliCompressSync(Buffer.from("....FOO-MARKER....")));
  writeFileSync(path.join(d, "a.gz"), zlib.gzipSync(Buffer.from("....FOO-MARKER....")));
  assert.equal(scanFile(path.join(d, "a.br"), sigs).length, 1);
  assert.equal(scanFile(path.join(d, "a.gz"), sigs).length, 1);
  const CH = 16 * 1024 * 1024;
  const big = Buffer.alloc(CH + 64, 0x41);
  big.write("FOO-MARKER", CH - 4); // 境界を跨ぐ
  writeFileSync(path.join(d, "big.bin"), big);
  assert.equal(scanFile(path.join(d, "big.bin"), sigs).length, 1);
  writeFileSync(path.join(d, "clean.bin"), Buffer.alloc(1024, 0x41));
  assert.equal(scanFile(path.join(d, "clean.bin"), sigs).length, 0);
});

test("checkArtifact: NOTICES 自身の文字列は走査対象外 (謝辞に部品名が出ても誤検知しない)", () => {
  const reg = synthRegistry({ attribution: "FOO-MARKER acknowledgement" });
  const a = artifact({ registry: reg, files: { "index.html": "<html>" } });
  assert.deepEqual(check(a).problems, []);
});

// ---- font-asset (GUI-9 の代替フォント Open Sans / Barlow, #616) ------------------------------------------------------
const realFont = (id) => clone(loadRegistry().components.find((c) => c.id === id));

test("実 registry: Open Sans / Barlow は font-asset として同梱登録され、NOTICES に版・取得元・sha256・OFL 本文・著作権が出る", () => {
  const reg = loadRegistry();
  const flDir = process.env.FL_WIN64_DIR;
  const { txt, model } = generate({ registry: reg, records: loadRecords(), fonts: loadFonts(), flDir });
  for (const [id, ver, copy, file, sha] of [
    ["open-sans", "3.003", "The Open Sans Project Authors", "OpenSans-Regular.ttf", "c53aceea2dcf5b4098099c0c4d0a061d17e178a049317b42a422b1a9f7f8eb59"],
    ["barlow", "1.408", "The Barlow Project Authors", "Barlow-Regular.ttf", "95aa02c7c43096e0dd44d787ba6216864a67157e402adab59b35572e0c1577ea"],
  ]) {
    const c = reg.components.find((x) => x.id === id);
    assert.equal(c.kind, "font-asset");
    assert.equal(c.bundled, true);
    assert.equal(c.version, ver);
    assert.deepEqual(validateFontAsset(c), []);
    assert.ok(model.components.some((x) => x.id === id));
    for (const needle of [`[component:${id}] ${c.name} ${ver}`, copy, file, `sha256:${sha}`, c.fontAsset.commit, "SIL OPEN FONT LICENSE Version 1.1", "Reserved Font Name: none"]) assert.ok(txt.includes(needle), `${id}: ${needle}`);
  }
});

test("validateFontAsset: 正常な実データは通る", () => assert.deepEqual(validateFontAsset(realFont("barlow")), []));

for (const [name, mutate, re] of [
  ["取得スクリプトの検証 sha256 と食い違う", (c) => { c.fontAsset.files[0].sha256 = "1".repeat(64); }, /取得スクリプトの検証値に無い/],
  ["別の部品の sha256 を当てる (名前と sha256 の対応が食い違う)", (c) => { c.fontAsset.files[0].sha256 = realFont("barlow").fontAsset.files[0].sha256; }, /取得スクリプトの検証値に無い/],
  ["ライセンス本文の改ざん", (c) => { c.fontAsset.licenseFile.text += "x"; }, /licenseFile の sha256 が本文と一致しない/],
  ["ライセンス本文が無い", (c) => { delete c.fontAsset.licenseFile.text; }, /licenseFile .* が無い/],
  ["upstream が commit 固定でない", (c) => { c.fontAsset.commit = "main"; }, /40hex/],
  ["ファイル URL が commit 固定でない", (c) => { c.fontAsset.files[0].url = c.fontAsset.files[0].url.replace(c.fontAsset.commit, "main"); }, /url が commit 固定でない/],
  ["著作権表示が無い", (c) => { delete c.fontAsset.copyright; }, /fontAsset\.copyright/],
  ["版が無い", (c) => { delete c.version; }, /version が無い/],
  ["release-guard の allowlist に無い sha256", (c) => { c.fontAsset.files[0].sha256 = "2".repeat(64); c.coveredBy = ["tools/legal/notices/e2e.sh"]; }, /allowlist\.json に無い/],
  ["取得スクリプトが無い", (c) => { c.coveredBy = ["tools/gui/test"]; }, /取得スクリプト/],
  ["fontAsset 自体が無い", (c) => { delete c.fontAsset; }, /fontAsset が無い/],
]) {
  test(`validateFontAsset NEG: ${name}`, () => {
    const c = realFont("open-sans");
    mutate(c);
    const p = validateFontAsset(c);
    assert.ok(p.some((m) => re.test(m)), JSON.stringify(p));
  });
}

test("checkRegistry NEG: 実 registry の font-asset を壊すと check が失敗する (component 経由で届く)", () => {
  const reg = loadRegistry();
  reg.components.find((c) => c.id === "barlow").fontAsset.files[0].sha256 = "3".repeat(64);
  const p = checkRegistry({ registry: reg, records: loadRecords(), fonts: loadFonts() }).problems;
  assert.ok(p.some((m) => /component barlow: .*取得スクリプトの検証値に無い/.test(m)), JSON.stringify(p));
});

test("release-guard allowlist: font-asset の sha256 は window のみ許容 (file / chunk 一致は許容しない)", () => {
  const al = JSON.parse(readFileSync(path.join(REPO, "tools/legal/release-guard/allowlist.json"), "utf8")).entries;
  for (const id of ["open-sans", "barlow"]) {
    const sum = loadRegistry().components.find((c) => c.id === id).fontAsset.files[0].sha256;
    const e = al.filter((x) => x.sha256 === sum);
    assert.equal(e.length, 1, id);
    assert.deepEqual(e[0].kinds, ["window"]);
    assert.ok(e[0].reason.length > 10);
  }
});

function fontArtifact(reg, { bytes, notices = true }) {
  const g = { registry: reg, records: loadRecords(), fonts: loadFonts() };
  const d = mkdtempSync(path.join(tmp, "fontart-"));
  if (notices) {
    const r = generate({ ...g, flDir: process.env.FL_WIN64_DIR });
    writeFileSync(path.join(d, NOTICES_TXT), r.txt);
    writeFileSync(path.join(d, NOTICES_HTML), r.html);
  }
  writeFileSync(path.join(d, "fonts/OpenSans-Regular.ttf".split("/").pop()), bytes);
  return { ...g, entries: walk(d), repoRoot: REPO };
}
const FONT_FILE = path.join(REPO, "tools/gui/work/OpenSans-Regular.ttf");
const haveFont = (() => { try { return readFileSync(FONT_FILE).length > 0; } catch { return false; } })();
const haveFl = Boolean(process.env.FL_WIN64_DIR);

test("checkArtifact: 実 OpenSans-Regular.ttf (fetch_fonts.sh の取得物) を載せると open-sans を検出し、NOTICES があれば通る", { skip: !(haveFont && haveFl) && "tools/gui/work (fetch_fonts.sh) と FL_WIN64_DIR が要る" }, () => {
  const a = fontArtifact(loadRegistry(), { bytes: readFileSync(FONT_FILE) });
  const r = checkArtifact(a);
  assert.deepEqual(r.problems, []);
  assert.deepEqual(Object.keys(r.detected), ["open-sans"]);
});

test("checkArtifact NEG: 実 OpenSans-Regular.ttf を載せ registry が bundled=false だと失敗 (登録なしの同梱フォント)", { skip: !(haveFont && haveFl) && "tools/gui/work (fetch_fonts.sh) と FL_WIN64_DIR が要る" }, () => {
  const reg = loadRegistry();
  const c = reg.components.find((x) => x.id === "open-sans");
  c.bundled = false;
  c.reason = "test";
  const a = fontArtifact(reg, { bytes: readFileSync(FONT_FILE) });
  const p = checkArtifact(a).problems;
  assert.ok(p.some((m) => /open-sans の痕跡.*bundled=false/.test(m)), JSON.stringify(p));
});

test("checkArtifact NEG: 同じフォントでも 1 バイト違えば font-asset としては検出されない (範囲外の明示)", { skip: !(haveFont && haveFl) && "tools/gui/work (fetch_fonts.sh) と FL_WIN64_DIR が要る" }, () => {
  const b = Buffer.from(readFileSync(FONT_FILE));
  b[b.length - 1] ^= 1;
  const r = checkArtifact(fontArtifact(loadRegistry(), { bytes: b }));
  assert.deepEqual(Object.keys(r.detected), []);
});

// ---- CLI -----------------------------------------------------------------------------------------------------------
test("CLI: check は実 repo で PASS、--artifact に NOTICES が無い dir を渡すと exit 1", () => {
  const cli = path.join(REPO, "tools/legal/notices/cli.mjs");
  const ok = spawnSync("node", [cli, "check"], { encoding: "utf8" });
  assert.equal(ok.status, 0, ok.stderr);
  assert.match(ok.stdout, /notices-check: PASS/);
  const d = mkdtempSync(path.join(tmp, "cliart-"));
  writeFileSync(path.join(d, "index.html"), "<html>");
  const ng = spawnSync("node", [cli, "check", "--artifact", d], { encoding: "utf8" });
  assert.equal(ng.status, 1);
  assert.match(ng.stderr, /THIRD_PARTY_NOTICES\.txt が成果物に無い/);
});

test("CLI: 引数不正は exit 2", () => {
  const r = spawnSync("node", [path.join(REPO, "tools/legal/notices/cli.mjs"), "bogus"], { encoding: "utf8" });
  assert.equal(r.status, 2);
  assert.ok(execFileSync);
});
