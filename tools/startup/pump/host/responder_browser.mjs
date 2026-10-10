/* responder_browser.mjs — ctrl 要求リングのホスト側排水 (ブラウザ Worker 版)。
 * node 版 (responder_worker.mjs) と同一プロトコル。init を postMessage で受ける。 */
let i32, f64, reqAddr, respAddr, CAP;
let served = 0, running = true;

const R_SEQ = 0, R_OP = 1, R_A0 = 2, R_REQID = 4, R_TREQ = 6;   // i32 語
const P_SEQ = 0, P_REQID = 1, P_RET = 2, P_TRESP = 6;
const HDR_DEQ = 1;

function popReq() {
    const base = reqAddr >> 2;
    const pos = Atomics.load(i32, base + HDR_DEQ);
    const slot = base + 16 + (pos % CAP) * 8;
    const seq = Atomics.load(i32, slot + R_SEQ);
    if (((seq - (pos + 1)) | 0) !== 0) return null;
    const rec = {
        op: Atomics.load(i32, slot + R_OP),
        a0: Atomics.load(i32, slot + R_A0) >>> 0,
        reqId: Atomics.load(i32, slot + R_REQID) >>> 0,
    };
    Atomics.store(i32, slot + R_SEQ, pos + CAP);
    Atomics.store(i32, base + HDR_DEQ, pos + 1);
    return rec;
}

function writeResp(rec, ret) {
    const w = respAddr >> 2, f = respAddr / 8;
    const seq = Atomics.load(i32, w + P_SEQ);
    Atomics.store(i32, w + P_REQID, rec.reqId | 0);
    f64[f + P_RET / 2] = ret;
    f64[f + P_TRESP / 2] = performance.timeOrigin + performance.now();
    Atomics.store(i32, w + P_SEQ, seq + 1);
    Atomics.notify(i32, w + P_SEQ, 1);
}

function drainOnce() {
    const rec = popReq();
    if (!rec) return false;
    writeResp(rec, rec.op === 2 ? performance.timeOrigin + performance.now() : rec.a0);
    served++;
    return true;
}

function loop() {
    if (!running) return;
    let any = false;
    for (let i = 0; i < 64; i++) any = drainOnce() || any;
    setTimeout(loop, any ? 0 : 0.5);
}

self.onmessage = ({ data }) => {
    if (data.t !== 'init') return;
    reqAddr = data.reqAddr;
    respAddr = data.respAddr;
    i32 = new Int32Array(data.sab);
    f64 = new Float64Array(data.sab);
    CAP = i32[(reqAddr >> 2) + 3];
    loop();
    self.postMessage({ t: 'ready', capacity: CAP });
};
