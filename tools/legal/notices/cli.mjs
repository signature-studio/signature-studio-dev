#!/usr/bin/env node
// THIRD_PARTY_NOTICES CLI (LGL-3, #86)
//   cli.mjs generate [--out <dir>] [--fl-dir <FL_WIN64_DIR>] [--strict]
//   cli.mjs check    [--artifact <dist>...] [--json out.json]        registry / 記録 / repo の整合 (+ 成果物の欠落検出)
//   cli.mjs fonts    --fl-dir <FL_WIN64_DIR> [--write]               FL のファイル一覧 (block25163) から fonts.json を再生成
//   cli.mjs pins     --fl-dir <FL_WIN64_DIR> [--first-block 24735]   System/Texts/Licenses 15 本の pin (registry.flTexts) を出力
// 終了コード: 0 PASS / 1 検査失敗 / 2 引数・入力不正 / 3 strict で NOTICES 不完全
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { FL_WIN64_DIR } from "../../shared/paths.mjs";
import {
  checkArtifact, checkRegistry, decodeText, FONTS_PATH, generate, loadFonts, loadRecords, loadRegistry, NOTICES_HTML, NOTICES_TXT, sha256, walk,
} from "./lib.mjs";

const [cmd, ...rest] = process.argv.slice(2);
const multi = (n) => rest.flatMap((a, i) => (a === `--${n}` ? [rest[i + 1]] : []));
const one = (n, d) => multi(n).at(-1) ?? d;
const has = (n) => rest.includes(`--${n}`);
const flDir = one("fl-dir", FL_WIN64_DIR);

function flFileList() {
  if (!flDir) throw new Error("--fl-dir (または FL_WIN64_DIR) が必要");
  const f = [path.join(flDir, "extracted/block25163_DATA.bin"), path.join(flDir, "block25163_DATA.bin")].find((p) => {
    try {
      readFileSync(p);
      return true;
    } catch {
      return false;
    }
  });
  if (!f) throw new Error(`block25163_DATA.bin (FL のファイル一覧) が ${flDir} に無い`);
  // 行形式: <win path>/<size>/<mtime>。ディレクトリは size = -1
  return decodeText(readFileSync(f))
    .split("\n")
    .filter(Boolean)
    .map((l) => {
      const m = /^(.*)\/(-?\d+)\/(\d+)$/.exec(l);
      return m ? { path: m[1].replace(/\\/g, "/"), size: Number(m[2]) } : null;
    })
    .filter((x) => x && x.size >= 0);
}

try {
  if (cmd === "generate") {
    const out = path.resolve(one("out", "."));
    const { txt, html, model } = generate({ flDir, strict: has("strict") });
    mkdirSync(out, { recursive: true });
    writeFileSync(path.join(out, NOTICES_TXT), txt);
    writeFileSync(path.join(out, NOTICES_HTML), html);
    console.log(`notices: ${path.join(out, NOTICES_TXT)} (${Buffer.byteLength(txt)} B, components ${model.components.length}, ${model.complete ? "complete" : `INCOMPLETE: ${model.missing.length} 件`})`);
    if (!model.complete) for (const m of model.missing) console.error(`  - ${m}`);
  } else if (cmd === "check") {
    const registry = loadRegistry();
    const records = loadRecords();
    const fonts = loadFonts();
    const r = checkRegistry({ registry, records, fonts });
    const art = multi("artifact").map((dir) => ({ dir, ...checkArtifact({ entries: walk(path.resolve(dir)), registry, records, fonts }) }));
    const problems = [...r.problems, ...art.flatMap((a) => a.problems.map((p) => `[artifact ${a.dir}] ${p}`))];
    if (one("json")) writeFileSync(one("json"), JSON.stringify({ problems, warnings: r.warnings, artifacts: art.map((a) => ({ dir: a.dir, detected: a.detected })) }, null, 1));
    for (const w of r.warnings) console.error(`warn: ${w}`);
    if (problems.length) {
      console.error(`notices-check: FAIL (${problems.length} 件)\n  ${problems.join("\n  ")}`);
      process.exit(1);
    }
    const bundled = registry.components.filter((c) => c.bundled).length;
    console.log(`notices-check: PASS components=${registry.components.length} (bundled ${bundled}) records=${records.size} fonts=${fonts.files.length} artifacts=${art.length}`);
  } else if (cmd === "fonts") {
    const list = flFileList();
    const dirOf = (p) => p.slice(0, p.lastIndexOf("/"));
    const FONT = /\.(ttf|otf|zfo|woff2?|eot|ttc)$/i;
    const TEXT = /(^|\/)(OFL|LICEN[CS]E|COPYING)[^/]*\.txt$/i;
    const excludeDir = /^System\/Tools\/LilyPond\//;
    const texts = new Map(list.filter((x) => TEXT.test(x.path)).map((x) => [dirOf(x.path), x.path]));
    const files = list
      .filter((x) => FONT.test(x.path) && !excludeDir.test(x.path))
      .map((x) => {
        const t = texts.get(dirOf(x.path));
        return t ? { path: x.path, size: x.size, status: "license-text", licenseFile: t.slice(t.lastIndexOf("/") + 1) } : { path: x.path, size: x.size, status: "origin-unverified" };
      })
      .sort((a, b) => a.path.localeCompare(b.path));
    const doc = { schema: 1, source: "FL Studio win64 file list (extracted/block25163_DATA.bin)", excluded: ["System/Tools/LilyPond/** (GPL ツール。同梱しない: docs/LEGAL.md §3.2)"], files };
    const s = `${JSON.stringify(doc, null, 1)}\n`;
    if (has("write")) writeFileSync(FONTS_PATH, s);
    else process.stdout.write(s);
    console.error(`fonts: ${files.length} files (license-text ${files.filter((f) => f.status === "license-text").length}, origin-unverified ${files.filter((f) => f.status === "origin-unverified").length})${has("write") ? ` -> ${FONTS_PATH}` : ""}`);
  } else if (cmd === "pins") {
    const list = flFileList().filter((x) => /^System\/Texts\/Licenses\/[^/]+\.txt$/.test(x.path));
    const first = Number(one("first-block", 24735));
    const pins = list.map((x, i) => {
      const block = `block${String(first + i).padStart(5, "0")}_DATA.bin`;
      const file = path.join(flDir, "extracted", block);
      const buf = readFileSync(file);
      if (buf.length !== x.size) throw new Error(`${x.path}: ファイル一覧のサイズ ${x.size} と ${block} の ${buf.length} が違う (--first-block を確認)`);
      return { file: x.path.split("/").pop(), block, size: x.size, sha256: sha256(buf) };
    });
    console.log(JSON.stringify(pins, null, 2));
  } else {
    console.error("usage: cli.mjs generate|check|fonts|pins ... (先頭コメント参照)");
    process.exit(2);
  }
} catch (e) {
  console.error(`notices: ${e.message}`);
  process.exit(e.code === "NOTICES_INCOMPLETE" ? 3 : 2);
}
