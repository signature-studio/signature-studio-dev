// #2131: 同一プロセスで ON/OFF の 2 インスタンスを unit 0..LS_MAX で並走させ、unit ごとに kind とメモリ (4 KiB ページ) と SP を比べる。
// survey_units.mjs は全 unit を 1 インスタンスで順に実行するため、unit N の結果は先行 unit の状態に依る (lock-step で再現を確かめる)。
//   usage (tools/m11 で実行): LS_A=<dir> LS_B=<dir> [LS_MAX=190] [LS_CKPT=189] [LS_TARGET=190] node trap_triage/lockstep_2131.mjs
//   dir には m11_boot.cjs・m11_boot.cjs.wasm・m11_image.bin を置く (build ごとに別 dir へ退避する)。
//   env: LS_CKPT=<unit> 直後の差分ページを記録 (既定 189) / LS_MAXTESTS=<n> ページ縮約の試行上限 (0 で縮約しない)
//        LS_SYNC_SP=1 縮約時に SP も揃える / LS_REVERSE=1 B の差分ページを A へ / LS_FORCEB=1 A の差分ページと SP を B へ写す
//        LS_FIX=<hex,..> A の指定 u32 を B の値へ / LS_WATCH=<hex,..> 指定 u32 の ON/OFF 差を unit ごとに出す
//        LS_ERR=1 unit ごとの stderr 行数 / LS_TRACE=<dir> LS_TRACE_U=<unit,..> 指定 unit の icall/UStrAsg/[ov] trace を書き出す (ov 側の trace は ov_2131_trace.patch)
import fs from 'fs';

const LS_MAX = +(process.env.LS_MAX || 190);
const TARGET = +(process.env.LS_TARGET || 190);
const MAXTESTS = +(process.env.LS_MAXTESTS || 40);
const CKPT = +(process.env.LS_CKPT || 189);
const PG = 4096;

const boot = async (dir) => {
  const m = await import(dir + '/m11_boot.cjs');
  const err = [];
  const mod = await m.default({ printErr: (s) => err.push(String(s)) });
  mod.HEAPU8.set(fs.readFileSync(dir + '/m11_image.bin'), 0);
  mod._m11_set_survey(1);
  const sp_boot = mod._emscripten_stack_get_current();
  try { mod._m11_boot_enter(0n, 1n); } catch (e) {
    if (!(e && e.m11_dllmain_done !== undefined)) throw e;
    mod.__emscripten_stack_restore(sp_boot);
  }
  return { mod, sp0: mod._emscripten_stack_get_current(), err };
};

const runUnit = (st, i) => {
  try {
    const r = st.mod._m11_call_unit(i);
    return r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss';
  } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) return 'halt0';
    const msg = ((e && e.message) || String(e)).split('\n')[0];
    st.mod.__emscripten_stack_restore(st.sp0);
    return /out of bounds/.test(msg) && !/table/.test(msg) ? 'oob' : /abort/i.test(msg) ? 'abort' : 'other';
  }
};

const diffPages = (ma, mb) => {
  const a = ma.HEAPU8, b = mb.HEAPU8;
  if (a.length !== b.length) console.log('heap length differs', a.length, b.length);
  const n = Math.min(a.length, b.length);
  const ba = Buffer.from(a.buffer, a.byteOffset, n), bb = Buffer.from(b.buffer, b.byteOffset, n);
  if (ba.equals(bb)) return [];
  const out = [];
  for (let off = 0; off < n; off += PG) if (!ba.subarray(off, off + PG).equals(bb.subarray(off, off + PG))) out.push(off / PG);
  return out;
};

const coalesce = (pages) => {
  const r = [];
  for (const p of pages) { if (r.length && r[r.length - 1][1] === p) r[r.length - 1][1] = p + 1; else r.push([p, p + 1]); }
  return r.map(([s, e]) => '0x' + (s * PG).toString(16) + '-0x' + (e * PG).toString(16));
};

// phase 1
const A = await boot(process.env.LS_A), B = await boot(process.env.LS_B);
console.log('boot diffPages =', diffPages(A.mod, B.mod).length);
let U = CKPT, Upages = [], spA = 0;
const pd = new Map();
for (let i = 0; i <= LS_MAX; i++) {
  const trU = (process.env.LS_TRACE_U || '').split(',').filter(Boolean).map(Number);
  const tr = process.env.LS_TRACE && (i === TARGET || trU.includes(i));
  if (tr) { A.mod._m11_set_trace(1); B.mod._m11_set_trace(1); A.err.length = 0; B.err.length = 0; }
  const ka = runUnit(A, i), kb = runUnit(B, i);
  if (tr) {
    A.mod._m11_set_trace(0); B.mod._m11_set_trace(0);
    fs.writeFileSync(process.env.LS_TRACE + '/trace_on_' + i + '.txt', A.err.join('\n'));
    fs.writeFileSync(process.env.LS_TRACE + '/trace_off_' + i + '.txt', B.err.join('\n'));
  }
  const dp = diffPages(A.mod, B.mod);
  if (process.env.LS_WATCH) for (const w of process.env.LS_WATCH.split(',')) {
    const o = parseInt(w, 16), va = A.mod.HEAPU8, vb = B.mod.HEAPU8;
    const x = new DataView(va.buffer, va.byteOffset, va.length).getUint32(o, true), y = new DataView(vb.buffer, vb.byteOffset, vb.length).getUint32(o, true);
    if (x !== y || i === LS_MAX) console.log(`watch unit ${i} 0x${o.toString(16)} ON=${x.toString(16)} OFF=${y.toString(16)} ${x !== y ? 'DIFF' : 'same'}`);
  }
  if (process.env.LS_ERR && (A.err.length || B.err.length)) console.log(`unit ${i} stderr A=${A.err.length} B=${B.err.length} A-first=${JSON.stringify(A.err.slice(0, 2)).slice(0, 160)} B-first=${JSON.stringify(B.err.slice(0, 2)).slice(0, 160)}`);
  A.err.length = 0; B.err.length = 0;
  if (ka !== kb || i === TARGET) console.log(`unit ${i} A=${ka} B=${kb} diffPages=${dp.length}`);
  if (i === CKPT && process.env.LS_FIX) for (const w of process.env.LS_FIX.split(',')) {
    const o = parseInt(w, 16), vb = B.mod.HEAPU8, va = A.mod.HEAPU8;
    const v = new DataView(vb.buffer, vb.byteOffset, vb.length).getUint32(o, true);
    new DataView(va.buffer, va.byteOffset, va.length).setUint32(o, v, true);
    console.log(`fix A(ON) 0x${o.toString(16)} <- OFF value 0x${v.toString(16)} (at checkpoint ${CKPT})`);
  }
  if (i === CKPT && process.env.LS_FIX) console.log(`fix: diffPages now=${diffPages(A.mod, B.mod).length}`);
  if (i === CKPT && process.env.LS_REVERSE) {
    for (const p of dp) A.mod.HEAPU8.set(B.mod.HEAPU8.subarray(p * PG, (p + 1) * PG), p * PG);
    console.log(`reverse: copied ${dp.length} OFF pages into A(ON) at checkpoint; diffPages now=${diffPages(A.mod, B.mod).length}`);
  }
  if (i === CKPT && process.env.LS_FORCEB) {
    for (const p of dp) B.mod.HEAPU8.set(A.mod.HEAPU8.subarray(p * PG, (p + 1) * PG), p * PG);
    B.mod.__emscripten_stack_restore(A.mod._emscripten_stack_get_current());
    console.log(`forceB: copied ${dp.length} A(ON) pages into B and SP; diffPages now=${diffPages(A.mod, B.mod).length}`);
  }
  if (i === CKPT) {
    Upages = dp;
    for (const p of Upages) pd.set(p, Buffer.from(A.mod.HEAPU8.subarray(p * PG, (p + 1) * PG)));
    console.log(`checkpoint unit ${CKPT}: diffPages=${dp.length} ranges:`, coalesce(dp).join(' '));
    if (process.env.LS_DUMP) {
      const pg = parseInt(process.env.LS_DUMP, 16) / PG, ea = A.mod.HEAPU8, eb = B.mod.HEAPU8;
      const da = new DataView(ea.buffer, ea.byteOffset, ea.length), db = new DataView(eb.buffer, eb.byteOffset, eb.length);
      let n = 0;
      for (let o = pg * PG; o < (pg + 1) * PG; o += 4) if (da.getUint32(o, true) !== db.getUint32(o, true)) { if (n++ < 40) console.log(`  dump 0x${o.toString(16)}: ON=${da.getUint32(o, true).toString(16)} OFF=${db.getUint32(o, true).toString(16)}`); }
      console.log('  differing u32 in page:', n);
    }
    spA = A.mod._emscripten_stack_get_current();
    console.log(`checkpoint sp A(ON)=0x${spA.toString(16)} B(OFF)=0x${B.mod._emscripten_stack_get_current().toString(16)} heapA=${A.mod.HEAPU8.length} heapB=${B.mod.HEAPU8.length}`);
  }
}

// overlay: B (OFF) を 0..U まで走らせ、S のページに A の内容を重ね、U+1..LS_MAX を走らせて TARGET の kind を返す
let tests = 0;
const testOverlay = async (S) => {
  tests++;
  const st = await boot(process.env.LS_B);
  for (let i = 0; i <= U; i++) runUnit(st, i);
  for (const p of S) st.mod.HEAPU8.set(pd.get(p), p * PG);
  if (process.env.LS_SYNC_SP) st.mod.__emscripten_stack_restore(spA);
  let k = null;
  for (let i = U + 1; i <= LS_MAX; i++) { const r = runUnit(st, i); if (i === TARGET) k = r; }
  return k;
};

const kAll = await testOverlay(Upages);
const kNone = await testOverlay([]);
console.log(`overlay all(${Upages.length} pages) -> TARGET=${kAll}; overlay none -> TARGET=${kNone}`);
if (kAll === kNone || kAll === null) process.exit(0);

let S = Upages.slice();
let chunk = Math.ceil(S.length / 2);
while (S.length > 1 && chunk >= 1 && tests < MAXTESTS) {
  let reduced = false;
  for (let s = 0; s < S.length && tests < MAXTESTS; s += chunk) {
    const cand = S.slice(0, s).concat(S.slice(s + chunk));
    if (cand.length && (await testOverlay(cand)) === 'oob') { S = cand; reduced = true; break; }
  }
  if (!reduced) { if (chunk === 1) break; chunk = Math.ceil(chunk / 2); }
}
console.log(`minimal page set (tests=${tests}, ${S.length} pages):`, coalesce(S).join(' '));
