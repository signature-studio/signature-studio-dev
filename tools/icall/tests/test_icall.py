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

OTT = os.path.join(os.environ.get('ANALYSIS_DIR', '/home/ubuntu/work/analysis'), 'plugins/ott/binaries/OTT_vst2_win64.dll')
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
check('jtm: jmp [r10+rdx*8+0x40] -> cmp qword [r10+rdx*8+0x40] (REX.W 81 /7)', R.jtm_head(bytes.fromhex('43ff64d240')) == bytes.fromhex('4b817cd240'))
check('jtm: jmp [rax+rcx*8] -> cmp qword [rax+rcx*8]', R.jtm_head(bytes.fromhex('ff24c8')) == bytes.fromhex('48813cc8'))
check('jtm: jmp [rip+disp] は対象外', R.jtm_head(bytes.fromhex('ff2500000000')) is None)
check('jtm: jmp rax (reg 形) は対象外', R.jtm_head(bytes.fromhex('ffe0')) is None)

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
check('stk: cmp [rsp+0x20],0 (読み取り) は引数でない', R.stk_slots_stored(_seq('48837c242000'), 1) == 0)
check('stk: test [rsp+0x28],rax (読み取り) は引数でない', R.stk_slots_stored(_seq('4885442428'), 1) == 0)
check('stk: cmp 後の mov [rsp+0x20] は 1 語', R.stk_slots_stored(_seq('48837c242000', mov_5th), 2) == 1)
check('stk: SITE_TAIL 長さが nstk に比例', R.site_tail_len(3) - R.site_tail_len(0) == 3 * R.STK_COPY_ONE)

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

# ---- ICALL-6 (#361): ir_fix_vstore (RetDec が xmm→stack store を void helper にして落とす)
_vl = os.path.join(_td, 'v.ll')
open(_vl, 'w').write("""define i64 @function_1801a9be0() {
  %0 = alloca i128
  %xmm1.0.reg2mem = alloca i128
  %5 = load i128, i128* %0
  %6 = load i128, i128* %0
  call void @__asm_vmovapd.22(i128 %5, i128 %10), !insn.addr !7138
  %274 = call i128 @__asm_vmovapd(i128 %5), !insn.addr !7222
  call void @__asm_movups(i128 %6, i128 %10)
  call void @__asm_vmovdqa(i256 %221, i256 %207)
  ret i64 0
}
""")
_rc, _o = _run('ir_fix_vstore.py', _vl, _vl + '.o')
_t = open(_vl + '.o').read()
_j = json.loads(_o)
check('fix_vstore: alloca 由来の宛先 2 件 (vmovapd / movups) を store 化し、読出し 1 件を reload に置換', _j['vstore_fixed'] == 2 and _j['vstore_reloads'] == 1 and 'store i128 %10, i128* %vst.0' in _t
      and '%vld.0 = load i128, i128* %vst.0' in _t and '@__asm_vmovapd(i128 %vld.0)' in _t and 'call void @__asm_vmovapd.22' not in _t, _o)
check('fix_vstore: 256bit (i256) は触らず unresolved に数える', _j['vstore_unresolved'] == 1 and '@__asm_vmovdqa(i256' in _t, _o)
# ---- #1025: ir_fix_vstore --direct (alloca 以外の宛先ポインタ。既定 off)
_vd = os.path.join(_td, 'vd.ll')
open(_vd, 'w').write("""define void @function_x(i64 %0) {
  %48 = add i64 %0, 104
  %49 = inttoptr i64 %48 to i128*
  %50 = load i128, i128* %49, align 8
  call void @__asm_movups(i128 %50, i128 %47)
  ret void
}
""")
_rc, _o = _run('ir_fix_vstore.py', _vd, _vd + '.off')
check('fix_vstore: 既定 (--direct なし) では非 alloca 宛先を触らず unresolved に数える', json.loads(_o)['vstore_unresolved'] == 1 and 'store i128' not in open(_vd + '.off').read(), _o)
_rc, _o = _run('ir_fix_vstore.py', _vd, _vd + '.on', '--direct')
_t = open(_vd + '.on').read()
check('fix_vstore: --direct で非 alloca 宛先の helper 呼出しを store i128 に置換 (使用 2 箇所のみ)', json.loads(_o)['vstore_direct'] == 1 and 'store i128 %47, i128* %49' in _t and '__asm_movups' not in _t, _o)

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
        # #514/#530: 書換え後の関数 range + stub が連続配置 ([a,b)+[b,c)) だと RetDec --select-ranges が併合して define が落ちる
        spans = sorted([(int(a, 16), int(b, 16)) for a, b in m['func_range_new'].values()]
                       + [(m['stub'], m['stub'] + m['stub_len']), (m['comis_stub'], m['comis_stub'] + m['comis_stub_len'])])
        contig = [(hex(a[1]), hex(b[0])) for a, b in zip(spans, spans[1:]) if a[1] == b[0]]
        check('rewrite 関数 range が連続配置でない (#514)', not contig, '%d 組: %s' % (len(contig), contig[:3]))
        # 書換え後 PE 上で、元の site 位置が展開されている (call stub が存在)
        img2 = A.Image(out)
        check('新 section が PE に追加', any(s[3] == '.icall' for s in img2.secs))
    else:
        print('SKIP pe tests (work/route/F.txt が無い: bash ott_route.sh を先に)')
else:
    print('SKIP pe tests (OTT DLL 無し)')
print('RESULT %s (%d failed)' % ('PASS' if not fails else 'FAIL', len(fails)))
sys.exit(1 if fails else 0)
