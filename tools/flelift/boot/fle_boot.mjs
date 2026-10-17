// fle_boot.mjs — FLE-2 boot runner: x64c lift (fleboot.cjs) で DllMain attach 連鎖を実行し
// boot / unit#18 / survey (942) の実測を JSON に出す。
//
//   node fle_boot.mjs <boot.cjs> <out.json> [--boot-only] [--survey] [--trace]
//
// 注意: survey を同じプロセスで通しで回すと unit i=283 が状態依存 hang する (FLE-2 実測:
// survey_drive.sh の seg_0 が 180s timeout、seg_283 の隔離実行では oob で即終了)。
// survey は survey_drive.sh (セグメント + 再開 + merge_survey.py) を使うこと。
//
// 分類: ok / oob (memory access out of bounds) / trap (その他 RuntimeError) /
//       halt0 (longjmp 計数が増えた = Halt0→RestoreContext 経路) / exit (ExitProcess) /
//       soft (strict 時の未実装 import) / unlifted / missing / badjump / unsup / empty / noproc
import { writeFileSync, readFileSync, mkdirSync, appendFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { basename } from 'node:path';

const cjs = process.argv[2];
const outPath = process.argv[3] || 'work/boot/boot_summary.json';
const BOOT_ONLY = process.argv.includes('--boot-only');
const SURVEY = process.argv.includes('--survey') || !BOOT_ONLY;
const TRACE = process.env.FLE_BOOT_TRACE === '1';

// FLE-15 (#3770): 有界実行。FLE_BOOT_LOG_CAP (bytes・既定 0 = 無効) を超えた console 出力 (stdout/stderr) で
// 例外を投げ、boot を抜けて結果 JSON を出す (診断 route は反復出力で 20GB 級になるため #3491)。
// 停止は boot 内の JS 例外 (fle_throw_kind と同じ経路)。時間上限は fle6_measure.sh の timeout が担う。
// FLE_BOOT_TIME_CAP (秒・既定 0 = 無効): 出力の度に経過を見て、超えたら同じ経路で抜ける (出力が途切れない反復の打ち切り)。
// FLE_BOOT_QUIET_BIN=1: U+FFFD・制御文字を含む行 (ガストの生バイト列の反復) は表示せず数えるだけにし、上限の計数に入れない。
const LOG_CAP = Number(process.env.FLE_BOOT_LOG_CAP || 0);
const TIME_CAP = Number(process.env.FLE_BOOT_TIME_CAP || 0);
const QUIET_BIN = process.env.FLE_BOOT_QUIET_BIN === '1';
const LOG_T0 = Date.now();
const logCap = { cap: LOG_CAP, time_cap_s: TIME_CAP, quiet_bin: QUIET_BIN, bytes: 0, lines: 0, bin_lines: 0, bin_bytes: 0, hit: null, elapsed_ms: null, head: [], tail: [] };
if (LOG_CAP > 0 || TIME_CAP > 0) {
    for (const k of ['log', 'error']) {
        const orig = console[k].bind(console);
        console[k] = (...a) => {
            const s = a.map(String).join(' ');
            const el = Date.now() - LOG_T0;
            if (!logCap.hit && TIME_CAP > 0 && el > TIME_CAP * 1000) {
                logCap.hit = 'time'; logCap.elapsed_ms = el;
                throw new Error('FLE_BOOT_LOG_CAP exceeded (time ' + TIME_CAP + ' s)');
            }
            const bin = /\uFFFD|[\x00-\x08\x0e-\x1f]/.test(s);
            if (QUIET_BIN && bin) { logCap.bin_lines++; logCap.bin_bytes += Buffer.byteLength(s) + 1; return; }
            logCap.bytes += Buffer.byteLength(s) + 1; logCap.lines++;
            if (logCap.head.length < 40) logCap.head.push(s.slice(0, 240));
            logCap.tail.push(s.slice(0, 240)); if (logCap.tail.length > 40) logCap.tail.shift();
            if (!logCap.hit && LOG_CAP > 0 && logCap.bytes > LOG_CAP) {
                logCap.hit = 'bytes'; logCap.elapsed_ms = el;
                // #5027: この throw は Emscripten の tty write (FS) が EIO に変換して飲むため boot を止めない。
                // #5058: 代わりに guest の次の dispatch (fle_probe_dispatch) で log_cap の例外を投げて止める。
                globalThis.FLE_LOG_CAP_HIT = 1;
                throw new Error('FLE_BOOT_LOG_CAP exceeded (' + LOG_CAP + ' bytes)');
            }
            orig(...a);
        };
    }
}

const mod = await import(cjs);
let m = await (mod.default ? mod.default() : mod());
const U8 = m.HEAPU8;

if (TRACE) { try { m._shimx_set_trace(1); } catch { /* nosx では未 export */ } }
// FLE-6: dsp_ippv2 shim の mode。FLE_IPP=0 (ネガコン) / 1 (shim 有) / 2 (#2702: shim 有 + ippsZero_8u 以外で停止) / 3 (ILTools 分岐入力)。
// 未指定・空 = 既定 3 (#672 PM 判断 2026-10-15: ILT 分岐入力を既定化。ネガコンは FLE_IPP=0 を明示する)。
const IPP_MODE = (process.env.FLE_IPP === undefined || process.env.FLE_IPP === '') ? 3 : ({ '1': 1, '2': 2, '3': 3 }[process.env.FLE_IPP] || 0);
const IPP_ON = IPP_MODE !== 0;
m._fle_boot_set_ipp(IPP_MODE);
// FLE-672 診断: FLE_DIAG_NULLFILL=1 は root 無しの fill (0x6a7b70) で buf = 0 の呼出しを戻す。未指定は従来どおり停止する。
const DIAG_NULLFILL = process.env.FLE_DIAG_NULLFILL === '1';
m._fle_boot_set_diag_nullfill(DIAG_NULLFILL ? 1 : 0);

const MM = 0x13a5c90, PKG = 0x13768b0;
function rd64(a) { return '0x' + U8.slice(a, a + 8).reduce((s, b, i) => s + BigInt(b) * (1n << BigInt(8 * i)), 0n).toString(16); }
function mmTable() { return { getmem: rd64(MM), freemem: rd64(MM + 8), realloc: rd64(MM + 16), slot3: rd64(MM + 24) }; }

function classify(e) {
    if (e && e.fle_kind) {
        if (e.fle_kind === 'exit') return { cls: 'exit', code: e.fle_a };
        if (e.fle_kind === 'soft') return { cls: 'soft', name: e.name };
        return { cls: e.fle_kind, target: e.fle_a };   // unlifted / badjump / unsup / <import名>
    }
    const s = String(e && e.message || e);
    if (/out of bounds/.test(s)) return { cls: 'oob', msg: s.slice(0, 160) };
    if (/FLE_BOOT_LOG_CAP/.test(s)) return { cls: 'log_cap', msg: s.slice(0, 160) };
    return { cls: 'trap', msg: s.slice(0, 160) };
}

// ---------------- 寛容起動 (#2719, m11 WIN-3 相当) ----------------
// FLE_TOLERANT=1: InitUnits を逐次ループ (fle_tolerant_run) に渡す (C 側 g_tolerant)。unit ごとに try/catch で隔離し、
// 失敗 (例外・longjmp) は skipped と記録して次へ進む。trap 後は C stack と guest RSP を戻す。image は戻さない (状態は unit 間で持ち越す)。
// FLE_TOLERANT=2 は診断用: 失敗 unit の後で InitTable (ヘッダと units 配列) を起動時の値へ戻す (状態の補修。既定ではない)。
const TOL_MODE = { '1': 1, '2': 2 }[process.env.FLE_TOLERANT] || 0;
const TOLERANT = TOL_MODE !== 0;
const SKIP_KINDS = new Set(['halt0', 'oob', 'trap', 'unlifted', 'badjump', 'unsup', 'exit', 'raise', 'soft', 'clobber']);
m._fle_boot_set_tolerant(TOLERANT ? 1 : 0);
const tol = { on: TOL_MODE, started: 0, hook_ran: false, kinds: {}, skipped: [], miss_units: [], units: [], restored: 0 };
if (TOLERANT) m.fle_tolerant_run = () => {
    tol.hook_ran = true;
    const count = Number(m._fle_units_total());
    const cstk = Number(m._emscripten_stack_get_current());
    const rsp0 = Number(m._fle_rsp_get());
    // InitContext (0x15eac90 の InitTable ポインタ 16B) と InitTable (ヘッダ 16B・units 配列) の起動時の値。unit の後で proc が 0 に変わったら clobber (m11 の clobber と同じ判定)
    const tblP = m.HEAPU32[0x15eac90 >>> 2], unitsP = m.HEAPU32[(tblP + 8) >>> 2];
    const ctxSnap = U8.slice(0x15eac90, 0x15eac90 + 16), tblSnap = U8.slice(tblP, tblP + 16), unitsSnap = U8.slice(unitsP, unitsP + 16 * count);
    const procs0 = []; for (let i = 0; i < count; i++) procs0.push(Number(m._fle_unit_proc(i)));
    const heads0 = procs0.map((p) => (p ? U8.slice(p, p + 8) : null));   // unit proc 先頭 8B (empty 判定の textwin 値)
    for (let i = 0; i < count; i++) {
        tol.started++;
        const proc = Number(m._fle_unit_proc(i));
        const lj0 = Number(m._fle_n_longjmp()), d0 = Number(m._fle_n_disp0());
        const gm0 = Number(m._fle_n_getmem()), fm0 = Number(m._fle_n_freemem());
        let r = null, err = null;
        try { r = Number(m._fle_call_unit_at(i)); } catch (e) { err = e; }
        m.__emscripten_stack_restore(cstk);
        m._fle_rsp_set(rsp0);
        const lj = Number(m._fle_n_longjmp()) - lj0, dsp0 = Number(m._fle_n_disp0()) - d0;
        const rec = { i, va: '0x' + proc.toString(16) };
        let kind;
        if (err) {
            const c = classify(err);
            kind = c.cls;
            if (c.target !== undefined) rec.target = '0x' + (Number(c.target) >>> 0).toString(16);
            if (c.code !== undefined) rec.code = c.code;
            if (c.msg) rec.msg = c.msg.slice(0, 120);
        } else if (r === 0) kind = procs0[i] ? 'clobber' : 'noproc';   // 起動時は proc があったのに 0 → 直前の unit が units 配列を壊した
        else if (r === 1) kind = 'empty';
        else if (lj > 0) kind = 'halt0';
        else kind = 'ok';
        if (dsp0 > 0 && !err) tol.miss_units.push([i, dsp0]);   // dispatch(0) で fail-soft に戻った unit (silent miscompile の候補)
        tol.kinds[kind] = (tol.kinds[kind] || 0) + 1;
        if (SKIP_KINDS.has(kind)) { rec.kind = kind; rec.gm = Number(m._fle_n_getmem()) - gm0; rec.fm = Number(m._fle_n_freemem()) - fm0; tol.skipped.push(rec); }
        tol.units.push([i, kind, rec.va, Number(m._fle_n_getmem()) - gm0, Number(m._fle_n_freemem()) - fm0, dsp0]);
        if (TOL_MODE === 2 && SKIP_KINDS.has(kind)) {
            U8.set(ctxSnap, 0x15eac90); U8.set(tblSnap, tblP); U8.set(unitsSnap, unitsP);
            for (let k = 0; k < count; k++) if (heads0[k]) U8.set(heads0[k], procs0[k]);
            tol.restored++;
        }
    }
};

// ---------------- boot phase ----------------
const before = { mm: mmTable(), units_arr_ptr: rd64(PKG + 8), count: m.HEAPU32[PKG / 4] };
let boot = { rc: null, threw: null, units_run: 0, units_total: 0, units_empty: 0, rax: null, longjmp: 0 };
try {
    m._fle_boot_enter(0);
    boot.rc = 'returned';
} catch (e) {
    boot.threw = classify(e);
    if (e && e.stack) boot.threw.stack = e.stack.split('\n').slice(0, 6).join('\n');
}
// #5027: cap 超過 (logCap.hit) の後も guest は走り続け、boot の停止理由は cap の例外ではなく後続の exit になる
// (cap の throw は Emscripten の tty write が EIO に変換して飲む)。上限超過は log_cap として報告し、生の停止理由は threw_raw に残す。
// #5058: 停止は fle_probe_dispatch が投げる log_cap で行うので、cls が log_cap の場合は包み直さない (threw_raw は無し)。
if (logCap.hit === 'bytes' && boot.threw && boot.threw.cls !== 'log_cap') {
    boot.threw_raw = boot.threw;
    boot.threw = { cls: 'log_cap', msg: 'FLE_BOOT_LOG_CAP exceeded (' + LOG_CAP + ' bytes); raw=' + boot.threw.cls };
} else if (logCap.hit === 'bytes' && !boot.threw) {
    boot.threw = { cls: 'log_cap', msg: 'FLE_BOOT_LOG_CAP exceeded (' + LOG_CAP + ' bytes); raw=returned' };
}
boot.units_run = Number(m._fle_units_run()); boot.units_total = Number(m._fle_units_total()); boot.units_empty = Number(m._fle_units_empty());
boot.longjmp = Number(m._fle_n_longjmp());
const r0 = m._fle_rget(0);
boot.rax = '0x' + BigInt.asUintN(64, typeof r0 === 'bigint' ? r0 : BigInt(r0)).toString(16);
boot.stage = Number(m._fle_boot_stage());
boot.diag_nullfill = { on: DIAG_NULLFILL, skip: Number(m._fle_diag_skip_n()), pass: Number(m._fle_diag_pass_n()) };
boot.getmem = Number(m._fle_n_getmem()); boot.freemem = Number(m._fle_n_freemem());
boot.va_calls = Number(m._fle_va_calls()); boot.va_bytes = Number(m._fle_va_bytes());
boot.getproc = Number(m._fle_n_getproc()); boot.exit = Number(m._fle_n_exit());
boot.cb_calls = Number(m._fle_n_cb()); boot.soft_calls = Number(m._fle_n_soft()); boot.soft_uniq = Number(m._fle_n_soft_uniq());
boot.mm_after = mmTable();
// PY-123 (#3028): boot 停止時点の undo 管理オブジェクトと安全判定の実行時値 (guest VA = wasm アドレス)
const UNDO_MGR_SLOT = 0x15e1c78, UNDO_RET_SINGLETON = 0x16b82e0, UNDO_SAFE_GLOBAL = 0x15e4790;
const undoProbe = (() => {
    const dv = new DataView(m.HEAPU8.buffer);
    const inb = (a) => a >= 0n && a + 8n <= BigInt(U8.length);
    const u64 = (a) => (inb(a) ? dv.getBigUint64(Number(a), true) : null);
    const u32 = (a) => (inb(a) ? dv.getUint32(Number(a), true) : null);
    const hx = (v) => (v === null ? null : '0x' + v.toString(16));
    const mgr = u64(BigInt(UNDO_MGR_SLOT));
    const safeGlobal = u64(BigInt(UNDO_SAFE_GLOBAL));
    const safeObj = safeGlobal === null ? null : u64(safeGlobal + 8n);
    const mgrOk = mgr !== null && mgr !== 0n;
    const safeOk = safeObj !== null && safeObj !== 0n;
    return {
        slot_0x15e1c78: hx(mgr),
        pos_0x20: mgrOk ? u32(mgr + 0x20n) : null,
        count_0x24: mgrOk ? u32(mgr + 0x24n) : null,
        ret_singleton_0x16b82e0: hx(u64(BigInt(UNDO_RET_SINGLETON))),
        slot_0x15e4790: hx(safeGlobal),
        safe_obj: hx(safeObj),
        safe_obj_0x98: safeOk ? hx(u64(safeObj + 0x98n)) : null,
        safe_obj_0x88: safeOk ? hx(u64(safeObj + 0x88n)) : null,
    };
})();
boot.undo_probe = undoProbe;
// PY-123 (#3028): 監視 slot の変化点 (fle_boot.c の py_watch・40 B/件)。site: 0=fle_run 直前 1=unit 前 2=unit 後 3=memset 後
const pyEvents = (() => {
    const n = Number(m._fle_py_ev_n()), p = Number(m._fle_py_ev_ptr());
    const dv = new DataView(m.HEAPU8.buffer);
    const hx = (v) => '0x' + v.toString(16);
    const out = [];
    for (let i = 0; i < n; i++) {
        const b = p + 40 * i;
        out.push({
            unit: dv.getUint32(b, true), site: dv.getUint32(b + 4, true),
            slot: hx(dv.getUint32(b + 8, true)), proc: hx(dv.getUint32(b + 12, true)),
            old: hx(dv.getBigUint64(b + 16, true)), new: hx(dv.getBigUint64(b + 24, true)), aux: hx(dv.getBigUint64(b + 32, true)),
        });
    }
    return { n, over: Number(m._fle_py_ev_over()), events: out };
})();
boot.py_events = pyEvents;
console.log('FLEBOOT_PY123 ' + JSON.stringify(pyEvents));
// PY-201 (#3028): unit dispatch 直前の undo 状態 (fle_boot.c の py_snap_undo・64 B/件)。last = 最後に記録した unit 直前、trace = 値が変わった unit
const pySnap = (() => {
    const dv = new DataView(m.HEAPU8.buffer);
    const hx = (v) => '0x' + v.toString(16);
    const rd = (b) => ({
        unit: dv.getUint32(b, true), pos: dv.getUint32(b + 4, true), count: dv.getUint32(b + 8, true),
        mgr: hx(dv.getBigUint64(b + 16, true)), safe_g: hx(dv.getBigUint64(b + 24, true)),
        safe_obj: hx(dv.getBigUint64(b + 32, true)), f98: hx(dv.getBigUint64(b + 40, true)),
        f88: hx(dv.getBigUint64(b + 48, true)), sing: hx(dv.getBigUint64(b + 56, true)),
    });
    const last = rd(Number(m._fle_py_snap_last_ptr()));
    const n = Number(m._fle_py_snap_trace_n()), p = Number(m._fle_py_snap_trace_ptr());
    const trace = [];
    for (let i = 0; i < n; i++) trace.push(rd(p + 64 * i));
    return { last, trace, over: Number(m._fle_py_snap_trace_over()) };
})();
boot.py_snap = pySnap;
console.log('FLEBOOT_PY201 ' + JSON.stringify(pySnap));
// PY-106 (#2909): 例外型の参照。sink 0xd82daf は rcx = M[M[M[0x15e1140]]] を PyErr_SetString の型に使う (PE の逆アセンブル)
const pyExcProbe = (() => {
    const u64 = (a) => (a + 8 <= m.HEAPU8.length ? new DataView(m.HEAPU8.buffer).getBigUint64(a, true) : null);
    const hx = (v) => (v === null || v === undefined ? null : '0x' + v.toString(16));
    const a1 = u64(0x15e1140);
    const slot = a1 ? u64(Number(a1)) : null;
    const excType = slot ? u64(Number(slot)) : null;
    return { chain_0x15e1140: hx(a1), slot_0x16b8488: hx(slot), exc_type: hx(excType), bind_0x16b8250: hx(u64(0x16b8250)) };
})();
console.log('FLEBOOT_PY106 ' + JSON.stringify(pyExcProbe));
// FLE-6: dsp_ippv2 GetProcAddress 結果 (0x15F34A0 = ippsZero_8u の登録値) と IPP 呼出の証跡
boot.ipp_ptr_15F34A0 = rd64(0x15F34A0);
boot.ipp_ptr_15F40E8 = rd64(0x15F40E8);
boot.ipp_total = Number(m._fle_ipp_total());
boot.ipp_called = [];
for (let i = 0; i < Number(m._fle_ipp_names()); i++) {
    const c = Number(m._fle_ipp_count(i));
    if (c) boot.ipp_called.push([m.UTF8ToString(m._fle_ipp_name(i)), c, '0x' + Number(m._fle_ipp_site(i)).toString(16)]);
}
// ippsZero_8u の呼出し点は 0x67264b (`call qword ptr [rax]`・FF 10) と 0x6b91e8 の 2 つ (付録 REPORT_APPENDIX_4004.md §2)。target は直前の 0x672644 `mov rax,[0x15e0a48]` で読む (PE の逆アセンブル実測)。0x67264d は戻り番地 (ipp.called の ret)。読出し経路の値を残す
const objPtr = Number(BigInt(rd64(0x15e0a48)));
boot.ipp_call_slot = { slot_15e0a48: rd64(0x15e0a48), obj_first_qword: objPtr ? rd64(objPtr) : null };
const stopNm = m.UTF8ToString(m._fle_ipp_stop_name());
boot.ipp_stop = stopNm ? { name: stopNm, site: '0x' + Number(m._fle_ipp_stop_site()).toString(16) } : null;
// IPP トークン (0x7F100000+i) が guest メモリのどこに書かれたか (0x15F34A0 が 0 のときの所在確認。image 域のみ走査)
boot.ipp_token_at = [];
for (let i = 0; i < Number(m._fle_ipp_names()); i++) {
    if (!Number(m._fle_ipp_count(i))) continue;
    const tok = 0x7F100000 + i, hits = [];
    for (let a = 0x400000 >>> 2; a < 0x2000000 >>> 2 && hits.length < 4; a++) {
        if (m.HEAPU32[a] === tok) hits.push('0x' + (a * 4).toString(16));
    }
    boot.ipp_token_at.push([m.UTF8ToString(m._fle_ipp_name(i)), hits]);
}
// unit 番号 = units_run は「dispatch した unit 数」(開始で計数、完了でない)。
// raise 等で中断した場合、実行中 (未完走) なのは units_run 番目 (1-based) の unit。
// FLE-2 実測: units_run=17 → i=16 proc 0x454090 の body 内で FreeMem 失敗 raise
// (guest stack 復元で確認、dbg_u18.mjs 参照)。unit#18 (0x455790) は未到達。
boot.stopped_at_1based = boot.units_run;

// PERF-P22 (#3330): boot 停止時点の出力メモリ (wasm 線形メモリ) の sha256。計数・ipp 状態とは別の値で、summary のトップレベル outmem に出す (boot の外。boot+ipp の署名 (variant_boot.sh) に入れないため)。
// (a) full = 線形メモリ全体。(b) no_cstack = 全体から emscripten の C スタック [end, base) を除いた範囲
// (スタックの残骸は C の最適化水準に依る一時値なので、変種間比較からは外す)。
// (c) PE の書込み可能セクション (IMAGE_SCN_MEM_WRITE) を 1 本ずつ (guest 側の状態そのもの)。
// FLE_OUTMEM_DUMP=<dir> のとき、線形メモリ全体を <dir>/outmem_<variant>.bin に書く (別算法 (sha256sum) での検算用)。
const outMem = (() => {
    const H = m.HEAPU8, len = H.length;
    const sha = (parts) => { const h = createHash('sha256'); for (const [a, b] of parts) if (b > a) h.update(H.subarray(a, b)); return h.digest('hex'); };
    const stBase = Number(m._emscripten_stack_get_base() >>> 0), stEnd = Number(m._emscripten_stack_get_end() >>> 0);
    const res = { mem_bytes: len, stack: { base: '0x' + stBase.toString(16), end: '0x' + stEnd.toString(16) },
        full: sha([[0, len]]), no_cstack: sha([[0, stEnd], [stBase, len]]), sections: {} };
    const IMG = 0x400000;
    const dv = new DataView(H.buffer);
    if (H[IMG] === 0x4d && H[IMG + 1] === 0x5a) {
        const pe = IMG + dv.getUint32(IMG + 0x3c, true), nsec = dv.getUint16(pe + 6, true);
        const optSz = dv.getUint16(pe + 20, true), secTab = pe + 24 + optSz;
        const ranges = [];
        for (let i = 0; i < nsec; i++) {
            const s = secTab + 40 * i;
            const name = String.fromCharCode(...H.subarray(s, s + 8)).replace(/\0.*$/, '');
            const vsz = dv.getUint32(s + 8, true), va = dv.getUint32(s + 12, true), chr = dv.getUint32(s + 36, true);
            if (!(chr & 0x80000000)) continue;
            res.sections[name] = { va: '0x' + va.toString(16), size: vsz, sha256: sha([[IMG + va, IMG + va + vsz]]) };
            ranges.push([IMG + va, IMG + va + vsz]);
        }
        res.image_writable = sha(ranges);
    }
    const dumpDir = process.env.FLE_OUTMEM_DUMP;
    if (dumpDir) {
        mkdirSync(dumpDir, { recursive: true });
        writeFileSync(`${dumpDir}/outmem_${basename(outPath, '.json')}.bin`, H.subarray(0, len));
    }
    return res;
})();
console.log('FLEBOOT_OUTMEM ' + JSON.stringify({ full: outMem.full, no_cstack: outMem.no_cstack, image_writable: outMem.image_writable, sections: Object.fromEntries(Object.entries(outMem.sections).map(([k, v]) => [k, v.sha256])) }));

// ---------------- CreateFruityInstance 観測 (#2719) ----------------
// 寛容起動の後で CreateFruityInstance (0x1375990) を 1 回呼ぶ。soft (未実装 import) の呼出し回数の差分で、
// 呼出中に現れた API 名を記録する (RegisterClassW / CreateWindowExW の自然到達の有無)。
const softSnap = () => { const mp = new Map(); for (let i = 0; i < Number(m._fle_n_soft_uniq()); i++) mp.set(m.UTF8ToString(m._fle_soft_name(i)), Number(m._fle_soft_count(i))); return mp; };
let cfi = null;
if (TOLERANT) {
    const CFI_VA = 0x1375990;
    const cstk0 = Number(m._emscripten_stack_get_current()), rsp0 = Number(m._fle_rsp_get());
    const lj0 = Number(m._fle_n_longjmp()), s0 = softSnap(), e0 = Number(m._fle_n_exit());
    // #4464: FLE_CFI_SEED=1 のとき、CFI 経路の global slot (0x1104e30・0x5ac270) を PE の静的値に戻してから呼ぶ。
    // 既定 (未指定) は従来どおり。slot は boot 中に 0 になっており、chain は rcx をこの slot から再読込する。
    if (process.env.FLE_CFI_SEED === '1') {
        const seed = [[0x1104e30, 0x1104ef8], [0x5ac270, 0x5ac338]];
        for (const [slot, val] of seed) { const dv = new DataView(m.HEAPU8.buffer); console.error('[cfi-seed] before ' + slot.toString(16) + '=0x' + dv.getBigUint64(slot, true).toString(16) + ' ac308=0x' + dv.getBigUint64(0x5ac308, true).toString(16)); dv.setBigUint64(slot, BigInt(val), true); }
    }
    // #5337: FLE_CFI_RECV=1 のとき受け手 slot 0x5ac308 を PE の静的値 0x40f960 (file off 0x1ab708) へ戻す。
    // fle_data_install が敷設する範囲 (memcpy 11,083 件・合計 4,002,981 B) はこの slot を含まないため、boot 中は 0 のまま。
    // FLE_CFI_SELF=<VA> のとき fle_run の第 1 引数 (rcx = self) をその値にする。既定は 0。
    if (process.env.FLE_CFI_RECV === '1') {
        const dv = new DataView(m.HEAPU8.buffer);
        console.error('[cfi-recv] before ac308=0x' + dv.getBigUint64(0x5ac308, true).toString(16));
        dv.setBigUint64(0x5ac308, 0x40f960n, true);
    }
    const CFI_SELF = process.env.FLE_CFI_SELF ? BigInt(process.env.FLE_CFI_SELF) : 0n;
    let cr = null, cerr = null;
    try { cr = m._fle_run(CFI_VA, CFI_SELF, 0n, 0n, 0n, 0n, 0n, 0n, 0n); } catch (e) { cerr = e; }
    m.__emscripten_stack_restore(cstk0); m._fle_rsp_set(rsp0);
    const s1 = softSnap(), called = [];
    for (const [nm, c] of s1) { const d = c - (s0.get(nm) || 0); if (d > 0) called.push([nm, d]); }
    cfi = {
        va: '0x' + CFI_VA.toString(16),
        rc: cerr ? null : '0x' + BigInt.asUintN(64, BigInt(cr)).toString(16),
        threw: cerr ? classify(cerr) : null,
        // trap 地点の手掛かり: wasm の例外スタック (関数 index → VA は fle_lifted の対応表で引く)
        stack: cerr && cerr.stack ? String(cerr.stack).split('\n').slice(0, 12).join('\n') : null,
        longjmp: Number(m._fle_n_longjmp()) - lj0, exit: Number(m._fle_n_exit()) - e0,
        // dispatch リングの末尾 4 件 (CFI 呼出し中の最後の関数 VA。trap 地点の推定に使う)
        last_dispatch: [124, 125, 126, 127].map((k) => '0x' + (Number(m._fle_ring_at(k)) >>> 0).toString(16)),
        soft_called: called.sort((a, b) => b[1] - a[1]).slice(0, 60),
    };
}

// ---------------- survey phase (942 unit 隔離) ----------------
let survey = null;
if (SURVEY) {
    // survey は boot 実機連鎖と同じインスタンスで行う (InitContext 0x15eac90 は boot の _InitLib が設定済み)。
    // unit は 1 本ずつ fle_run (新 RSP) で隔離実行し、trap/raise/halt0 を JS 側で分類する。
    const tbl = 0x15eac90;
    let tblPtr = BigInt(m.HEAPU32[tbl/4+1]) << 32n | BigInt(m.HEAPU32[tbl/4]);
    // #4854: 既定 (mode 3) の boot は unit 895 の後の exit (ExitProcess 経路) で InitContext.InitTable が 0 になる。
    // InitUnits の開始時の値は PackageInfo (PKG = 0x13768b0・_StartLib の rdx) なので、survey の前にそれへ戻す。
    const tblRestored = process.env.FLE_SURVEY_NOREPAIR !== '1' && tblPtr === 0n && m.HEAPU32[PKG / 4] > 0;
    if (tblRestored) { m.HEAPU32[tbl / 4] = PKG; m.HEAPU32[tbl / 4 + 1] = 0; tblPtr = BigInt(PKG); }
    if (tblPtr === 0n) {
        survey = { error: 'InitContext.InitTable == 0 (boot が _InitLib に届かず)' };
    } else {
        const total = Number(m._fle_units_total());
        const FROM = Number(process.env.FLE_SURVEY_FROM || 0);
        const TO = Math.min(Number(process.env.FLE_SURVEY_TO || total), total);
        const byCls = {}; const details = [];
        let longjmp0 = Number(m._fle_n_longjmp());
        // noproc / empty も jsonl に 1 行ずつ残す (merge_survey.py が 942 件を数えられるように・#4854)
        const emit = (i, cls, info) => { try { appendFileSync(outPath.replace(/\.json$/, '.jsonl'), JSON.stringify([i, cls, info]) + '\n'); } catch { } };
        for (let i = FROM; i < TO; i++) {
            console.error('[survey] unit ' + i + '/' + total);
            const proc = Number(m._fle_unit_proc(i) >>> 0);
            if (!proc) { byCls['noproc'] = (byCls['noproc'] || 0) + 1; details.push([i, 'noproc', 0]); emit(i, 'noproc', 0); continue; }
            // InitUnits と同じ [proc]!=0 check (実機 semantics: 先頭 8B が 0 なら skip)
            let zero8 = true;
            for (let k = 0; k < 8; k++) if (U8[proc + k]) { zero8 = false; break; }
            if (zero8) { byCls['empty'] = (byCls['empty'] || 0) + 1; details.push([i, 'empty', proc]); emit(i, 'empty', proc); continue; }
            const lj = Number(m._fle_n_longjmp());
            let cls = 'ok', info = 0;
            try {
                m._fle_run(proc, 0n, 0n, 0n, 0n, 0n, 0n, 0n, 0n);
                if (Number(m._fle_n_longjmp()) > lj) cls = 'halt0';
            } catch (e) {
                const c = classify(e);
                cls = (c.cls === 'exit' || c.cls === 'raise') ? 'halt0' : c.cls;   // halt 系に集約
                info = c.name || c.target || c.code || (c.msg ? c.msg.slice(0, 80) : 0);
            }
            byCls[cls] = (byCls[cls] || 0) + 1;
            console.error('[sv] ' + i + ' ' + cls + ' ' + (typeof info === 'string' ? info : '0x' + (info >>> 0).toString(16)));
            try { appendFileSync(outPath.replace(/\.json$/, '.jsonl'), JSON.stringify([i, cls, typeof info === 'string' ? info : info >>> 0]) + '\n'); } catch { }
            if (cls !== 'ok' && cls !== 'empty') details.push([i, cls, typeof info === 'string' ? info : '0x' + (info >>> 0).toString(16)]);
        }
        survey = { from: FROM, to: TO, total, byCls, halt0_total_longjmp: Number(m._fle_n_longjmp()) - longjmp0, details: details.slice(0, 400) };
    }
}

const softs = [];
for (let i = 0; i < Number(m._fle_n_soft_uniq()); i++) softs.push(`${m.UTF8ToString(m._fle_soft_name(i))}:${m._fle_soft_count(i)}`);
softs.sort((a, b) => Number(b.split(':')[1]) - Number(a.split(':')[1]));

// FLE-15 (#3770): 画素ストア 0x6bbc20 の計数 (fle_boot.c px_probe)。呼出し点 ret=0x6c9380 (f_6c9280 の 0x6c937a 直後) の回数と矩形
const pxRaw = typeof m._fle_px_stat === 'function' ? Array.from({ length: 16 }, (_, k) => m._fle_px_stat(k)) : null;
const px6bbc20 = pxRaw && { calls_all: pxRaw[0], calls_site_6c9380: pxRaw[1], first_rect_x0_y0_x1_y1: pxRaw.slice(2, 6), last_rect_x0_y0_x1_y1: pxRaw.slice(6, 10), rect_changes: pxRaw[10], x_min_max_y_min_max: pxRaw.slice(11, 15), calls_other_ret: pxRaw[15] };
const summary = {
    variant: process.env.FLE_BOOT_VARIANT || 'plain',
    wasm_size: (() => { try { return readFileSync(cjs + '.wasm').size; } catch { return null; } })(),
    boot,
    outmem: outMem,
    survey,
    tolerant: TOLERANT ? { mode: TOL_MODE, started: tol.started, hook_ran: tol.hook_ran, kinds: tol.kinds, skipped_n: tol.skipped.length, restored: tol.restored, skipped: tol.skipped, miss_units: tol.miss_units, units: tol.units } : null,
    cfi,
    log_cap: logCap,
    px6bbc20,
    soft_top: softs.slice(0, 40),
    ipp: { mode: IPP_MODE, on: IPP_ON, ptr_15F34A0: boot.ipp_ptr_15F34A0, ptr_15F40E8: boot.ipp_ptr_15F40E8, total: boot.ipp_total, called: boot.ipp_called, stop: boot.ipp_stop, token_at: boot.ipp_token_at, call_slot: boot.ipp_call_slot },
    notes: {
        entry: '0x1376820', longjmp_target: '0x1376840', init_table: '0x13768b0',
        baseline_retdec: {
            boot_units: '17 dispatched (16 completed), raise 0xEEDFADE in unit#17 (0x454090)',
            survey: 'm11 sx 純リンク baseline (tools/m11/work/shimx_link/baseline/m11_boot.survey.json): '
                  + 'ok 800 / oob 50 / halt0 44 / closure外 46 / abort 1 / noproc 1。'
                  + 'なお --fix 変種は ok 800 / oob 41 / halt0 53 (CAB-129 halt0 対応表適用)。',
            route_diff: 'results/verdict_boot.jsonl (gen_verdict.py: baseline を native 側、x64c を wasm 側に対応)',
        },
    },
};
mkdirSync(new URL('.', 'file://' + outPath).pathname, { recursive: true });
writeFileSync(outPath, JSON.stringify(summary, null, 1));
console.log('FLEBOOT_RESULT ' + JSON.stringify({
    units_run: boot.units_run, units_total: boot.units_total, stopped_at: boot.stopped_at_1based,
    boot_threw: boot.threw && (boot.threw.cls + (boot.threw.msg ? ' ' + boot.threw.msg : '')),
    boot_threw_raw: boot.threw_raw ? boot.threw_raw.cls : null,
    log_cap: LOG_CAP || TIME_CAP ? { hit: logCap.hit, bytes: logCap.bytes, lines: logCap.lines, bin_lines: logCap.bin_lines, elapsed_ms: logCap.elapsed_ms } : null,
    px6bbc20,
    longjmp: boot.longjmp, getmem: boot.getmem, freemem: boot.freemem,
    va_calls: boot.va_calls, va_bytes: boot.va_bytes, exit: boot.exit,
    survey: survey && survey.byCls ? survey.byCls : (survey && survey.prologue_threw || null),
    ipp_mode: IPP_MODE, ipp_on: IPP_ON, ipp_ptr_15F34A0: boot.ipp_ptr_15F34A0,
    ipp_total: boot.ipp_total, ipp_called: boot.ipp_called, ipp_stop: boot.ipp_stop, diag_nullfill: boot.diag_nullfill,
    tolerant: TOLERANT ? { mode: TOL_MODE, started: tol.started, hook_ran: tol.hook_ran, kinds: tol.kinds, skipped_n: tol.skipped.length, restored: tol.restored, miss_units: tol.miss_units.length } : null,
    cfi: cfi && { rc: cfi.rc, threw: cfi.threw && cfi.threw.cls, longjmp: cfi.longjmp, exit: cfi.exit },
}));
console.log('FLEBOOT_UNDO ' + JSON.stringify(undoProbe));
// #6213: 陽性対照の読取り (boot 停止時点の受け手 slot の値。監視が出ない理由の切り分け用・読むだけ)
{
    const dv6213 = new DataView(m.HEAPU8.buffer);
    const r6213 = (a) => (a + 8 <= U8.length ? '0x' + dv6213.getBigUint64(a, true).toString(16) : null);
    console.log('FLEBOOT_SLOT6213 ' + JSON.stringify({ slot_0x5ac308: r6213(0x5ac308), slot_0x11f6100: r6213(0x11f6100), slot_0x976410: r6213(0x976410) }));
}
// PY-4877 (#5168): FLE_PY4877_PC=1 のとき、boot 停止後に patternCount (0xd64d40) を直接実行し、呼出し前の E[1..999] を読む (計測のみ)。
// 読みは呼出し前 (pre) と呼出し後 (post) の両方を取る。summary の書出し後なので boot の計数には影響しない。
if (process.env.FLE_PY4877_PC === '1') {
    const rowsNz = (tag) => {
        const rows = [];
        for (let i = 1; i <= 999; i++) {
            const v = { i, p84: m._fle_py_e_u8(i, 0x84), p10: m._fle_py_e_u32(i, 0x10), p14: m._fle_py_e_u8(i, 0x14), p20: m._fle_py_e_u64(i, 0x20), p28: m._fle_py_e_u64(i, 0x28) };
            if (v.p84 || v.p10 || v.p14 || v.p20 || v.p28) rows.push(v);
        }
        console.log('FLEBOOT_PY4877_' + tag + ' ' + JSON.stringify({ nonzero_rows: rows.length, rows: rows.slice(0, 40).map((r) => ({ i: r.i, p84: '0x' + r.p84.toString(16), p10: '0x' + r.p10.toString(16), p14: '0x' + r.p14.toString(16), p20: '0x' + BigInt(r.p20).toString(16), p28: '0x' + BigInt(r.p28).toString(16) })) }));
        return rows.length;
    };
    rowsNz('PRE');
    let pcRet = null, pcThrew = null;
    try { pcRet = m._fle_py_pattern_count(); } catch (e) { pcThrew = classify(e); }
    console.log('FLEBOOT_PY4877_CALL ' + JSON.stringify({ ret: pcRet, threw: pcThrew }));
    rowsNz('POST');
}
// PY-106 (#2909): 束縛関数 0xc395a0 を boot 停止後に直接実行し、resolver が引いた名前と slot の値を読む (FLE_PY106_BIND=1 のときだけ。
// summary の書出しの後で行うので boot の計数・outmem には影響しない)。sink 0xd82daf と同じ 3 段 load を実メモリで辿る。
if (process.env.FLE_PY106_BIND === '1') {
    const SLOT_HEAD = 0x15e1140, SLOT_EXC = 0x16b8488, SLOT_SETSTR = 0x16b8408, SLOT_NEWINTERP = 0x16b8250;
    const hx = (v) => '0x' + BigInt.asUintN(64, BigInt(v)).toString(16);
    const rd64 = (a) => new DataView(m.HEAPU8.buffer).getBigUint64(Number(a), true);
    const head0 = rd64(SLOT_HEAD);
    const getproc0 = m._fle_n_getproc();
    // FLE_PY106_MM=1: unit 209 で 0 になった GetMem の関数ポインタ (0x13a5c90) を boot 初期値 0x407a50 に戻してから束縛を試す (計測のみ)
    const mmBefore = rd64(0x13a5c90);
    if (process.env.FLE_PY106_MM === '1') new DataView(m.HEAPU8.buffer).setBigUint64(0x13a5c90, 0x407a50n, true);
    console.log('FLEBOOT_PY106MM ' + JSON.stringify({ restore: process.env.FLE_PY106_MM === '1', before: hx(mmBefore), after: hx(rd64(0x13a5c90)) }));
    let threw = null;
    try { m._fle_py_bind_probe(); } catch (e) { threw = classify(e); }
    // throw (exit) の経路でも C 側の計数と名前表を読む。読みは戻り値に頼らず、名前表は空文字まで、計数は前後差で取る
    const getproc_calls = m._fle_n_getproc() - getproc0, hook_calls = m._fle_py_bind_hook_n();
    const ringTail = []; for (let k = 96; k < 128; k++) ringTail.push('0x' + (Number(m._fle_ring_at(k)) >>> 0).toString(16));
    console.log('FLEBOOT_PY106RING ' + JSON.stringify(ringTail));
    const names = [];
    for (let i = 0; i < 128; i++) { const nm = m.UTF8ToString(m._fle_py_bind_name(i)); if (nm === '') break; names.push({ i, name: nm, cell: BigInt(m._fle_py_bind_cell(i)) }); }
    const n = names.length;
    const nameOf = (v) => { const x = names.find((y) => y.cell === BigInt.asUintN(64, BigInt(v))); return x ? x.name : null; };
    const slotExc = rd64(SLOT_EXC);
    // boot 停止時の head は 0 (unit 209 で 0 化)。sink と同じ load を辿るため、head を PE の値 (SLOT_EXC) に戻してから読む
    new DataView(m.HEAPU8.buffer).setBigUint64(SLOT_HEAD, BigInt(SLOT_EXC), true);
    const v1 = rd64(SLOT_HEAD), v2 = rd64(v1), v3 = rd64(v2);
    const tok = Number(v3) - 0x7f300000;
    const pyB = {
        probe: { threw, names_n: n, getproc_calls, hook_calls },
        head_at_stop: hx(head0), slot_exc_after_bind: hx(slotExc), name_of_slot_exc: nameOf(slotExc),
        slot_setstr_after_bind: hx(rd64(SLOT_SETSTR)), name_of_slot_setstr: nameOf(rd64(SLOT_SETSTR)),
        slot_newinterp_after_bind: hx(rd64(SLOT_NEWINTERP)), name_of_slot_newinterp: nameOf(rd64(SLOT_NEWINTERP)),
        head_restored: hx(SLOT_EXC),
        chain: { load1_head: hx(v1), load2: hx(v2), load3_type_tok: hx(v3), type_name: names[tok] ? names[tok].name : null },
        names: names.map((x) => [x.i, x.name, hx(x.cell)]),
    };
    writeFileSync(outPath.replace(/\.json$/, '_py106bind.json'), JSON.stringify(pyB, null, 1));
    console.log('FLEBOOT_PY106B ' + JSON.stringify({ threw: pyB.probe.threw, names_n: n, getproc_calls, hook_calls, head_at_stop: pyB.head_at_stop, name_of_slot_exc: pyB.name_of_slot_exc, name_of_slot_setstr: pyB.name_of_slot_setstr, name_of_slot_newinterp: pyB.name_of_slot_newinterp, type_name: pyB.chain.type_name, load3: pyB.chain.load3_type_tok }));
}
// FLE-6 ネガコン判定: shim 無し (既定 / FLE_IPP=0) なら 0x15F34A0 = 0、shim 有り (FLE_IPP=1) なら非 0 でなければならない。
// mode 2 (#2702) は停止を測る測定モードなので判定しない (ok の値は出すが終了コードは変えない)。
const ippPtrOk = IPP_ON ? !/^0x0+$/.test(boot.ipp_ptr_15F34A0) : /^0x0+$/.test(boot.ipp_ptr_15F34A0);
console.log('FLEBOOT_IPP_CHECK ' + JSON.stringify({ mode: IPP_MODE, ptr_15F34A0: boot.ipp_ptr_15F34A0, ok: ippPtrOk }));
// 寛容起動 (#2719) は測定のみ: root 有の 0x15F34A0 は終了時に消えるため (#3060) 判定に使わない
if (!ippPtrOk && IPP_MODE !== 2 && !TOLERANT) process.exitCode = 3;
