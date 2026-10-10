// ページ側: engine Worker を起動し、結果を /__report へ POST する (headless Chrome ハーネス用)
const q = new URLSearchParams(location.search);
const cfg = {
  base: q.get('base') ?? location.origin + '/',
  phase: q.get('phase') ?? 'cold',
  loader: (q.get('loader') ?? 'sab') as 'sab' | 'xhr',
  expected: q.get('expected') ?? 'expected.json',
  verify: q.get('verify') !== '0',
  ra: Number(q.get('ra') ?? 8),
};
const log = document.getElementById('log')!;
const post = (v: unknown) => fetch(location.origin + '/__report', { method: 'POST', body: JSON.stringify(v) });
try {
  const expected = await (await fetch(cfg.expected)).json();
  const w = new Worker(new URL('./engine-worker.js', import.meta.url), { type: 'module' });
  w.onerror = (e) => void post({ ok: false, error: 'worker error: ' + e.message });
  // 監視: worker からの音信が 90s 無ければ最後の stage 付きで報告する (無限停止を報告漏れにしない)
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
  w.postMessage({ ...cfg, expected, pageIsolated: crossOriginIsolated });
} catch (e) {
  await post({ ok: false, error: String(e) });
}
