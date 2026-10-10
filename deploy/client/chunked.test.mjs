// node --test deploy/client/chunked.test.mjs
// 05-stage.mjs で分割した最小 wasm を実 HTTP サーバから連結ロードする (再試行 / 改ざん検知 / Access 失効 / 順序保証)
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test, { after, before } from "node:test";
import {
  AccessExpiredError, ChunkIntegrityError, chunkedArrayBuffer, chunkedStream,
  compileChunkedWasm, descriptorUrlFor, instantiateChunkedWasm,
} from "./chunked.mjs";

const here = import.meta.dirname;
const FIXTURE = path.resolve(here, "../../tools/e2e/fixtures/add.wasm");
let tmp, site, server, base;
const faults = new Map(); // path -> async (req,res) => boolean(handled)
const hits = new Map();

// 先頭に custom section (name "pad") で 3000B 詰めた有効 wasm (>maxFile を作る)
function paddedWasm() {
  const src = readFileSync(FIXTURE);
  const name = Buffer.from("pad");
  const payload = Buffer.concat([Buffer.from([name.length]), name, Buffer.alloc(3000, 0x5a)]);
  const leb = (n) => { const o = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; o.push(b); } while (n); return Buffer.from(o); };
  const sec = Buffer.concat([Buffer.from([0]), leb(payload.length), payload]);
  return Buffer.concat([src.subarray(0, 8), sec, src.subarray(8)]);
}

before(async () => {
  tmp = mkdtempSync(path.join(tmpdir(), "chunked-test-"));
  const src = path.join(tmp, "src");
  mkdirSync(path.join(src, "wasm"), { recursive: true });
  writeFileSync(path.join(src, "index.html"), "<!doctype html>");
  writeFileSync(path.join(src, "wasm/big.0123456789ab.wasm"), paddedWasm());
  site = path.join(tmp, "site");
  execFileSync("node", [path.join(here, "../scripts/05-stage.mjs"), "--src", src, "--out", site, "--max-file", "1024", "--part-size", "700"], { stdio: "pipe" });
  server = http.createServer(async (req, res) => {
    const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    hits.set(p, (hits.get(p) ?? 0) + 1);
    const f = faults.get(p);
    if (f && (await f(req, res))) return;
    const file = path.join(site, p);
    if (!file.startsWith(site) || !existsSync(file) || !statSync(file).isFile()) { res.writeHead(404).end(); return; }
    res.writeHead(200, { "content-length": statSync(file).size });
    createReadStream(file).pipe(res);
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => { server.close(); rmSync(tmp, { recursive: true, force: true }); });

const D = () => `${base}${"/wasm/big.0123456789ab.wasm"}.parts/index.json`;
const desc = () => JSON.parse(readFileSync(path.join(site, "wasm/big.0123456789ab.wasm.parts/index.json"), "utf8"));
const reset = () => { faults.clear(); hits.clear(); };

test("stage: 元ファイルは置かれず part + descriptor になる / _headers 生成", () => {
  assert.equal(existsSync(path.join(site, "wasm/big.0123456789ab.wasm")), false);
  const d = desc();
  assert.ok(d.parts.length >= 4, `parts=${d.parts.length}`);
  assert.equal(d.parts.reduce((a, p) => a + p.size, 0), d.size);
  assert.ok(d.parts.every((p) => p.size <= 700));
  assert.match(readFileSync(path.join(site, "_headers"), "utf8"), /Cross-Origin-Embedder-Policy: require-corp/);
  assert.equal(descriptorUrlFor("/wasm/big.0123456789ab.wasm"), "/wasm/big.0123456789ab.wasm.parts/index.json");
});

test("連結 ReadableStream を WebAssembly.compileStreaming に渡せて add が動く", async () => {
  reset();
  const mod = await compileChunkedWasm(D(), { concurrency: 3 });
  const inst = await WebAssembly.instantiate(mod);
  assert.equal(typeof Object.values(inst.exports).find((v) => typeof v === "function"), "function");
  const r = await instantiateChunkedWasm(D(), {}, { concurrency: 2 });
  assert.ok(r.instance);
});

test("連結結果が元バイト列と一致 / 全体 sha256 一致 / 並列度が背圧で制限される", async () => {
  reset();
  const buf = new Uint8Array(await chunkedArrayBuffer(D(), { concurrency: 4 }));
  assert.deepEqual(Buffer.from(buf), paddedWasm());
  assert.equal(createHash("sha256").update(buf).digest("hex"), desc().sha256);
  reset();
  const { stream } = await chunkedStream(D(), { concurrency: 2 });
  const reader = stream.getReader();
  await reader.read(); // 1 part 読んだ時点で先読みは emit(1)+concurrency(2)=最大 3 part
  await new Promise((r) => setTimeout(r, 100));
  const partHits = [...hits.keys()].filter((k) => k.endsWith(".part")).length;
  assert.ok(partHits <= 3, `先読み part=${partHits}`);
  await reader.cancel();
});

test("503 / 429(Retry-After) は再試行して成功する", async () => {
  reset();
  const d = desc();
  let n503 = 0, n429 = 0;
  faults.set(`/wasm/big.0123456789ab.wasm.parts/${d.parts[1].name}`, async (_q, res) => (n503++ < 2 ? (res.writeHead(503).end(), true) : false));
  faults.set(`/wasm/big.0123456789ab.wasm.parts/${d.parts[2].name}`, async (_q, res) => (n429++ < 1 ? (res.writeHead(429, { "retry-after": "0" }).end(), true) : false));
  const buf = new Uint8Array(await chunkedArrayBuffer(D(), { baseDelay: 5 }));
  assert.equal(buf.length, d.size);
  assert.equal(n503, 3);
  assert.equal(n429, 2);
});

test("part 改ざんは ChunkIntegrityError", async () => {
  reset();
  const d = desc();
  faults.set(`/wasm/big.0123456789ab.wasm.parts/${d.parts[0].name}`, async (_q, res) => {
    res.writeHead(200).end(Buffer.alloc(d.parts[0].size, 1));
    return true;
  });
  await assert.rejects(chunkedArrayBuffer(D()), ChunkIntegrityError);
});

test("Access 失効 (302) は再試行せず AccessExpiredError", async () => {
  reset();
  const d = desc();
  faults.set(`/wasm/big.0123456789ab.wasm.parts/${d.parts[1].name}`, async (_q, res) => (res.writeHead(302, { location: "https://team.cloudflareaccess.com/" }).end(), true));
  await assert.rejects(chunkedArrayBuffer(D(), { baseDelay: 5 }), AccessExpiredError);
  assert.equal(hits.get(`/wasm/big.0123456789ab.wasm.parts/${d.parts[1].name}`), 1);
});

test("永続的 5xx は retries 後に失敗", async () => {
  reset();
  const d = desc();
  faults.set(`/wasm/big.0123456789ab.wasm.parts/${d.parts[0].name}`, async (_q, res) => (res.writeHead(500).end(), true));
  await assert.rejects(chunkedArrayBuffer(D(), { baseDelay: 1, retries: 2 }), /HTTP 500/);
  assert.equal(hits.get(`/wasm/big.0123456789ab.wasm.parts/${d.parts[0].name}`), 3);
});
