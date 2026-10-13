// bun test tools/runtime/chunked_manifest.test.ts
// 大物 wasm の manifest 経路 (stage_wasm.mjs → manifest.entry.file = <file>.parts/index.json → fetchCompile の chunked 分岐) を
// 合成 wasm (tools/e2e/fixtures/add.wasm) で検証する。実 FLEngine 規模の計測は #1150 が追跡する。
import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { fetchCompile, isChunkedDescriptor } from "../../src/runtime/loader_boot";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const FIXTURE = path.join(root, "tools/e2e/fixtures/add.wasm");

test("大物 entry は descriptor を指し、fetchCompile の chunked 分岐で直接コンパイルと同じ module になる", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "stage-chunked-"));
  const r = spawnSync("node", [path.join(here, "stage_wasm.mjs"), "--extra", `${FIXTURE}:big-add:big-add`, "--max-file=20", "--part-size=16"], {
    env: { ...process.env, RUNTIME_WASM_DIR: dir },
    encoding: "utf8",
  });
  expect(r.status).toBe(0);
  const manifest = JSON.parse(readFileSync(path.join(dir, "manifest.json"), "utf8"));
  const e = manifest.entries.find((x: { id: string }) => x.id === "big-add");
  expect(e).toBeTruthy();
  expect(isChunkedDescriptor(e.file)).toBe(true);
  expect(e.file).toMatch(/^big-add\.[0-9a-f]{12}\.wasm\.parts\/index\.json$/);
  const partsDir = path.join(dir, path.dirname(e.file));
  const original = path.join(dir, e.file.replace(".parts/index.json", ""));
  expect(existsSync(original)).toBe(false); // 元ファイルは置かない

  const desc = JSON.parse(readFileSync(path.join(dir, e.file), "utf8"));
  expect(desc.size).toBe(e.bytes);
  expect(desc.sha256).toBe(e.sha256);
  expect(desc.parts.length).toBeGreaterThan(1);
  expect(desc.parts.reduce((a: number, p: { size: number }) => a + p.size, 0)).toBe(desc.size);
  expect(readdirSync(partsDir).filter((f) => f.endsWith(".part")).length).toBe(desc.parts.length);

  const server = Bun.serve({
    port: 0,
    hostname: "127.0.0.1",
    fetch(req) {
      const p = decodeURIComponent(new URL(req.url).pathname);
      const f = path.join(dir, p);
      if (!f.startsWith(dir) || !existsSync(f) || !statSync(f).isFile()) return new Response("nf", { status: 404 });
      return new Response(Bun.file(f));
    },
  });
  try {
    const base = `http://127.0.0.1:${server.port}/`;
    const url = new URL(e.file, base).href;
    const { module } = await fetchCompile(url, { cacheMode: "none", compile: "streaming" });
    const direct = new WebAssembly.Module(readFileSync(FIXTURE));
    expect(WebAssembly.Module.exports(module)).toEqual(WebAssembly.Module.exports(direct));
    expect(WebAssembly.Module.imports(module)).toEqual(WebAssembly.Module.imports(direct));
    const { module: viaBytes } = await fetchCompile(url, { cacheMode: "none", compile: "bytes" });
    expect(WebAssembly.Module.exports(viaBytes)).toEqual(WebAssembly.Module.exports(direct));
  } finally {
    server.stop(true);
  }
});
