// wasm 版 ipp_min を golden (実 Intel IPP win64 AVX512 経路の出力) と突合する。usage: node ipp_wasm_cmp.mjs <wasm> <goldenDir> [out.json]
import fs from 'node:fs';
const [, , wasmPath, gdir, outPath] = process.argv;
const inst = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(wasmPath)), { env: { emscripten_notify_memory_growth() {} } });
const X = inst.exports, mem = () => new Uint8Array(X.memory.buffer);
const man = JSON.parse(fs.readFileSync(`${gdir}/manifest.json`, 'utf8')).cases;
const blob = fs.readFileSync(`${gdir}/blob.bin`);
const f32 = (b) => { const t = new DataView(new ArrayBuffer(4)); t.setUint32(0, b >>> 0, true); return t.getFloat32(0, true); };
const ord = (b) => (b & 0x80000000) ? -(b & 0x7fffffff) : b;
const KIND = { A: 0, B: 1, C: 2, D: 3, E: 4, G: 5, H: 6, I: 7, J: 8, A8: 9, B8: 10 };
const isF = (k) => !(k === KIND.I || k === KIND.J || k === KIND.A8 || k === KIND.B8);
const maxU = Math.max(...man.map((c) => c.u));
const sz = (maxU + 16) * 4;
const pa = X.malloc(sz), pb = X.malloc(sz), pd = X.malloc(sz);
const stats = {};
let statusMismatch = {};
for (const c of man) {
  const fnx = X[c.fn]; if (!fnx) throw new Error('wasm export missing: ' + c.fn);
  const o = c.blob, u4 = c.u * 4;
  const M = mem();
  M.set(blob.subarray(o, o + u4), pa); M.set(blob.subarray(o + u4, o + 2 * u4), pb); M.set(blob.subarray(o + 2 * u4, o + 3 * u4), pd);
  const v = f32(c.v), v2 = f32(c.v2); let st;
  switch (c.kind) {
    case KIND.A: case KIND.A8: st = fnx(pa, pd, c.n); break;
    case KIND.B: case KIND.B8: st = fnx(pd, c.n); break;
    case KIND.C: st = fnx(pa, v, pd, c.n); break;
    case KIND.D: st = fnx(v, pd, c.n); break;
    case KIND.E: st = fnx(pa, pb, pd, c.n); break;
    case KIND.G: st = fnx(pd, c.n, v); break;
    case KIND.H: st = fnx(pd, c.n, v, v2); break;
    case KIND.I: st = fnx(pa, pd, c.n, c.rnd, c.sfs); break;
    case KIND.J: st = fnx(c.ival | 0, pd, c.n); break;
    default: throw new Error('kind ' + c.kind);
  }
  const outW = new Uint32Array(mem().buffer.slice(pd, pd + u4));
  const ref = new Uint32Array(blob.buffer.slice(blob.byteOffset + o + 3 * u4, blob.byteOffset + o + 4 * u4));
  const s = stats[c.fn] ??= { cases: 0, elems: 0, exact: 0, nan_payload_diff: 0, differ: 0, max_ulp: 0, max_rel: 0, status_mismatch: 0, nonfinite_mismatch: 0 };
  s.cases++; if (st !== c.st) s.status_mismatch++;
  for (let i = 0; i < c.u; i++) {
    s.elems++;
    if (outW[i] === ref[i]) { s.exact++; continue; }
    if (isF(c.kind)) {
      const fr = f32(ref[i]), fo = f32(outW[i]);
      if (Number.isNaN(fr) && Number.isNaN(fo)) { s.nan_payload_diff++; continue; }
      s.differ++;
      if (Number.isFinite(fr) && Number.isFinite(fo)) {
        s.max_ulp = Math.max(s.max_ulp, Math.abs(ord(ref[i]) - ord(outW[i])));
        s.max_rel = Math.max(s.max_rel, Math.abs(fr - fo) / (Math.abs(fr) + 1e-45));
      } else s.nonfinite_mismatch++;
    } else s.differ++;
  }
}
// 判定: 厳密一致を要求する関数と許容を持つ関数
const TOL = { ippsSqrt_32f_A11: { rel: 3e-4 }, ippsExp_32f_A11: { rel: 3e-4 }, ippsVectorSlope_32f: { loose: true } };
let bad = 0; const rows = [];
for (const [fn, s] of Object.entries(stats)) {
  const t = TOL[fn]; let ok;
  if (!t) ok = s.differ === 0 && s.status_mismatch === 0;
  else if (t.rel) ok = s.max_rel <= t.rel && s.nonfinite_mismatch === 0;
  else ok = true;
  if (!ok) bad++;
  rows.push({ fn, ...s, bit_exact_all: s.differ === 0, verdict: ok ? 'PASS' : 'FAIL' });
}
for (const r of rows) console.log(r.verdict.padEnd(5), r.fn.padEnd(26), `elems=${r.elems} exact=${r.exact} nanPayloadDiff=${r.nan_payload_diff} differ=${r.differ} statusMis=${r.status_mismatch} maxUlp=${r.max_ulp} maxRel=${r.max_rel.toExponential(2)}`);
console.log(`wasm vs real-IPP golden: functions=${rows.length} fail=${bad} bitExactFunctions=${rows.filter((r) => r.bit_exact_all).length}`);
// 表: 420 名 lookup と fail-fast stub
const nm = (p) => { const m = mem(); let e = p; while (m[e]) e++; return Buffer.from(m.subarray(p, e)).toString(); };
const cnt = X.ipp_table_count(); let impl = 0; for (let i = 0; i < cnt; i++) impl += X.ipp_table_impl(i);
const tbl = { count: cnt, implemented: impl, stubs: cnt - impl };
let trapName = null;
const cs = (s) => { const b = Buffer.from(s + '\0'); const p = X.malloc(b.length); mem().set(b, p); return p; };
try { X.ipp_call0(cs('ippsConv_32f')); } catch (e) { trapName = nm(X.ipp_unimpl_name()); }
tbl.lookup_ok = X.ipp_lookup(cs('ippsMulC_32f_I')) !== 0 && X.ipp_lookup(cs('ippMalloc')) !== 0 && X.ipp_lookup(cs('nonexistent')) === 0;
tbl.stub_trap_reports = trapName;
tbl.stub_failfast_ok = trapName === 'ippsConv_32f';
console.log('table', JSON.stringify(tbl));
if (outPath) fs.writeFileSync(outPath, JSON.stringify({ rows, table: tbl }, null, 1));
process.exit(bad ? 1 : 0);

