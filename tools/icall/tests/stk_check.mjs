// stk_check.mjs MOD.cjs: ICALL_CHECK_STK 付き build で OTT ctor→setParameter→resume→process を実行し、
// dispatch ごとに BLK+0x48 (stack 引数スロット先頭) が ICALL_BLK+0x100 と一致 / 8 byte 整列 / STKBUF 12 語が線形メモリ内 かを runtime で検査する。
// assert: dispatch>0 かつ ptr_bad==0 (終了コード)。nonzero_stkbuf は診断値 (stack 引数ありの site が実行された dispatch 数) で assert しない。
import { load } from '../../ott/diff/api.mjs';
const api = await load(process.argv[2]);
const m = api.mod;
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = 256;
const U32 = m.HEAPU32, F32 = m.HEAPF32;
for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
api.ctor(OBJ);
for (let p = 0; p < 19; p++) api.setParam(OBJ, p, 0.5);
api.resume(OBJ); api.process(OBJ, IN_A, OU_A, N);
const n = Number(m._icall_stk_checked()), bad = Number(m._icall_stk_nonzero()), pbad = Number(m._icall_stk_ptr_bad());
console.log(`stk_check dispatch=${n} ptr_bad=${pbad} nonzero_stkbuf=${bad}`);
process.exit(n > 0 && pbad === 0 ? 0 : 1);
