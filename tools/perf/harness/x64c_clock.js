// SharedArrayBuffer カウンタ時計 (AudioWorklet には performance/高分解能 timer が無いため)。
// Dedicated Worker で Atomics.store(u32[0]) を回し続け、AudioWorklet 側は Atomics.load の差分 (modulo 2^32) を時間として使う。
// u32[1] != 0 で停止 (spin 中は onmessage が処理されないため停止も SAB 経由)。 較正用に自身の performance.now() での ticks/ms も返す。
onmessage = (e) => {
  if (e.data.type !== 'start') return;
  const u32 = new Uint32Array(e.data.sab); let i = 0;
  postMessage({ type: 'started' });
  setTimeout(() => {
    const t0 = performance.now();
    while (Atomics.load(u32, 1) === 0) { for (let k = 0; k < 4096; k++) { i++; Atomics.store(u32, 0, i | 0); } }
    postMessage({ type: 'stopped', ticksPerMs: i / (performance.now() - t0), ticks: i });
  }, 0);
};
