// ws_v1 ABI の合成テスト wasm 生成 (emcc 不要・依存なし)。
//   node gen_wasm.mjs <out.wasm> [--stages M] [--filler F] [--nops N] [--no-reset]
// ws_process(128): in[128] を out へ写し、M 個の stage 関数を順に呼ぶ。
// stage j: v = fround(fround(x*c_j) + z_j); z_j = fround(v*d_j); out = v  (z_j は linear memory 上の状態)
// filler: 呼ばれない関数 (module サイズ/関数数を K 倍の代わりに稼ぐ; lazy compile 対象)
import fs from 'node:fs';

export const BUF = 4096, OUT = BUF + 512, STATE = 16, MAX_STAGES = 1000;
// 段ごとの直流ゲイン c/(1-d) = 0.999 (1000 段連鎖しても発散・消失しない)
export const stageConst = (j) => { const d = Math.fround((j % 5) * 0.1); return { c: Math.fround((1 - d) * 0.999), d }; };

const uleb = (n) => { const o = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; o.push(b); } while (n); return o; };
const sleb = (n) => { const o = []; for (;;) { const b = n & 0x7f; n >>= 7; if ((n === 0 && !(b & 0x40)) || (n === -1 && (b & 0x40))) { o.push(b); return o; } o.push(b | 0x80); } };
const f32c = (v) => { const b = Buffer.alloc(4); b.writeFloatLE(v); return [0x43, ...b]; };
const vec = (items) => [...uleb(items.length), ...items.flat()];
const section = (id, body) => [id, ...uleb(body.length), ...body];
const str = (s) => [...uleb(s.length), ...Buffer.from(s)];
const body = (locals, code) => { const b = [...vec(locals), ...code, 0x0b]; return [...uleb(b.length), ...b]; };
const I32 = 0x7f, F32 = 0x7d;
const op = { lget: 0x20, ltee: 0x22, i32c: 0x41, i32add: 0x6a, i32shl: 0x74, i32ltu: 0x49, f32load: 0x2a, f32store: 0x38, i32store: 0x36, f32add: 0x92, f32mul: 0x94, call: 0x10, loop: 0x03, brif: 0x0d, end: 0x0b, drop: 0x1a };
const mem = (align, off) => [align, ...uleb(off)];

export function genWasm({ stages = 64, filler = 0, nops = 0, reset = true, pad = 0 } = {}) {
  if (stages > MAX_STAGES) throw new Error('stages > ' + MAX_STAGES);
  const M = stages;
  // types: 0 ()->(), 1 ()->i32, 2 (i32)->()
  const types = section(1, vec([[0x60, 0, 0], [0x60, 0, 1, I32], [0x60, 1, I32, 0]]));
  // 関数 index: 0 ws_buffers / 1 ws_process / 2 ws_reset / 3..3+M-1 stage / 以降 filler
  const fnTypes = [1, 2, 0, ...Array(M).fill(0), ...Array(filler).fill(1)];
  const funcs = section(3, vec(fnTypes.map((t) => uleb(t))));
  const memory = section(5, [1, 0, 1]);
  const exports = section(7, vec([
    [...str('memory'), 2, 0],
    [...str('ws_buffers'), 0, 0],
    [...str('ws_process'), 0, 1],
    ...(reset ? [[...str('ws_reset'), 0, 2]] : []),
  ]));
  const code = [];
  code.push(body([], [op.i32c, ...sleb(BUF)]));
  const proc = [
    op.loop, 0x40,
    op.lget, 1, op.i32c, 2, op.i32shl,
    op.lget, 1, op.i32c, 2, op.i32shl, op.f32load, ...mem(2, BUF),
    op.f32store, ...mem(2, OUT),
    op.lget, 1, op.i32c, 1, op.i32add, op.ltee, 1, op.lget, 0, op.i32ltu, op.brif, 0,
    op.end,
    ...Array.from({ length: M }, (_, j) => [op.call, ...uleb(3 + j)]).flat(),
  ];
  code.push(body([[1, I32]], proc));
  code.push(body([[1, I32]], [
    op.loop, 0x40,
    op.lget, 0, op.i32c, 2, op.i32shl, op.i32c, 0, op.i32store, ...mem(2, STATE),
    op.lget, 0, op.i32c, 1, op.i32add, op.ltee, 0, op.i32c, ...sleb(M), op.i32ltu, op.brif, 0,
    op.end,
  ]));
  for (let j = 0; j < M; j++) {
    const { c, d } = stageConst(j);
    const so = STATE + 4 * j;
    code.push(body([[1, I32], [1, F32]], [
      ...Array(nops).fill([op.i32c, 0, op.drop]).flat(),
      op.loop, 0x40,
      op.lget, 0, op.i32c, 2, op.i32shl,
      op.lget, 0, op.i32c, 2, op.i32shl, op.f32load, ...mem(2, OUT), ...f32c(c), op.f32mul,
      op.i32c, 0, op.f32load, ...mem(2, so), op.f32add, op.ltee, 1,
      op.f32store, ...mem(2, OUT),
      op.i32c, 0, op.lget, 1, ...f32c(d), op.f32mul, op.f32store, ...mem(2, so),
      op.lget, 0, op.i32c, 1, op.i32add, op.ltee, 0, op.i32c, ...sleb(128), op.i32ltu, op.brif, 0,
      op.end,
    ]));
  }
  for (let k = 0; k < filler; k++) {
    code.push(body([], [op.i32c, ...sleb(k * 7 + 1), op.i32c, ...sleb(k + 3), 0x6c, op.i32c, ...sleb(k ^ 0x55), op.i32add, op.i32c, 5, 0x72, op.i32c, ...sleb(k + 9), 0x73]));
  }
  const head = Buffer.from([0x00, 0x61, 0x73, 0x6d, 1, 0, 0, 0, ...types, ...funcs, ...memory, ...exports, ...section(10, vec(code))]);
  if (pad <= 0) return head;
  // custom section "pad" で実コード以外のサイズを稼ぐ (検証のみで compile 対象外)
  const nm = str('pad'), n = Math.max(0, pad - head.length - 1 - 5 - nm.length);
  const hdr = Buffer.from([0, ...uleb5(n + nm.length), ...nm]);
  return Buffer.concat([head, hdr, Buffer.alloc(n, 0xa5)]);
}
const uleb5 = (n) => { const o = []; for (let i = 0; i < 5; i++) { let b = n & 0x7f; n >>>= 7; if (i < 4) b |= 0x80; o.push(b); } return o; };

// 参照モデル (bit-exact): state z[] を持ち、1 ブロック (128f) 進める
export function makeRef(stages) {
  const z = new Float32Array(stages);
  return (inp) => {
    const out = Float32Array.from(inp);
    for (let j = 0; j < stages; j++) {
      const { c, d } = stageConst(j);
      for (let i = 0; i < 128; i++) { const v = Math.fround(Math.fround(out[i] * c) + z[j]); z[j] = Math.fround(v * d); out[i] = v; }
    }
    return out;
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf('--' + k); return i >= 0 ? +a[i + 1] : d; };
  const b = genWasm({ stages: opt('stages', 64), filler: opt('filler', 0), nops: opt('nops', 0), pad: opt('pad', 0), reset: !a.includes('--no-reset') });
  fs.writeFileSync(a[0], b);
  console.log(`${a[0]} ${b.length} B`);
}
