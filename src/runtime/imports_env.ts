/**
 * emscripten (-sSTANDALONE 風 / glue 無し) wasm が要求する env / wasi import の JS 実装。
 * - 既存 M1/M6/M10/M11 の `-sENVIRONMENT=node` ビルドが要求する名前を glue 無しで満たす。
 * - ここに無い import (Win32 API / lifted function_xxxx) は loader.buildImports が fail-fast フォワーダで埋める。
 * - wasm64 ビルドではポインタ引数が BigInt になる → n() で吸収。
 * DOM 非依存。
 */

import { growMemoryTo, MemoryView, describeMemory } from "./mem";

export class ExitStatus extends Error {
  constructor(readonly code: number) {
    super(`exit(${code})`);
    this.name = "ExitStatus";
  }
}
export class WasmAbort extends Error {
  constructor(msg = "abort()") {
    super(msg);
    this.name = "WasmAbort";
  }
}

export type EnvHost = {
  /** instantiate 後に確定する (imported memory の場合は事前に渡す) */
  getMemory: () => WebAssembly.Memory | null;
  getTable?: () => WebAssembly.Table | null;
  /** EM_JS / EM_ASM 本体解決用 (instantiate 後の exports。初回呼び出し時に参照される) */
  getExports?: () => Record<string, unknown> | null;
  /** fd 1/2 の行バッファ出力先 */
  onStdio: (stream: "stdout" | "stderr", line: string) => void;
};

type Fn = (...a: never[]) => unknown;
const n = (v: unknown): number => (typeof v === "bigint" ? Number(v) : (v as number));

const ENOENT = -44;
const ENOSYS = -52;
const EBADF = 8;
const ESPIPE = 70;

/** key = "module.name" */
export function createEnvImports(host: EnvHost): Record<string, Fn> {
  let view: MemoryView | null = null;
  const mv = (): MemoryView => {
    const m = host.getMemory();
    if (!m) throw new Error("[env] memory 未確定");
    if (!view || view.memory !== m) view = new MemoryView(m);
    return view;
  };
  const ptrSize = (): number => (describeMemory(mv().memory).model === "wasm64" ? 8 : 4);
  const pending: Record<number, string> = { 1: "", 2: "" };
  const emit = (fd: number, text: string) => {
    const stream = fd === 2 ? "stderr" : "stdout";
    pending[fd] = (pending[fd] ?? "") + text;
    let i: number;
    while ((i = pending[fd]!.indexOf("\n")) >= 0) {
      host.onStdio(stream, pending[fd]!.slice(0, i));
      pending[fd] = pending[fd]!.slice(i + 1);
    }
  };
  const flush = () => {
    for (const fd of [1, 2]) if (pending[fd]) { host.onStdio(fd === 2 ? "stderr" : "stdout", pending[fd]!); pending[fd] = ""; }
  };

  const impl: Record<string, Fn> = {
    "env.emscripten_get_now": (() => performance.now()) as Fn,
    "env.emscripten_resize_heap": ((req: unknown) => {
      const m = host.getMemory();
      return m && growMemoryTo(m, n(req)) ? 1 : 0;
    }) as Fn,
    "env._abort_js": (() => { throw new WasmAbort(); }) as Fn,
    "env.exit": ((c: unknown) => { flush(); throw new ExitStatus(n(c)); }) as Fn,
    "wasi_snapshot_preview1.proc_exit": ((c: unknown) => { flush(); throw new ExitStatus(n(c)); }) as Fn,
    "env.emscripten_err": ((p: unknown) => emit(2, mv().readCString(n(p)) + "\n")) as Fn,
    "env._emscripten_runtime_keepalive_clear": (() => {}) as Fn,
    "env.__call_sighandler": ((fn: unknown, sig: unknown) => {
      const t = host.getTable?.();
      const f = t?.get(n(fn)) as ((s: number) => void) | null | undefined;
      if (!f) throw new Error(`[env] __call_sighandler: table[${n(fn)}] 無し`);
      f(n(sig));
    }) as Fn,
    "wasi_snapshot_preview1.fd_close": (() => 0) as Fn,
    "wasi_snapshot_preview1.fd_seek": (() => ESPIPE) as Fn,
    "wasi_snapshot_preview1.fd_fdstat_get": ((fd: unknown, p: unknown) => {
      const f = n(fd);
      if (f > 2) return EBADF;
      const m = mv();
      m.u8.fill(0, n(p), n(p) + 24);
      m.u8[n(p)] = 2; // FILETYPE_CHARACTER_DEVICE
      return 0;
    }) as Fn,
    "wasi_snapshot_preview1.fd_read": ((_fd: unknown, _iov: unknown, _cnt: unknown, pnum: unknown) => {
      const ps = ptrSize();
      if (ps === 8) mv().setU64(n(pnum), 0n); else mv().setU32(n(pnum), 0);
      return 0;
    }) as Fn,
    "wasi_snapshot_preview1.fd_write": ((fd: unknown, iov: unknown, cnt: unknown, pnum: unknown) => {
      const m = mv(), ps = ptrSize();
      const base = n(iov);
      let total = 0, text = "";
      const dec = new TextDecoder();
      for (let i = 0; i < n(cnt); i++) {
        const o = base + i * ps * 2;
        const p = ps === 8 ? Number(m.u64(o)) : m.u32(o);
        const len = ps === 8 ? Number(m.u64(o + 8)) : m.u32(o + 4);
        text += dec.decode(m.readBytes(p, len), { stream: true });
        total += len;
      }
      if (n(fd) === 1 || n(fd) === 2) emit(n(fd), text);
      if (ps === 8) m.setU64(n(pnum), BigInt(total)); else m.setU32(n(pnum), total);
      return 0;
    }) as Fn,
  };
  for (const k of ["openat", "stat64", "lstat64", "fstat64", "newfstatat"]) impl[`env.__syscall_${k}`] = (() => ENOENT) as Fn;
  impl["env.__syscall_ftruncate64"] = (() => ENOSYS) as Fn;
  Object.defineProperty(impl, "__flush", { value: flush, enumerable: false });
  return impl;
}

/** "(int code)" / "$0, $1" → ["code"] / ["$0","$1"] */
function paramNames(list: string): string[] {
  return list
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => p.split(/[\s*&]+/).filter(Boolean).pop()!);
}

/**
 * EM_JS / EM_ASM の汎用実装 (glue 無しで動かすため)。
 *  - EM_JS(ret, NAME, (args), { body }): wasm が env.NAME を import し、`__em_js__NAME` export (= C 文字列 "(args)<::>{body}")
 *    を持つ → 初回呼び出し時にその文字列から Function を生成。
 *  - EM_ASM: env.emscripten_asm_const_{int,double,ptr}(code, sigPtr, argbuf) → code 文字列 "$0,$1<::>{body}" を実行。
 */
export function createEmJsImports(module: WebAssembly.Module, host: EnvHost): Record<string, Fn> {
  const exportNames = new Set(WebAssembly.Module.exports(module).map((e) => e.name));
  const out: Record<string, Fn> = {};
  let view: MemoryView | null = null;
  const mv = (): MemoryView => {
    const m = host.getMemory();
    if (!m) throw new Error("[emjs] memory 未確定");
    if (!view || view.memory !== m) view = new MemoryView(m);
    return view;
  };
  const build = (src: string): ((...a: unknown[]) => unknown) => {
    const i = src.indexOf("<::>");
    if (i < 0) throw new Error(`[emjs] '<::>' 区切り無し: ${src.slice(0, 80)}`);
    let params = src.slice(0, i).trim();
    if (params.startsWith("(")) params = params.slice(1, params.lastIndexOf(")"));
    return new Function(...paramNames(params), src.slice(i + 4)) as (...a: unknown[]) => unknown;
  };
  for (const imp of WebAssembly.Module.imports(module)) {
    if (imp.kind !== "function" || !exportNames.has(`__em_js__${imp.name}`)) continue;
    let f: ((...a: unknown[]) => unknown) | null = null;
    out[`${imp.module}.${imp.name}`] = ((...args: unknown[]) => {
      if (!f) {
        const g = host.getExports?.()?.[`__em_js__${imp.name}`] as WebAssembly.Global | undefined;
        if (!g) throw new Error(`[emjs] __em_js__${imp.name} が export に見つかりません`);
        f = build(mv().readCString(Number(g.value), 1 << 16));
      }
      return f(...args);
    }) as Fn;
  }
  const asmCache = new Map<number, (...a: unknown[]) => unknown>();
  const asmConst = ((code: unknown, sigPtr: unknown, argbuf: unknown) => {
    const m = mv();
    const c = n(code);
    let f = asmCache.get(c);
    if (!f) asmCache.set(c, (f = build(m.readCString(c, 1 << 16))));
    const sig = m.readCString(n(sigPtr), 64);
    const ps = describeMemory(m.memory).model === "wasm64" ? 8 : 4;
    let buf = n(argbuf);
    const args: unknown[] = [];
    for (const ch of sig) {
      if (ch === "d") { buf = (buf + 7) & ~7; args.push(m.dv.getFloat64(buf, true)); buf += 8; }
      else if (ch === "j") { buf = (buf + 7) & ~7; args.push(m.u64(buf)); buf += 8; }
      else if (ch === "p" && ps === 8) { buf = (buf + 7) & ~7; args.push(Number(m.u64(buf))); buf += 8; }
      else { args.push(m.dv.getInt32(buf, true)); buf += 4; }
    }
    return f(...args);
  }) as Fn;
  for (const k of ["int", "double", "ptr", "int_sync_on_main_thread", "double_sync_on_main_thread", "ptr_sync_on_main_thread"]) out[`env.emscripten_asm_const_${k}`] = asmConst;
  return out;
}

export function flushStdio(env: Record<string, Fn>): void {
  (env as unknown as { __flush?: () => void }).__flush?.();
}
