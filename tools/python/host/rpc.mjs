// SAB 同期 RPC: Python worker(client, 同期ブロック) ⇄ FLEngine 側(server, 非同期)。
// postMessage を介さず Atomics のみで往復する (client: Atomics.wait, server: Atomics.waitAsync)。
//
// 共有メモリ構成: ctrl = Int32Array(sab, 0, 4)  [0]=state(0 idle,1 req,2 resp) [1]=reqLen [2]=respLen [3]=reserved
//                 data = Uint8Array(sab, 16)     要求/応答 JSON を同一領域に交互に置く
export const RPC_DATA_BYTES = 1 << 20;
export function createRpcBuffer() {
  return new SharedArrayBuffer(16 + RPC_DATA_BYTES);
}

const te = new TextEncoder();
const td = new TextDecoder();

export class RpcClient {
  constructor(sab) {
    this.ctrl = new Int32Array(sab, 0, 4);
    this.data = new Uint8Array(sab, 16);
  }
  /** 同期呼出し。Worker 内専用 (Atomics.wait はメインスレッドで不可)。 */
  call(msg) {
    const bytes = te.encode(JSON.stringify(msg));
    if (bytes.length > this.data.length) throw new Error("rpc request too large");
    this.data.set(bytes, 0);
    this.ctrl[1] = bytes.length;
    Atomics.store(this.ctrl, 0, 1);
    Atomics.notify(this.ctrl, 0);
    while (Atomics.load(this.ctrl, 0) !== 2) Atomics.wait(this.ctrl, 0, 1);
    const res = JSON.parse(td.decode(this.data.slice(0, this.ctrl[2])));
    Atomics.store(this.ctrl, 0, 0);
    Atomics.notify(this.ctrl, 0);
    return res;
  }
}

export class RpcServer {
  /** handler(msg) -> response (同期/非同期どちらも可) */
  constructor(sab, handler) {
    this.ctrl = new Int32Array(sab, 0, 4);
    this.data = new Uint8Array(sab, 16);
    this.handler = handler;
    this.running = true;
    this.served = 0;
    this.done = this.#loop();
  }
  async #loop() {
    while (this.running) {
      const s = Atomics.load(this.ctrl, 0);
      if (s === 1) {
        let out;
        try {
          const msg = JSON.parse(td.decode(this.data.slice(0, this.ctrl[1])));
          out = { ok: await this.handler(msg) };
        } catch (e) {
          out = { err: String(e && e.message || e), code: (e && e.flCode) || 0 };
        }
        const bytes = te.encode(JSON.stringify(out));
        this.data.set(bytes, 0);
        this.ctrl[2] = bytes.length;
        Atomics.store(this.ctrl, 0, 2);
        Atomics.notify(this.ctrl, 0);
        this.served++;
      } else {
        const w = Atomics.waitAsync(this.ctrl, 0, s);
        if (w.async) await w.value;
      }
    }
  }
  stop() {
    this.running = false;
    Atomics.add(this.ctrl, 3, 1);
    Atomics.store(this.ctrl, 0, Atomics.load(this.ctrl, 0));
    Atomics.notify(this.ctrl, 0);
  }
}
