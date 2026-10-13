// M11-N21 (#572): .data 末尾 slot (RVA 0x11e5000) の補正状態と、それを実行時に使う unit #12 の挙動を測る。
//   slot  : 補正済 = LVA 0x25f00+LB / 未補正 = VA 0x425f00 のまま
//   unit #12: Init=0x42d870 (カウンタ 0→-1 で 0x4123c0 を呼ぶ) → 表 .text RVA 0x2d3b8 (24B x26 レコード
//             {dest, src(=slot のあるアドレス), type}) を走査。レコード #1 (src=slot) は type 2 =
//             0x4123a0(&tmp, *slot) → 0x41c820(dest, TResStringRec*) 。slot の値が TResStringRec* として使われる。
//   survey モード (InitUnits 抑止) で boot 後に unit #12 だけを呼び、戻り値 / trap / 0x41c820 の引数観測を出す。
// 使い方: node m11_slot_probe.mjs [--expect-slot-fixed | --expect-slot-unfixed] [--json out.json]
import fs from 'fs';
const M11 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const LB = Number(process.env.M11_LB_BASE || 0);
const mode = process.argv[2] || '';
const jidx = process.argv.indexOf('--json');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const errs = [];
const mod = await m2.default({ printErr: (s) => errs.push(String(s)) });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { mod.__emscripten_stack_restore(sp); }
const dv = () => new DataView(mod.HEAPU8.buffer);
const q = (a) => dv().getBigUint64(a, true);
const hx = (v) => '0x' + v.toString(16);
const slot = q(0x11e5000 + LB);
const fixed = slot === BigInt(0x25f00 + LB);
const cnt0 = dv().getInt32(0x11ec378 + LB, true);
let r = null, trap = null;
try { r = mod._m11_call_unit(12); } catch (e) { trap = (e && e.message) || String(e); mod.__emscripten_stack_restore(sp); }
const cnt1 = dv().getInt32(0x11ec378 + LB, true);
const res = { lb: LB, slot: hx(slot), slot_fixed: fixed, unit12_counter_before: cnt0, unit12_counter_after: cnt1,
              unit12_ret: r, unit12_trap: trap, unit12_dest_0xfa9a58: hx(q(0xfa9a58 + LB)),
              rsi_field8_seen_by_41c820: hx(q(Number(slot) + 8)),
              stderr_tail: errs.slice(-3) };
console.log('SLOT_PROBE ' + JSON.stringify(res));
if (jidx > 0) fs.writeFileSync(process.argv[jidx + 1], JSON.stringify(res, null, 1));
if (mode === '--expect-slot-fixed' && !fixed) { console.log('FAIL: slot 未補正'); process.exit(1); }
if (mode === '--expect-slot-unfixed' && fixed) { console.log('FAIL: slot が補正済み (ネガコンが成立していない)'); process.exit(1); }
