// FLP ブラウザ E2E 用フィクスチャ解決。FL 同梱ファイルはリポジトリにも配布物にも含めない。
// 入力 (どちらか):
//   E2E_FLP_WIN_DIR = fl-win64.tar.zst の `extracted/` (block*_DATA.bin)。manifest の sha256 で .flp を特定
//   FL_ROOT         = FL の Resources/FL (manifest の rel で解決)
// 無ければ null (check は SKIP。E2E_REQUIRE_FLP=1 で FAIL)。
import { createHash } from "node:crypto";
import { closeSync, copyFileSync, existsSync, mkdirSync, openSync, readFileSync, readSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { parseFlp } from "../../flp/src/flp.ts";

const FLP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../flp");
const manifest = JSON.parse(readFileSync(path.join(FLP, "corpus/manifest.json"), "utf8"));
const fstManifest = JSON.parse(readFileSync(path.join(FLP, "corpus/fst_manifest.json"), "utf8"));

const STAGE = path.resolve(FLP, "../e2e/work/flp-fixtures");
const sha = (b) => createHash("sha256").update(b).digest("hex");

// 代表 .flp (manifest.rel): 空 / 拡張 ID 0xAC を含む 25.2 / 26.1 保存 / 7MB 級
const FLP_RELS = [
  "Data/System/Empty.flp",
  "Data/Demo projects/NewStuff.flp",
  "Data/Templates/Minimal/Basic with limiter/Basic with limiter.flp",
  "Data/Demo projects/Demo songs/Mehdi Ebrahiminejad - Never Out.flp",
];
// .fst / .fsc (fst_manifest.rel。sha256 を持たないので win 側は size + format で特定)
const PRESET_RELS = ["Data/Patches/Channel presets/3x Osc/Accordeon 2.fst", "Data/Patches/Scores/4 steps.fsc"];

function winBlocks(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    if (!name.endsWith("_DATA.bin")) continue;
    const abs = path.join(dir, name);
    const fd = openSync(abs, "r");
    const head = Buffer.alloc(4);
    readSync(fd, head, 0, 4, 0);
    closeSync(fd);
    if (head.toString("latin1") === "FLhd") out.push({ name, abs });
  }
  return out;
}

export function resolveFixtures() {
  const winDir = process.env.E2E_FLP_WIN_DIR;
  const flRoot = process.env.FL_ROOT;
  const wants = [
    ...FLP_RELS.map((rel) => ({ rel, m: manifest.projects.find((p) => p.rel === path.posix.normalize(rel)) })),
    ...PRESET_RELS.map((rel) => ({ rel, m: fstManifest.presets.find((p) => p.rel === rel) })),
  ];
  for (const w of wants) if (!w.m) throw new Error(`manifest に無い: ${w.rel}`);

  if (winDir && existsSync(winDir)) {
    const blocks = winBlocks(winDir);
    const bySha = new Map();
    const bySize = new Map();
    for (const b of blocks) {
      const buf = readFileSync(b.abs);
      b.buf = buf;
      bySha.set(sha(buf), b);
      if (!bySize.has(buf.length)) bySize.set(buf.length, []);
      bySize.get(buf.length).push(b);
    }
    const files = wants.map(({ rel, m }) => {
      // .flp は sha256 で一意。preset は manifest に sha256 が無いので size 一致 + イベント数一致の最初の候補
      const b = m.sha256
        ? bySha.get(m.sha256)
        : (bySize.get(m.size) ?? []).find((c) => parseFlp(c.buf).events.length === m.events);
      if (!b) throw new Error(`win 抽出物に該当ブロック無し: ${rel}`);
      // file picker に渡す実ファイルは元の名前でステージング (work/ は gitignore)
      mkdirSync(STAGE, { recursive: true });
      const abs = path.join(STAGE, path.basename(rel));
      copyFileSync(b.abs, abs);
      return { rel, abs, name: path.basename(rel), ext: path.extname(rel), buf: b.buf, manifest: m, source: `win:${b.name}` };
    });
    return { source: "win", files };
  }
  if (flRoot && existsSync(flRoot)) {
    const files = wants.map(({ rel, m }) => {
      const abs = path.join(flRoot, rel);
      const buf = readFileSync(abs);
      return { rel, abs, name: path.basename(rel), ext: path.extname(rel), buf, manifest: m, source: `mac:${rel}` };
    });
    return { source: "mac", files };
  }
  return null;
}
