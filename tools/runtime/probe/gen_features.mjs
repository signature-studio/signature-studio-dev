// wasm 機能検出用の極小モジュールを binaryen wasm-as で生成し features.json (base64) に出力する。
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdtempSync, readFileSync } from "node:fs";
import path from "node:path";
const WASM_AS = process.env.WASM_AS || "/opt/emsdk/upstream/bin/wasm-as";
const F = {
  simd: [["--enable-simd"], `(module (func (result v128) (v128.const i32x4 1 2 3 4)))`],
  relaxed_simd: [["--enable-simd", "--enable-relaxed-simd"], `(module (func (param v128) (result v128) (i32x4.relaxed_trunc_f32x4_s (local.get 0))))`],
  threads_atomics: [["--enable-threads", "--enable-bulk-memory"], `(module (memory 1 1 shared) (func (result i32) (i32.atomic.rmw.add (i32.const 0) (i32.const 1))))`],
  bulk_memory: [["--enable-bulk-memory"], `(module (memory 1) (func (memory.copy (i32.const 0) (i32.const 8) (i32.const 4))))`],
  reference_types: [["--enable-reference-types"], `(module (table 1 externref) (func (param externref) (result externref) (local.get 0)))`],
  multivalue: [["--enable-multivalue"], `(module (func (result i32 i32) (i32.const 1) (i32.const 2)))`],
  mutable_globals: [["--enable-mutable-globals"], `(module (global (export "g") (mut i32) (i32.const 1)))`],
  sign_ext: [["--enable-sign-ext"], `(module (func (result i32) (i32.extend8_s (i32.const 1))))`],
  nontrapping_f2i: [["--enable-nontrapping-float-to-int"], `(module (func (result i32) (i32.trunc_sat_f32_s (f32.const 1))))`],
  tail_call: [["--enable-tail-call"], `(module (func $a (result i32) (return_call $b)) (func $b (result i32) (i32.const 1)))`],
  extended_const: [["--enable-extended-const"], `(module (global i32 (i32.add (i32.const 1) (i32.const 2))))`],
  memory64: [["--enable-memory64"], `(module (memory i64 1) (func (result i64) (i64.load (i64.const 0))))`],
  multi_memory: [["--enable-multimemory"], `(module (memory 1) (memory 1))`],
  eh_legacy: [["--enable-exception-handling"], `(module (tag $t) (func (try (do (throw $t)) (catch_all))))`],
  eh_exnref: [["--enable-exception-handling", "--enable-reference-types"], `(module (tag $t) (func (block $b (try_table (catch_all $b) (throw $t)))))`],
  gc: [["--enable-gc", "--enable-reference-types"], `(module (type $s (struct (field i32))) (func (result (ref null $s)) (ref.null $s)))`],
  wide_arithmetic: [["--enable-wide-arithmetic", "--enable-multivalue"], `(module (func (param i64 i64 i64 i64) (result i64 i64) (i64.add128 (local.get 0) (local.get 1) (local.get 2) (local.get 3))))`],
  custom_page_sizes: [["--enable-custom-page-sizes"], `(module (memory 1 2 (pagesize 1)))`],
  shared_everything: [[], `(module)`],
};
const dir = mkdtempSync("/tmp/opencode/feat-");
const out = {};
for (const [k, [flags, wat]] of Object.entries(F)) {
  const wf = path.join(dir, k + ".wat"), bf = path.join(dir, k + ".wasm");
  writeFileSync(wf, wat);
  try {
    execFileSync(WASM_AS, [...flags, wf, "-o", bf], { stdio: ["ignore", "pipe", "pipe"] });
    out[k] = readFileSync(bf).toString("base64");
  } catch (e) { out[k] = null; console.error("gen fail", k, String(e.stderr || e).slice(0, 200)); }
}
writeFileSync(path.join(path.dirname(new URL(import.meta.url).pathname), "features.json"), JSON.stringify(out, null, 1));
console.log("features:", Object.keys(out).filter((k) => out[k]).length, "/", Object.keys(out).length);
