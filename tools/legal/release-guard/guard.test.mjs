// node --test tools/legal/release-guard/   (素材不要。FL 由来バイトの代わりに決定的な擬似乱数を「FL 由来」として使う)
import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import zlib from "node:zlib";
import { buildDenylist, collectEntries, globToRe, loadAllowlist, loadDenylist, minOf, scanEntries } from "./lib.mjs";

const CLI = path.join(import.meta.dirname, "cli.mjs");
const prng = (seed, n) => {
  const out = Buffer.alloc(n);
  for (let i = 0, c = 0; i < n; c++) createHash("sha256").update(`${seed}:${c}`).digest().copy(out, i), (i += 32);
  return out;
};
const tmp = mkdtempSync(path.join(process.env.RUNNER_TEMP ?? os.tmpdir(), "rg-test-"));
test.after(() => rmSync(tmp, { recursive: true, force: true }));
const put = (rel, buf) => {
  const f = path.join(tmp, rel);
  mkdirSync(path.dirname(f), { recursive: true });
  writeFileSync(f, buf);
  return f;
};

const FL = prng("fl-dll", 600_000); // 「FL 由来」
const FL2 = prng("fl-asset", 100_000);
const analysis = path.join(tmp, "analysis");
put("analysis/FLEngine.dll", FL);
put("analysis/data/asset.bin", FL2);
const dlDir = path.join(tmp, "dl");
let dl;
test("build: deny-list 生成", async () => {
  const r = await buildDenylist({ from: [analysis], out: dlDir });
  assert.ok(r.windows > 100, `windows=${r.windows}`);
  assert.equal(r.files, 2);
  dl = loadDenylist(dlDir);
});

const scan = (dir, allow = []) => scanEntries(collectEntries({ src: [dir] }), dl, allow);

test("クリーンな dist は成功", async () => {
  put("clean/index.html", Buffer.from("<html>hello</html>".repeat(100)));
  put("clean/app.js", prng("own-code", 300_000));
  const rep = await scan(path.join(tmp, "clean"));
  assert.equal(rep.failed, 0);
  assert.equal(rep.files, 2);
});

test("ファイルがそのまま混入 → 失敗 (file)", async () => {
  put("d1/wasm/x.bin", FL2);
  const rep = await scan(path.join(tmp, "d1"));
  assert.equal(rep.failed, 1);
  assert.ok(rep.violations[0].hits.some((h) => h.kind === "file"));
});

test("FL バイトの一部 (別ファイルに埋込・オフセット違い) → 失敗 (window)", async () => {
  const part = FL.subarray(123_457, 123_457 + 20_000);
  put("d2/blob.dat", Buffer.concat([prng("pad", 777), part, prng("pad2", 5000)]));
  const rep = await scan(path.join(tmp, "d2"));
  assert.equal(rep.failed, 1);
  assert.ok(rep.violations[0].hits.some((h) => h.kind === "window"));
});

test("brotli / zstd / gzip で圧縮した混入も失敗 (decoded 走査)", async () => {
  put("d3/a.bin.br", zlib.brotliCompressSync(FL));
  put("d3/b.bin.zst", zlib.zstdCompressSync(FL));
  put("d3/c.bin.gz", zlib.gzipSync(FL));
  const rep = await scan(path.join(tmp, "d3"));
  assert.equal(rep.failed, 3);
  for (const v of rep.violations) assert.ok(v.hits.some((h) => h.kind === "window" && /decoded/.test(h.stream)), v.key);
});

test("壊れた .br は raw のみ走査して note を残す (落ちない)", async () => {
  put("d4/broken.br", randomBytes(2000));
  const rep = await scan(path.join(tmp, "d4"));
  assert.equal(rep.failed, 0);
  assert.equal(rep.notes.length, 1);
});

test("chunk id (tools/assets manifest) 一致 → 失敗", async () => {
  const id = "0123456789abcdef0123456789abcdef";
  const mf = put("mf/manifest.json", JSON.stringify({ name: "fl-test", chunks: { id } }));
  const dir2 = path.join(tmp, "dl-chunk");
  await buildDenylist({ from: [analysis], manifests: [mf], out: dir2 });
  const dl2 = loadDenylist(dir2);
  put("d5/c/01/" + id + ".raw", prng("anything", 4096));
  const rep = await scanEntries(collectEntries({ src: [path.join(tmp, "d5")] }), dl2, []);
  assert.equal(rep.failed, 1);
  assert.equal(rep.violations[0].hits[0].kind, "chunk");
});

test("allow-list: reason 必須 / path glob / sha256 で許容", async () => {
  put("d6/shim/own.bin", FL2);
  assert.throws(() => loadAllowlist(put("al-bad.json", JSON.stringify({ entries: [{ path: "x" }] }))), /reason/);
  const al = loadAllowlist(put("al.json", JSON.stringify({ entries: [{ path: "shim/**", reason: "自作 shim (テスト)" }] })));
  const rep = await scan(path.join(tmp, "d6"), al);
  assert.equal(rep.failed, 0);
  assert.equal(rep.suppressed.length, 1);
  const alSha = loadAllowlist(put("al2.json", JSON.stringify({ entries: [{ path: "shim/**", sha256: "0".repeat(64), reason: "別ハッシュ" }] })));
  assert.equal((await scan(path.join(tmp, "d6"), alSha)).failed, 1); // sha 不一致なら許容されない
});

test("globToRe", () => {
  assert.ok(globToRe("shim/**").test("shim/a/b.wasm"));
  assert.ok(globToRe("*.js").test("a.js"));
  assert.ok(!globToRe("*.js").test("d/a.js"));
});

const run = (args, env = {}) => spawnSync("node", [CLI, ...args], { encoding: "utf8", env: { ...process.env, ...env } });

test("CLI: 違反=exit 6 / クリーン=exit 0 / deny-list 無し=exit 4 / 対象 0 件=exit 2", () => {
  assert.equal(run(["scan", "--src", path.join(tmp, "d2"), "--denylist", dlDir, "--allowlist", path.join(tmp, "none.json")]).status, 6);
  assert.equal(run(["scan", "--src", path.join(tmp, "clean"), "--denylist", dlDir, "--allowlist", path.join(tmp, "none.json")]).status, 0);
  assert.equal(run(["scan", "--src", path.join(tmp, "clean"), "--denylist", path.join(tmp, "nodl")]).status, 4);
  mkdirSync(path.join(tmp, "empty"));
  assert.equal(run(["scan", "--src", path.join(tmp, "empty"), "--denylist", dlDir]).status, 2);
});

test("deploy 05-stage: 違反 dist は exit 6 で stage せず / --skip-release-guard でのみ通過 / deny-list 無しは exit 4", () => {
  const stage = path.resolve(import.meta.dirname, "../../../deploy/scripts/05-stage.mjs");
  const env = { RELEASE_GUARD_DENYLIST: dlDir, RELEASE_GUARD_ALLOWLIST: path.join(tmp, "none.json") };
  const s = (src, out, extra = [], e = env) => spawnSync("node", [stage, "--src", src, "--out", out, ...extra], { encoding: "utf8", env: { ...process.env, ...e } });
  put("d7/index.html", "<html></html>");
  put("d7/blob.dat", FL2);
  const bad = s(path.join(tmp, "d7"), path.join(tmp, "out-bad"));
  assert.equal(bad.status, 6, bad.stderr);
  assert.match(bad.stderr, /blob\.dat/);
  assert.equal(s(path.join(tmp, "clean"), path.join(tmp, "out-ok")).status, 0);
  assert.equal(s(path.join(tmp, "d7"), path.join(tmp, "out-skip"), ["--skip-release-guard"]).status, 0);
  assert.equal(s(path.join(tmp, "clean"), path.join(tmp, "out-nodl"), [], { RELEASE_GUARD_DENYLIST: path.join(tmp, "nodl") }).status, 4);
});

test("minOf: 大量 (スプレッド引数上限超え) の窓でも落ちない", () => {
  const m = new Map();
  for (let i = 0; i < 500_000; i++) m.set(i, 500_000 - i);
  assert.equal(minOf(m.values()), 1);
});
