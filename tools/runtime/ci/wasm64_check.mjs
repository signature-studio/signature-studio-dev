// wasm32 / wasm64 の同一ビルド対を同一手順で駆動し、出力ハッシュ一致を判定する (不一致は exit 1)。
// usage: node wasm64_check.mjs <target> <wasm32> <wasm64> <driver.mjs> [expected,hash,list]
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";

const [target, f32, f64, driver, expectArg = ""] = process.argv.slice(2);
const { loadOtt, makeRunner } = await import(pathToFileURL(path.resolve(driver)));
const hex = (h) => h.toString(16).padStart(8, "0");
const expected = expectArg ? expectArg.split(",") : [];
const PARAMS = [0.5, 0.1];

// memory section (id 5) の limits flags bit2 = memory64。ドライバの is64 は memory.type() 依存で常に false になるため使わない
function isMemory64(bytes) {
  let p = 8;
  const leb = () => { let r = 0, s = 0, b; do { b = bytes[p++]; r |= (b & 0x7f) << s; s += 7; } while (b & 0x80); return r; };
  while (p < bytes.length) {
    const id = bytes[p++], size = leb(), end = p + size;
    if (id === 5) { leb(); return (bytes[p] & 0x04) !== 0; }
    p = end;
  }
  throw new Error("memory section not found");
}

let ok = true;
const fail = (m) => { console.error(`[wasm64_check:${target}] FAIL ${m}`); ok = false; };
const got = {};
for (const [name, file, want64] of [["wasm32", f32, false], ["wasm64", f64, true]]) {
  const bytes = readFileSync(file);
  const is64 = isMemory64(bytes);
  if (is64 !== want64) fail(`${name}: memory64=${is64} (期待 ${want64}) — ビルドが取り違えられている`);
  const o = await loadOtt(bytes);
  if (o.missing.length) console.log(`[wasm64_check:${target}] ${name} missing imports: ${o.missing.length}`);
  const r = makeRunner(o);
  got[name] = PARAMS.map((p) => { r.setup(p); r.process(); return hex(r.hash()); });
  console.log(`[wasm64_check:${target}] ${name} memory64=${is64} hashes=${got[name].join(",")}`);
}
if (got.wasm32.join() !== got.wasm64.join()) fail(`wasm32 と wasm64 の出力ハッシュが不一致`);
if (new Set(got.wasm32).size < got.wasm32.length) fail("パラメータ違いでハッシュが同一 (駆動が効いていない)");
if (expected.length && got.wasm32.join() !== expected.join()) fail(`期待ハッシュ ${expected.join(",")} と不一致`);
console.log(`[wasm64_check:${target}] ${ok ? "PASS" : "FAIL"}`);
process.exit(ok ? 0 : 1);
