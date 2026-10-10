// seed_page.ts — CAB-216 e2e ページ: seed_worker を起動し結果を /__report へ POST (単発シナリオ = 1 Chrome 起動)。
const q = new URLSearchParams(location.search);
const phase = q.get('phase') ?? 'seed';
const log = document.getElementById('log')!;
const post = (v: unknown) => fetch(location.origin + '/__report', { method: 'POST', body: JSON.stringify(v) });
try {
  const w = new Worker(new URL('./seed-worker.js', import.meta.url), { type: 'module' });
  const dump = (ev: any) => `worker error: ${ev.message ?? JSON.stringify(String(ev))} @${ev.filename ?? ''}:${ev.lineno ?? ''}`;
  w.onerror = (e) => void post({ ok: false, error: dump(e), stage: 'page' });
  let lastStage = 'boot';
  let lastMsgAt = Date.now();
  const wd = setInterval(() => {
    if (Date.now() - lastMsgAt > 120000) {
      clearInterval(wd);
      void post({ ok: false, error: `watchdog: no worker message for 120s (last stage=${lastStage})`, stage: lastStage });
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
    log.textContent = JSON.stringify(e.data, null, 1);
    await post(e.data);
  };
  w.postMessage({ phase });
} catch (e) {
  await post({ ok: false, error: String(e), stage: 'page' });
}
