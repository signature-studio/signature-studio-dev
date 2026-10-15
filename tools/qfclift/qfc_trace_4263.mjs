// qfc_trace_4263.mjs — 計測専用 (T-SH-107 / #4263)。qfc_trace_4263.sh が呼ぶ。判定はしない。
//   env: QFC_CJS (計測版 wasm の .cjs)。QFC_REASON (DllMain の reason・既定 1)。DllMain → FontCache_GetStats → FontCache_CleanUp を qfc_run で順に実行し、
//   stderr を全行出す ([trace4263] の行を含む)。
const mod = await import(process.env.QFC_CJS);
const m = await mod.default({ printErr: (s) => console.log(String(s)), print: () => {} });
m._fle_data_install();
m._fle_init();
const buf = m._malloc(0x1000);
const reason = Number(process.env.QFC_REASON ?? 1);
const steps = [
  ['DllMain', 0x59c1f0, [0x400000, reason, 0]],
  ['FontCache_GetStats', 0x57faf0, [buf]],
  ['FontCache_CleanUp', 0x57f980, []],
];
for (const [name, va, args] of steps) {
  try {
    const r = m._qfc_run(va, ...[...args, 0, 0, 0, 0].slice(0, 4).map((x) => BigInt(x)), 0n, 0n, 0n, 0n);
    console.log('[ret] ' + name + ' 0x' + BigInt.asUintN(64, BigInt(r)).toString(16));
  } catch (e) {
    console.log('[trap] ' + name + ' ' + String(e).slice(0, 160));
    break;
  }
}
