/* responder_worker.mjs — ctrl 要求リングのホスト側排水 (別スレッド)。
 * 「C がリングに要求を書き、ホスト (JS) が排水して戻す」のホスト側。
 * 要求リングの Vyukov pop を JS で実装し (C 側 pctrl_push と対)、応答メールボックスに
 * req_id 照合で書き戻して notify する。 */
import { parentPort, workerData } from 'node:worker_threads';

const { sab, reqAddr, respAddr } = workerData;
const i32 = new Int32Array(sab);
const f64 = new Float64Array(sab);

/* 要求スロット: 8×i32 = [seq, op, a0, a1, req_id, pad, t_req(f64)] */
const R_SEQ = 0, R_OP = 1, R_A0 = 2, R_A1 = 3, R_REQID = 4, R_TREQ_F64 = 6;
/* 応答: 8×i32 = [seq, req_id, ret0, ret1, pad, pad, t_resp(f64)] */
const P_SEQ = 0, P_REQID = 1, P_RET_F64 = 2, P_TRESP_F64 = 6;

const HDR_ENQ = 0, HDR_DEQ = 1, HDR_WAKE = 2, HDR_CAP = 3;
const CAP = i32[(reqAddr >> 2) + HDR_CAP];

function popReq() {
    const base = reqAddr >> 2;
    for (;;) {
        const pos = Atomics.load(i32, base + HDR_DEQ);
        const slot = base + 16 + (pos % CAP) * 8;   // ヘッダ16語 + スロット8語×(pos % CAP)
        const seq = Atomics.load(i32, slot + R_SEQ);
        if (((seq - (pos + 1)) | 0) !== 0) return null;
        const rec = {
            op: Atomics.load(i32, slot + R_OP),
            a0: Atomics.load(i32, slot + R_A0) >>> 0,
            a1: Atomics.load(i32, slot + R_A1) >>> 0,
            reqId: Atomics.load(i32, slot + R_REQID) >>> 0,
            tReq: f64[slot / 2 + R_TREQ_F64 / 2],   // i32 語 → f64 語
        };
        Atomics.store(i32, slot + R_SEQ, pos + CAP);
        Atomics.store(i32, base + HDR_DEQ, pos + 1);
        return rec;
    }
}

function writeResp(rec, ret) {
    const w = respAddr >> 2;        // i32 語
    const f = respAddr / 8;         // f64 語 (8B アライン)
    const seq = Atomics.load(i32, w);
    Atomics.store(i32, w + P_REQID, rec.reqId | 0);
    f64[f + P_RET_F64 / 2] = ret;               // ワード 2..3
    f64[f + P_TRESP_F64 / 2] = performance.timeOrigin + performance.now();  // ワード 6..7
    Atomics.store(i32, w + P_SEQ, seq + 1);
    Atomics.notify(i32, w + P_SEQ, 1);
}

let served = 0;
let running = true;
parentPort.on('message', (m) => { if (m?.t === 'stop') running = false; });

function drainOnce() {
    const rec = popReq();
    if (!rec) return false;
    let ret = 0;
    switch (rec.op) {
        case 2: ret = performance.timeOrigin + performance.now(); break;  // EPOCH_NOW
        case 3: ret = rec.a0; break;                                       // ECHO
        default: ret = 0;
    }
    writeResp(rec, ret);
    served++;
    return true;
}

function loop() {
    try {
        if (!running) { parentPort.postMessage({ t: 'done', served }); return; }
        let any = false;
        for (let i = 0; i < 64; i++) any = drainOnce() || any;
        setTimeout(loop, any ? 0 : 0.5);   // 0.5ms 周期の排水 (futex 待ちの C 側と並走)
    } catch (e) {
        parentPort.postMessage({ t: 'loop-error', message: String(e && e.stack || e) });
    }
}
loop();
parentPort.postMessage({ t: 'ready', capacity: CAP });
