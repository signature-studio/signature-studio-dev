// ring_common.mjs — SAB ring / RPC 試験の共通定数と信号 (node 参照 ring_node_ref.mjs と Chrome 側 ring_rpc_worker.mjs が共有).
export const H = 128, NBLK = 500, NRPC = 4, CAP = 4096, SR = 44100;
// ctl (Int32): C_WR = 生産済みフレーム総数 (producer が store), C_RD = 消費済みフレーム総数 (consumer が store)
export const C_WR = 0, C_RD = 1;
// rpc (Int32): client が OP/ARG を書いて REQ を store・notify、worker は Atomics.wait(REQ) で待ち RET を書いて RESP を store・notify
export const R_REQ = 0, R_RESP = 1, R_OP = 2, R_ARG = 3, R_RET = 4;
export const OP_LOAD = 1, OP_CONFIG = 2, OP_BLOCK = 3, OP_SHUTDOWN = 9;
export const PLUGIN_VENDOR = 'Xfer Records', PLUGIN_ALIAS = 'OTT0_x64.dll';
export const PATH = (vendor, alias) => `C:\\Program Files\\Common Files\\VST2\\${vendor}\\${alias}`;
// view: 長さ 2H の channel-major (L[0..H), R[0..H)) / ph: 先頭サンプル位置
export function fillIn(view, ph) {
  for (let i = 0; i < H; i++) { view[i] = Math.fround(Math.sin((i + ph) * 0.05) * 0.7 + Math.sin((i + ph) * 0.011) * 0.3); view[H + i] = Math.fround(Math.cos((i + ph) * 0.13) * 0.5); }
}
export function configure(x, e) {
  for (let i = 0; i < 20; i++) x.host_set_param(e, i, i === 19 ? 0 : 0.5);
  x.host_dispatch(e, 12, 0, 1n, 0, 0);
}
export function wstr(x, s) {
  const p = x.host_alloc(2 * (s.length + 1)); const d = new DataView(x.memory.buffer);
  for (let i = 0; i < s.length; i++) d.setUint16(p + 2 * i, s.charCodeAt(i), true);
  d.setUint16(p + 2 * s.length, 0, true); return p;
}
export function mkAudio(x) {
  const inB = x.host_alloc(2 * H * 4), outB = x.host_alloc(2 * H * 4), inA = x.host_alloc(16), outA = x.host_alloc(16);
  const d = new DataView(x.memory.buffer);
  for (let c = 0; c < 2; c++) { d.setBigUint64(inA + c * 8, BigInt(inB + c * H * 4), true); d.setBigUint64(outA + c * 8, BigInt(outB + c * H * 4), true); }
  return { inB, outB, inA, outA };
}
// 総和チェックサム: 出力 float の bit パターンを uint32 で足す (mod 2^32)。float 総和は OTT 出力が 1e27 級に育つため溢れて判定不能になるので使わない。
// 順序は ring の interleave (L,R) と同じ。node 参照と Chrome 側で同じ式を使う。
export function accum(s, out) {
  const u = new Uint32Array(out.buffer, out.byteOffset, out.length);
  for (let i = 0; i < H; i++) { s = (s + u[i]) >>> 0; s = (s + u[H + i]) >>> 0; }
  return s;
}
// 1 block 処理: 入力 ph を guest に書き、host_process 後の出力 (channel-major 2H float) を返す
export function processBlock(x, e, au, ph) {
  fillIn(new Float32Array(x.memory.buffer, au.inB, 2 * H), ph);
  x.host_process(e, au.inA, au.outA, H);
  return new Float32Array(x.memory.buffer.slice(au.outB, au.outB + 2 * H * 4));
}
