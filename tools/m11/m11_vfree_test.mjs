// M11 VirtualAlloc/VirtualFree 単体テスト (#513): VirtualFree(MEM_RELEASE) が実解放になっていること
//   3 周 x (8MB x 100 = 800MB) を確保→解放する. 累計 2.4GB は wasm 上限 (1.78GB) を超えるので, 実解放なら OOM 0 で完走し,
//   解放しない (M11_VFREE_NOOP=1 = ネガティブコントロール) と 3 周目で OOM になる.
//   使い方: node m11_vfree_test.mjs            → PASS/FAIL (exit 0/1)
//           M11_VFREE_NOOP=1 node m11_vfree_test.mjs  → NC: OOM が出れば NC_OK (exit 0), 出なければ NC_FAIL (exit 1)
const M11 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
const nc = process.env.M11_VFREE_NOOP === '1';
if (nc) mod._m11_set_vfree_noop(1);
const MEM_COMMIT_RESERVE = 0x3000, MEM_DECOMMIT = 0x4000, MEM_RELEASE = 0x8000, MB = 1 << 20;
const st = () => ({ live: Number(mod._m11_va_live()), peak: Number(mod._m11_va_peak()), oom: Number(mod._m11_va_oom()), freed: Number(mod._m11_va_freed()),
  unknown: Number(mod._m11_va_free_unknown()), skipped: Number(mod._m11_va_free_skipped()), decommit: Number(mod._m11_va_decommit()), calls: Number(mod._m11_va_calls()) });
const s0 = st();
const rounds = [];
for (let r = 0; r < 3; r++) {
  const ptrs = [];
  for (let k = 0; k < 100; k++) { const p = mod._VirtualAlloc(0, 8 * MB, MEM_COMMIT_RESERVE, 4); if (p) ptrs.push(p); }
  const mid = st();
  for (const p of ptrs) mod._VirtualFree(p, 0, MEM_RELEASE);
  const end = st();
  rounds.push({ round: r, got: ptrs.length, live_mid_MB: (mid.live - s0.live) / 1e6, live_end_MB: (end.live - s0.live) / 1e6, oom: end.oom - s0.oom });
}
// 表に無い解放 (二重解放 / 未知ポインタ) と DECOMMIT は落ちずに数えられる
const q = mod._VirtualAlloc(0, MB, MEM_COMMIT_RESERVE, 4);
const a = st();
mod._VirtualFree(q, MB, MEM_DECOMMIT);
const b = st();
mod._VirtualFree(q, 0, MEM_RELEASE);
mod._VirtualFree(q, 0, MEM_RELEASE);
mod._VirtualFree(12345, 0, MEM_RELEASE);
const c = st();
const e = st();
const res = { nc, rounds, decommit_kept_live: b.live === a.live && b.decommit === a.decommit + 1, double_and_unknown_free_counted: c.unknown - b.unknown + (nc ? c.skipped - b.skipped : 0) >= 2,
  final: { live_MB: (e.live - s0.live) / 1e6, peak_MB: e.peak / 1e6, oom: e.oom - s0.oom, freed: e.freed - s0.freed, unknown: e.unknown - s0.unknown, skipped: e.skipped - s0.skipped } };
console.log('M11_VFREE_TEST ' + JSON.stringify(res));
if (!nc) {
  const ok = res.final.oom === 0 && rounds.every((r) => r.got === 100 && r.live_end_MB === 0) && res.decommit_kept_live && res.final.freed === 301 && res.final.unknown === 2;
  console.log(ok ? 'PASS' : 'FAIL'); process.exit(ok ? 0 : 1);
} else {
  const ok = res.final.oom > 0 && res.final.freed === 0;
  console.log(ok ? 'NC_OK (解放しないと OOM になる)' : 'NC_FAIL'); process.exit(ok ? 0 : 1);
}
