// node --test tools/assets/deploy-manifest/make-manifest.test.mjs
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { build, crossCheckBootManifest, hashedName, plan } from "./make-manifest.mjs";
import { verify } from "./verify-release.mjs";

const sha = (b) => createHash("sha256").update(b).digest("hex");
function fixture() {
  const d = mkdtempSync(path.join(tmpdir(), "mm-"));
  mkdirSync(path.join(d, "w"), { recursive: true });
  return d;
}

test("immutable 配下の非ハッシュ名はハッシュ名になり、ハッシュ名は不変 (冪等)", () => {
  const d = fixture();
  const body = Buffer.from("wasm-body");
  writeFileSync(path.join(d, "w/ott.wasm"), body);
  writeFileSync(path.join(d, "w/m1.0123456789ab.wasm"), "x");
  const files = plan([{ dest: "wasm", src: path.join(d, "w") }]);
  const byPath = Object.fromEntries(files.map((f) => [f.path, f]));
  assert.ok(byPath[`wasm/ott.${sha(body).slice(0, 12)}.wasm`], Object.keys(byPath).join());
  assert.ok(byPath["wasm/m1.0123456789ab.wasm"]);
  assert.equal(byPath[`wasm/ott.${sha(body).slice(0, 12)}.wasm`].contentType, "application/wasm");
  assert.equal(byPath["wasm/m1.0123456789ab.wasm"].renamed, false);
});

test("document (/wasm/manifest.json) と immutable 外は改名しない", () => {
  const d = fixture();
  writeFileSync(path.join(d, "w/manifest.json"), "{}");
  writeFileSync(path.join(d, "w/a.js"), "1");
  const files = plan([{ dest: "wasm", src: path.join(d, "w/manifest.json") }, { dest: "worklets", src: path.join(d, "w/a.js") }]);
  assert.deepEqual(files.map((f) => f.path), ["wasm/manifest.json", "worklets/a.js"]);
  assert.ok(files.every((f) => !f.renamed));
});

test("data は /data 配下でハッシュ名 + octet-stream", () => {
  const d = fixture();
  writeFileSync(path.join(d, "w/blob.bin"), "abc");
  const [f] = plan([{ dest: "data", src: path.join(d, "w/blob.bin") }]);
  assert.match(f.path, /^data\/blob\.[0-9a-f]{12}\.bin$/);
  assert.equal(f.contentType, "application/octet-stream");
});

test("予約名・衝突・拡張子無しは中止", () => {
  const d = fixture();
  writeFileSync(path.join(d, "w/release.json"), "{}");
  assert.throws(() => plan([{ dest: "", src: path.join(d, "w/release.json") }]), /予約名/);
  writeFileSync(path.join(d, "w/x.js"), "a");
  mkdirSync(path.join(d, "w2"));
  writeFileSync(path.join(d, "w2/x.js"), "b");
  assert.throws(() => plan([{ dest: "worklets", src: path.join(d, "w/x.js") }, { dest: "worklets", src: path.join(d, "w2/x.js") }]), /衝突/);
  writeFileSync(path.join(d, "w/noext"), "a");
  assert.throws(() => plan([{ dest: "wasm", src: path.join(d, "w/noext") }]), /拡張子/);
  assert.throws(() => hashedName("noext", "00"), /拡張子/);
});

test("ブート manifest の file/glue/sha256 突合 (ネガティブ: 壊すと検出)", () => {
  const d = fixture();
  const wasm = Buffer.from("w");
  const name = `m1.${sha(wasm).slice(0, 12)}.wasm`;
  writeFileSync(path.join(d, "w", name), wasm);
  const entry = { id: "m1", file: name, sha256: sha(wasm), bytes: 1 };
  const write = (e) => writeFileSync(path.join(d, "w/manifest.json"), JSON.stringify({ version: 1, entries: [e] }));
  write(entry);
  assert.deepEqual(crossCheckBootManifest(plan([{ dest: "wasm", src: path.join(d, "w") }])), { checked: true, problems: [] });
  write({ ...entry, sha256: "0".repeat(64) });
  assert.match(crossCheckBootManifest(plan([{ dest: "wasm", src: path.join(d, "w") }])).problems[0], /sha256 不一致/);
  write({ ...entry, glue: "missing.0123456789ab.mjs" });
  assert.match(crossCheckBootManifest(plan([{ dest: "wasm", src: path.join(d, "w") }])).problems[0], /glue/);
});

test("build は 05-stage 契約 {version:1, files:[{path,src,contentType}]}", () => {
  const d = fixture();
  writeFileSync(path.join(d, "w/a.js"), "1");
  const m = build(plan([{ dest: "worklets", src: path.join(d, "w/a.js") }]));
  assert.equal(m.version, 1);
  assert.deepEqual(Object.keys(m.files[0]).slice(0, 3), ["path", "src", "contentType"]);
});

test("verify-release: sha256 を壊すと検出", () => {
  const m = { files: [{ path: "a", sha256: "aa", size: 1, contentType: "x" }] };
  assert.equal(verify(m, { files: { a: { sha256: "aa", size: 1, contentType: "x" } } }).problems.length, 0);
  assert.equal(verify(m, { files: { a: { sha256: "bb", size: 1, contentType: "x" } } }).problems.length, 1);
  assert.equal(verify(m, { files: {} }).problems.length, 1);
});
