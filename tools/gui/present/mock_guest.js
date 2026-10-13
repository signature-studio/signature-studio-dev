// mock_guest.js — 実 shim/FL を使わずに GuiShared を JS から書く「模擬 guest」(GUI-4 present e2e 用)。
// wasm 無し: SAB の WebAssembly.Memory 上に GuiShared + surface 画素を置き、out ring へ SURF_*/PRESENT/FRAME_END を push する。
// ページ main thread と guest worker の両方から import される (ブロッキング待機はしない)。
import { CMD, GUI_MAGIC, GUI_OUT_RECS, OFF, S, SURF_WORDS, W as WORD } from "/js/gui_proto.js";

export function hash32(a, b, c) {
  let h = Math.imul(a ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(b + 0x7f4a7c15, 0xc2b2ae35) ^ Math.imul(c + 0x165667b1, 0x27d4eb2f);
  h ^= h >>> 15; h = Math.imul(h, 0x85ebca6b); h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35); h ^= h >>> 16;
  return h >>> 0;
}

export function memPagesFor(bytes) { return Math.ceil((OFF.total + bytes + 4096) / 65536); }

export class MockGuest {
  constructor(memory, base, width, height) {
    this.memory = memory; this.base = base; this.W = width; this.H = height;
    this.i32 = new Int32Array(memory.buffer, base, OFF.total / 4);
    this.u32 = new Uint32Array(memory.buffer, base, OFF.total / 4);
    this.next = (base + OFF.total + 63) & ~63;
    this.seq = 0;
    Atomics.store(this.i32, WORD.screenW, width); Atomics.store(this.i32, WORD.screenH, height);
    Atomics.store(this.i32, WORD.magic, GUI_MAGIC); Atomics.store(this.i32, WORD.version, 1); Atomics.store(this.i32, WORD.totalSize, OFF.total);
  }
  alloc(bytes) {
    const p = this.next; this.next = (p + bytes + 63) & ~63;
    if (this.next > this.memory.buffer.byteLength) throw new Error(`mock guest: out of memory (${this.next} > ${this.memory.buffer.byteLength})`);
    return p;
  }
  so(id) { return (OFF.surf >> 2) + id * SURF_WORDS; }
  pushOut(cmd, surf, a = 0, b = 0, c = 0, d = 0, e = 0) {
    const i32 = this.i32;
    const head = Atomics.load(i32, WORD.outHead) >>> 0, tail = Atomics.load(i32, WORD.outTail) >>> 0;
    if (tail - head >= GUI_OUT_RECS) throw new Error("mock guest: out ring full");
    const o = (OFF.outRecs >> 2) + (tail & (GUI_OUT_RECS - 1)) * 8;
    i32[o] = cmd; i32[o + 1] = surf; i32[o + 2] = a; i32[o + 3] = b; i32[o + 4] = c; i32[o + 5] = d; i32[o + 6] = e; i32[o + 7] = 0;
    Atomics.store(i32, WORD.outTail, (tail + 1) | 0);
    Atomics.notify(i32, WORD.outTail);
  }
  info(id) {
    const o = this.so(id), u = this.u32, i = this.i32;
    return { id, state: Atomics.load(i, o + S.state), visible: u[o + S.visible], x: i[o + S.x], y: i[o + S.y], w: u[o + S.w], h: u[o + S.h], stride: u[o + S.stride], pixels: u[o + S.pixels], z: u[o + S.z] };
  }
  px(id) { const s = this.info(id); return new Uint32Array(this.memory.buffer, s.pixels, (s.stride >> 2) * s.h); }
  create(id, x, y, w, h, z, visible = 1) {
    const o = this.so(id), i = this.i32;
    const pixels = this.alloc(w * h * 4);
    new Uint32Array(this.memory.buffer, pixels, w * h).fill(0xff000000);
    i[o + S.visible] = visible; i[o + S.x] = x; i[o + S.y] = y; i[o + S.w] = w; i[o + S.h] = h; i[o + S.stride] = w * 4; i[o + S.pixels] = pixels; i[o + S.z] = z;
    i[o + S.gen]++; Atomics.store(i, o + S.wseq, 0);
    Atomics.store(i, o + S.state, 1);
    this.pushOut(CMD.SURF_CREATE, id);
  }
  change(id, p) {
    const o = this.so(id), i = this.i32, cur = this.info(id);
    if (p.x !== undefined) i[o + S.x] = p.x;
    if (p.y !== undefined) i[o + S.y] = p.y;
    if (p.z !== undefined) i[o + S.z] = p.z;
    if (p.visible !== undefined) i[o + S.visible] = p.visible;
    if ((p.w !== undefined && p.w !== cur.w) || (p.h !== undefined && p.h !== cur.h)) {
      const w = p.w ?? cur.w, h = p.h ?? cur.h, np = this.alloc(w * h * 4);
      const dst = new Uint32Array(this.memory.buffer, np, w * h); dst.fill(0xff000000);
      const src = this.px(id), cw = Math.min(w, cur.w), ch = Math.min(h, cur.h);
      for (let y = 0; y < ch; y++) dst.set(src.subarray(y * (cur.stride >> 2), y * (cur.stride >> 2) + cw), y * w);
      i[o + S.w] = w; i[o + S.h] = h; i[o + S.stride] = w * 4; i[o + S.pixels] = np; i[o + S.gen]++;
    }
    this.pushOut(CMD.SURF_CHANGE, id);
  }
  destroy(id) {
    const o = this.so(id);
    this.pushOut(CMD.SURF_DESTROY, id);
    Atomics.store(this.i32, o + S.state, 0); this.i32[o + S.pixels] = 0;
  }
  /** [l,t,r,b) を hash(seed,x,y) で塗る (alpha も乱数: 表示側が alpha=255 に固定することを検査する) */
  paint(id, l, t, r, b, seed) {
    const s = this.info(id), px = this.px(id), sw = s.stride >> 2;
    for (let y = t; y < b; y++) for (let x = l; x < r; x++) px[y * sw + x] = hash32(seed, x, y);
  }
  present(id, l, t, r, b) { this.pushOut(CMD.PRESENT, id, l, t, r, b, this.seq + 1); }
  frameEnd() { this.seq++; this.pushOut(CMD.FRAME_END, this.seq); return this.seq; }
  wseqBegin(id) { const w = this.so(id) + S.wseq; if (!(Atomics.load(this.i32, w) & 1)) Atomics.add(this.i32, w, 1); }
  wseqEnd(id) { const w = this.so(id) + S.wseq; if (Atomics.load(this.i32, w) & 1) Atomics.add(this.i32, w, 1); }
  /** 描画器と独立な期待画像: z 昇順の painter's algorithm をバイト単位で (B,G,R,A) -> (R,G,B,255) */
  oracle() {
    const out = new Uint8Array(this.W * this.H * 4);
    for (let k = 3; k < out.length; k += 4) out[k] = 255;
    const list = [];
    for (let id = 0; id < 16; id++) { const s = this.info(id); if (s.state && s.visible) list.push(s); }
    list.sort((a, b) => a.z - b.z);
    for (const s of list) {
      const bytes = new Uint8Array(this.memory.buffer, s.pixels, s.stride * s.h);
      for (let y = 0; y < s.h; y++) {
        const dy = s.y + y; if (dy < 0 || dy >= this.H) continue;
        for (let x = 0; x < s.w; x++) {
          const dx = s.x + x; if (dx < 0 || dx >= this.W) continue;
          const si = y * s.stride + x * 4, di = (dy * this.W + dx) * 4;
          out[di] = bytes[si + 2]; out[di + 1] = bytes[si + 1]; out[di + 2] = bytes[si];
        }
      }
    }
    return out;
  }
  topSurfaceAt(x, y) {
    let best = null;
    for (let id = 0; id < 16; id++) {
      const s = this.info(id);
      if (s.state && s.visible && x >= s.x && x < s.x + s.w && y >= s.y && y < s.y + s.h && (!best || s.z > best.z)) best = s;
    }
    return best;
  }
}
