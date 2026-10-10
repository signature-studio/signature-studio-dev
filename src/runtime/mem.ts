/**
 * メモリモデル (tools/runtime/DESIGN.md §1 の決定を型/定数として固定する)。
 *
 * 決定: 既定は wasm32 + LVA 敷設 (PE ImageBase を引いた線形アドレス)。
 *       Memory64 は「同一 IR を p:64 datalayout で再ビルドすれば動く」ことを実測済みの退避路として
 *       `MemoryModel = "wasm64"` で型だけ保持する (DOM / Worker どちらからも import 可)。
 */

export const WASM_PAGE = 65536;
export const GiB = 1024 * 1024 * 1024;
export const MAX_PAGES_WASM32 = 65536; // 4GiB

export type MemoryModel = "wasm32" | "wasm64";

export type MemoryPlan = {
  model: MemoryModel;
  initialPages: number;
  maximumPages: number;
  /** pthread (共有 wasm memory) 用。true なら SharedArrayBuffer 背面 (crossOriginIsolated 必須) */
  shared: boolean;
};

/**
 * 線形アドレス計画 (wasm32 / M11 実績値)。
 *   [0x00000000, 0x018c0000)  FLEngine PE イメージ (linear = VA - ImageBase(0x400000) = RVA)
 *   [0x10000000, ...)         emscripten 静的データ (GLOBAL_BASE=256MiB。M6/M8–M11 共通)
 *   その上                    スタック (8MiB) → shim malloc arena (sbrk 成長, 上限 4GiB)
 * 64bit PE の ImageBase(0x180000000) を持つプラグイン DLL は 4GiB を超えるため V-shift (M6: +0x30000000) し、
 * プラグインごとに別 wasm インスタンス (= 別 Memory) に載せる。
 */
export const LAYOUT = {
  FLENGINE_IMAGE_BASE: 0x400000,
  FLENGINE_SIZE_OF_IMAGE: 0x18c0000,
  GLOBAL_BASE: 0x10000000,
  PLUGIN_IMAGE_BASE: 0x180000000,
  PLUGIN_VSHIFT_BASE: 0x30000000,
} as const;

/** FLEngine の仮想アドレス → wasm32 線形アドレス (LVA)。 */
export function flengineVaToLinear(va: number): number {
  return va - LAYOUT.FLENGINE_IMAGE_BASE;
}

/** 64bit プラグイン DLL の仮想アドレス (0x180000000+RVA) → V-shift 後線形アドレス。 */
export function pluginVaToLinear(va: bigint): number {
  return Number(va - BigInt(LAYOUT.PLUGIN_IMAGE_BASE)) + LAYOUT.PLUGIN_VSHIFT_BASE;
}

export const DEFAULT_PLAN: MemoryPlan = {
  model: "wasm32",
  initialPages: Math.ceil((300 * 1024 * 1024) / WASM_PAGE), // M11 実績: 静的データ 294MiB
  maximumPages: MAX_PAGES_WASM32,
  shared: false,
};

type MemoryTypeInfo = { address?: string; shared?: boolean; minimum: number | bigint; maximum?: number | bigint };

/** WebAssembly.Memory の実体モデルを調べる (type reflection 無ければ wasm32 とみなす)。 */
export function describeMemory(mem: WebAssembly.Memory): {
  model: MemoryModel;
  shared: boolean;
  bytes: number;
} {
  const t = (mem as unknown as { type?: () => MemoryTypeInfo }).type?.();
  const buf = mem.buffer;
  return {
    model: t?.address === "i64" ? "wasm64" : "wasm32",
    shared: t?.shared ?? (typeof SharedArrayBuffer !== "undefined" && buf instanceof SharedArrayBuffer),
    bytes: buf.byteLength,
  };
}

/** 計画に従い Memory を生成 (imported-memory ビルド用)。wasm64 は BigInt 記述子になる。 */
export function createMemory(plan: MemoryPlan): WebAssembly.Memory {
  if (plan.shared && typeof crossOriginIsolated !== "undefined" && !crossOriginIsolated) {
    throw new Error("[mem] shared memory には crossOriginIsolated (COOP/COEP) が必要です");
  }
  const desc: Record<string, unknown> =
    plan.model === "wasm64"
      ? {
          address: "i64",
          initial: BigInt(plan.initialPages),
          maximum: BigInt(plan.maximumPages),
        }
      : { initial: plan.initialPages, maximum: plan.maximumPages };
  if (plan.shared) desc["shared"] = true;
  return new WebAssembly.Memory(desc as unknown as WebAssembly.MemoryDescriptor);
}

/**
 * emscripten_resize_heap 相当。requestedBytes に届くまで Memory を伸ばす。
 * 成功 true / 上限超過 false。共有メモリでも grow は全スレッドに見える (buffer は取り直しが必要)。
 */
export function growMemoryTo(mem: WebAssembly.Memory, requestedBytes: number, maxPages = MAX_PAGES_WASM32): boolean {
  const cur = mem.buffer.byteLength / WASM_PAGE;
  const need = Math.ceil(requestedBytes / WASM_PAGE);
  if (need <= cur) return true;
  // 1.25x 以上伸ばして grow 回数を抑える (grow は新 ArrayBuffer を作るため view の取り直しが必要)
  const target = Math.min(maxPages, Math.max(need, Math.ceil(cur * 1.25)));
  if (target < need) return false;
  const model = describeMemory(mem).model;
  try {
    const delta = target - cur;
    mem.grow((model === "wasm64" ? BigInt(delta) : delta) as never);
    return true;
  } catch {
    try {
      const delta = need - cur;
      mem.grow((model === "wasm64" ? BigInt(delta) : delta) as never);
      return true;
    } catch {
      return false;
    }
  }
}

/**
 * Memory 上の型付き view。grow で buffer が差し替わるため、アクセス毎に `refresh()` 済みか確認する。
 * wasm64 でもヒープ 4GiB 未満の間は number で扱える (全アドレスは LVA 敷設で 2^32 未満)。
 */
export class MemoryView {
  private _buf: ArrayBufferLike | null = null;
  private _u8!: Uint8Array;
  private _dv!: DataView;
  constructor(readonly memory: WebAssembly.Memory) {
    this.refresh();
  }
  refresh(): void {
    const b = this.memory.buffer;
    if (b !== this._buf) {
      this._buf = b;
      this._u8 = new Uint8Array(b);
      this._dv = new DataView(b);
    }
  }
  get u8(): Uint8Array {
    this.refresh();
    return this._u8;
  }
  get dv(): DataView {
    this.refresh();
    return this._dv;
  }
  get byteLength(): number {
    return this.memory.buffer.byteLength;
  }
  u32(addr: number): number {
    return this.dv.getUint32(addr, true);
  }
  setU32(addr: number, v: number): void {
    this.dv.setUint32(addr, v >>> 0, true);
  }
  u64(addr: number): bigint {
    return this.dv.getBigUint64(addr, true);
  }
  setU64(addr: number, v: bigint): void {
    this.dv.setBigUint64(addr, v, true);
  }
  f32(addr: number): number {
    return this.dv.getFloat32(addr, true);
  }
  /** SharedArrayBuffer 背面の TextDecoder は view の copy が必要 (decode は共有 view 不可) */
  private copy(addr: number, len: number): Uint8Array {
    const out = new Uint8Array(len);
    out.set(this.u8.subarray(addr, addr + len));
    return out;
  }
  readBytes(addr: number, len: number): Uint8Array {
    return this.copy(addr, len);
  }
  writeBytes(addr: number, src: Uint8Array): void {
    this.u8.set(src, addr);
  }
  readUtf8(addr: number, len: number): string {
    return new TextDecoder().decode(this.copy(addr, len));
  }
  readCString(addr: number, max = 4096): string {
    const u8 = this.u8;
    let end = addr;
    while (end - addr < max && u8[end] !== 0) end++;
    return this.readUtf8(addr, end - addr);
  }
}
