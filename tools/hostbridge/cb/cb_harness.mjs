/* cb_harness.mjs — hostbridge/cb ハーネスの駆動と検証 (CAB-177)。
 *   node cb_harness.mjs <cb_mod.cjs> [--out DIR]
 * guest 側エントリを実行し、R2 (VA コールバック往復) / R3 (トークン往復) の結果を検査して cb_result.json を出力。
 * exit 0 = 全 check PASS。
 */
import fs from 'fs';
import path from 'path';

const cjs = path.resolve(process.argv[2]);
const outDir = process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1] : path.dirname(cjs);
const tag = path.basename(cjs).replace(/\.cjs$/, '');
const checks = [];
let nfail = 0;
function check(name, cond, detail = '') {
  checks.push({ name, ok: !!cond, detail: String(detail).slice(0, 120) });
  if (!cond) nfail++;
  console.log(`[cb] ${cond ? 'OK' : 'FAIL'} ${name}${cond ? '' : ' :: ' + detail}`);
}

const m2 = await import(cjs);
const stderr = [];
const mk = m2.default || m2.cbcreate || m2;   /* MODULARIZE (= h2/m11 run harness 流儀) */
const mod = await mk({ printErr: (s) => stderr.push(String(s)) });
const isMt = typeof mod._g_thread === 'function';

check('ctor boot (constructor 実行)', mod._cb_booted() === 1, `booted=${mod._cb_booted()}`);

/* R2: EnumCalendarInfoW — M11 純リンク unit 18 の実測形 (VA 0x4476d0 を guest から直接渡す) */
const cal = mod._g_enum_calendar();
check('R2 EnumCalendarInfoW 往復 (VA→trampoline→lift fn)', cal >= 1, `hits=${cal}`);

/* R2: EnumSystemLocalesW 往復 */
const loc = mod._g_enum_locales();
check('R2 EnumSystemLocalesW 往復', loc >= 4, `hits=${loc}`);

/* R2: closure 外 VA → graceful (invoke miss, trap 無し) */
const unk = mod._g_enum_unknown();
check('R2 closure 外 VA は graceful (miss 計数, trap 無し)', unk >= 100, `miss*100+hits=${unk}`);

/* R2: InitOnceExecuteOnce (i3 形状, 完了後は fn 不呼出) */
const once = mod._g_initonce();
check('R2 InitOnceExecuteOnce 往復', once === 1, `hits=${once}`);

/* R2: 実 C 関数ポインタの恒等経路 (M4 互換) */
check('R2 恒等経路 (実 C ポインタ)', mod._g_identity() === 1);

/* R2: BLK route (__icall_dispatch 相当) への invoke 差し替え */
const blk = mod._g_route_switch();
check('R2 BLK route (__icall_dispatch 相当) 往復', blk >= 4, `blk_hits=${blk}`);

/* R2 非同期: FlsAlloc は ST でも動く */
check('R2 FlsAlloc 往復 (寿命: FlsFree まで)', mod._g_fls() === 1);

if (isMt) {
  const th = mod._g_thread();
  check('R2 CreateThread 往復 (start VA, rc=42)', th === 42, `rc=${th}`);
  const tm = mod._g_timer();
  check('R2 CreateTimerQueueTimer 往復 (2 回以上発火)', tm >= 2, `hits=${tm}`);
  const pw = mod._g_pool();
  check('R2 CreateThreadpoolWork 往復 (v3 形状, work 自身が第3引数)', pw === 1, `ret=${pw}`);
} else {
  console.log('[cb] SKIP thread/timer/pool (ST build)');
}

/* R3: GetProcAddress → トークン → lift dispatch → 実体 3 往復 */
const r3 = mod._g_r3_roundtrip();
check('R3 トークン往復 (ILGetSize/ILIsEqual/GetThreadUILanguage)', r3 === 7, `ret=${r3}`);

/* 統計 */
mod._g_stats(mod._g_stats_buf());
const st = mod.HEAPU32.subarray(mod._g_stats_buf() >> 2, (mod._g_stats_buf() >> 2) + 8);const [slots, calls, iok, imiss, lt_n] = [st[0], st[1], st[2], st[3], st[4]];
check('統合: slot 数 = 登録 distinct VA 数', slots >= (isMt ? 9 : 6), `slots=${slots}`);
check('統合: トランポリン実呼出 = invoke ok + miss', calls === iok + imiss, `calls=${calls} ok=${iok} miss=${imiss}`);
check('R3 lifttab 13 エントリ', lt_n === 13, `n=${lt_n}`);

const result = { tag, build: isMt ? 'mt' : 'st', checks: checks.length, failed: nfail,
                 stats: { slots, calls, invoke_ok: iok, invoke_miss: imiss, lifttab: lt_n },
                 stderr_tail: stderr.slice(-6) };
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'cb_result.json'), JSON.stringify(result, null, 1) + '\n');
console.log(`CB_RESULT ${JSON.stringify(result)}`);
process.exit(nfail ? 1 : 0);
