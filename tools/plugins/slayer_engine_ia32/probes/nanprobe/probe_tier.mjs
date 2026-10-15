// probe_tier.mjs: NaN どうしの演算が返す NaN のビットを、wasm の tier (Liftoff / TurboFan) ごとに出す (#4775)。
// emcc を使わず、wasm のバイト列を直接組み立てる (依存なし)。
// 使い方 (tier ごとに 1 回ずつ、出力を比べる):
//   node --liftoff-only probe_tier.mjs > liftoff.txt
//   node --no-liftoff   probe_tier.mjs > turbofan.txt
//   diff liftoff.txt turbofan.txt
// 期待: f32/f64 の add・mul で NaN どうしの行にビット差が出る (sub は一致)。

function uleb(n) {
  const out = [];
  do {
    let b = n & 0x7f;
    n >>>= 7;
    if (n !== 0) b |= 0x80;
    out.push(b);
  } while (n !== 0);
  return out;
}
function str(s) {
  return [...uleb(s.length), ...Buffer.from(s)];
}
function section(id, body) {
  return [id, ...uleb(body.length), ...body];
}
function vec(items) {
  return [...uleb(items.length), ...items.flat()];
}

// 型: 0 = (f32,f32)->f32, 1 = (f64,f64)->f64, 2 = (f32)->f64, 3 = (f64)->f32, 4 = (f32)->f32
const T_F32 = 0x7d, T_F64 = 0x7c;
const functype = (params, results) => [0x60, ...vec(params.map((p) => [p])), ...vec(results.map((r) => [r]))];
const TYPES = [
  functype([T_F32, T_F32], [T_F32]),
  functype([T_F64, T_F64], [T_F64]),
  functype([T_F32], [T_F64]),
  functype([T_F64], [T_F32]),
  functype([T_F32], [T_F32]),
];

// 関数: [名前, 型番号, 本体の opcode 列 (引数は local 0,1)]
const LG = (i) => [0x20, i]; // local.get i
const FUNCS = [
  ['f32_add', 0, [...LG(0), ...LG(1), 0x92]],
  ['f32_sub', 0, [...LG(0), ...LG(1), 0x93]],
  ['f32_mul', 0, [...LG(0), ...LG(1), 0x94]],
  ['f32_div', 0, [...LG(0), ...LG(1), 0x95]],
  ['f64_add', 1, [...LG(0), ...LG(1), 0xa0]],
  ['f64_sub', 1, [...LG(0), ...LG(1), 0xa1]],
  ['f64_mul', 1, [...LG(0), ...LG(1), 0xa2]],
  ['promote', 2, [...LG(0), 0xbb]], // f64.promote_f32
  ['demote', 3, [...LG(0), 0xb6]], // f32.demote_f64
  ['f32_neg', 4, [...LG(0), 0x8c]],
];

const typeSec = section(1, vec(TYPES));
const funcSec = section(3, vec(FUNCS.map(([, t]) => [...uleb(t)])));
const exportSec = section(7, vec(FUNCS.map(([name], i) => [...str(name), 0x00, ...uleb(i)])));
const codeSec = section(
  10,
  vec(
    FUNCS.map(([, , body]) => {
      const fbody = [0x00, ...body, 0x0b]; // locals 0 個
      return [...uleb(fbody.length), ...fbody];
    }),
  ),
);
const bytes = new Uint8Array([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00, ...typeSec, ...funcSec, ...exportSec, ...codeSec]);

const { instance } = await WebAssembly.instantiate(bytes, {});
const ex = instance.exports;

// 入力: NaN の符号・ペイロードを変えた値 (f32 の bit 列)。 数値も混ぜる。
const f32bits = [0x7fc00000, 0x7fc00001, 0xffc00000, 0x7f800001, 0xffffffff, 0x3f800000, 0x00000000, 0x80000000];
const f32s = f32bits.map((b) => {
  const u = new Uint32Array([b]);
  return new Float32Array(u.buffer)[0];
});
const hex32 = (x) => new Uint32Array(new Float32Array([x]).buffer)[0].toString(16).padStart(8, '0');
const hex64 = (x) => {
  const d = new DataView(new ArrayBuffer(8));
  d.setFloat64(0, x);
  return d.getBigUint64(0).toString(16).padStart(16, '0');
};

const lines = [];
for (const name of ['f32_add', 'f32_sub', 'f32_mul', 'f32_div']) {
  for (const a of f32s) for (const b of f32s) {
    lines.push(`${name} ${hex32(a)} ${hex32(b)} -> ${hex32(ex[name](a, b))}`);
  }
}
for (const name of ['f64_add', 'f64_sub', 'f64_mul']) {
  for (const a of f32s) for (const b of f32s) {
    const x = new Float64Array([a])[0];
    const y = new Float64Array([b])[0];
    lines.push(`${name} ${hex64(x)} ${hex64(y)} -> ${hex64(ex[name](x, y))}`);
  }
}
for (const a of f32s) lines.push(`promote ${hex32(a)} -> ${hex64(ex.promote(a))}`);
for (const a of f32s) lines.push(`f32_neg ${hex32(a)} -> ${hex32(ex.f32_neg(a))}`);
const d64 = [0x7ff8000000000000n, 0xfff8000000000001n, 0x7ff0000000000001n];
for (const v of d64) {
  const d = new DataView(new ArrayBuffer(8));
  d.setBigUint64(0, v);
  lines.push(`demote ${v.toString(16)} -> ${hex32(ex.demote(d.getFloat64(0)))}`);
}

console.log(lines.join('\n'));
