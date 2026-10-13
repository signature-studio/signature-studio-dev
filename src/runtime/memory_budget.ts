/**
 * WebAssembly.Memory 個数予算 (RT-6 / #125)。
 *
 * 1 レンダラプロセスで作れる Memory は wasm32 = 124 個 / wasm64 (max 16GiB) = 62 個 (tools/runtime/REPORT.md RT-6)。
 * main と Worker の合算で数えられる (main 60 + Worker 64 で 124)。「プラグイン DLL 1 本 = 1 Memory」では
 * 上限到達が `RangeError: could not allocate memory` として実行時に突然現れるため、
 * Memory 生成の前に個数を予約し、枯渇時は LRU で未使用プラグインを追い出す。
 *
 * - `MemoryBudget`: 個数カウンタ。`SharedArrayBuffer` 背面にすれば main / Worker / pthread 間で共有できる。
 * - `PluginPool`: プラグイン 1 本 = 1 Memory の遅延ロード・LRU 追い出し。
 *
 * DOM / Worker どちらからも import 可 (依存なし)。
 */

/** 実測した 1 レンダラ上限 (Chrome 154, 検収再測も同値)。wasm64 は wasm32 の 2 倍の枠を消費するとみなす。 */
export const NATIVE_MEMORY_LIMIT_WASM32 = 124;
export const SLOTS_PER_MEMORY = { wasm32: 1, wasm64: 2 } as const;
/** FLEngine 本体・AudioWorklet・GUI 等のプラグイン以外が使う分を差し引いた、プラグインへの既定割当 (issue: 同時ロード <100)。 */
export const DEFAULT_PLUGIN_CAPACITY = 96;

export type MemoryKind = keyof typeof SLOTS_PER_MEMORY;

export class MemoryBudgetExceeded extends Error {
  readonly owner: string;
  readonly requested: number;
  readonly inUse: number;
  readonly capacity: number;
  constructor(owner: string, requested: number, inUse: number, capacity: number) {
    super(`[memory-budget] "${owner}": ${requested} slot 要求, 使用中 ${inUse}/${capacity}`);
    this.name = "MemoryBudgetExceeded";
    this.owner = owner;
    this.requested = requested;
    this.inUse = inUse;
    this.capacity = capacity;
  }
}

export type Lease = {
  readonly owner: string;
  readonly slots: number;
  readonly released: boolean;
  /** 冪等。枠を返す (Memory への参照を落とすのは呼び出し側の責務) */
  release(): void;
};

export class MemoryBudget {
  readonly capacity: number;
  private readonly counter: Int32Array;

  /**
   * @param capacity  同時に保持できる slot 数 (wasm32 Memory = 1 slot)
   * @param shared    他スレッドと共有するカウンタ (`MemoryBudget.createSharedCounter()` の戻り値を postMessage で渡す)。
   *                  省略時はこのスレッド内だけのカウンタ
   */
  constructor(capacity: number = DEFAULT_PLUGIN_CAPACITY, shared?: SharedArrayBuffer) {
    if (!Number.isInteger(capacity) || capacity < 1) throw new RangeError(`capacity: ${capacity}`);
    this.capacity = capacity;
    this.counter = new Int32Array(shared ?? new ArrayBuffer(4));
  }

  static createSharedCounter(): SharedArrayBuffer {
    return new SharedArrayBuffer(4);
  }

  /** プロセス (カウンタ共有範囲) 全体の使用 slot 数 */
  get inUse(): number {
    return Atomics.load(this.counter, 0);
  }

  /** 枠を予約する。足りなければ予約せず null (CAS ループなのでスレッド間で超過予約しない) */
  tryAcquire(owner: string, kind: MemoryKind = "wasm32"): Lease | null {
    const slots = SLOTS_PER_MEMORY[kind];
    for (;;) {
      const cur = Atomics.load(this.counter, 0);
      if (cur + slots > this.capacity) return null;
      if (Atomics.compareExchange(this.counter, 0, cur, cur + slots) === cur) break;
    }
    let released = false;
    return {
      owner,
      slots,
      get released() {
        return released;
      },
      release: () => {
        if (released) return;
        released = true;
        Atomics.sub(this.counter, 0, slots);
      },
    };
  }

  acquire(owner: string, kind: MemoryKind = "wasm32"): Lease {
    const l = this.tryAcquire(owner, kind);
    if (!l) throw new MemoryBudgetExceeded(owner, SLOTS_PER_MEMORY[kind], this.inUse, this.capacity);
    return l;
  }
}

/** 枠を予約してから Memory を作る。作成に失敗したら枠を返して再 throw (予約リークなし)。 */
export function createBudgetedMemory(
  budget: MemoryBudget,
  owner: string,
  desc: { initial: number; maximum?: number; shared?: boolean },
): { memory: WebAssembly.Memory; lease: Lease } {
  const lease = budget.acquire(owner, "wasm32");
  try {
    return { memory: new WebAssembly.Memory(desc), lease };
  } catch (e) {
    lease.release();
    throw e;
  }
}

export type PluginLoad<T> = { value: T; kind?: MemoryKind; dispose?: () => void };

type Entry<T> = {
  id: string;
  value: T;
  lease: Lease;
  dispose?: () => void;
  pins: number;
  lastUsed: number;
};

export type PoolHandle<T> = { readonly id: string; readonly value: T; unpin(): void };

/** ロード中の id。`waiters` = この完了を待つ pin() 呼び出し数 (同期で加算され、エントリ登録時に pins として引き継ぐ) */
type Loading<T> = { promise: Promise<Entry<T>>; waiters: number };

/**
 * 「プラグイン 1 本 = 1 Memory」のプール。`pin` で取得 (未ロードならロード)、`unpin` で使用終了 (ウォーム保持)。
 * 枠が無ければ pin 数 0 のエントリを LRU 順に追い出して再試行。全て pin 中なら MemoryBudgetExceeded。
 * 追い出し = lease 返却 + dispose + Map からの参照除去 (Memory は参照が切れれば GC で回収される。実測済み)。
 */
export class PluginPool<T> {
  private readonly entries = new Map<string, Entry<T>>();
  private readonly loading = new Map<string, Loading<T>>();
  private tick = 0;
  evictions = 0;
  private readonly budget: MemoryBudget;
  private readonly load: (id: string) => Promise<PluginLoad<T>>;

  constructor(budget: MemoryBudget, load: (id: string) => Promise<PluginLoad<T>>) {
    this.budget = budget;
    this.load = load;
  }

  get size(): number {
    return this.entries.size;
  }

  has(id: string): boolean {
    return this.entries.has(id);
  }

  async pin(id: string): Promise<PoolHandle<T>> {
    let e = this.entries.get(id);
    if (e) {
      e.pins++;
    } else {
      let l = this.loading.get(id);
      if (!l) {
        const nl = { waiters: 0 } as Loading<T>;
        nl.promise = this.loadOne(id, () => nl.waiters).finally(() => {
          if (this.loading.get(id) === nl) this.loading.delete(id);
        });
        this.loading.set(id, nl);
        l = nl;
      }
      // pin は loadOne がエントリを登録する時点で waiters 分が確保済み (await 後に pins++ すると、その間に
      // 別 id のロードが pins=0 のこのエントリを追い出し、破棄済みハンドルを返す)
      l.waiters++;
      e = await l.promise;
    }
    e.lastUsed = ++this.tick;
    const entry = e;
    let done = false;
    return {
      id,
      value: entry.value,
      unpin: () => {
        if (done) return;
        done = true;
        entry.pins--;
      },
    };
  }

  /** pin 数 0 のエントリを LRU で 1 つ追い出す。追い出せたら true */
  evictOne(): boolean {
    let victim: Entry<T> | null = null;
    for (const e of this.entries.values()) if (e.pins === 0 && (!victim || e.lastUsed < victim.lastUsed)) victim = e;
    if (!victim) return false;
    this.drop(victim);
    this.evictions++;
    return true;
  }

  /** 強制アンロード (pin 中は false) */
  unload(id: string): boolean {
    const e = this.entries.get(id);
    if (!e || e.pins > 0) return false;
    this.drop(e);
    return true;
  }

  private drop(e: Entry<T>): void {
    this.entries.delete(e.id);
    try {
      e.dispose?.();
    } finally {
      e.lease.release();
    }
  }

  private async loadOne(id: string, initialPins: () => number): Promise<Entry<T>> {
    // 枠は load() の前に確保できないので (kind が load 結果で決まる)、まず wasm32 1 枠を確保 → 結果の kind で差分調整
    let lease = this.budget.tryAcquire(id, "wasm32");
    while (!lease) {
      if (!this.evictOne()) throw new MemoryBudgetExceeded(id, 1, this.budget.inUse, this.budget.capacity);
      lease = this.budget.tryAcquire(id, "wasm32");
    }
    let r: PluginLoad<T>;
    try {
      r = await this.load(id);
    } catch (err) {
      lease.release();
      throw err;
    }
    if (r.kind && r.kind !== "wasm32") {
      // wasm64: 追加の枠を取る (足りなければ追い出し)。取れなければ全て巻き戻す
      let ex = this.budget.tryAcquire(id, "wasm32");
      try {
        while (!ex) {
          if (!this.evictOne()) throw new MemoryBudgetExceeded(id, SLOTS_PER_MEMORY[r.kind], this.budget.inUse, this.budget.capacity);
          ex = this.budget.tryAcquire(id, "wasm32");
        }
      } catch (err) {
        // victim の dispose が throw した場合も含め、確保済みの base 枠を返す
        lease.release();
        r.dispose?.();
        throw err;
      }
      const base = lease;
      lease = {
        owner: id,
        slots: 2,
        get released() {
          return base.released;
        },
        release() {
          base.release();
          ex!.release();
        },
      };
    }
    const e: Entry<T> = { id, value: r.value, lease, dispose: r.dispose, pins: initialPins(), lastUsed: ++this.tick };
    this.entries.set(id, e);
    return e;
  }
}
