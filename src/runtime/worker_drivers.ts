/**
 * Worker 内で wasm を駆動する「プログラム」群。
 * 本番の FL 起動 (fl-main) が入るまでは既存 PoC wasm (M1/M6/M10/M11) を同じ経路で走らせる検証用ドライバ。
 * 各ドライバは ProgramResult を返す (checks = 自己検証, data = ブラウザ⇔node 参照比較用の値)。
 */

import { createEmJsImports, createEnvImports, flushStdio, type EnvHost } from "./imports_env";
import { instantiateCompiled } from "./loader";
import { buildImports, initEmscripten } from "./loader_boot";
import { MemoryView, describeMemory } from "./mem";
import type { ManifestEntry, ProgramResult, Check } from "./worker_protocol";

export type DriverCtx = {
  module: WebAssembly.Module;
  entry: ManifestEntry;
  log: (stream: "stdout" | "stderr" | "info", text: string) => void;
};

export type Instantiated = {
  exports: Record<string, unknown>;
  memory: WebAssembly.Memory;
  mem: MemoryView;
  unresolved: string[];
  stdout: string[];
  stderr: string[];
  initialized: string[];
  initMs: number;
  instantiateMs: number;
  env: ReturnType<typeof createEnvImports>;
};

/** emscripten 標準 wasm のインスタンス化 + 定型初期化 (stack_init → ctors) */
export async function instantiateStandard(ctx: DriverCtx, opts: { runInit?: boolean } = {}): Promise<Instantiated> {
  const stdout: string[] = [];
  const stderr: string[] = [];
  let memory: WebAssembly.Memory | null = null;
  let table: WebAssembly.Table | null = null;
  let exportsRef: Record<string, unknown> | null = null;
  const host: EnvHost = {
    getMemory: () => memory,
    getTable: () => table,
    getExports: () => exportsRef,
    onStdio: (stream, line) => {
      (stream === "stdout" ? stdout : stderr).push(line);
      ctx.log(stream, line);
    },
  };
  const env = createEnvImports(host);
  const emjs = createEmJsImports(ctx.module, host);
  const { imports, unresolved } = buildImports(ctx.module, [env, emjs]);
  const t0 = performance.now();
  const { instance } = await instantiateCompiled(ctx.module, imports);
  const instantiateMs = performance.now() - t0;
  const exports = instance.exports as Record<string, unknown>;
  exportsRef = exports;
  memory = exports["memory"] as WebAssembly.Memory;
  table = (exports["__indirect_function_table"] as WebAssembly.Table | undefined) ?? null;
  const t1 = performance.now();
  const initialized = opts.runInit === false ? [] : initEmscripten(instance.exports);
  const initMs = performance.now() - t1;
  return { exports, memory, mem: new MemoryView(memory), unresolved, stdout, stderr, initialized, initMs, instantiateMs, env };
}

const fn = (ex: Record<string, unknown>, name: string) => {
  const f = ex[name];
  if (typeof f !== "function") throw new Error(`export '${name}' が見つかりません`);
  return f as (...a: unknown[]) => unknown;
};

// ---------------------------------------------------------------- M1 hello
async function m1Hello(ctx: DriverCtx): Promise<ProgramResult> {
  const inst = await instantiateStandard(ctx);
  const rc = fn(inst.exports, "__main_argc_argv")(0, 0);
  flushStdio(inst.env);
  const text = inst.stdout.join("\n");
  const checks: Check[] = [
    { name: "stdout == 'hello from e2e, answer=42'", ok: text === "hello from e2e, answer=42", detail: text },
    { name: "main rc == 0", ok: rc === 0, detail: String(rc) },
    { name: "unresolved imports == 0", ok: inst.unresolved.length === 0, detail: inst.unresolved.join(",") },
  ];
  return { ok: checks.every((c) => c.ok), checks, data: { instantiateMs: inst.instantiateMs, initMs: inst.initMs, stdout: text, rc, memory: describeMemory(inst.memory) } };
}

// ---------------------------------------------------------------- OTT DSP (M6/M10 lifted)
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = 256;
const f32bits = (v: number): bigint => {
  const f = new Float32Array([v]);
  return BigInt(new Uint32Array(f.buffer)[0]!);
};

async function ottT1(ctx: DriverCtx): Promise<ProgramResult> {
  const inst = await instantiateStandard(ctx);
  const ex = inst.exports;
  fn(ex, "m6_data_install")();
  const m = inst.mem;
  // M6 世代の setParam は 2 引数 (f32 引数接続前)、M7 以降は 3 引数。wasm export の length で判別
  const setParamArity = fn(ex, "function_180120af0").length;
  const setup = (val: number) => {
    fn(ex, "function_18011d400")(BigInt(OBJ), 0n);
    for (let i = 0; i < 20; i++) {
      if (setParamArity >= 3) fn(ex, "function_180120af0")(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32bits(val));
      else fn(ex, "function_180120af0")(BigInt(OBJ), BigInt(i));
    }
    fn(ex, "function_180120800")(BigInt(OBJ));
    m.u8[OBJ + 0x248] = 0;
    const f32 = new Float32Array(m.memory.buffer);
    for (let i = 0; i < N; i++) {
      f32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
      f32[BUF / 4 + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
    }
    m.setU32(IN_A, BUF); m.setU32(IN_A + 8, BUF + N * 4);
    m.setU32(OU_A, BUF + N * 8); m.setU32(OU_A + 8, BUF + N * 12);
  };
  const process = () => fn(ex, "function_18011ec20")(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const hash = (): number => {
    let h = 0x811c9dc5;
    for (let i = 0; i < N * 2; i++) {
      h ^= m.u32(BUF + N * 8 + i * 4);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h >>> 0;
  };
  const hex = (n: number) => n.toString(16).padStart(8, "0");

  setup(0.5);
  const ctorOk = m.u32(OBJ + 0x30c) === 1 && m.u32(OBJ + 0x310) === 1;
  process();
  const h1 = hash();
  setup(0.5);
  process();
  const h2 = hash();
  setup(0.1);
  process();
  const h3 = hash();
  // 参考速度 (情報のみ。判定には使わない)
  setup(0.5);
  const t0 = performance.now();
  for (let i = 0; i < 100; i++) process();
  const usPerBlock = ((performance.now() - t0) * 1000) / 100;

  const checks: Check[] = [
    { name: "ctor/resume flags ([0x30c]/[0x310] == 1/1)", ok: ctorOk },
    { name: "processReplacing 完走 (trap なし)", ok: true },
    { name: "determinism (再実行で出力 bit 一致)", ok: h1 === h2, detail: `${hex(h1)} / ${hex(h2)}` },
    setParamArity >= 3
      ? { name: "param 応答 (0.5 vs 0.1 で出力が変化)", ok: h1 !== h3, detail: `${hex(h1)} vs ${hex(h3)}` }
      : { name: "param 応答 (n/a: setParam 2 引数 ABI = M6 世代)", ok: true },
  ];
  return {
    ok: checks.every((c) => c.ok),
    checks,
    data: { instantiateMs: inst.instantiateMs, initMs: inst.initMs, hash0_5: hex(h1), hash0_1: hex(h3), unresolvedCount: inst.unresolved.length, usPerBlock: +usPerBlock.toFixed(2), memory: describeMemory(inst.memory) },
  };
}

// ---------------------------------------------------------------- M11 FLEngine boot
async function m11Boot(ctx: DriverCtx): Promise<ProgramResult> {
  const inst = await instantiateStandard(ctx);
  const ex = inst.exports;
  let threw: string | null = null;
  let rc: string | null = null;
  const t0 = performance.now();
  try {
    rc = String(fn(ex, "m11_boot_enter")(0n, 1n));
  } catch (e) {
    threw = e instanceof Error ? e.message : JSON.stringify(e);
  }
  const bootMs = performance.now() - t0;
  flushStdio(inst.env);
  const stage = Number(fn(ex, "m11_boot_stage")()) | 0;
  const initCount = Number(fn(ex, "m11_init_count")()) | 0;
  const vaUsed = Number(fn(ex, "m11_va_used")());
  const vaCalls = Number(fn(ex, "m11_va_calls")());
  const checks: Check[] = [
    { name: "module instantiate + ctors", ok: true, detail: `init ${inst.initMs.toFixed(0)}ms` },
    { name: "m11_boot_enter に到達 (stage >= 1)", ok: stage >= 1, detail: `stage=${stage}` },
  ];
  return {
    ok: checks.every((c) => c.ok),
    checks,
    data: { instantiateMs: inst.instantiateMs, initMs: inst.initMs, threw, rc, stage, initCount, vaUsed, vaCalls, bootMs: +bootMs.toFixed(1), memory: describeMemory(inst.memory), unresolvedCount: inst.unresolved.length, stdoutLines: inst.stdout.length, stderrTail: inst.stderr.slice(-3) },
  };
}

export const DRIVERS: Record<string, (ctx: DriverCtx) => Promise<ProgramResult>> = {
  "m1-hello": m1Hello,
  "ott-t1": ottT1,
  "m11-boot": m11Boot,
};
