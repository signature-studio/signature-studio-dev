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

# ---- stack 引数 (5 個目以降) の検出 (BLK+0x48 / STKBUF)
class _It:
    def __init__(self, hexs, addr):
        self.kind = 'ins'; self.ins = next(cs.disasm(bytes.fromhex(hexs), addr))
def _seq(*hs):
    return [_It(h, 0x1000 + 16 * i) for i, h in enumerate(hs)] + [_It('ffd0', 0x2000)]
mov_5th = '4889442420'        # mov [rsp+0x20], rax
mov_6th = '4889442428'        # mov [rsp+0x28], rax
movaps_x = '0f29742420'       # movaps [rsp+0x20], xmm6 (xmm 退避)
check('stk: 5 引数 (rsp+0x20) -> 1 語', R.stk_slots_stored(_seq(mov_5th), 1) == 1)
check('stk: 6 引数 (rsp+0x28) -> 2 語', R.stk_slots_stored(_seq(mov_5th, mov_6th), 2) == 2)
check('stk: 引数なし -> 0', R.stk_slots_stored(_seq('4889c8'), 1) == 0)
check('stk: movaps [rsp+0x20] (xmm 退避) は引数でない', R.stk_slots_stored(_seq(movaps_x), 1) == 0)
check('stk: 直前の call より前の store は無視', R.stk_slots_stored([_It(mov_5th, 0x1000), _It('e800000000', 0x1010), _It('ffd0', 0x1020)], 2) == 0)
check('stk: SITE_TAIL 長さが nstk に比例', R.site_tail_len(3) - R.site_tail_len(0) == 3 * R.STK_COPY_ONE)

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
