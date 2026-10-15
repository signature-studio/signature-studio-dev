// PERF-P25 (#3959): 1 instance (Memory 1 本) に M 個の OTT obj を畳む instantiate の成否を Node で掃引する。
// chrome_worklet.mjs --init-only と同じ setup 手順 (ctor・setParam 19 個・resume) を同期で行い、
// 1 M ごとに別 instance を作って、戻れば ok・timeout 秒を超えたら子プロセスごと打ち切る。
//   node tools/perf/p15/node_init_sweep.mjs --m 2,3,...,160 --timeout 20000 --out <jsonl>
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import { fileURLToPath } from 'node:url'; import { spawnSync } from 'node:child_process';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const WASM = path.join(HERE, '../../ott/work/lift/ottl.wasm');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const CHILD = argv.includes('--child');

if (CHILD) {
  const M = +arg('--m', 1);
  const OBJ0 = 0x31000000, STRIDE = 0x40000, IN0 = 0x34000000, OU0 = 0x34000080, BUF0 = 0x34100000, N = 128;
  const slot = (i) => ({ obj: OBJ0 + i * STRIDE, inA: IN0 + i * 0x100, ouA: OU0 + i * 0x100, buf: BUF0 + i * 0x2000 });
  const imports = {
    env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
    wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
  };
  const x = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(WASM)), imports).exports;
  x.__wasm_call_ctors(); x.ott_data_install();
  const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
  const run = (va, a, xs = []) => BigInt.asUintN(64, x.ott_run(0x30000000 + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), BigInt(a[2] ?? 0), BigInt(a[3] ?? 0), BigInt(xs[0] ?? 0), BigInt(xs[1] ?? 0), BigInt(xs[2] ?? 0), BigInt(xs[3] ?? 0)));
  const U32 = new Uint32Array(x.memory.buffer), F32 = new Float32Array(x.memory.buffer);
  const t0 = Date.now();
  for (let i = 0; i < M; i++) {
    const s = slot(i);
    run(0x18011d400, [s.obj, 0]);
    for (let p = 0; p < 19; p++) run(0x180120af0, [s.obj, p], [0, 0, f32b(0.5)]);
    run(0x180120800, [s.obj]);
    for (let k = 0; k < N * 2; k++) F32[s.buf / 4 + k] = Math.fround(Math.sin(k * 0.05) * 0.5);
    U32[s.inA / 4] = s.buf; U32[s.inA / 4 + 2] = s.buf + N * 4; U32[s.ouA / 4] = s.buf + N * 8; U32[s.ouA / 4 + 2] = s.buf + N * 12;
  }
  process.stdout.write(JSON.stringify({ setup_ms: Date.now() - t0, memory_mib: +(x.memory.buffer.byteLength / 2 ** 20).toFixed(1) }));
  process.exit(0);
}

const MS = arg('--m', '1,130,145,146').split(',').map(Number);
const TMO = +arg('--timeout', 20000); const OUT = arg('--out', path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'perf', 'p25_node_sweep.jsonl'));
fs.mkdirSync(path.dirname(OUT), { recursive: true });
for (const m of MS) {
  const r = spawnSync(process.execPath, [fileURLToPath(import.meta.url), '--child', '--m', String(m)], { timeout: TMO, encoding: 'utf8' });
  const row = { mode: 'init_limit_node', M: m, timeout_ms: TMO, loadavg: os.loadavg().map((v) => +v.toFixed(2)) };
  if (r.error || r.status !== 0) row.error = r.error ? 'timeout' : `exit ${r.status}`;
  else Object.assign(row, JSON.parse(r.stdout), { ok: true });
  fs.appendFileSync(OUT, JSON.stringify(row) + '\n'); console.log(JSON.stringify(row));
}
