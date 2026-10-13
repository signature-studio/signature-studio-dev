/**
 * FL MIDI shim — JS コントローラ (Web MIDI ⇄ SAB MIDI ring)。
 *
 * wasm 側 (tools/audio/src/flmidi*.c) は winmm midiIn と midiOut 互換の実体で、Web MIDI には触れない。制御面はここが担当する:
 *   - mailbox (cmd_seq/ack_seq) を Atomics.waitAsync で待ち、SCAN / OPEN_IN / CLOSE_IN / OPEN_OUT / CLOSE_OUT を実行
 *   - 入力: MIDIInput.onmidimessage → 入力 ring (SPSC, producer = ここ)。溢れたら新しい方を捨てて in_dropped++
 *   - 出力: 出力 ring (producer = wasm) を消費し MIDIOutput.send。完了後に out_r を進めて wasm の MIDI スレッドを起こす
 *   - MIDIAccess.onstatechange → デバイス表を再作成 (scan_gen++)
 * このクラスは `MIDIAccessLike` を受け取るだけで main thread / Worker のどちらでも動く (Worker 直受信の実機検証は
 * tools/audio/harness/midi_run.mjs の worker_probe)。設計: tools/audio/docs/PROTOCOL.md §9
 */
import { FLM_CMD, FLM_DEV_ENTRY, FLM_E, FLM_K, FLM_LAYOUT, FLM_MAX_DEV, FLM_MAX_SYSEX, FLM_NAME_CHARS, FLM_REC, verifyMidiLayout, type FlmField } from "./midi-layout";

export interface MidiWasmApi {
  getBuffer(): SharedArrayBuffer;
  ctlPtr(): number;
  layoutCount(): number;
  layoutOff(i: number): number;
  layoutName(i: number): string;
  /** wasm 側 flm_init() (ring/表のアドレスを ctl に書く)。attach が scan より前に呼ぶ。冪等 */
  init(): void;
}
export interface MidiPortLike { id: string; name: string | null; state?: string; connection?: string; open?(): Promise<unknown>; close?(): Promise<unknown> }
export interface MidiInputLike extends MidiPortLike { onmidimessage: ((ev: { data: Uint8Array | null; timeStamp: number }) => void) | null }
export interface MidiOutputLike extends MidiPortLike { send(data: number[] | Uint8Array, timestamp?: number): void }
export interface MIDIAccessLike {
  inputs: Iterable<[string, MidiInputLike]> | { values(): Iterable<MidiInputLike> };
  outputs: Iterable<[string, MidiOutputLike]> | { values(): Iterable<MidiOutputLike> };
  onstatechange: ((ev: unknown) => void) | null;
}

type WaitAsyncResult = { async: false; value: "not-equal" | "timed-out" } | { async: true; value: Promise<"ok" | "timed-out"> };
const waitAsync = (ia: Int32Array, idx: number, val: number): WaitAsyncResult =>
  (Atomics as unknown as { waitAsync(ia: Int32Array, i: number, v: number): WaitAsyncResult }).waitAsync(ia, idx, val);

function portsOf<T extends MidiPortLike>(m: unknown): T[] {
  const v = (m as { values?: () => Iterable<T> }).values;
  if (typeof v === "function") return [...v.call(m)];
  return [...(m as Iterable<[string, T]>)].map((e) => e[1]);
}

const shortLen = (st: number): number => (st >= 0xf8 ? 1 : st >= 0xf0 ? (st === 0xf1 || st === 0xf3 ? 2 : st === 0xf2 ? 3 : 1) : st >= 0xc0 && st < 0xe0 ? 2 : 3);

export class FlMidiShim {
  private i32!: Int32Array;
  private ctl = 0;
  private disposed = false;
  private nextKey = 1;
  private keyOf = new Map<string, number>();
  private inPorts: MidiInputLike[] = [];
  private outPorts: MidiOutputLike[] = [];
  private inSlots = new Map<number, { port: MidiInputLike; gen: number }>();
  private outSlots = new Map<number, { port: MidiOutputLike; gen: number }>();
  commandsHandled = 0;
  /** テスト用: true の間、出力 ring の消費を止める (満杯の決定的再現) */
  outPaused = false;
  sendLog: { slot: number; data: number[] }[] = [];

  constructor(
    private api: MidiWasmApi,
    private access: MIDIAccessLike | null,
    private opts: { log?: (m: string) => void; keepSendLog?: boolean } = {},
  ) {}

  private log(m: string) { this.opts.log?.(m); }
  private ix(f: FlmField) { return (this.ctl + FLM_LAYOUT[f]) >> 2; }
  private ld(f: FlmField) { return Atomics.load(this.i32, this.ix(f)) >>> 0; }
  private st(f: FlmField, v: number) { Atomics.store(this.i32, this.ix(f), v | 0); }
  private add(f: FlmField) { return Atomics.add(this.i32, this.ix(f), 1); }
  private buf() { return this.api.getBuffer(); }

  attach(): void {
    this.api.init();
    verifyMidiLayout(this.api.layoutCount(), (i) => this.api.layoutOff(i), (i) => this.api.layoutName(i));
    this.ctl = this.api.ctlPtr();
    this.i32 = new Int32Array(this.buf(), 0, this.buf().byteLength >> 2);   // ctl は絶対アドレス。grow 後の更新は refresh() で
    this.scan();
    if (this.access) this.access.onstatechange = () => { this.scan(); };
    this.st("ctrl_ready", 1);
    Atomics.notify(this.i32, this.ix("ctrl_ready"));
    void this.cmdLoop();
    void this.outLoop();
    this.log(`midi attached ctl@${this.ctl} access=${this.access ? "yes" : "none"} in=${this.inPorts.length} out=${this.outPorts.length}`);
  }
  dispose(): void {
    this.disposed = true;
    for (const { port } of this.inSlots.values()) port.onmidimessage = null;
    if (this.access) this.access.onstatechange = null;
    Atomics.notify(this.i32, this.ix("cmd_seq"));
    Atomics.notify(this.i32, this.ix("out_w"));
  }
  private refresh() { const b = this.buf(); if (this.i32.buffer !== b) this.i32 = new Int32Array(b, 0, b.byteLength >> 2); }

  // ---- デバイス表 ------------------------------------------------------------------------------
  scan(): void {
    this.refresh();
    const ins = this.access ? portsOf<MidiInputLike>(this.access.inputs).filter((p) => p.state !== "disconnected").slice(0, FLM_MAX_DEV) : [];
    const outs = this.access ? portsOf<MidiOutputLike>(this.access.outputs).filter((p) => p.state !== "disconnected").slice(0, FLM_MAX_DEV) : [];
    this.inPorts = ins; this.outPorts = outs;
    const tbl = this.ld("dev_tbl_ptr");
    this.add("tbl_seq");                                   // 奇数 = 更新中
    const dv = new DataView(this.buf());
    const put = (dir: number, i: number, p: MidiPortLike) => {
      const o = tbl + (dir * FLM_MAX_DEV + i) * FLM_DEV_ENTRY;
      let key = this.keyOf.get(p.id);
      if (key === undefined) { key = this.nextKey++; this.keyOf.set(p.id, key); }
      for (let k = 0; k < FLM_NAME_CHARS; k++) dv.setUint16(o + k * 2, 0, true);
      const nm = p.name ?? "";
      for (let k = 0; k < Math.min(nm.length, FLM_NAME_CHARS - 1); k++) dv.setUint16(o + k * 2, nm.charCodeAt(k), true);
      dv.setUint32(o + 64, 0, true); dv.setUint32(o + 68, p.state === "connected" ? 1 : 0, true); dv.setUint32(o + 72, key, true);
    };
    ins.forEach((p, i) => put(0, i, p)); outs.forEach((p, i) => put(1, i, p));
    this.st("n_in", ins.length); this.st("n_out", outs.length);
    this.add("scan_gen");
    this.add("tbl_seq");                                   // 偶数 = 一貫
    Atomics.notify(this.i32, this.ix("tbl_seq"));
    this.log(`scan: in=${ins.length} out=${outs.length}`);
  }

  // ---- mailbox ---------------------------------------------------------------------------------
  private async cmdLoop(): Promise<void> {
    const iSeq = this.ix("cmd_seq");
    while (!this.disposed) {
      this.refresh();
      const seq = Atomics.load(this.i32, iSeq);
      if (seq !== this.ld("ack_seq")) {
        let status: number = 0;
        try { status = await this.handle(); } catch (e) { this.log(`cmd failed: ${(e as Error).stack ?? e}`); status = FLM_E.OPEN; }
        this.commandsHandled++;
        this.st("ack_status", status);
        Atomics.store(this.i32, this.ix("ack_seq"), seq);
        Atomics.notify(this.i32, this.ix("ack_seq"));
        continue;
      }
      const r = waitAsync(this.i32, iSeq, seq);
      if (r.async) await r.value;
    }
  }

  private async handle(): Promise<number> {
    const op = this.ld("cmd_op");
    const a = [0, 1, 2, 3].map((k) => Atomics.load(this.i32, this.ix("cmd_arg") + k) >>> 0);
    switch (op) {
      case FLM_CMD.SCAN: this.scan(); return 0;
      case FLM_CMD.OPEN_IN: {
        const [key, slot, gen] = a;
        const port = this.inPorts.find((p) => this.keyOf.get(p.id) === key);
        if (!port) return FLM_E.NODEV;
        try { await port.open?.(); } catch { return FLM_E.OPEN; }
        this.inSlots.set(slot, { port, gen });
        port.onmidimessage = (ev) => this.onMessage(slot, gen, ev);
        return 0;
      }
      case FLM_CMD.CLOSE_IN: {
        const s = this.inSlots.get(a[0]);
        if (s) { s.port.onmidimessage = null; this.inSlots.delete(a[0]); }
        return 0;
      }
      case FLM_CMD.OPEN_OUT: {
        const [key, slot, gen] = a;
        const port = this.outPorts.find((p) => this.keyOf.get(p.id) === key);
        if (!port) return FLM_E.NODEV;
        try { await port.open?.(); } catch { return FLM_E.OPEN; }
        this.outSlots.set(slot, { port, gen });
        return 0;
      }
      case FLM_CMD.CLOSE_OUT: this.outSlots.delete(a[0]); return 0;
      default: this.log(`unknown midi cmd ${op}`); return FLM_E.OPEN;
    }
  }

  /** テスト用: 任意の (slot, gen) 宛に注入 (閉じた slot 宛の stale 経路の再現) */
  injectForTest(slot: number, gen: number, data: Uint8Array, timeStamp = performance.now()): void { this.onMessage(slot, gen, { data, timeStamp }); }

  // ---- 入力 ring (producer) ---------------------------------------------------------------------
  private onMessage(slot: number, gen: number, ev: { data: Uint8Array | null; timeStamp: number }): void {
    this.refresh();
    const d = ev.data;
    if (!d || d.length === 0) { this.add("main_errors"); return; }
    const sysex = d[0] === 0xf0;
    let kind: number, val: number, len: number;
    if (sysex) {
      if (d.length > FLM_MAX_SYSEX) { this.add("main_errors"); return; }
      kind = FLM_K.SYSEX; val = d.length; len = d.length;
    } else {
      const need = shortLen(d[0]);
      if (d[0] < 0x80 || d.length < need) { this.add("main_errors"); return; }   // 継続バイト・途中切れは不正として計数
      kind = FLM_K.SHORT; val = d[0] | (need > 1 ? d[1] << 8 : 0) | (need > 2 ? d[2] << 16 : 0); len = 0;
    }
    const size = this.ld("in_ring_bytes"), base = this.ld("in_ring_ptr");
    const span = FLM_REC + ((len + FLM_REC - 1) & ~(FLM_REC - 1));
    const wr = this.ld("in_w"), rd = this.ld("in_r");
    if (size - ((wr - rd) >>> 0) < span) { this.add("in_dropped"); return; }
    const bytes = new Uint8Array(this.buf());
    const put = (pos: number, src: Uint8Array) => {
      const p = pos & (size - 1), first = Math.min(size - p, src.length);
      bytes.set(src.subarray(0, first), base + p);
      if (first < src.length) bytes.set(src.subarray(first), base + 0);
    };
    const hdr = new Uint8Array(FLM_REC), hv = new DataView(hdr.buffer);
    hv.setUint32(0, ((slot & 0xff) | (kind << 8) | ((gen & 0xffff) << 16)) >>> 0, true);
    hv.setUint32(4, val >>> 0, true);
    hv.setFloat64(8, performance.timeOrigin + ev.timeStamp, true);
    put(wr, hdr);
    if (len) put(wr + FLM_REC, d);
    this.st("in_w", (wr + span) | 0);
    this.add("in_accepted");
    this.add("wake");
    Atomics.notify(this.i32, this.ix("wake"));
  }

  // ---- 出力 ring (consumer) ---------------------------------------------------------------------
  private async outLoop(): Promise<void> {
    while (!this.disposed) {
      this.refresh();
      if (this.outPaused) { await new Promise((ok) => setTimeout(ok, 5)); continue; }
      const rd = this.ld("out_r"), wr = this.ld("out_w");
      if (rd === wr) {
        const r = waitAsync(this.i32, this.ix("out_w"), wr);
        if (r.async) await r.value;
        continue;
      }
      const size = this.ld("out_ring_bytes"), base = this.ld("out_ring_ptr");
      const bytes = new Uint8Array(this.buf());
      const get = (pos: number, n: number) => {
        const out = new Uint8Array(n), p = pos & (size - 1), first = Math.min(size - p, n);
        out.set(bytes.subarray(base + p, base + p + first), 0);
        if (first < n) out.set(bytes.subarray(base, base + n - first), first);
        return out;
      };
      const h = get(rd, FLM_REC), hv = new DataView(h.buffer);
      const w0 = hv.getUint32(0, true), val = hv.getUint32(4, true);
      const slot = w0 & 0xff, kind = (w0 >> 8) & 0xff, gen = w0 >>> 16;
      const plen = kind === FLM_K.SYSEX ? val : 0;
      const payload = plen ? get(rd + FLM_REC, plen) : new Uint8Array(0);
      const span = FLM_REC + ((plen + FLM_REC - 1) & ~(FLM_REC - 1));
      const s = this.outSlots.get(slot);
      if (!s || s.gen !== gen) this.add("out_errors");
      else {
        let data: Uint8Array;
        if (kind === FLM_K.SHORT) { const n = shortLen(val & 0xff); data = Uint8Array.from([val & 0xff, (val >> 8) & 0xff, (val >> 16) & 0xff].slice(0, n)); }
        else data = payload;
        try { s.port.send(data); this.add("out_sent"); if (this.opts.keepSendLog) this.sendLog.push({ slot, data: [...data] }); } catch (e) { this.log(`send failed: ${e}`); this.add("out_errors"); }
      }
      this.st("out_r", (rd + span) | 0);
      this.add("wake");
      Atomics.notify(this.i32, this.ix("wake"));
    }
  }
}
