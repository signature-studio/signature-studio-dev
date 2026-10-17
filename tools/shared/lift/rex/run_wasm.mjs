// lift 済み rex.wasm で cases.bin を実行し、native_ref.c と同一形式の res_wasm.bin を書く。
// usage: node run_wasm.mjs <workdir>      env REX_NEG=ctx で wasm 側だけ ctx 大域を 0 にする (ネガティブコントロール)
// REX_RUN_CRASHED=1 で元の機械語が落ちた case も wasm で実行する。wasm は同期実行で途中から止められないため、
// case ごとの worker (本ファイルを worker_threads で再読込) で走らせ、REX_CASE_MS (既定 2000ms) を超えて戻らない case は
// 時間切れとして捨て (timeout.txt に記録)、次の case から worker を作り直して続ける。元の機械語は native_ref.c で 300ms で打ち切る。
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";
import { readFileSync, writeFileSync } from "node:fs";

const NEG = process.env.REX_NEG || "";
const RUN_CRASHED = process.env.REX_RUN_CRASHED === "1";   // 1 = 元の機械語が落ちた case も wasm で実行する (movnti 到達の実測用)

if (isMainThread) {
  const W = process.argv[2];
  const CASE_MS = Number(process.env.REX_CASE_MS || 2000);
  const L = JSON.parse(readFileSync(`${W}/layout.json`, "utf8"));
  const ncase = readFileSync(`${W}/cases.bin`).readUInt32LE(0);
  const REC = 16 + L.arena_sz + L.data_sz;
  const recs = new Array(ncase).fill(null);
  const trapLines = [], trapKinds = [], timeoutLines = [];
  let traps = 0;

  const runFrom = (start) => new Promise((resolve, reject) => {
    const w = new Worker(new URL(import.meta.url), { workerData: { W, start, runCrashed: RUN_CRASHED, neg: NEG } });
    let timer = null, done = false, cur = -1;
    const finish = (fn, v) => { if (done) return; done = true; clearTimeout(timer); fn(v); };
    w.on("message", (m) => {
      if (m.type === "start") {
        cur = m.c;
        clearTimeout(timer);
        timer = setTimeout(() => {
          recs[cur] = Buffer.alloc(REC);
          recs[cur].writeBigUInt64LE(0xdeadn, 0); recs[cur].writeBigUInt64LE(0xdeadn, 8);
          timeoutLines.push(`${cur}`);
          w.terminate();
          finish(resolve, cur + 1);
        }, CASE_MS);
      } else if (m.type === "done") {
        clearTimeout(timer);
        recs[m.c] = Buffer.from(m.rec);
        if (m.trap !== null) { traps++; trapLines.push(`${m.c} ${m.trap}`); trapKinds.push(`${m.c} ${m.kind}`); }
      } else if (m.type === "end") {
        finish(resolve, ncase);
      }
    });
    w.on("error", (e) => finish(reject, e));
    w.on("exit", () => finish(reject, new Error(`run_wasm worker exited early (start=${start})`)));
  });

  let start = 0;
  while (start < ncase) start = await runFrom(start);

  const missing = recs.findIndex((r) => r === null);
  if (missing >= 0) throw new Error(`run_wasm: case ${missing} の結果が無い`);
  writeFileSync(`${W}/res_wasm.bin`, Buffer.concat(recs));
  writeFileSync(`${W}/trap.txt`, trapLines.map((l) => l + "\n").join(""));
  writeFileSync(`${W}/trap_kind.txt`, trapKinds.map((l) => l + "\n").join(""));   // 種類 (VA が 0 の trap の原因。境界外・未対応命令など)
  writeFileSync(`${W}/timeout.txt`, timeoutLines.map((l) => l + "\n").join(""));
  console.log(`[run_wasm] cases=${ncase} traps=${traps} timeouts=${timeoutLines.length} neg=${NEG || "none"}`);
} else {
  const { W, start, runCrashed, neg } = workerData;
  const L = JSON.parse(readFileSync(`${W}/layout.json`, "utf8"));
  const BASE = L.base, ARENA = L.arena, ARENA_SZ = L.arena_sz, CTX = BASE + L.ctx_rva;
  const DATA = BASE + L.data_rva, DATA_SZ = L.data_sz;
  const EXP = [BASE + L.exp_creator_rva, BASE + L.exp_info_rva];
  const img = readFileSync(`${W}/image_wasm.bin`);
  const DLLMAIN = process.env.REX_DLLMAIN === "1";   // 1 = DllMain(reason=1) を 1 回実行した後の image を基準にする (native_ref.c と同じ手順)
  const cases = readFileSync(`${W}/cases.bin`);
  const nat = readFileSync(`${W}/res_native.bin`);
  // WASI 呼出 (libc の stdio 等) は使わない想定。念のため未実装の import は 0 を返す (値は比較に影響しない)。
  // fd_write は書いた長さを返す (0 を返すと stdio が書込を繰り返して止まる)。trap 前の fprintf(stderr) の文字列は stderr に流す。
  const wasi = new Proxy({}, { get: (_, name) => name !== "fd_write" ? () => 0 : (fd, iovs, n, nwritten) => {
    const dv = new DataView(ex.memory.buffer), mem = new Uint8Array(ex.memory.buffer);
    let tot = 0;
    for (let i = 0; i < n; i++) {
      const p = dv.getUint32(iovs + 8 * i, true), len = dv.getUint32(iovs + 8 * i + 4, true);
      if (fd === 2) process.stderr.write(Buffer.from(mem.subarray(p, p + len)));
      tot += len;
    }
    dv.setUint32(nwritten, tot, true);
    return 0;
  } });
  const inst = await WebAssembly.instantiate(await WebAssembly.compile(readFileSync(`${W}/rex.wasm`)), { wasi_snapshot_preview1: wasi, env: wasi });
  const ex = inst.exports;
  // trap の JS スタックの最内側 lift 関数名 (rex.wasm は --profiling-funcs で名前付き: f_<VA>) から VA を取る。名前が無ければ 0。
  const wasmTrapVA = (e) => { const m = /\bf_([0-9a-f]+) \(/.exec(String(e && e.stack)); return m ? m[1] : "0"; };
  const REC = 16 + ARENA_SZ + DATA_SZ;
  if (DLLMAIN) {
    const mem0 = new Uint8Array(ex.memory.buffer);
    mem0.set(img, BASE);
    ex.rex_reset();
    ex.rex_run(BASE + L.dllmain_rva, BigInt(BASE), 1n, 0n, 0n);   // DllMain(hinst=BASE, reason=1, reserved=0, 0)
    const m0 = new Uint8Array(ex.memory.buffer);
    img.set(m0.subarray(BASE, BASE + img.length));   // 以後の case は DllMain 後の image から始める
  }
  const dv = new DataView(cases.buffer, cases.byteOffset, cases.byteLength);
  let p = 0;
  const ncase = dv.getUint32(p, true); p += 4;
  for (let c = 0; c < ncase; c++) {
    const fn = dv.getUint32(p, true); p += 8;
    const natMark = nat.readBigUInt64LE(c * REC) === 0xC2A5C2A5C2A5C2A5n;
    const a0 = dv.getBigUint64(p, true), a1 = dv.getBigUint64(p + 8, true);
    const a2 = dv.getBigUint64(p + 16, true), a3 = dv.getBigUint64(p + 24, true);
    p += 32;
    const ctx = dv.getBigUint64(p, true); p += 8;
    const arena = cases.subarray(p, p + ARENA_SZ); p += ARENA_SZ;
    if (c < start) continue;
    if (natMark && !runCrashed) { parentPort.postMessage({ type: "done", c, rec: Buffer.from(nat.subarray(c * REC, (c + 1) * REC)), trap: null }); continue; }   // 元の機械語が落ちた case は実行しない (比較対象外)
    parentPort.postMessage({ type: "start", c });
    const mem = new Uint8Array(ex.memory.buffer);
    const mdv = new DataView(ex.memory.buffer);
    mem.set(img, BASE);
    mem.set(arena, ARENA);
    mdv.setBigUint64(CTX, neg === "ctx" ? 0n : ctx, true);
    ex.rex_reset();
    let rax, hits, trap = null, kind = "";
    try {
      rax = ex.rex_run(EXP[fn], a0, a1, a2, a3);
      hits = ex.rex_hits_get();
    } catch (e) {
      trap = ex.rex_unsup_get().toString(16);   // trap した case と未対応命令の VA (movnti_check.py が読む)。境界外等の wasm trap は 0
      kind = String(e && e.message).replace(/\s+/g, " ");
      if (trap === "0") trap = wasmTrapVA(e);   // 境界外等: 最内側の lift 関数 (f_<VA>) の入口 VA (wasm の name section 由来)
      else kind = `unsup 0x${trap}`;   // 未対応命令 (ott_unsup) の trap は、境界外等・他の unreachable と区別して VA ごと記録する
      rax = 0xdeadn; hits = 0xdeadn;
    }
    const head = Buffer.alloc(16);
    head.writeBigUInt64LE(BigInt(rax), 0);
    head.writeBigUInt64LE(BigInt(hits), 8);
    const m2 = new Uint8Array(ex.memory.buffer);
    const rec = Buffer.concat([head, Buffer.from(m2.slice(ARENA, ARENA + ARENA_SZ)), Buffer.from(m2.slice(DATA, DATA + DATA_SZ))]);
    parentPort.postMessage({ type: "done", c, rec, trap, kind });
  }
  parentPort.postMessage({ type: "end" });
}
