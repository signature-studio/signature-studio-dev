// 分割照合 (chunk_verify.mjs) の selftest: 同一の合成キャプチャを「一括 (N ≥ 総フレーム)」と「分割 (小さい ring)」で照合し、結果が一致することを確認する。
// 使い方: node harness/chunk_selftest.mjs   (終了コード 0 = 全 PASS)
import { ChunkVerifier, CAP_Q, capSpecBytes } from "./chunk_verify.mjs";

const Q = CAP_Q, OCH = 2, ICH = 0;

// 書き込みと照合を交互に行う (本番の polling 相当)。ring は書き込み直後に step しないと上書きされる。
function runInterleaved({ N, total, stepEvery, opts }) {
  const sab = new SharedArrayBuffer(capSpecBytes(N, OCH, ICH));
  const out = new Float32Array(sab, 64, N * OCH);
  const fill = new Int32Array(sab, 64 + N * OCH * 4, N / Q);
  const hdr = new Int32Array(sab, 0, 16);
  const v = new ChunkVerifier({ sab, frames: N, outCh: OCH, inCh: ICH }, { mode: "ramp", sr: 48000, ring: N < total });
  let q = 0;
  for (let p = 0; p < total; p += Q, q++) {
    const b0 = new Float32Array(Q), b1 = new Float32Array(Q);
    for (let k = 0; k < Q; k++) {
      const f = p + k;
      b0[k] = (f & 0xFFFFFF) + 1; b1[k] = -((f & 0xFFFFFF) + 1);
      if (opts.bad && opts.bad.includes(f)) b0[k] += 1;
    }
    if (opts.silentQ && opts.silentQ.includes(q)) { b0.fill(0); b1.fill(0); }
    const blk = [b0, b1];
    for (let c = 0; c < OCH; c++) {
      const s = p % N, first = Math.min(Q, N - s);
      out.set(blk[c].subarray(0, first), c * N + s);
      if (first < Q) out.set(blk[c].subarray(first, Q), c * N);
    }
    fill[q % fill.length] = 8 + (q % 5);
    Atomics.store(hdr, 0, p + Q);
    if (stepEvery > 0 && q % stepEvery === stepEvery - 1) v.step();
  }
  return v.finish();
}

const TOTAL = 40 * 128 * 100;          // 512,000 f。N=2^12 では ring を 125 周する
const RING = 1 << 12;                  // 4096 f。未照合が N/2 を超えないよう stepEvery を抑える
const cases = [
  { n: "clean ramp", opts: {} },
  { n: "不一致 1 件 (frame 100000)", opts: { bad: [100000] } },
  { n: "不一致 3 件 (周回境界またぎ)", opts: { bad: [RING - 1, RING, 3 * RING + 5] } },
  { n: "無音 quantum 4 件 (underrun 相当)", opts: { silentQ: [7, 500, 1234, 3000] } },
];
let fail = 0;
const pick = (r) => ({ ok: r.ramp.bit_exact, mm: r.ramp.mismatches, first: r.ramp.first_mismatch_frame, n: r.ramp.frames_checked, fail: r.fail });
for (const c of cases) {
  const whole = pick(runInterleaved({ N: TOTAL + Q, total: TOTAL, stepEvery: 0, opts: { ...c.opts, ramp: true } }));
  const chunked = pick(runInterleaved({ N: RING, total: TOTAL, stepEvery: 8, opts: { ...c.opts, ramp: true } }));
  const same = whole.mm === chunked.mm && whole.first === chunked.first && whole.n === chunked.n && whole.ok === chunked.ok && !chunked.fail;
  if (!same) fail++;
  console.log(`${same ? "PASS" : "FAIL"} ${c.n.padEnd(34)} 一括 mm=${whole.mm} first=${whole.first} n=${whole.n} / 分割 mm=${chunked.mm} first=${chunked.first} n=${chunked.n}${chunked.fail ? " fail=" + chunked.fail : ""}`);
}
console.log(fail ? `${cases.length - fail}/${cases.length} PASS` : `${cases.length}/${cases.length} PASS`);
process.exit(fail ? 1 : 0);
