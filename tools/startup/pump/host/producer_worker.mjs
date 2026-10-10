/* producer_worker.mjs — e2e 用 producer (worker_threads)。
 * worker_pump.ts の PumpRing (実物、ABI の正本) を共有 wasm メモリ上のリングに使って push する。
 * これが「C 側リング ← JS producer (runtime 実装)」の結線そのもの。 */
import { parentPort, workerData } from 'node:worker_threads';

const { PumpRing, WM } = await import(workerData.pumpRingMjs);

const { sab, byteOffset, count, paceMs, message, tOffset } = workerData;
const ring = new PumpRing(sab, byteOffset);   // capacity はヘッダから (C 側が初期化済み)

const epoch = () => performance.timeOrigin + performance.now();

function push(m) {
    // 満杯は 1ms 待って再試行 (欠落 0 の責務は producer 側。dropped は失敗時にだけ増える)
    for (;;) {
        if (ring.push(m)) return true;
        const t = Date.now() + 1;
        while (Date.now() < t) { /* 1ms バックオフ */ }
    }
}

parentPort.on('message', async (msg) => {
    if (msg.t !== 'go') return;
    const t0 = performance.now();
    for (let i = 0; i < count; i++) {
        push({ message, ptx: i, pty: i, tPost: epoch() + tOffset });
        if (paceMs > 0) {
            const until = performance.now() + paceMs;
            while (performance.now() < until) { /* pace */ }
        }
    }
    const pushMs = performance.now() - t0;
    // タイマ発火時間の確保後、終了要求 (D 検収の pump selftest と同じ締め方)
    const timerWindow = workerData.timerMs * 4;
    const until = performance.now() + Math.max(0, timerWindow - (performance.now() - t0));
    while (performance.now() < until) { /* timer window */ }
    push({ message: WM.APP_RUNTIME_STOP, tPost: epoch() + tOffset });
    parentPort.postMessage({ t: 'done', pushMs, droppedDuringPush: ring.dropped() });
});
parentPort.postMessage({ t: 'ready', capacity: ring.capacity, dropped: ring.dropped() });
