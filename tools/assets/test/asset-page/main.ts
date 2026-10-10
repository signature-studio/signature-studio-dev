// asset e2e ページ: asset-worker を起動し結果を /__report へ POST (単発シナリオ = 1 Chrome 起動)。
const q = new URLSearchParams(location.search);
const cfg = {
  base: q.get('base') ?? location.origin + '/',
  scenario: q.get('scenario') ?? 'cold',
  path: q.get('path') ?? 'Engine/FLEngine.wasm',
  expected: q.get('expected') ?? 'asset-expected.json',
  chunk: Number(q.get('chunk') ?? 3),
};
const log = document.getElementById('log')!;
const post = (v: unknown) => fetch(location.origin + '/__report', { method: 'POST', body: JSON.stringify(v) });
try {
  const expected = await (await fetch(cfg.expected)).json();
  const w = new Worker(new URL('./asset-worker.js', import.meta.url), { type: 'module' });
  w.onerror = (e) => void post({ ok: false, error: 'worker error: ' + e.message, stage: 'page' });
  // 監視: 90s 音信無しなら最後の stage を添えて報告 (無限停止を報告漏れにしない)
  let lastStage = 'boot';
  let lastMsgAt = Date.now();
  const wd = setInterval(() => {
    if (Date.now() - lastMsgAt > 90000) {
      clearInterval(wd);
      void post({ ok: false, error: `watchdog: no worker message for 90s (last stage=${lastStage})`, stage: lastStage });
    }
  }, 5000);
  w.onmessage = async (e) => {
    lastMsgAt = Date.now();
    if (e.data?.ok === 'progress') {
      lastStage = e.data.stage;
      log.textContent = `stage: ${e.data.stage} (${e.data.elapsedMs}ms)`;
      return;
    }
    clearInterval(wd);
    lastStage = 'done';
    log.textContent = JSON.stringify(e.data, null, 1);
    await post(e.data);
  };
  w.postMessage({ ...cfg, expected, isolated: crossOriginIsolated, sab: typeof SharedArrayBuffer !== 'undefined' });
} catch (e) {
  await post({ ok: false, error: String(e) });
}
