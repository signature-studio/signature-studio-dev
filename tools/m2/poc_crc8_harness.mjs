// M2-5 PoC: RetDec lift IR → wasm 化した _FLAC__crc8 を node で実行し、
// 参照実装 (FLAC CRC-8, 多項式 0x07) と bit-exact 照合する。
//
//   tools/m2/work/ 配下で実行: node poc_crc8_harness.mjs
//
// 構成:
//   - easyflac_x86_64.drc.* : RetDec (--select-functions _FLAC__crc8 --select-decode-only)
//     でリフトした IR (tools/m2/work/crc8.drc.ll 由来, ir_normalize.py で正規形済)
//   - crc8_test.cjs         : 定型フラグで emcc が生成した glue (MODULARIZE)
//     (emcc 6.0 の --no-entry + 素 IR 系では wasmImports が空になるため、
//      instantiateWasm hook で import を no-op stub で埋めて自前 instantiate する)
//   - linear memory に対して EasyFLAC slice の crc8 テーブル
//     (VA 0x30a40 = 199232, 256B) を書き込んでから wasm 関数を呼ぶ。
//     (lifted IR は「アドレス値 == linear memory offset」の意味で load/store する)
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const mod = require("./crc8_test.cjs");
const createModule = mod["createModule"] ? mod.createModule
  : (mod.default && mod.default.createModule) ? mod.default.createModule
  : mod;

const TABLE_ADDR = 199232;   // 0x30a40 (RetDec IR 中の固定アドレス = crc8 テーブル先頭)
const TABLE_LEN = 256;
const PTR = 0x400000;        // 入力データの linear memory 領域 (emcc runtime 遷移外)
let capturedExports = null;  // instantiateWasm hook で保持する wasm exports

async function main() {
  const wasmBytes = readFileSync(new URL("./crc8_test.wasm", import.meta.url));
  const imports = {};          // instantiateWasm 内に import object は未使用化
  const raw = wasmBytes.buffer.slice(
    wasmBytes.byteOffset, wasmBytes.byteOffset + wasmBytes.byteLength);

  const Module = await createModule({
    instantiateWasm(info, receiveInstance) {
      // emcc runtime の JS library が pruned される (wasmImports が空になるため
      // import 面 env.* / wasi_snapshot_preview1.* を no-op stub で補完する)
      // wasm モジュールの import 面 (env.* / wasi_snapshot_preview1.*) を
      // モジュール自身から列挙し、glue で供給されないものを no-op stub で補完
      // (emcc runtime の JS library が pruned されるため)
      const wasmModule = new WebAssembly.Module(raw);
      const imps = WebAssembly.Module.imports(wasmModule);
      const imports = {
        env: info.env ?? {},
        wasi_snapshot_preview1: info.wasi_snapshot_preview1 ?? {},
      };
      for (const imp of imps) {
        imports[imp.module] ??= {};
        if (imp.kind === "function" &&
            typeof imports[imp.module][imp.name] !== "function") {
          imports[imp.module][imp.name] = () => {};
        }
      }
      return WebAssembly.instantiate(raw, imports)
        .then((r) => {
          // glue が exported を Module に置換しないため、wasm instance の
          // exports はこちらで保持して使う
          capturedExports = r.instance.exports;
          return receiveInstance(r.instance);
        });
    },
  });

  // glue (Module) は runtime library の部分割り当てしか行わないため、
  // ライフに wasm exports を直接使う (memory は instance 内群の memory buffer)
  const memoryBuffer = (capturedExports?.["memory"]?.buffer) ??
    Module.wasmMemory?.buffer;
  const heap = new Uint8Array(memoryBuffer);
  const wasmFn = capturedExports?.["_FLAC__crc8"] ?? Module["_FLAC__crc8"];
  if (!wasmFn) {
    throw new Error("_FLAC__crc8 が export されていません");
  }

  // linear memory にモジュールのテーブル領域をロード
  // (lifted IR は「アドレス値 == linear memory offset」の意味で load/store する;
  //  EasyFLAC slice は file offset == vmaddr のためそのまま読んで写す)
  const dylib = readFileSync(
    new URL("./easyflac_x86_64.dylib", import.meta.url));
  heap.set(dylib.subarray(TABLE_ADDR, TABLE_ADDR + TABLE_LEN), TABLE_ADDR);

  // 参照実装 (FLAC CRC-8 = poly 0x07)
  const crc8_prop = (bytes) => {
    let c = 0;
    for (const b of bytes) {
      c ^= b;
      for (let i = 0; i < 8; i++) {
        c = (c & 0x80) ? ((c << 1) ^ 0x07) & 0xff : (c << 1) & 0xff;
      }
    }
    return c & 0xff;
  };
  const cases = [
    "hello from e2e, answer=42",
    "hello from m2, flac crc8 poc",
    "wasm lifter IR smoke test",
    "D", "B", "CUSTOM TEST",
  ];
  const results = [];
  for (const s of cases) {
    const bytes = Buffer.from(s, "latin1");
    heap.set(bytes, PTR);
    const got = wasmFn(BigInt(PTR), BigInt(bytes.length));
    const expected = crc8_prop(bytes);
    results.push({ input: s, wasm: Number(got), expected, ok: Number(got) === expected });
  }

  for (const r of results) {
    console.log(`  [${r.ok ? "OK" : "NG"}] ${r.input} -> wasm:0x${r.wasm.toString(16).padStart(2, "0")} expected:0x${r.expected.toString(16).padStart(2, "0")}`);
  }
  const allOk = results.every((r) => r.ok);
  console.log(allOk
    ? "[poc_crc8] bit-exact OK (wasm == 参照実装・全ケース一致)"
    : "[poc_crc8] MISMATCH");
  writeFileSync("poc_crc8_results.json",
    JSON.stringify({ table_addr: TABLE_ADDR, table_len: TABLE_LEN, ptr: PTR,
                     inputs: results }, null, 1));
  process.exit(allOk ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
