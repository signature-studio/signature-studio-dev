// VM の状態を POST /admin/import の本文 (整形しない JSON) にまとめる (#2799)。無依存の Node。
// 入力は VM の 3 ファイルと GET /admin/export の出力: launched.json・relaunch.json・issues_state.json (pm_art)・export.json (phase)。
// 素材行 (oc_artifacts:) は src/launch.ts の ALLOW_ARTS の名前だけに正規化する。説明文・括弧書きは落とし、none と名前が混在したら名前を残す。
// 落とした語は issue 番号と一緒に標準エラーへ出す。200 KiB (src/vmstate.ts の MAX_IMPORT_BYTES) を超えたら、何も出力せず失敗する。
//
// 使い方 (リポジトリの root で): node infra/pm-worker/scripts/build_import.mjs --launched launched.json --relaunch relaunch.json \
//   --state issues_state.json --export export.json > import.json

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const MAX_IMPORT_BYTES = 200 * 1024; // src/vmstate.ts と同じ (test/unit/build_import.test.ts で突き合わせる)
// src/launch.ts の ALLOW_ARTS と同じ並び・同じ中身 (同じく突き合わせる)
export const ALLOW_ARTS = [
  "fl-win64", "plugins-ott", "plugins-freshair", "plugins-serum2", "plugins-massivex", "plugins-kilohearts",
  "toolchain-retdec", "toolchain-emsdk", "work-m11", "work-liftdiff", "work-m6-ott", "work-liftlib-targets",
  "work-liftlib", "work-icall", "work-fw-stage1", "analysis-ott-binaries", "analysis-mac-shared", "apt-mingw",
];

const PREFIX = "oc_artifacts:";

// 1 行の素材行を正規化する。戻り値は { line: "oc_artifacts: …" か null (素材が 1 つも残らない), dropped: 落とした語 }。
export function normalizeArtLine(raw) {
  const i = raw.indexOf(PREFIX);
  if (i < 0) return { line: null, dropped: [raw.trim()] };
  let body = raw.slice(i + PREFIX.length);
  let prev;
  do {
    prev = body;
    body = body.replace(/[(（][^()（）]*[)）]/g, " ");
  } while (body !== prev);
  const toks = body.replace(/[`*「」"']/g, " ").split(/[\s,、，;；]+/).filter(Boolean);
  const names = [];
  const dropped = [];
  let none = false;
  for (const t of toks) {
    if (t === "none") none = true;
    else if (ALLOW_ARTS.includes(t)) {
      if (!names.includes(t)) names.push(t);
    } else dropped.push(t);
  }
  if (names.length) return { line: `${PREFIX} ${names.join(" ")}`, dropped };
  if (none) return { line: `${PREFIX} none`, dropped };
  return { line: null, dropped };
}

// VM の値を取り込みの本文の形にする。relaunch.art が全部落ちたら null (count は残す)、pm_art は行ごと除く (推定に戻す)。
export function buildImport({ launched, relaunch, state, phase }, log = () => {}) {
  if (!phase) throw new Error("export の phase が null (一度も保存されていない)。最初の tick の後で export し直す");
  if (!state || typeof state.pm_art !== "object" || state.pm_art === null) throw new Error("issues_state.json に pm_art が無い");
  const norm = (n, kind, raw) => {
    const r = normalizeArtLine(raw);
    if (r.dropped.length) log(`issue #${n} (${kind}): 許可外として落とした語 ${JSON.stringify(r.dropped)}`);
    return r.line;
  };
  const out = { launched: {}, relaunch: {}, phase, pm_art: {} };
  for (const [n, at] of Object.entries(launched)) out.launched[n] = at;
  for (const [n, r] of Object.entries(relaunch)) {
    const art = r.art == null ? null : norm(n, "relaunch", r.art);
    if (r.art != null && art === null) log(`issue #${n} (relaunch): 素材が残らないので art を null にする (count は残す)`);
    out.relaunch[n] = { count: r.count, art };
  }
  for (const [n, p] of Object.entries(state.pm_art)) {
    const line = norm(n, "pm_art", p.line);
    if (line === null) log(`issue #${n} (pm_art): 素材が残らないので行ごと除く (推定に戻す)`);
    else out.pm_art[n] = { at: p.at, line };
  }
  return out;
}

// 整形しない JSON の文字列。上限を超えたら投げる (呼び出し側は何も書かない)。
export function serialize(obj) {
  const text = JSON.stringify(obj);
  const bytes = Buffer.byteLength(text, "utf8");
  if (bytes > MAX_IMPORT_BYTES) throw new Error(`import の本文が ${bytes} バイトで、上限 ${MAX_IMPORT_BYTES} バイト (200 KiB) を超える`);
  return text;
}

function main(argv) {
  const keys = ["launched", "relaunch", "state", "export"];
  const opt = {};
  for (let i = 0; i < argv.length; i += 2) {
    const k = argv[i]?.replace(/^--/, "");
    if (!keys.includes(k) || argv[i + 1] === undefined) return usage();
    opt[k] = argv[i + 1];
  }
  if (!keys.every((k) => k in opt)) return usage();
  const log = (m) => process.stderr.write(`build_import: ${m}\n`);
  const read = (p) => JSON.parse(readFileSync(p, "utf8"));
  try {
    const body = serialize(
      buildImport({ launched: read(opt.launched), relaunch: read(opt.relaunch), state: read(opt.state), phase: read(opt.export).phase }, log),
    );
    process.stdout.write(body);
  } catch (e) {
    log(e.message);
    process.exitCode = 1;
  }
}

function usage() {
  process.stderr.write("usage: build_import.mjs --launched <f> --relaunch <f> --state <issues_state.json> --export <export.json>\n");
  process.exitCode = 2;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main(process.argv.slice(2));
