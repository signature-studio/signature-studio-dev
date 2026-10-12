#!/usr/bin/env python3
"""tools/icall 回帰テスト (python3 tests/test_icall.py; pytest 不要)。
 unit: エンコーディング/ヘルパ (PE 不要)  /  pe: OTT DLL があれば rewriter・audit の数値を固定値で検証  /  slow(ICALL_SLOW=1): RetDec round-trip"""
import os, subprocess, sys, json, struct
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
import icall_rewrite as R
import audit_icall as A
import capstone

OTT = '/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll'
fails = []


def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' ' + str(info) if info and not cond else ''))
    if not cond:
        fails.append(name)


# ---- unit
check('lea_disp8 rcx+8', R.lea_disp8(1, 8) == bytes.fromhex('48 8d 49 08'.replace(' ', '')))
check('lea_disp8 r12-8 (SIB)', R.lea_disp8(12, -8) == bytes.fromhex('4d8da42 4f8'.replace(' ', '')) or R.lea_disp8(12, -8)[3] == 0x24)
check('modrm_tail rip', R.modrm_tail_len(bytes([0x05]), 0) == 4)
check('modrm_tail reg', R.modrm_tail_len(bytes([0xc1]), 0) == 0)
check('modrm_tail sib+disp8', R.modrm_tail_len(bytes([0x44, 0x24, 0x08]), 0) == 2)
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); cs.detail = True
ins = next(cs.disasm(bytes.fromhex('488b00'), 0x1000))
dp = R.derefix_pieces(ins)
check('derefix mov rax,[rax] (RetDec D7; base を書く命令は restore 不要)', dp is not None and dp[0] == R.lea_disp8(0, 8) and dp[1] == bytes.fromhex('488b40f8') and dp[2] == b'', dp)
ins = next(cs.disasm(bytes.fromhex('488b01'), 0x1000))
dp = R.derefix_pieces(ins)
check('derefix mov rax,[rcx] (restore lea 付き)', dp is not None and dp[0] == R.lea_disp8(1, 8) and dp[1] == bytes.fromhex('488b41f8') and dp[2] == R.lea_disp8(1, -8), dp)
ins = next(cs.disasm(bytes.fromhex('f3a5'), 0x1000))
check('derefix 対象外 rep movsd (string)', R.derefix_pieces(ins) is None)
ins = next(cs.disasm(bytes.fromhex('f30f1001'), 0x1000))
dp = R.derefix_pieces(ins)
check('derefix movss xmm0,[rcx] (restore lea 付き)', dp is not None and dp[2] == R.lea_disp8(1, -8))
ins = next(cs.disasm(bytes.fromhex('488b4108'), 0x1000))
check('derefix 対象外 [rcx+8]', R.derefix_pieces(ins) is None)
ins = next(cs.disasm(bytes.fromhex('660f2f0510000000'), 0x1000))
check('capstone disp_size 誤り (66 prefix rip-rel) を検知', ins.disp_size != 4, 'disp_size=%d' % ins.disp_size)

# ---- ICALL-5 追加 pass (ir_fix_mask / ir_override / simd_merge): PE 不要
import tempfile
def _run(script, *args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, script)] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout
_td = tempfile.mkdtemp()
_ll = os.path.join(_td, 'a.ll')
open(_ll, 'w').write("""define i64 @function_1801aa1a0() {
  %96 = icmp ult i64 %94, -4294967295
  %97 = add i64 %94, 4294967295
  %98 = select i1 %96, i64 %94, i64 %97, !insn.addr !7357
  %99 = icmp ult i64 %5, -4294967295
  %100 = add i64 %5, 7
  %101 = select i1 %99, i64 %5, i64 %100
  ret i64 %98
}
define i64 @function_1801c8c00(i64 %arg1) {
  ret i64 0
}
""")
_rc, _o = _run('ir_fix_mask.py', _ll, _ll + '.o')
_t = open(_ll + '.o').read()
check('fix_mask: select 形 1 件を and -4294967296 に置換 (別定数の同形は触らない)', json.loads(_o)['hi32_mask_fixed'] == 1 and '%98 = and i64 %94, -4294967296, !insn.addr !7357' in _t and '%101 = select' in _t, _o)
_rc, _o = _run('ir_override.py', _ll, _ll + '.o2', '1801c8c00')
_t = open(_ll + '.o2').read()
check('override: define → declare (引数個数保持)', _rc == 0 and 'declare i64 @function_1801c8c00(i64)' in _t and 'define i64 @function_1801c8c00' not in _t, _o)
_rc, _o = _run('ir_override.py', _ll, _ll + '.o3', '1801c8c00,deadbeef')
check('override: IR に無い VA は exit 1 (取りこぼし検知)', _rc == 1 and 'deadbeef' in json.loads(_o)['missing'], _o)
_gen = os.path.join(_td, 'g.c'); _ex = os.path.join(_td, 'e.c'); _out = os.path.join(_td, 'o.c')
open(_gen, 'w').write('static int m11_simd_unimpl_once(const char* n) { return 0; }\nEMSCRIPTEN_KEEPALIVE u128 __asm_foo(u128 a) { m11_simd_unimpl_once("__asm_foo"); return 0; }\nEMSCRIPTEN_KEEPALIVE u128 __asm_bar(u128 a) { m11_simd_unimpl_once("__asm_bar"); return 0; }\n')
open(_ex, 'w').write('u128 __asm_foo(u128 a) { return a; }\n')
_rc, _o = _run('simd_merge.py', _gen, _out, _ex)
_t = open(_out).read()
check('simd_merge: extra 定義済みの stub を除き、残る stub は abort する', '__asm_foo(u128 a) { m11' not in _t and 'abort()' in _t and '__asm_bar' in _t, _o)

# ---- pe: OTT closure に対する固定値
if os.path.exists(OTT):
    img = A.Image(OTT)
    F = os.path.join(ROOT, 'work', 'route', 'F.txt')
    if os.path.exists(F):
        out = '/tmp/opencode/icall_test_rw.dll' if os.path.isdir('/tmp/opencode') else '/tmp/icall_test_rw.dll'
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'icall_rewrite.py'), '--pe', OTT, '--funcs', F, '--out', out, '--map', out + '.json'],
                           capture_output=True, text=True)
        check('rewrite OTT F271 成功', r.returncode == 0, r.stderr[-300:])
        m = json.load(open(out + '.json'))
        check('rewrite OTT sites == 96', m['nsites'] == 96, m['nsites'])
        check('rewrite errors == {}', m['errors'] == {}, m['errors'])
        check('rewrite jt-chain >= 5', m['njt'] >= 5, m['njt'])
        # 書換え後 PE 上で、元の site 位置が展開されている (call stub が存在)
        img2 = A.Image(out)
        check('新 section が PE に追加', any(s[3] == '.icall' for s in img2.secs))
    else:
        print('SKIP pe tests (work/route/F.txt が無い: bash ott_route.sh を先に)')
else:
    print('SKIP pe tests (OTT DLL 無し)')
print('RESULT %s (%d failed)' % ('PASS' if not fails else 'FAIL', len(fails)))
sys.exit(1 if fails else 0)
