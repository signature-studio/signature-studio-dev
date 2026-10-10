/* run_e2e.mjs — CAB-102 e2e ランナ (node)。
 *
 *   node host/run_e2e.mjs <WORK> unit   … (a) リンク置換検証: 単体 (pump 強定義) + weak 対照
 *   node host/run_e2e.mjs <WORK> st     … HOSTED (ST ビルド) のポンプ疎通 + ctrl 非同期完了
 *   node host/run_e2e.mjs <WORK> mt     … (b)(c)(d) MT: ATOMIC 疎通/遅延, 2000 件ストレス,
 *                                          SPIN / NONE(worklet 相当), ctrl 要求応答 RTT
 *
 * producer は src/runtime/worker_pump.ts の PumpRing (実物をリポジトリの tsc でトランスパイル) で
 * 共有 wasm メモリ上のリングに push する (= RING ABI 結線の正本検証)。
 */
import { createRequire } from 'node:module';
import { execFileSync, spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { fileURLToPath } from 'node:url';
import { Worker } from 'node:worker_threads';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../../../..');
const WORK = path.resolve(process.argv[2] || '.');
const stage = process.argv[3] || 'all';

let checks = 0, fails = 0;
const results = {};
function ok(cond, label, detail) {
    checks++;
    if (!cond) { fails++; console.log(`  FAIL: ${label}${detail ? ` — ${detail}` : ''}`); }
    return !!cond;
}
const percentile = (arr, p) => (arr.length ? arr[Math.min(arr.length - 1, Math.floor(arr.length * p))] : NaN);
const pct = (v) => (typeof v !== 'number' || Number.isNaN(v) ? 'n/a' : v >= 100 ? v.toFixed(0) : v.toFixed(3));

/* ---- worker_pump.ts (正本) をリポジトリの tsc でトランスパイルして node から使えるようにする ---- */
function ensurePumpRingMjs() {
    const src = path.join(REPO, 'src/runtime/worker_pump.ts');
    const out = path.join(WORK, 'worker_pump.mjs');
    if (existsSync(out) && statSync(out).mtimeMs >= statSync(src).mtimeMs) return out;
    const tmp = path.join(WORK, 'wp_ts');
    mkdirSync(tmp, { recursive: true });
    const tsc = path.join(REPO, 'node_modules/typescript/bin/tsc');
    execFileSync(process.execPath, [tsc, src, '--ignoreConfig', '--outDir', tmp, '--module', 'esnext', '--target', 'es2022'], { stdio: 'pipe' });
    cpSync(path.join(tmp, 'worker_pump.js'), out);
    return out;
}
const pumpRingMjs = ensurePumpRingMjs();
const { PumpRing, WM } = await import(pathToFileURL(pumpRingMjs).href);

/* ---- 共通ヘルパ ---- */
const epoch = () => performance.timeOrigin + performance.now();
const sleep = (ms) => new Promise((r) => setTimeout(r, Math.max(0, ms)));
async function loadMod(file) {
    const factory = require(file);
    return await factory();
}
function views(mod) {
    return { i32: mod.HEAP32, f64: mod.HEAPF64, buf: mod.HEAP32.buffer };
}
function readLog(mod, n) {
    const { f64, i32 } = views(mod);
    const a = mod._pump_pop_log_addr();
    const w = a >> 2;                      // i32 語単位。1 エントリ = 6 語 (24B: f64, f64, u32, u32)
    const f0 = a / 8;                      // f64 語単位。1 エントリ = 3 語
    const out = [];
    for (let i = 0; i < n; i++) {
        out.push({
            tPop: f64[f0 + i * 3],
            tPost: f64[f0 + i * 3 + 1],
            message: i32[w + i * 6 + 4] >>> 0,
            aux: i32[w + i * 6 + 5] >>> 0,
        });
    }
    return out;
}
function latencyOf(log) {
    const lat = log.filter((e) => e.tPost > 0 && e.message !== WM.TIMER).map((e) => e.tPop - e.tPost).sort((a, b) => a - b);
    const tlat = log.filter((e) => e.message === WM.TIMER && e.tPost > 0).map((e) => e.tPop - e.tPost).sort((a, b) => a - b);
    return {
        n: lat.length, p50: percentile(lat, 0.5), p90: percentile(lat, 0.9), p99: percentile(lat, 0.99), max: lat[lat.length - 1] ?? NaN,
        timerLateP50: percentile(tlat, 0.5), timerN: tlat.length,
    };
}
function stats(mod) {
    const { i32 } = views(mod);
    const a = mod._pump_stats_addr() >> 2;
    const f = (i) => i32[a + i] >>> 0;
    /* PumpStats の語順 (pump_abi.h) */
    return {
        pops: f(0), pushes: f(1), pushFull: f(2), timersSet: f(3), timersKilled: f(4), timersFired: f(5), paints: f(6),
        waitsAtomic: f(7), waitsSlice: f(8), waitsSpin: f(9), waitChunks: f(10), waitChunksTimedout: f(11),
        hostedEmpty: f(12), nowaitEmpty: f(13), dispatched: f(14), sentCalls: f(15), quitPosts: f(16),
        stashHit: f(17), stashSkip: f(18), stashOverflow: f(19), ctrlReq: f(20), ctrlOk: f(21), ctrlTimeout: f(22),
        wndprocMiss: f(23),
    };
}
/* 正確な時計較正: node では C モジュールが main スレッドで動くので直接差が取れる (誤差 ≈0)。
 * ctrl 経由の pump_calibrate はレスポンダの排水粒度分 (~RTT/2) の誤差を持つため、計測用にはこちらを使う。 */
function syncClock(mod) {
    mod._pump_set_clock_offset(performance.timeOrigin + performance.now() - mod._pump_now_raw());
}
function ringDropped(mod) {
    const { i32 } = views(mod);
    return i32[(mod._pump_ring_addr() >> 2) + 5] >>> 0;
}
function readMsg(mod) {
    const w = mod._pump_scratch_addr() >> 2;
    const { i32 } = views(mod);
    return {
        hwnd: i32[w] >>> 0,
        message: i32[w + 2] >>> 0,
        wParam: (i32[w + 5] >>> 0) * 4294967296 + (i32[w + 4] >>> 0),
    };
}

/* ctrl 応答 (ST: 同一スレッドで排水 = 「C が要求を書き、ホストが排水して戻す」の ST 形) */
function drainCtrlST(mod) {
    const { i32, f64 } = views(mod);
    const base = mod._pump_ctrl_req_addr() >> 2;
    const respW = mod._pump_ctrl_resp_addr() >> 2;   // i32 語
    const respF = mod._pump_ctrl_resp_addr() / 8;    // f64 語 (8B アライン)
    const cap = i32[base + 3];
    for (;;) {
        const pos = Atomics.load(i32, base + 1);
        const slot = base + 16 + (pos % cap) * 8;
        const seq = Atomics.load(i32, slot);
        if (((seq - (pos + 1)) | 0) !== 0) break;
        const rec = { reqId: i32[slot + 4] >>> 0, a0: i32[slot + 2] >>> 0, op: i32[slot + 1] >>> 0 };
        Atomics.store(i32, slot, pos + cap);
        Atomics.store(i32, base + 1, pos + 1);
        const s = Atomics.load(i32, respW);
        i32[respW + 1] = rec.reqId | 0;
        f64[respF + 1] = rec.op === 2 ? epoch() : rec.a0;   // ワード 2..3 (f64)
        f64[respF + 3] = epoch();                            // ワード 6..7 (f64)
        Atomics.store(i32, respW, s + 1);
    }
}

function spawnProducer(cfg) {
    return new Promise((resolve, reject) => {
        const w = new Worker(path.join(HERE, 'producer_worker.mjs'), { workerData: { pumpRingMjs, ...cfg } });
        let readyResolve; const ready = new Promise((r) => (readyResolve = r));
        w.once('message', (m) => { if (m.t === 'ready') readyResolve(m); });
        let doneResolve; const done = new Promise((r) => (doneResolve = r));
        w.on('message', (m) => { if (m.t === 'done') doneResolve(m); });
        w.on('error', reject);
        ready.then(() => resolve({ w, ready, done }));
    });
}
function spawnResponder(cfg) {
    return new Promise((resolve, reject) => {
        const w = new Worker(path.join(HERE, 'responder_worker.mjs'), { workerData: cfg });
        w.once('message', (m) => { if (m.t === 'ready') resolve(w); });
        w.on('error', reject);
    });
}

/* ================================================================= unit (a) */
if (stage === 'unit' || stage === 'all') {
    console.log('[unit] (a) リンク置換検証: pump 強定義が winstubs weak を置き、重複定義なし');
    {
        const r = spawnSync(process.execPath, [path.join(WORK, 'unit_st.cjs')], { encoding: 'utf8', timeout: 60000 });
        const lines = new Map(r.stdout.split('\n').filter((l) => l.includes('\t')).map((l) => [l.slice(0, l.indexOf('\t')), l.slice(l.indexOf('\t') + 1)]));
        ok(r.status === 0, `unit_st: 異常終了 status=${r.status}`, r.stderr.slice(-300));
        const caseIds = [...lines.keys()].filter((k) => /^T\d+$/.test(k));
        ok(caseIds.length >= 30, `unit: ケース数 (${caseIds.length} < 30)`);
        for (const k of caseIds) {
            const v = lines.get(k) || '';
            ok(v.startsWith('pass'), `unit ${k}: ${v}`);
        }
        ok(lines.get('unit') === 'ALL PASS', 'unit: ALL PASS 行');
        /* (a) 対照: weak のままでは GetMessageW(空) = 0 (WM_QUIT 扱いでループ即終了)。
         * pump 強定義では HOSTED の -1。行動面の置換証拠。 */
        const w = spawnSync(process.execPath, [path.join(WORK, 'weak_st.cjs')], { encoding: 'utf8', timeout: 60000 });
        const m = /GetMessageW_empty_ret=(-?\d+)/.exec(w.stdout);
        ok(!!m, 'weak 対照の出力', w.stderr.slice(-200));
        ok(m && m[1] === '0', `weak stub は空で 0 を返すはず (実測 ${m?.[1]})`);
        ok(lines.get('T48')?.startsWith('pass'), 'GetProcAddress が強定義へ解決 (T48)', lines.get('T48'));
        results.replace = { cases: caseIds.length, weakEmptyRet: m?.[1], pumpEmptyRet: 'HOSTED: -1' };
        console.log(`  unit: ${caseIds.length} ケース / weak 対照 GetMessageW(空)=${m?.[1]} → pump 強定義は -1 に変化 (置換実証)`);
    }
}

/* ================================================================= st (HOSTED) */
if (stage === 'st' || stage === 'all') {
    console.log('[st] HOSTED (ST ビルド): C はブロックせず待ち時間ヒントを返し、ホスト (JS) が寝て再入場する');
    const mod = await loadMod(path.join(WORK, 'e2e_st.cjs'));
    const v = views(mod);
    mod._e2e_setup();
    mod._pump_set_wait_mode(3 /* HOSTED */);
    const ring = new PumpRing(v.buf, mod._pump_ring_addr());   // 同一スレッド views (非共有メモリ)
    ok(ring.capacity === 1024, `ring capacity (実測 ${ring.capacity})`);
    ok((v.i32[(mod._pump_ring_addr() >> 2) + 3] >>> 0) === 0x50554d50, 'ring magic (C 側初期化をホストが検査)');

    /* ctrl: C が要求を書く → ホストが排水して戻す。較正 (EPOCH_NOW) → ECHO 0xBEEF の順に検証。
     * 非同期完了は pump_ctrl_take_done (内部 service_done) が拾う。 */
    mod._pump_calibrate();
    drainCtrlST(mod);
    mod._e2e_ctrl_take_done();                     // 校正要求の完了を吸い出す (戻り値 = host epoch / 捨てる)
    ok(mod._pump_clock_calibrated() === 1, 'ST: 時刻較正が非同期完了 (pump_step 経由)');
    syncClock(mod);                                // 計測用に正確なオフセットへ差し替え (node は同スレッド直接差)
    mod._e2e_ctrl_async_req();
    drainCtrlST(mod);
    const ctrlRet = mod._e2e_ctrl_take_done();
    ok(ctrlRet === 0xbeef, `ctrl 非同期完了 ret (実測 ${ctrlRet})`);

    /* producer は同スレッド (setInterval)。ホストループ: pump_step + pump_wait_ms */
    mod._e2e_setup_timer(0, 7, 10, 0);
    const N = 500;
    let sent = 0, received = 0, timers = 0, stops = 0, stopQueued = false;
    const iv = setInterval(() => {
        if (sent < N) { if (ring.push({ message: WM.MOUSEMOVE, ptx: sent, pty: sent, tPost: epoch() })) sent++; }
    }, 2);
    const deadline = Date.now() + 30000;
    let quit = false;
    while (!quit && Date.now() < deadline) {
        for (let burst = 0; burst < 64 && !quit; burst++) {   // 空になるまで一掃 (HOSTED の step はブロックしない)
            const r = mod._pump_step(mod._pump_scratch_addr());
            if (r === -1) break;
            if (r === 0) { quit = true; break; }
            const m = readMsg(mod);
            if (m.message === WM.MOUSEMOVE) received++;
            else if (m.message === WM.TIMER) timers++;
            else if (m.message === WM.APP_RUNTIME_STOP) { stops++; mod._pump_t_post_quit(0); }
        }
        if (quit) break;
        drainCtrlST(mod);
        if (sent >= N && !stopQueued) stopQueued = ring.push({ message: WM.APP_RUNTIME_STOP, tPost: epoch() });
        const hint = mod._pump_wait_ms();
        await sleep(Math.min(hint < 0 ? 2 : hint, 2));
    }
    clearInterval(iv);
    const s = stats(mod);
    const lat = latencyOf(readLog(mod, mod._pump_pop_log_count()));
    results.st = { sent, received, timers, stops, lat, hostedEmpty: s.hostedEmpty };
    ok(received === N, `ST 疎通: 受信 ${received}/${N}`);
    ok(timers >= 3, `ST: WM_TIMER 発火 ${timers} (>=3)`);
    ok(s.hostedEmpty > 0, `ST: 実待ち (hosted_empty=${s.hostedEmpty}) — C は一度もブロックせずホストに返している`);
    ok(ringDropped(mod) === 0, `ST: 欠落 ${ringDropped(mod)}`);
    ok(stops === 1, `ST: STOP は 1 回 (${stops})`);
    console.log(`  ST hosted: received=${received}/${N} timers=${timers} p50=${pct(lat.p50)}ms p99=${pct(lat.p99)}ms hosted_empty=${s.hostedEmpty} dropped=${ringDropped(mod)}`);
}

/* ================================================================= mt (b)(c)(d) */
if (stage === 'mt' || stage === 'all') {
    /* ---- (b)+(c) ATOMIC 疎通 + 遅延計測 ---- */
    console.log('[mt] ATOMIC: 共有メモリ上のリングを C が memory.atomic.wait32 で直接ブロック');
    {
        const mod = await loadMod(path.join(WORK, 'e2e_mt.cjs'));
        mod._e2e_setup();
        mod._pump_set_wait_mode(0 /* ATOMIC */);
        const v = views(mod);
        const responder = await spawnResponder({ sab: v.buf, reqAddr: mod._pump_ctrl_req_addr(), respAddr: mod._pump_ctrl_resp_addr() });
        syncClock(mod);   // 計測用の正確な較正 (node は main スレッド直接差)
        ok(mod._pump_clock_calibrated() === 1, 'MT: 時刻較正完了 (page 直接差)');
        mod._e2e_setup_timer(0, 7, 10, 0);

        const N = 300, PACE = 1;
        const prod = await spawnProducer({ sab: v.buf, byteOffset: mod._pump_ring_addr(), count: N, paceMs: PACE, message: WM.MOUSEMOVE, timerMs: 10, tOffset: 0 });
        prod.w.postMessage({ t: 'go' });
        const t0 = performance.now();
        const runOk = mod._e2e_consumer_run(30000);   // ← C がブロックする間も producer/responder は動く
        const wall = performance.now() - t0;
        const s = stats(mod);
        const lat = latencyOf(readLog(mod, mod._pump_pop_log_count()));
        const prodDone = await prod.done;
        results.mtAtomic = { ...lat, received: s.pops, timers: s.timersFired, waits: s.waitsAtomic, dropped: ringDropped(mod), wall };
        ok(runOk === 1, 'MT ATOMIC: コンシューマループが WM_QUIT で正常終了');
        ok(s.pops >= N, `MT 疎通: pops ${s.pops} >= ${N}`);
        ok(prodDone.droppedDuringPush === 0 && ringDropped(mod) === 0, `欠落: ring=${ringDropped(mod)} producer=${prodDone.droppedDuringPush}`);
        ok(s.timersFired >= 3, `WM_TIMER 発火 ${s.timersFired} (>=3)`);
        ok(s.waitsAtomic > 0, `実ブロッキング wait (waits_atomic=${s.waitsAtomic})`);
        ok(lat.p50 < 1.0, `p50 ${pct(lat.p50)}ms < 1ms (D 検収 0.01ms との比較は REPORT)`, `p50=${lat.p50}`);
        console.log(`  MT atomic: n=${lat.n} p50=${pct(lat.p50)}ms p90=${pct(lat.p90)}ms p99=${pct(lat.p99)}ms max=${pct(lat.max)}ms | timers=${s.timersFired} waits=${s.waitsAtomic} wall=${wall.toFixed(0)}ms`);
        await responder.terminate();
        await prod.w.terminate();
    }

    /* ---- (d) 2000 件ストレス ---- */
    console.log('[mt] (d) 2000 件ストレス (バースト, 欠落 0 + 順序検証)');
    {
        const mod = await loadMod(path.join(WORK, 'e2e_mt.cjs'));
        mod._e2e_setup();
        mod._pump_set_wait_mode(0);
        const v = views(mod);
        const responder = await spawnResponder({ sab: v.buf, reqAddr: mod._pump_ctrl_req_addr(), respAddr: mod._pump_ctrl_resp_addr() });
        syncClock(mod);
        mod._e2e_setup_timer(0, 7, 10, 0);
        const N = 2000;
        const prod = await spawnProducer({ sab: v.buf, byteOffset: mod._pump_ring_addr(), count: N, paceMs: 0, message: WM.MOUSEMOVE, timerMs: 10, tOffset: 0 });
        prod.w.postMessage({ t: 'go' });
        const runOk = mod._e2e_consumer_run(60000);
        const s = stats(mod);
        const log = readLog(mod, mod._pump_pop_log_count());
        /* 順序: MOUSEMOVE の pt.x (producer 通し番号) が単調増加 = 欠落 0 の強証拠 */
        let lastPtx = -1, orderOK = true, seen = 0;
        for (const e of log) {
            if (e.message === WM.MOUSEMOVE) {
                if (e.aux !== lastPtx + 1) orderOK = false;
                lastPtx = e.aux; seen++;
            }
        }
        const prodDone = await prod.done;
        results.mtStress = { n: N, received: seen, dropped: ringDropped(mod), orderOK, pushMs: prodDone.pushMs };
        ok(runOk === 1, 'stress: 正常終了');
        ok(seen === N, `stress: 受信 ${seen}/${N} (欠落 ${N - seen})`);
        ok(orderOK, 'stress: 通し番号が単調増加 (順序保存・欠落なし)');
        ok(ringDropped(mod) === 0 && prodDone.droppedDuringPush === 0, `stress: dropped ring=${ringDropped(mod)}`);
        console.log(`  MT stress: received=${seen}/${N} order=${orderOK ? 'OK' : 'NG'} dropped=${ringDropped(mod)} push=${prodDone.pushMs.toFixed(0)}ms`);
        await responder.terminate();
        await prod.w.terminate();
    }

    /* ---- (c) SPIN 戦略 ---- */
    console.log('[mt] SPIN: wake 語のビジーウェイト (極短待ち。CPU 消費との引き換え)');
    {
        const mod = await loadMod(path.join(WORK, 'e2e_mt.cjs'));
        mod._e2e_setup();
        mod._pump_set_wait_mode(2 /* SPIN */);
        const v = views(mod);
        const responder = await spawnResponder({ sab: v.buf, reqAddr: mod._pump_ctrl_req_addr(), respAddr: mod._pump_ctrl_resp_addr() });
        syncClock(mod);
        mod._e2e_setup_timer(0, 7, 10, 0);
        const N = 200, PACE = 2;
        const prod = await spawnProducer({ sab: v.buf, byteOffset: mod._pump_ring_addr(), count: N, paceMs: PACE, message: WM.MOUSEMOVE, timerMs: 10, tOffset: 0 });
        prod.w.postMessage({ t: 'go' });
        const runOk = mod._e2e_consumer_run(30000);
        const s = stats(mod);
        const lat = latencyOf(readLog(mod, mod._pump_pop_log_count()));
        results.mtSpin = { ...lat, waits: s.waitsSpin };
        ok(runOk === 1, 'SPIN: 正常終了');
        ok(s.pops >= N, `SPIN 疎通: pops ${s.pops} >= ${N}`);
        ok(s.waitsSpin > 0, `spin チャンク計数 (${s.waitsSpin})`);
        console.log(`  MT spin: p50=${pct(lat.p50)}ms p99=${pct(lat.p99)}ms waits_spin=${s.waitsSpin}`);
        await responder.terminate();
        await prod.w.terminate();
    }

    /* ---- NONE (worklet 相当): 決して待たない ---- */
    console.log('[mt] NONE (worklet 相当): Peek poll のみ。Atomics.wait 不可の文脈を模擬');
    {
        const mod = await loadMod(path.join(WORK, 'e2e_mt.cjs'));
        mod._e2e_setup();
        mod._pump_set_wait_mode(4 /* NONE */);
        const v = views(mod);
        const N = 2000;
        const prod = await spawnProducer({ sab: v.buf, byteOffset: mod._pump_ring_addr(), count: N, paceMs: 0.5, message: WM.MOUSEMOVE, timerMs: 10, tOffset: 0 });
        prod.w.postMessage({ t: 'go' });
        let received = 0, stopSeen = false, callMax = 0;
        const t0 = performance.now();
        while (!stopSeen && performance.now() - t0 < 60000) {
            const c0 = performance.now();
            const m = mod._e2e_poll_once();
            const dt = performance.now() - c0;
            if (dt > callMax) callMax = dt;   // 1 poll 呼出の所要 (ブロック無しの証拠)
            if (m === WM.MOUSEMOVE) received++;
            else if (m === WM.APP_RUNTIME_STOP) stopSeen = true;
            await sleep(0.25);   // worklet の 128f (≈2.7ms) より短いポーリング周期
        }
        const wall = performance.now() - t0;
        const lat = latencyOf(readLog(mod, mod._pump_pop_log_count()));
        const dropped = ringDropped(mod);
        results.mtNone = { received, wall, callMax, lat, dropped };
        ok(received === N, `NONE: 受信 ${received}/${N} (実欠落 0)`);
        ok(callMax < 1.0, `NONE: 1 poll 呼出が非ブロッキング (max ${callMax.toFixed(3)}ms < 1ms)`);
        ok(wall < 30000, `NONE: poll 掬い完了 (wall=${wall.toFixed(0)}ms)`);
        console.log(`  MT none(worklet 相当): received=${received}/${N} p50=${pct(lat.p50)}ms p99=${pct(lat.p99)}ms wall=${wall.toFixed(0)}ms pollMax=${callMax.toFixed(3)}ms ringFull(押し戻し)=${dropped}`);
        await prod.done;
        await prod.w.terminate();
    }

    /* ---- ctrl 要求応答 RTT (応答待ち戦略の比較) ---- */
    console.log('[mt] ctrl: C が要求を書き→ホストが排水して戻す (応答待ち戦略別 RTT)');
    {
        const mod = await loadMod(path.join(WORK, 'e2e_mt.cjs'));
        mod._e2e_setup();
        mod._pump_set_wait_mode(0 /* ATOMIC — calibrate の前に設定 (実効モード) */);
        const v = views(mod);
        const responder = await spawnResponder({ sab: v.buf, reqAddr: mod._pump_ctrl_req_addr(), respAddr: mod._pump_ctrl_resp_addr() });
        mod._pump_calibrate();   // ctrl 経由較正の機能確認 (ATOMIC で応答待ちする経路)
        const rttAll = () => {
            const n = mod._pump_ctrl_rtt_count();
            const arr = [];
            for (let i = 0; i < n; i++) arr.push(mod._pump_ctrl_rtt(i));
            return arr;
        };
        const warm = rttAll().length;
        mod._pump_set_wait_mode(0);
        const nAtomicRaw = mod._e2e_ctrl_probe(50);
        const nAtomic = Math.floor(nAtomicRaw / 100), lastRc = -(nAtomicRaw % 100);
        const arrA = rttAll().slice(warm);
        mod._pump_set_wait_mode(2);
        const warm2 = rttAll().length;
        mod._e2e_ctrl_probe(20);
        const arrS = rttAll().slice(warm2);
        const st = (arr) => { const a = [...arr].sort((x, y) => x - y); return { n: arr.length, p50: percentile(a, 0.5), p99: percentile(a, 0.99) }; };
        const rA = st(arrA), rS = st(arrS);
        ok(nAtomic === 50 && lastRc === 0, `ctrl ATOMIC: 成功 ${nAtomic}/50 (lastRc=${lastRc})`);
        ok(rA.n === 50, 'ctrl RTT ログが積まれている');
        ok(rA.p50 < 5000, `ctrl RTT p50 ${pct(rA.p50)}µs < 5ms`, `p50=${rA.p50}`);
        results.ctrl = { atomic: rA, spin: rS };
        console.log(`  ctrl RTT: ATOMIC p50=${pct(rA.p50)}µs p99=${pct(rA.p99)}µs (n=${rA.n}) / SPIN p50=${pct(rS.p50)}µs (n=${rS.n})`);
        await responder.terminate();
    }
}

/* ---- サマリ ---- */
console.log(`\nE2E ${stage}: ${fails === 0 ? 'ALL PASS' : 'FAILED'} (checks=${checks}, fails=${fails})`);
writeFileSync(path.join(WORK, 'e2e_summary.json'), JSON.stringify({ stage, checks, fails, ...results }, null, 1));
process.exit(fails === 0 ? 0 : 1);
