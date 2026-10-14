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

const cjs = process.argv[2];
const outPath = process.argv[3] || 'work/boot/boot_summary.json';
const BOOT_ONLY = process.argv.includes('--boot-only');
const SURVEY = process.argv.includes('--survey') || !BOOT_ONLY;
const TRACE = process.env.FLE_BOOT_TRACE === '1';

const mod = await import(cjs);
let m = await (mod.default ? mod.default() : mod());
const U8 = m.HEAPU8;

if (TRACE) { try { m._shimx_set_trace(1); } catch { /* nosx では未 export */ } }
// FLE-6: dsp_ippv2 shim は既定で無効。FLE_IPP=1 のときだけ有効 (ネガコン FLE_IPP=0 / 未指定 = 修正前の挙動)。
// FLE_IPP=2 (#2702): shim 有 + ippsZero_8u 以外の IPP 呼出で停止 (停止名と呼出元を summary に出す)。
const IPP_MODE = { '1': 1, '2': 2 }[process.env.FLE_IPP] || 0;
const IPP_ON = IPP_MODE !== 0;
m._fle_boot_set_ipp(IPP_MODE);

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
    return { cls: 'trap', msg: s.slice(0, 160) };
}

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
boot.units_run = Number(m._fle_units_run()); boot.units_total = Number(m._fle_units_total()); boot.units_empty = Number(m._fle_units_empty());
boot.longjmp = Number(m._fle_n_longjmp());
const r0 = m._fle_rget(0);
boot.rax = '0x' + BigInt.asUintN(64, typeof r0 === 'bigint' ? r0 : BigInt(r0)).toString(16);
boot.stage = Number(m._fle_boot_stage());
boot.getmem = Number(m._fle_n_getmem()); boot.freemem = Number(m._fle_n_freemem());
boot.va_calls = Number(m._fle_va_calls()); boot.va_bytes = Number(m._fle_va_bytes());
boot.getproc = Number(m._fle_n_getproc()); boot.exit = Number(m._fle_n_exit());
boot.cb_calls = Number(m._fle_n_cb()); boot.soft_calls = Number(m._fle_n_soft()); boot.soft_uniq = Number(m._fle_n_soft_uniq());
boot.mm_after = mmTable();
// FLE-6: dsp_ippv2 GetProcAddress 結果 (0x15F34A0 = ippsZero_8u の登録値) と IPP 呼出の証跡
boot.ipp_ptr_15F34A0 = rd64(0x15F34A0);
boot.ipp_ptr_15F40E8 = rd64(0x15F40E8);
boot.ipp_total = Number(m._fle_ipp_total());
boot.ipp_called = [];
for (let i = 0; i < Number(m._fle_ipp_names()); i++) {
    const c = Number(m._fle_ipp_count(i));
    if (c) boot.ipp_called.push([m.UTF8ToString(m._fle_ipp_name(i)), c, '0x' + Number(m._fle_ipp_site(i)).toString(16)]);
}
// ippsZero_8u の唯一の呼出し点 0x67264d は `mov rax,[0x15e0a48]; call [rax]` (lift 行の実測)。読出し経路の値を残す
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

// ---------------- survey phase (942 unit 隔離) ----------------
let survey = null;
if (SURVEY) {
    // survey は boot 実機連鎖と同じインスタンスで行う (InitContext 0x15eac90 は boot の _InitLib が設定済み)。
    // unit は 1 本ずつ fle_run (新 RSP) で隔離実行し、trap/raise/halt0 を JS 側で分類する。
    const tbl = 0x15eac90;
    const tblPtr = BigInt(m.HEAPU32[tbl/4+1]) << 32n | BigInt(m.HEAPU32[tbl/4]);
    if (tblPtr === 0n) {
        survey = { error: 'InitContext.InitTable == 0 (boot が _InitLib に届かず)' };
    } else {
        const total = Number(m._fle_units_total());
        const FROM = Number(process.env.FLE_SURVEY_FROM || 0);
        const TO = Math.min(Number(process.env.FLE_SURVEY_TO || total), total);
        const byCls = {}; const details = [];
        let longjmp0 = Number(m._fle_n_longjmp());
        for (let i = FROM; i < TO; i++) {
            console.error('[survey] unit ' + i + '/' + total);
            const proc = Number(m._fle_unit_proc(i) >>> 0);
            if (!proc) { byCls['noproc'] = (byCls['noproc'] || 0) + 1; details.push([i, 'noproc', 0]); continue; }
            // InitUnits と同じ [proc]!=0 check (実機 semantics: 先頭 8B が 0 なら skip)
            let zero8 = true;
            for (let k = 0; k < 8; k++) if (U8[proc + k]) { zero8 = false; break; }
            if (zero8) { byCls['empty'] = (byCls['empty'] || 0) + 1; details.push([i, 'empty', proc]); continue; }
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
for (let i = 0; i < Number(m._fle_n_soft_uniq()); i++) softs.push(`${m._fle_soft_name(i)}:${m._fle_soft_count(i)}`);
softs.sort((a, b) => Number(b.split(':')[1]) - Number(a.split(':')[1]));

const summary = {
    variant: process.env.FLE_BOOT_VARIANT || 'plain',
    wasm_size: (() => { try { return readFileSync(cjs + '.wasm').size; } catch { return null; } })(),
    boot,
    survey,
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
    longjmp: boot.longjmp, getmem: boot.getmem, freemem: boot.freemem,
    va_calls: boot.va_calls, va_bytes: boot.va_bytes, exit: boot.exit,
    survey: survey && survey.byCls ? survey.byCls : (survey && survey.prologue_threw || null),
    ipp_mode: IPP_MODE, ipp_on: IPP_ON, ipp_ptr_15F34A0: boot.ipp_ptr_15F34A0,
    ipp_total: boot.ipp_total, ipp_called: boot.ipp_called, ipp_stop: boot.ipp_stop,
}));
// FLE-6 ネガコン判定: shim 無し (既定 / FLE_IPP=0) なら 0x15F34A0 = 0、shim 有り (FLE_IPP=1) なら非 0 でなければならない。
// mode 2 (#2702) は停止を測る測定モードなので判定しない (ok の値は出すが終了コードは変えない)。
const ippPtrOk = IPP_ON ? !/^0x0+$/.test(boot.ipp_ptr_15F34A0) : /^0x0+$/.test(boot.ipp_ptr_15F34A0);
console.log('FLEBOOT_IPP_CHECK ' + JSON.stringify({ mode: IPP_MODE, ptr_15F34A0: boot.ipp_ptr_15F34A0, ok: ippPtrOk }));
if (!ippPtrOk && IPP_MODE !== 2) process.exitCode = 3;
