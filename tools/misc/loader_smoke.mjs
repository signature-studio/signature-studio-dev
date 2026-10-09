#!/usr/bin/env node
/**
 * ローダ ロジックの Node 検証スクリプト (フェーズ 3)。
 *
 * ブラウザ実機テストの代わりに、src/runtime/{loader,imports}.ts のロジックを
 * Node 上で直接実行して検証する (Node 26 は .ts を strip-types で読める)。
 *
 * 検証内容:
 *  1. loader.instantiateWasm — tools/m1/build/wasm_elf.wasm (M1 産物) を
 *     wasi_snapshot_preview1.fd_write を shim して instantiate する。
 *     fd_write は InstancedWasm.memory (ローダが返した memory) を参照して
 *     iov を取り出す → exports と memory の受け渡しが正しいことの実証。
 *  2. fail-fast フォワーダ — createImportForwarder が呼ぶと throw すること。
 *
 * 実行: node tools/misc/loader_smoke.mjs
 * (前提: tools/m1/build/wasm_elf.wasm が存在する = tools/m1/m1.sh 済み)
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { createImportForwarder } from "../../src/runtime/imports.ts";
import { instantiateWasm } from "../../src/runtime/loader.ts";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const wasmPath = path.join(repoRoot, "tools/m1/build/wasm_elf.wasm");

function fail(msg) {
  console.error(`[smoke] FAIL: ${msg}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// 1. M1 wasm をローダ経由で instantiate し、stdout (fd_write) を拾う
// ---------------------------------------------------------------------------
const bytes = readFileSync(wasmPath);
if (bytes.length === 0) fail("wasm_elf.wasm が空です (m1.sh を実行してください)");

// fd_write は instantiate 後にしか得られない instance.memory を参照するので
// ローダ結果を格納するホルダを先に用意する
let inst = null;
let stdout = "";

function fd_write(fd, iovs, iovsLen, nwritten) {
  const mem = inst?.memory;
  if (!mem) throw new Error("fd_write: memory が未接続 (ローダが memory を返しません)");
  if (fd !== 1 && fd !== 2) throw new Error(`fd_write: 予期しない fd=${fd}`);
  const view = new DataView(mem.buffer);
  let written = 0;
  for (let i = 0; i < iovsLen; i++) {
    const ptr = view.getUint32(iovs + i * 8, true);
    const len = view.getUint32(iovs + i * 8 + 4, true);
    stdout += new TextDecoder().decode(new Uint8Array(mem.buffer, ptr, len));
    written += len;
  }
  view.setUint32(nwritten, written, true);
  return 0;
}

console.log("[smoke] instantiate tools/m1/build/wasm_elf.wasm …");
inst = await instantiateWasm(bytes, {
  wasi_snapshot_preview1: { fd_write },
});
if (!inst.memory) fail("ローダが memory を返しませんでした");

inst.exports["__wasm_call_ctors"]?.();
const main = inst.exports["__main_argc_argv"];
if (typeof main !== "function") fail('export "__main_argc_argv" がありません');
const ret = main(0, 0);
console.log(`[smoke] main() → ${ret}, stdout=[${stdout.trim()}]`);

if (!stdout.includes("hello from e2e, answer=42")) {
  fail(`期待した stdout が得られませんでした: "${stdout.trim()}"`);
}

// ---------------------------------------------------------------------------
// 2. fail-fast フォワーダ (呼ぶと throw)
// ---------------------------------------------------------------------------
try {
  createImportForwarder("kernel32.CreateFileA")(1, 2, 3);
  fail("フォワーダが throw しませんでした");
} catch (e) {
  const msg = e instanceof Error ? e.message : String(e);
  if (!msg.includes("kernel32.CreateFileA")) {
    fail(`フォワーダの例外メッセージが不正: ${msg}`);
  }
  console.log(`[smoke] fail-fast forwarder OK (throw: "${msg}")`);
}

// 3. 空バイト列は fail-fast されることの確認
try {
  await instantiateWasm(new Uint8Array(0));
  fail("空バイト列で例外が投げられませんでした");
} catch {
  console.log("[smoke] 空 wasm バイト列の fail-fast OK");
}

console.log("[smoke] ALL OK");
