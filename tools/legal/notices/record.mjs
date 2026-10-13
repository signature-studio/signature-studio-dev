#!/usr/bin/env node
// OSS wasm 再ビルドの記録 (LGL-3, #86)。各 build.sh が成功時に 1 回呼び、records/<id>.json を書く。
//   node tools/legal/notices/record.mjs --id freetype-2.7 --name FreeType --version 2.7 --license-spdx FTL \
//     --url https://.../freetype-2.7.tar.gz --archive <tarball> [--commit <sha> --git-dir <dir>] \
//     --src-dir <展開先> --license-file docs/FTL.TXT [--license-file ...] \
//     --script tools/shared/oss/freetype/build.sh --toolchain emcc --target wasm32 [--target wasm64] \
//     --step "configure=<引数列>" [--step ...] [--patch <repo 相対 path>[:要約]] [--out <records dir>]
// 記録に入るのは upstream の版・ソース sha256 (または git commit)・ライセンス本文・configure/cmake 引数・適用パッチ・toolchain 版のみ。
// 時刻・絶対パスは入れない (同じ入力なら同じ JSON になる = 再ビルドで差分が出たら入力が変わった証拠)。
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { decodeText, RECORDS_DIR, REPO, sha256, validateRecord } from "./lib.mjs";

const argv = process.argv.slice(2);
const multi = (n) => argv.flatMap((a, i) => (a === `--${n}` ? [argv[i + 1]] : []));
const one = (n, d) => multi(n).at(-1) ?? d;
const need = (n) => {
  const v = one(n);
  if (!v) {
    console.error(`notices-record: --${n} が必要`);
    process.exit(2);
  }
  return v;
};

const rel = (p) => {
  const r = path.relative(REPO, path.resolve(REPO, p)).split(path.sep).join("/");
  if (r.startsWith("..")) {
    console.error(`notices-record: repo 外のパスは記録できない: ${p}`);
    process.exit(2);
  }
  return r;
};

function toolchain(v) {
  if (v !== "emcc") return v;
  const out = execFileSync("emcc", ["--version"], { encoding: "utf8" }).split("\n")[0];
  const m = /\)\s+(\d+\.\d+\.\d+)/.exec(out);
  if (!m) throw new Error(`emcc --version を解釈できない: ${out}`);
  return `emcc ${m[1]}`;
}

const id = need("id");
const upstream = { url: need("url") };
if (one("archive")) {
  upstream.archive = path.basename(one("archive"));
  upstream.sha256 = sha256(readFileSync(one("archive")));
}
if (one("commit")) {
  upstream.commit = one("commit");
  if (one("git-dir")) {
    const head = execFileSync("git", ["-C", one("git-dir"), "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
    if (head !== upstream.commit) {
      console.error(`notices-record: ${one("git-dir")} の HEAD ${head} が --commit ${upstream.commit} と違う`);
      process.exit(2);
    }
  }
}

const srcDir = need("src-dir");
const licenseFiles = multi("license-file").map((f) => {
  const p = path.join(srcDir, f);
  if (!existsSync(p)) {
    console.error(`notices-record: ライセンスファイルが無い: ${p}`);
    process.exit(2);
  }
  const text = decodeText(readFileSync(p));
  return { path: f, sha256: sha256(text), text };
});

const steps = multi("step").map((s) => {
  const i = s.indexOf("=");
  if (i < 1) throw new Error(`--step は name=args 形式: ${s}`);
  return { step: s.slice(0, i), args: s.slice(i + 1) };
});
const patches = multi("patch").map((s) => {
  const [p, ...summary] = s.split(":");
  const file = path.resolve(REPO, p);
  if (!existsSync(file)) throw new Error(`パッチが無い: ${p}`);
  return { path: rel(file), sha256: sha256(readFileSync(file)), summary: summary.join(":") || undefined };
});

const record = {
  schema: 1,
  id,
  name: need("name"),
  version: need("version"),
  provenance: "build-script",
  upstream,
  license: { spdx: need("license-spdx"), files: licenseFiles },
  build: {
    script: rel(need("script")),
    toolchain: toolchain(need("toolchain")),
    targets: multi("target"),
    args: steps,
    patches,
  },
};
const problems = validateRecord(record, id);
if (problems.length) {
  console.error(`notices-record: 記録が不完全:\n  ${problems.join("\n  ")}`);
  process.exit(2);
}
const out = path.resolve(one("out", RECORDS_DIR));
mkdirSync(out, { recursive: true });
const file = path.join(out, `${id}.json`);
writeFileSync(file, `${JSON.stringify(record, null, 2)}\n`);
console.log(`[notices] recorded ${path.relative(REPO, file)} (${record.name} ${record.version}, source ${upstream.sha256 ? `sha256:${upstream.sha256.slice(0, 12)}` : `commit:${upstream.commit.slice(0, 12)}`})`);
