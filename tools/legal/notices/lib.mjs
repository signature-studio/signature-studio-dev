// THIRD_PARTY_NOTICES 自動生成 + 記録欠落検出 (LGL-3, #86)。事実整理であり法的助言ではない (docs/LEGAL.md §3.2・§6 緩和策 4)。
//
// 入力:
//   registry.json   同梱しうる第三者部品の台帳 (種別・ライセンス・謝辞・FL 同梱表記の pin・走査用 signature)
//   records/*.json  OSS wasm 再ビルドごとの記録 (upstream 版 / ソース sha256 or commit / ライセンス本文 / configure 引数 / パッチ / toolchain)
//                   各 build.sh が record.mjs で書く
//   fonts.json      FL 同梱フォントの一覧 (本文なし = 出所未確認)
//   FL 同梱表記      System/Texts/Licenses/*.txt 15 本 (素材。FL_WIN64_DIR の block か、そのまま置いた dir から読み sha256 で検証)
// 出力: THIRD_PARTY_NOTICES.txt / .html (時刻を入れない = 同じ入力なら同じバイト列)
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { closeSync, existsSync, openSync, readdirSync, readFileSync, readSync, statSync } from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { FL_WIN64_DIR } from "../../shared/paths.mjs";

export const HERE = import.meta.dirname;
export const REPO = path.resolve(HERE, "../../..");
// 環境変数での差し替えは e2e.sh のネガティブコントロール用 (実 registry / records を壊さずに検査する)
export const REGISTRY_PATH = process.env.NOTICES_REGISTRY ?? path.join(HERE, "registry.json");
export const RECORDS_DIR = process.env.NOTICES_RECORDS_DIR ?? path.join(HERE, "records");
export const FONTS_PATH = process.env.NOTICES_FONTS ?? path.join(HERE, "fonts.json");
export const INCOMPLETE_MARK = "[NOTICES-INCOMPLETE]";
export const NOTICES_TXT = "THIRD_PARTY_NOTICES.txt";
export const NOTICES_HTML = "THIRD_PARTY_NOTICES.html";

export const sha256 = (data) => createHash("sha256").update(data).digest("hex");

/** ライセンス本文のバイト列 -> 文字列 (BOM 除去・CRLF/CR -> LF・末尾空白行の正規化)。UTF-8 でなければ latin1 */
export function decodeText(buf) {
  if (typeof buf === "string") buf = Buffer.from(buf, "utf8");
  let s;
  try {
    s = new TextDecoder("utf-8", { fatal: true }).decode(buf);
  } catch {
    s = buf.toString("latin1");
  }
  return `${s.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").replace(/\s+$/, "")}\n`;
}

const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));
export const loadRegistry = (p = REGISTRY_PATH) => readJson(p);
export const loadFonts = (p = FONTS_PATH) => (existsSync(p) ? readJson(p) : null);

export function loadRecords(dir = RECORDS_DIR) {
  const out = new Map();
  if (!existsSync(dir)) return out;
  for (const f of readdirSync(dir).sort()) {
    if (!f.endsWith(".json")) continue;
    const rec = readJson(path.join(dir, f));
    out.set(path.basename(f, ".json"), rec);
  }
  return out;
}

const HEX64 = /^[0-9a-f]{64}$/;
const HEX40 = /^[0-9a-f]{40}$/;
const KINDS = ["rebuilt", "vendored", "fl-embedded", "font-asset"];
export const DEFAULT_FORBIDDEN_ARGS = ["--enable-gpl", "--enable-nonfree", "--enable-version3", "--enable-libx264", "--enable-libx265", "--enable-libxvid"];

/** 記録 1 件の検証。問題の文字列配列を返す (空 = OK)。repoRoot を渡すとパッチ/スクリプトの実在と sha256 も検査 */
export function validateRecord(rec, expectedId, { repoRoot = REPO, forbiddenArgs = DEFAULT_FORBIDDEN_ARGS, checkFiles = true } = {}) {
  const p = [];
  const at = (m) => p.push(`record ${expectedId}: ${m}`);
  if (rec?.schema !== 1) return [`record ${expectedId}: schema が 1 でない`];
  if (rec.id !== expectedId) at(`id "${rec.id}" がファイル名と違う`);
  for (const k of ["name", "version"]) if (!rec[k] || typeof rec[k] !== "string") at(`${k} が無い`);
  const u = rec.upstream ?? {};
  if (!u.url) at("upstream.url が無い");
  if (!(HEX64.test(u.sha256 ?? "") || HEX40.test(u.commit ?? ""))) at("upstream.sha256 (ソース tarball) か upstream.commit (git) のどちらかが必要");
  if (u.sha256 && !u.archive) at("upstream.sha256 があるのに upstream.archive が無い");
  const l = rec.license ?? {};
  if (!l.spdx) at("license.spdx が無い");
  if (!Array.isArray(l.files) || l.files.length === 0) at("license.files が空 (upstream のライセンス本文が必須)");
  for (const f of l.files ?? []) {
    if (!f.path || !f.text) at(`license.files[${f.path}] に本文が無い`);
    else if (sha256(f.text) !== f.sha256) at(`license.files[${f.path}] の sha256 が本文と一致しない`);
  }
  const b = rec.build ?? {};
  if (!b.script) at("build.script が無い");
  else if (checkFiles && !existsSync(path.join(repoRoot, b.script))) at(`build.script が repo に無い: ${b.script}`);
  if (!b.toolchain) at("build.toolchain が無い");
  if (!Array.isArray(b.args) || b.args.length === 0) at("build.args (configure/cmake 引数) が空");
  for (const a of b.args ?? []) {
    if (!a.step || typeof a.args !== "string" || !a.args.trim()) at(`build.args の項目が不正: ${JSON.stringify(a)}`);
    else
      for (const bad of forbiddenArgs) {
        if (a.args.split(/\s+/).some((t) => t === bad || t.startsWith(`${bad}=`))) at(`build.args に禁止フラグ ${bad} (${a.step})`);
      }
  }
  if (!Array.isArray(b.patches)) at("build.patches が配列でない (パッチ無しは [] を明示)");
  for (const pt of b.patches ?? []) {
    if (!pt.path || !HEX64.test(pt.sha256 ?? "")) at(`build.patches の項目が不正: ${JSON.stringify(pt)}`);
    else if (checkFiles) {
      const f = path.join(repoRoot, pt.path);
      if (!existsSync(f)) at(`パッチが repo に無い: ${pt.path}`);
      else if (sha256(readFileSync(f)) !== pt.sha256) at(`パッチ ${pt.path} が記録時から変わっている (再ビルドして記録を更新)`);
    }
  }
  return p;
}

/**
 * font-asset (GUI-9 の OSS 代替フォント。リポジトリには入れず fetch スクリプトが取得する) の検証。問題文字列の配列 (空 = OK)。
 *   - upstream は commit 固定 (url に commit を含む)・版・著作権表示・ライセンス本文 (sha256 一致)・各ファイルの size/sha256 が必須
 *   - 各ファイルの sha256 が取得スクリプト・検証値台帳 (coveredBy の存在するファイル全て) の検証値と一致すること (registry だけ更新して取得物が変わる事故の検出)
 *   - 各ファイルの sha256 が release guard の allow-list にあること (FL 同梱の旧版と窓を共有し、無いと公開物が exit 6 になる: REPORT)
 */
export function validateFontAsset(c, { repoRoot = REPO } = {}) {
  const p = [];
  const f = c.fontAsset;
  if (!f) return ["fontAsset が無い"];
  if (!c.version) p.push("version が無い");
  for (const k of ["copyright", "repository", "commit"]) if (!f[k]) p.push(`fontAsset.${k} が無い`);
  if (!HEX40.test(f.commit ?? "")) p.push("fontAsset.commit が 40hex でない (upstream は commit 固定)");
  if (typeof f.modified !== "boolean") p.push("fontAsset.modified (true/false) が無い");
  if (typeof f.reservedFontName !== "boolean") p.push("fontAsset.reservedFontName (true/false) が無い");
  const lic = f.licenseFile ?? {};
  if (!lic.path || !lic.url || !lic.text) p.push("fontAsset.licenseFile (path / url / text) が無い");
  else if (sha256(lic.text) !== lic.sha256) p.push("fontAsset.licenseFile の sha256 が本文と一致しない");
  if (lic.url && !lic.url.includes(f.commit ?? "\0")) p.push("fontAsset.licenseFile.url が commit 固定でない");
  if (!Array.isArray(f.files) || f.files.length === 0) p.push("fontAsset.files が空");
  const scripts = (c.coveredBy ?? []).map((x) => path.join(repoRoot, x)).filter((x) => existsSync(x) && statSync(x).isFile());
  const scriptText = scripts.length ? scripts.map((x) => readFileSync(x, "utf8")).join("\n") : null;
  if (scriptText === null) p.push("coveredBy に取得スクリプト (ファイル) が無い");
  const allowPath = path.join(repoRoot, "tools/legal/release-guard/allowlist.json");
  const allow = existsSync(allowPath) ? (JSON.parse(readFileSync(allowPath, "utf8")).entries ?? []) : [];
  for (const x of f.files ?? []) {
    if (!x.name || !x.url || !HEX64.test(x.sha256 ?? "") || !Number.isInteger(x.size)) {
      p.push(`fontAsset.files の項目が不正: ${JSON.stringify(x)}`);
      continue;
    }
    if (!x.url.includes(f.commit ?? "\0")) p.push(`${x.name}: url が commit 固定でない`);
    // 台帳 (fonts.tsv: file<TAB>url<TAB>sha256<TAB>face) の同名行で、名前と sha256 の対応を見る
    const paired = (scriptText ?? "").split("\n").some((l) => { const c = l.split("\t"); return c[0] === x.name && c.includes(x.sha256); });
    if (scriptText !== null && !paired) p.push(`${x.name}: sha256 が取得スクリプトの検証値に無い (台帳の同名行と食い違う。registry と取得物が食い違う)`);
    if (!allow.some((e) => e.sha256 === x.sha256 && e.reason)) p.push(`${x.name}: sha256 が release-guard の allowlist.json に無い (FL 同梱フォントと窓を共有するため公開物が guard で exit 6 になる)`);
  }
  return p;
}

/** FL 同梱表記の読み出し。flDir は FL_WIN64_DIR (extracted/blockNNNNN_DATA.bin) か、txt を直接置いた dir。 */
export function resolveFlTexts(registry, { flDir } = {}) {
  const got = new Map(); // file -> { text } | { error }
  const pins = registry.flTexts ?? [];
  const dirs = [];
  if (flDir) dirs.push(flDir);
  for (const pin of pins) {
    let buf = null;
    for (const d of dirs) {
      const cands = [path.join(d, "extracted", pin.block), path.join(d, pin.block), path.join(d, "System/Texts/Licenses", pin.file), path.join(d, pin.file)];
      const hit = cands.find((c) => existsSync(c) && statSync(c).isFile());
      if (hit) {
        buf = readFileSync(hit);
        break;
      }
    }
    if (!buf) got.set(pin.file, { error: "missing" });
    else if (sha256(buf) !== pin.sha256) got.set(pin.file, { error: `sha256 mismatch (FL 版が registry の pin と違う: ${sha256(buf).slice(0, 12)} != ${pin.sha256.slice(0, 12)})` });
    else got.set(pin.file, { text: decodeText(buf) });
  }
  return got;
}

// ライセンスファイル名: LICENSE / LICENSE.md / LICENSE.pffft.txt / COPYING.LGPLv2.1 / COPYING3 / NOTICE / OFL.txt (notices.test.mjs や THIRD_PARTY_NOTICES.txt は対象外)
export const REL_LICENSE_NAME = /(^|\/)(LICEN[CS]E|COPYING|NOTICE|OFL)([._\-0-9][^/]*)?$/i;

export function gitTracked(repoRoot = REPO) {
  try {
    return execFileSync("git", ["-C", repoRoot, "ls-files"], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }).split("\n").filter(Boolean);
  } catch {
    return [];
  }
}

/** build.sh を持つ OSS 再ビルド dir (repo 相対) */
export function ossBuildDirs(repoRoot = REPO) {
  const base = path.join(repoRoot, "tools/shared/oss");
  if (!existsSync(base)) return [];
  return readdirSync(base, { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(path.join(base, e.name, "build.sh")))
    .map((e) => `tools/shared/oss/${e.name}`)
    .sort();
}

const under = (file, prefix) => file === prefix || file.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`);

/**
 * registry / records / repo 内容の整合検査。素材 (FL) を要さない。
 * 返り値 problems が空でなければ CI で失敗させる。
 */
export function checkRegistry({ registry, records, fonts, repoRoot = REPO, tracked = gitTracked(repoRoot), buildDirs = ossBuildDirs(repoRoot) }) {
  const problems = [];
  const warnings = [];
  const forbidden = registry.forbiddenArgs ?? DEFAULT_FORBIDDEN_ARGS;
  const comps = registry.components ?? [];
  if (registry.schema !== 1) problems.push("registry: schema が 1 でない");
  const ids = new Set();
  const recordRefs = new Set();
  for (const c of comps) {
    const w = (m) => problems.push(`component ${c.id}: ${m}`);
    if (!c.id || ids.has(c.id)) w(`id が空か重複`);
    ids.add(c.id);
    for (const k of ["name", "kind", "license"]) if (!c[k]) w(`${k} が無い`);
    if (!KINDS.includes(c.kind)) w(`kind "${c.kind}" が不正 (${KINDS.join(" | ")})`);
    if (typeof c.bundled !== "boolean") w("bundled (true/false) が無い");
    if (c.bundled === false && !c.reason) w("bundled=false には reason が必要 (同梱しない根拠)");
    for (const cp of c.coveredBy ?? []) if (!existsSync(path.join(repoRoot, cp))) w(`coveredBy のパスが repo に無い: ${cp}`);
    for (const f of c.flTexts ?? []) if (!(registry.flTexts ?? []).some((x) => x.file === f)) w(`flTexts "${f}" が registry.flTexts に無い`);
    if (c.bundled !== true) continue;
    if (c.kind === "rebuilt") {
      if (!c.records?.length) w("rebuilt で bundled=true なのに records が無い (再ビルド記録が必須)");
      for (const rid of c.records ?? []) {
        recordRefs.add(rid);
        const rec = records.get(rid);
        if (!rec) {
          w(`記録 records/${rid}.json が無い (該当 build.sh を実行して記録する)`);
          continue;
        }
        problems.push(...validateRecord(rec, rid, { repoRoot, forbiddenArgs: forbidden }));
      }
    } else if (c.kind === "vendored") {
      const v = c.vendored ?? {};
      if (!v.url || !HEX40.test(v.commit ?? "")) w("vendored.url / vendored.commit (40hex) が必要");
      if (!v.path || !existsSync(path.join(repoRoot, v.path))) w(`vendored.path が repo に無い: ${v.path}`);
      if (!v.licenseFile || !existsSync(path.join(repoRoot, v.licenseFile))) w(`vendored.licenseFile が repo に無い: ${v.licenseFile}`);
      if (!Array.isArray(v.modifications)) w("vendored.modifications (無改変は [] を明示) が必要");
    } else if (c.kind === "fl-embedded") {
      if (!c.flTexts?.length) w("fl-embedded で bundled=true なのに flTexts (FL 同梱表記) が無い");
    } else if (c.kind === "font-asset") {
      for (const m of validateFontAsset(c, { repoRoot })) w(m);
    }
    if (c.copyleft && !["none", "weak", "strong"].includes(c.copyleft)) w(`copyleft "${c.copyleft}" が不正`);
    if (c.copyleft === "strong") w("copyleft=strong (GPL 系) は同梱不可 (docs/LEGAL.md §3.2)");
  }
  // 記録が registry のどれからも参照されていない (= NOTICES に出ない) 孤児
  for (const rid of records.keys()) if (!recordRefs.has(rid)) problems.push(`record ${rid}: registry のどの component からも参照されていない (NOTICES に出ない)`);
  // FL 同梱表記の pin
  for (const t of registry.flTexts ?? []) {
    if (!t.file || !t.block || !HEX64.test(t.sha256 ?? "") || !Number.isInteger(t.size)) problems.push(`flTexts ${t.file}: file/block/size/sha256 が不正`);
    if (!comps.some((c) => (c.flTexts ?? []).includes(t.file))) problems.push(`flTexts ${t.file}: どの component からも参照されていない`);
  }
  // 記録なしの OSS 再ビルドスクリプト: tools/shared/oss/*/build.sh は全て component に紐づく
  for (const d of buildDirs) {
    if (!comps.some((c) => (c.coveredBy ?? []).some((cp) => under(d, cp)))) problems.push(`${d}/build.sh: OSS 再ビルドスクリプトが registry の coveredBy に無い (記録なしの OSS)`);
  }
  // 記録なしの vendored OSS: repo 内の LICENSE/COPYING/NOTICE/OFL ファイルは registry が把握していること
  const ignore = registry.ignoreLicensePaths ?? [];
  for (const f of tracked) {
    if (!REL_LICENSE_NAME.test(f)) continue;
    if (ignore.some((i) => under(f, i))) continue;
    const covered = comps.some((c) => (c.coveredBy ?? []).some((cp) => under(f, cp)) || (c.vendored?.path && under(f, c.vendored.path)));
    if (!covered) problems.push(`${f}: repo 内のライセンスファイルがどの component の coveredBy / vendored.path にも無い (記録なしの同梱 OSS)`);
  }
  // フォント
  if (!fonts) problems.push("fonts.json が無い (本文なしフォントの一覧は必須: docs/LEGAL.md §3.1)");
  else {
    if (!Array.isArray(fonts.files) || fonts.files.length === 0) problems.push("fonts.json: files が空");
    for (const f of fonts.files ?? []) if (!["license-text", "origin-unverified"].includes(f.status)) problems.push(`fonts.json: ${f.path} の status "${f.status}" が不正`);
    for (const t of fonts.licenseTexts ?? []) if (!(registry.flTexts ?? []).concat(fonts.licenseTexts).some((x) => x.file === t.file)) problems.push(`fonts.json: licenseTexts ${t.file}`);
  }
  if (!comps.some((c) => c.attribution)) warnings.push("attribution を持つ component が 0 件 (FreeType の謝辞が必須: FTL §2)");
  return { problems, warnings };
}

// ---------------------------------------------------------------------------------------------------------------------
// モデル構築と描画

export function registryDigest(registry, records, fonts) {
  const h = createHash("sha256");
  h.update(JSON.stringify(registry));
  for (const [k, v] of [...records.entries()].sort(([a], [b]) => a.localeCompare(b))) h.update(`\n${k}\n${JSON.stringify(v)}`);
  h.update(`\n${JSON.stringify(fonts)}`);
  return h.digest("hex");
}

export function buildModel({ registry, records, fonts, flTexts }) {
  const missing = [];
  const bundled = registry.components.filter((c) => c.bundled);
  const components = bundled.map((c) => {
    const recs = (c.records ?? []).map((rid) => records.get(rid)).filter(Boolean);
    const fl = (c.flTexts ?? []).map((f) => ({ file: f, ...(flTexts.get(f) ?? { error: "missing" }) }));
    for (const t of fl) if (t.error) missing.push(`${c.id}: FL 同梱表記 ${t.file}: ${t.error}`);
    return { ...c, recs, fl, displayVersion: recs.map((r) => r.version).join(", ") || c.version || "" };
  });
  const allFl = (registry.flTexts ?? []).map((p) => ({ ...p, ...(flTexts.get(p.file) ?? { error: "missing" }) }));
  for (const t of allFl) if (t.error && !missing.some((m) => m.includes(`FL 同梱表記 ${t.file}`))) missing.push(`FL 同梱表記 ${t.file}: ${t.error}`);
  return {
    registry,
    components,
    notBundled: registry.components.filter((c) => !c.bundled),
    allFl,
    fonts,
    digest: registryDigest(registry, records, fonts),
    missing,
    complete: missing.length === 0,
  };
}

const line = (c = "-", n = 78) => c.repeat(n);
const LGPL_NOTE = [
  "This component is licensed under the GNU Lesser General Public License. It is built from the unmodified upstream source identified below",
  "(plus the patches listed, if any) as a separately loadable WebAssembly module, apart from any code derived from FL Studio.",
  "The upstream source archive, its SHA-256, the exact configure arguments and the patches used are recorded here so the module can be rebuilt",
  "(see the build script named below, in this project's source repository) and replaced by a rebuilt or modified version.",
];

function componentLines(c) {
  const L = [];
  L.push(line("="), `[component:${c.id}] ${c.name}${c.displayVersion ? ` ${c.displayVersion}` : ""}`, line("="));
  L.push(`License: ${c.license}`, `Kind: ${c.kind}${c.copyleft && c.copyleft !== "none" ? `  Copyleft: ${c.copyleft}` : ""}`);
  if (c.homepage) L.push(`Homepage: ${c.homepage}`);
  if (c.attribution) L.push("", "Acknowledgement (required by the license):", `  ${c.attribution}`);
  if (c.note) L.push("", `Note: ${c.note}`);
  if (c.kind === "vendored") {
    const v = c.vendored;
    L.push("", `Vendored source: ${v.url} @ ${v.commit}`, `Path in this repository: ${v.path}`);
    L.push(v.modifications.length ? "Modifications:" : "Modifications: none", ...v.modifications.map((m) => `  - ${m}`));
  }
  if (c.kind === "font-asset") {
    const f = c.fontAsset;
    L.push("", `Copyright: ${f.copyright}`, `Upstream: ${f.repository} @ ${f.commit}`);
    L.push(`Reserved Font Name: ${f.reservedFontName ? "yes" : "none"}.  Modified: ${f.modified ? "yes" : "no (the font files are distributed byte-for-byte as obtained from upstream)"}.`);
    L.push("Font files (not part of FL Studio; fetched from the URL below and verified by SHA-256):");
    for (const x of f.files) L.push(`  - ${x.name}  ${x.size} B  sha256:${x.sha256}`, `    ${x.url}`);
    L.push("", `License text (${c.license}) from upstream: ${f.licenseFile.path}  (${f.licenseFile.url})`, line(), f.licenseFile.text.replace(/\n$/, ""), line());
  }
  if (c.kind === "fl-embedded") L.push("", "Included inside FL Studio binaries that are translated into the WebAssembly output; the notice text shipped with FL Studio is reproduced in Appendix A.");
  for (const r of c.recs) {
    L.push("", `-- Rebuild record: ${r.name} ${r.version} (records/${r.id}.json) --`);
    L.push(`Upstream: ${r.upstream.url}`);
    if (r.upstream.archive) L.push(`Source archive: ${r.upstream.archive}  sha256:${r.upstream.sha256}`);
    if (r.upstream.commit) L.push(`Source commit: ${r.upstream.commit}`);
    L.push(`Build script: ${r.build.script}`, `Toolchain: ${r.build.toolchain}${r.build.targets.length ? `  Targets: ${r.build.targets.join(", ")}` : ""}`);
    for (const a of r.build.args) L.push(`Build [${a.step}]: ${a.args}`);
    L.push(r.build.patches.length ? "Patches applied:" : "Patches applied: none");
    for (const p of r.build.patches) L.push(`  - ${p.path} sha256:${p.sha256}${p.summary ? `  (${p.summary})` : ""}`);
    if (c.copyleft === "weak") L.push("", ...LGPL_NOTE);
    for (const f of r.license.files) L.push("", `License text (${r.license.spdx}) from upstream ${r.name} ${r.version}: ${f.path}`, line(), f.text.replace(/\n$/, ""), line());
  }
  if (c.kind === "vendored") {
    L.push("", `License text from ${c.vendored.licenseFile}`, line(), c.vendoredText.replace(/\n$/, ""), line());
  }
  if (c.fl.length) L.push("", `FL Studio notice files for this component: ${c.fl.map((t) => t.file).join(", ")} (Appendix A)`);
  L.push("");
  return L;
}

export function renderTxt(model) {
  const L = [];
  L.push("THIRD PARTY NOTICES — Signature Studio", line("="));
  L.push("Generated by tools/legal/notices (LGL-3). This is a statement of facts, not legal advice.");
  L.push(`Registry digest: sha256:${model.digest}`);
  L.push(`Reference FL Studio build: ${model.registry.flVersion}`, "");
  if (!model.complete) {
    L.push(`${INCOMPLETE_MARK} この NOTICES は不完全です (下記の本文が素材から読めなかった)。リリースには使えません。`);
    for (const m of model.missing) L.push(`  - ${m}`);
    L.push("");
  }
  L.push("1. Summary", line());
  for (const c of model.components) L.push(`  ${c.id.padEnd(14)} ${(`${c.name}${c.displayVersion ? ` ${c.displayVersion}` : ""}`).padEnd(34)} ${c.license}`);
  L.push("", "2. Components", line(), "");
  for (const c of model.components) L.push(...componentLines(c));
  L.push("3. Fonts", line(), "");
  L.push(...fontLines(model.fonts));
  L.push("", "4. Components reviewed and not bundled", line());
  for (const c of model.notBundled) L.push(`  ${c.id}: ${c.name} — ${c.reason}`);
  L.push("", "Appendix A. Notices shipped with FL Studio (System/Texts/Licenses)", line("="), "");
  for (const t of model.allFl) {
    L.push(`### ${t.file}`, line());
    L.push(t.text ? t.text.replace(/\n$/, "") : `${INCOMPLETE_MARK} ${t.file}: ${t.error}`);
    L.push(line(), "");
  }
  return `${L.join("\n")}\n`;
}

function fontLines(fonts) {
  const L = [];
  const withText = fonts.files.filter((f) => f.status === "license-text");
  const unverified = fonts.files.filter((f) => f.status === "origin-unverified");
  L.push(`Font files found in the FL Studio installation: ${fonts.files.length}`);
  L.push(`  with a licence text in the same directory: ${withText.length}`, `  origin unverified (no licence text found): ${unverified.length}`, "");
  L.push("Origin unverified (no licence text shipped with the file; docs/LEGAL.md §3.1). Treated as unreviewed, not as permitted:");
  for (const f of unverified) L.push(`  - ${f.path}  (${f.size} B)`);
  L.push("", "With licence text (SIL Open Font License; the text file sits next to the font):");
  for (const f of withText) L.push(`  - ${f.path}  (${f.size} B)  licence: ${f.licenseFile}`);
  return L;
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function renderHtml(model) {
  const txt = renderTxt(model);
  const comps = model.components.map((c) => `<li><a href="#c-${esc(c.id)}">${esc(c.name)}${c.displayVersion ? ` ${esc(c.displayVersion)}` : ""}</a> — ${esc(c.license)}</li>`).join("\n");
  const secs = model.components.map((c) => `<section id="c-${esc(c.id)}"><pre>${esc(componentLines(c).join("\n"))}</pre></section>`).join("\n");
  const fl = model.allFl.map((t) => `<section><h3>${esc(t.file)}</h3><pre>${esc(t.text ?? `${INCOMPLETE_MARK} ${t.file}: ${t.error}`)}</pre></section>`).join("\n");
  const head = txt.split("\n").slice(0, 5).join("\n");
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Third party notices — Signature Studio</title>
<style>body{font:14px/1.5 sans-serif;max-width:60em;margin:2em auto;padding:0 1em}pre{white-space:pre-wrap;background:#f6f6f6;padding:.6em;overflow-x:auto}</style></head>
<body><h1>Third party notices — Signature Studio</h1>
<pre>${esc(head)}</pre>
${model.complete ? "" : `<p><strong>${INCOMPLETE_MARK}</strong> ${esc(model.missing.join("; "))}</p>`}
<h2>Components</h2><ul>
${comps}
</ul>
${secs}
<h2>Fonts</h2><pre>${esc(fontLines(model.fonts).join("\n"))}</pre>
<h2>Components reviewed and not bundled</h2><ul>${model.notBundled.map((c) => `<li>${esc(c.id)}: ${esc(c.name)} — ${esc(c.reason)}</li>`).join("")}</ul>
<h2>Appendix A. Notices shipped with FL Studio</h2>
${fl}
</body></html>
`;
}

/** registry + records + FL 同梱表記 -> { txt, html, model }。vendored は repo 内のライセンスファイルを読む */
export function generate({ registry = loadRegistry(), records = loadRecords(), fonts = loadFonts(), flDir = FL_WIN64_DIR, strict = false, repoRoot = REPO } = {}) {
  const flTexts = resolveFlTexts(registry, { flDir });
  const model = buildModel({ registry, records, fonts, flTexts });
  for (const c of model.components) if (c.kind === "vendored") c.vendoredText = decodeText(readFileSync(path.join(repoRoot, c.vendored.licenseFile)));
  // 謝辞は必ず本文に出ること (FTL §2 など)
  const txt = renderTxt(model);
  for (const c of model.components) {
    if (c.attribution && !txt.includes(c.attribution)) throw new Error(`謝辞が NOTICES に出ていない: ${c.id}`);
    if (!txt.includes(`[component:${c.id}]`)) throw new Error(`component が NOTICES に出ていない: ${c.id}`);
  }
  if (strict && !model.complete) {
    const e = new Error(`NOTICES が不完全 (strict):\n  ${model.missing.join("\n  ")}`);
    e.code = "NOTICES_INCOMPLETE";
    throw e;
  }
  return { txt, html: renderHtml(model), model };
}

// ---------------------------------------------------------------------------------------------------------------------
// 成果物 (dist / stage 済み site) の走査

export function walk(dir, base = dir, acc = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, base, acc);
    else acc.push({ key: path.relative(base, p).split(path.sep).join("/"), file: p });
  }
  return acc;
}

const CHUNK = 16 * 1024 * 1024;

function* chunksOf(file) {
  // 圧縮 chunk は展開後ストリームを走査する (release-guard と同じ想定: tools/assets の .br/.zst/.gz)
  const st = statSync(file);
  if (/\.(br|gz|zst)$/.test(file) && st.size < 512 * 1024 * 1024) {
    const raw = readFileSync(file);
    try {
      if (file.endsWith(".br")) return yield zlib.brotliDecompressSync(raw);
      if (file.endsWith(".gz")) return yield zlib.gunzipSync(raw);
      if (typeof zlib.zstdDecompressSync === "function") return yield zlib.zstdDecompressSync(raw);
    } catch {
      /* 展開失敗は raw を走査 */
    }
    return yield raw;
  }
  let off = 0;
  const h = openSync(file, "r");
  try {
    const buf = Buffer.allocUnsafe(CHUNK);
    for (let n; (n = readSync(h, buf, 0, CHUNK, off)) > 0; off += n) yield Buffer.from(buf.subarray(0, n));
  } finally {
    closeSync(h);
  }
}

/** 1 ファイル内の signature 一致を返す ([{id, sig}])。chunk 境界は最長 signature - 1 バイトの重なりで跨ぐ */
export function scanFile(file, sigs) {
  const hits = new Map();
  const maxLen = Math.max(...sigs.map((s) => Buffer.byteLength(s.sig)));
  let tail = Buffer.alloc(0);
  for (const chunk of chunksOf(file)) {
    const buf = tail.length ? Buffer.concat([tail, chunk]) : chunk;
    for (const s of sigs) if (!hits.has(`${s.id}\0${s.sig}`) && buf.includes(s.sig)) hits.set(`${s.id}\0${s.sig}`, s);
    tail = buf.subarray(Math.max(0, buf.length - (maxLen - 1)));
  }
  return [...hits.values()];
}

/**
 * 成果物の検査。entries = [{key, file}]。
 *   - THIRD_PARTY_NOTICES.txt / .html が含まれ、INCOMPLETE でなく、現在の registry digest と一致し、同梱 component が全て載っていること
 *   - registry の signature が成果物内で見つかった component は bundled=true かつ記録が有効であること
 *   - kind=forbidden の signature (GPL 系など) が見つかったら失敗
 * 返り値 { problems, detected }
 */
export function checkArtifact({ entries, registry = loadRegistry(), records = loadRecords(), fonts = loadFonts(), repoRoot = REPO }) {
  const problems = [];
  const keys = new Map(entries.map((e) => [e.key, e]));
  const txtEntry = keys.get(NOTICES_TXT);
  const digest = registryDigest(registry, records, fonts);
  if (!txtEntry) problems.push(`${NOTICES_TXT} が成果物に無い (vite build で出力される。生成: node tools/legal/notices/cli.mjs generate)`);
  else {
    const t = readFileSync(txtEntry.file, "utf8");
    if (t.includes(INCOMPLETE_MARK) && t.split("\n").some((l) => l.startsWith(INCOMPLETE_MARK))) problems.push(`${NOTICES_TXT} が不完全 (${INCOMPLETE_MARK})。FL 素材 (FL_WIN64_DIR) を付けて NOTICES_STRICT=1 で再ビルドする`);
    if (!t.includes(`Registry digest: sha256:${digest}`)) problems.push(`${NOTICES_TXT} が現在の registry / records と一致しない (古い成果物。再生成が必要)`);
    for (const c of registry.components.filter((x) => x.bundled)) if (!t.includes(`[component:${c.id}]`)) problems.push(`${NOTICES_TXT} に同梱 component ${c.id} が無い`);
  }
  if (!keys.has(NOTICES_HTML)) problems.push(`${NOTICES_HTML} が成果物に無い`);

  const sigs = [];
  for (const c of registry.components) for (const s of c.signatures ?? []) sigs.push({ id: c.id, sig: s, kind: "component" });
  for (const f of registry.forbidden ?? []) for (const s of f.signatures ?? []) sigs.push({ id: f.id, sig: s, kind: "forbidden", reason: f.reason });
  const detected = new Map();
  if (sigs.length) {
    for (const e of entries) {
      if (e.key === NOTICES_TXT || e.key === NOTICES_HTML) continue;
      for (const h of scanFile(e.file, sigs)) {
        if (!detected.has(h.id)) detected.set(h.id, []);
        detected.get(h.id).push({ key: e.key, sig: h.sig, kind: h.kind, reason: h.reason });
      }
    }
  }
  // font-asset は固有文字列に頼らず、ファイル全体の sha256 (size で絞る) で検出する。改変・subset 版は検出範囲外 (REPORT)
  const fontAssets = registry.components.flatMap((c) => (c.fontAsset?.files ?? []).map((x) => ({ id: c.id, ...x })));
  if (fontAssets.length) {
    for (const e of entries) {
      if (e.key === NOTICES_TXT || e.key === NOTICES_HTML) continue;
      const size = statSync(e.file).size;
      const cands = fontAssets.filter((x) => x.size === size);
      if (!cands.length) continue;
      const sum = sha256(readFileSync(e.file));
      for (const x of cands) {
        if (x.sha256 !== sum) continue;
        if (!detected.has(x.id)) detected.set(x.id, []);
        detected.get(x.id).push({ key: e.key, sig: `sha256:${sum.slice(0, 12)} (${x.name})`, kind: "component" });
      }
    }
  }
  for (const [id, hits] of detected) {
    const h = hits[0];
    if (h.kind === "forbidden") {
      problems.push(`${h.key}: 同梱禁止の部品 ${id} の痕跡 "${h.sig}" (${h.reason})`);
      continue;
    }
    const c = registry.components.find((x) => x.id === id);
    if (!c.bundled) problems.push(`${h.key}: ${id} の痕跡 "${h.sig}" があるが registry は bundled=false (${c.reason})。bundled=true にして記録を付けること`);
    else if (c.kind === "rebuilt") {
      for (const rid of c.records ?? []) {
        const rec = records.get(rid);
        const errs = rec ? validateRecord(rec, rid, { repoRoot }) : ["記録なし"];
        if (errs.length) problems.push(`${h.key}: ${id} (痕跡 "${h.sig}") の再ビルド記録 ${rid} が無効: ${errs[0]}`);
      }
      if (!c.records?.length) problems.push(`${h.key}: ${id} (痕跡 "${h.sig}") に再ビルド記録が無い`);
    }
  }
  return { problems, detected: Object.fromEntries([...detected].map(([k, v]) => [k, v.map((x) => `${x.key}:${x.sig}`)])) };
}

/** deploy 経路のゲート (05-stage 用)。違反なら exit 7。skip は明示バイパスのみ */
export function gate({ entries, skip = false, label = "stage" }) {
  if (skip) {
    console.error(`notices-gate[${label}]: --skip-notices-gate により検査を省略`);
    return;
  }
  const r = checkArtifact({ entries });
  if (r.problems.length) {
    console.error(`notices-gate[${label}]: FAIL (${r.problems.length} 件)\n  ${r.problems.join("\n  ")}`);
    process.exit(7);
  }
  console.error(`notices-gate[${label}]: PASS (${entries.length} files${Object.keys(r.detected).length ? `, 検出 OSS: ${Object.keys(r.detected).join(",")}` : ""})`);
}
