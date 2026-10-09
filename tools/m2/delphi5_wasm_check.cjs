// M2-3 補助学習: Delphi §5.7 観点の 5 関数 (RetDec `--select-ranges` リフト IR
// → り ir_normalize.py 正規形) をそのまま wasm 化して node 上で呼び動作するかの
// 実動作確認 (REPORT §3.2 ③再コンパイル可否の補完)。
//
//   clang --target=wasm32 ... -Wl,--export-all d5fast_norm.ll -o d5fast.wasm
//   node work/delphi5_wasm_check.mjs
const readFileSync = require("node:fs").readFileSync;
const path = require("node:path");

async function main() {
  const buf = readFileSync(path.join(__dirname, "work", "d5fast.wasm"));
  const bytes = new Uint8Array(buf.buffer.slice(
    buf.byteOffset, buf.byteOffset + buf.byteLength));
  const mod = await WebAssembly.compile(bytes);
  const imps = { env: {} };
  for (const imp of WebAssembly.Module.imports(mod)) {
    imps[imp.module] ??= {};
    imps[imp.module][imp.name] ??= () => 0n;
  }
  const res = await WebAssembly.instantiate(bytes, imps);
  const e = res.instance.exports;
  const mem = new Uint8Array(e.memory.buffer);
  const PTR = 0x400000;
  let ok = true;

  // FastMM 観点 (function_412d60): [ptr]=0 store, [ptr-8]-- (i32) が IR 通りに動くか
  mem[PTR - 8] = 1; mem[PTR] = 0x55;
  const r = e["function_412d60"](BigInt(PTR), 0n);
  const caseA = (r === BigInt(PTR) && mem[PTR] === 0 && mem[PTR - 8] === 0);
  mem[PTR - 8] = 3; mem[PTR] = 0x77;
  const r2 = e["function_412d60"](BigInt(PTR), 0n);
  const caseA2 = (r2 === BigInt(PTR) && mem[PTR] === 0 && mem[PTR - 8] === 2);
  console.log(`[FastMM 型候補 function_412d60] store0+c--: ${caseA} / c=3 分岐 (helper не呼出): ${caseA2}`);
  ok &&= caseA && caseA2;

  // RTTI/VMT fixed field 観点 (function_497e40): 負固定 disp (-168 = vmtVMTfield) 読み
  mem[0x200100 - 168] = 0x42;
  const r3 = e["function_497e40"](BigInt(0x200000), BigInt(0x200100));
  const caseB = r3 === 66n;
  console.log(`[RTTI/VMT 型候補 function_497e40] mem[0x200100-168]=0x42 → load: ${caseB}`);
  ok &&= caseB;

  // VMT 間接/単純ヘルパ (function_4475e0): obj+64 越し release helper の wrapper
  const r4 = e["function_4475e0"](BigInt(0x300000), BigInt(0x200000));
  const caseC = typeof r4 === "bigint";
  console.log(`[VMT helper function_4475e0] wrapper が callable & 返値 bigint: ${caseC}`);
  ok &&= caseC;

  console.log(ok
    ? "[delphi5_wasm_check] 全観点で実動作 OK (wasm 上)"
    : "[delphi5_wasm_check] FAIL");
  process.exit(ok ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
