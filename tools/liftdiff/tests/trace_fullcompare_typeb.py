#!/usr/bin/env python3
"""LD-27 (#1034): m11 unreachable の型 B (L が leaf) 食い違いを、完全 trace で再確認する。

batch jsonl の trace_head (最大 12 件) は native/wasm の先頭から切られるため、
最後の共通 entry L の求め方が不正確になりうる。本スクリプトは対象 case を
xfill 既定 (1) と xfill=0 の両方で、ランナの完全 trace を取り直して比較する。

  python3 tools/liftdiff/tests/trace_fullcompare_typeb.py TARGET.json [batch.jsonl]

TARGET.json は targets/m11.json を使う (pe は ${FL_WIN64_DIR}/extracted/block00031_PE.bin を指す)。
入力 batch 既定 = tools/liftdiff/work/m11/batch_closure.jsonl。ビルド済み work/ を要する (再ビルドはしない)。
結果は stdout に出す (results/ への書き込みはしない)。
class: X = xmm0 入力の脱落 (呼出元/L の entry で xmm0 を読み、x0 が native≠wasm) / M = L が MXCSR 系 (0x40a380 / 0x40a3b0) / R = 未特定。
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from liftdiff import Session  # noqa: E402
from ldlib import cases  # noqa: E402
import capstone  # noqa: E402
from capstone import x86_const as X  # noqa: E402

target = sys.argv[1]
batch = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'work/m11/batch_closure.jsonl')
sess = Session(target, shards=1, build=False, trace=True)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def leaf(va):
    """ret/int3 まで call 無しなら True (型 B の判定。trace_diverge_unreachable.py と同一)。"""
    for ins in md.disasm(sess.pe.read(va - sess.pe.base, 0x600), va):
        if ins.id == X.X86_INS_CALL:
            return False
        if ins.id in (X.X86_INS_RET, X.X86_INS_INT3):
            break
    return True


def first_div_L(N, W):
    """(L, L の位置) を返す。L は最後の共通 entry (位置は共通接頭辞の末尾)。"""
    i = 0
    while i < len(N) and i < len(W) and N[i] == W[i]:
        i += 1
    if i == len(N) == len(W) or i == 0:
        return None, None
    return N[i - 1], i - 1


WRITE_ONLY = {'movsd', 'movss', 'movaps', 'movapd', 'movups', 'movupd', 'movq', 'movd', 'movdqa', 'movdqu',
              'cvtsi2sd', 'cvtsi2ss', 'cvtss2sd', 'cvtsd2ss', 'cvttsd2si', 'pxor', 'xorps', 'xorpd', 'movlpd', 'movhpd'}


def reads_xmm0(f):
    """f の本体で xmm0 が「書かれる前に読まれる」なら True (xmm0 の入力 = 署名外の引数の読み)。"""
    for ins in md.disasm(sess.pe.read(f - sess.pe.base, 0x400), f):
        if ins.id == X.X86_INS_RET:
            return False
        ops = [o.strip() for o in ins.op_str.split(',')]
        if 'xmm0' not in ins.op_str:
            continue
        if ops[0] == 'xmm0' and ins.mnemonic in WRITE_ONLY:
            return False
        return True
    return False


def r_kind(L, caller, ir_by_fn, mach):
    """R 類の D15 判定 (trace_diverge_unreachable.py §1 より広い: 呼出元も見る)。L または呼出元が、機械語のメモリ間接 call を持ち、
    IR の call 数 ≤ 機械語の直接 call 先数 なら 'D15' (メモリ間接 call 脱落の候補)。それ以外は 'other' (ldfix 型は未判定)。"""
    for v in (L, caller):
        if v is None:
            continue
        d, mi, _ = mach(v)
        body = ir_by_fn.get('function_%x' % v)
        if body is None:
            continue
        ic = len(re.findall(r'\bcall\b', body))
        if mi > 0 and ic <= len(d):
            return 'D15'
    return 'other'


def call_site(caller, L):
    """caller の本体で L への直接 call 命令の番地 (最初の 1 件) と、その後の最初の jcc と分岐先を返す。"""
    if caller is None:
        return None, None, None
    ins_list = list(md.disasm(sess.pe.read(caller - sess.pe.base, 0x800), caller))
    for k, ins in enumerate(ins_list):
        if ins.id == X.X86_INS_CALL and ins.op_str == '0x%x' % L:
            after = ins_list[k + 1:k + 9]
            text = ' ; '.join('%s %s' % (a.mnemonic, a.op_str) for a in after[:4])
            jcc = next(((a.mnemonic, a.op_str) for a in after if a.mnemonic.startswith('j') and a.mnemonic != 'jmp'), None)
            return ins.address, text, jcc
    return None, None, None


IR_PATH = os.environ.get('LD_M11_IR') or os.path.join(ROOT, '../m11/work/boot_final3.ll')


def load_ir(path):
    """boot_final3.ll の function_<va> 本体 (define から閉じ括弧まで) を {名前: テキスト} で返す。"""
    out, cur, buf = {}, None, []
    for line in open(path):
        if cur is None:
            if line.startswith('define ') and '@function_' in line:
                cur = line.split('@', 1)[1].split('(', 1)[0]
                buf = [line]
        else:
            buf.append(line)
            if line.startswith('}'):
                out[cur] = ''.join(buf)
                cur = None
    return out


def mach(va):
    """trace_diverge_unreachable.py の mach と同一: (直接 call 先集合, メモリ間接 call 数, レジスタ間接 call 数)。"""
    direct, mem_ind, reg_ind = set(), 0, 0
    for i in md.disasm(sess.pe.read(va - sess.pe.base, 0x600), va):
        if i.id == X.X86_INS_CALL:
            op = i.operands[0]
            if op.type == X.X86_OP_IMM:
                direct.add(op.imm)
            elif op.type == X.X86_OP_MEM:
                if op.mem.base != X.X86_REG_RIP:
                    mem_ind += 1
            else:
                reg_ind += 1
        if i.id in (X.X86_INS_RET, X.X86_INS_INT3):
            break
    return direct, mem_ind, reg_ind


IRS = load_ir(IR_PATH)
rkinds = collections.Counter()
items = []
for line in open(batch):
    r = json.loads(line)
    cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
    if not (cs and (cs[0].get('wasm_detail') or '').startswith('unreachable') and cs[0].get('wasm_status') != 'badjson'):
        continue
    c = cs[0]
    N = [int(t[0], 16) for t in c['raw']['native']['trace_head']]
    W = [int(t[0], 16) for t in c['raw']['wasm']['trace_head']]
    L, _ = first_div_L(N, W)
    if L is None or not leaf(L):
        continue
    items.append((int(r['function']['va'], 16) if isinstance(r['function']['va'], str) else r['function']['va'], c['pattern'], L))

print('# 型 B 候補 %d case (trace_head 基準の L が leaf)' % len(items))
nat, was = sess.make_runners()
rows = []
RP = os.environ.get('LD_RETPROBE_OUT')   # LD-220 (#4466): 戻り値の直接計測 (ld_native の LD_RETPROBE_VA=40a3d0 と併用)
rp_stat = collections.Counter()


def rp_lines(pos):
    """native 1 run の間に追記された rp 行 (rp run=... rax=...) を dict のリストで返す。"""
    if not RP or not os.path.exists(RP):
        return []
    with open(RP) as f:
        f.seek(pos)
        return [dict(t.split('=', 1) for t in l.split()[1:]) for l in f if l.startswith('rp ')]


try:
    for fva, pat, L in items:
        name = sess.fn_name(fva)
        sig = sess.sigs.get(name)
        if not sig or not sig['defined']:
            print('fn=0x%x pat=%s skipped (no sig)' % (fva, pat))
            continue
        for xf in (True, False):
            line = cases.case_line(fva, name, pat, sig, trace=True, xfill=xf)
            pos = os.path.getsize(RP) if RP and os.path.exists(RP) else 0
            rn = nat.run_cases([line], ['n'])[0]
            RL = rp_lines(pos)
            rw = was.run_cases([line], ['w'])[0]
            TN = rn.get('trace', [])
            TW = rw.get('trace', [])
            N = [int(t[0], 16) for t in TN]
            W = [int(t[0], 16) for t in TW]
            Lf, i = first_div_L(N, W)
            nxt = caller = lx = cx = None
            if Lf is not None:
                nxt = (N[i + 1] if i + 1 < len(N) else None, W[i + 1] if i + 1 < len(W) else None)
                lx = (TN[i][10], TW[i][10])
                if i >= 1:
                    caller = N[i - 1]
                    cx = (TN[i - 1][10], TW[i - 1][10])
            typ = ('B' if leaf(Lf) else 'notB') if Lf is not None else '-'
            site, post, jcc = call_site(caller, Lf) if Lf is not None else (None, None, None)
            if Lf is None:
                cls = '-'
            elif Lf in (0x40a380, 0x40a3b0):
                cls = 'M'
            elif (cx and cx[0] != cx[1] and reads_xmm0(caller)) or (lx[0] != lx[1] and reads_xmm0(Lf)):
                cls = 'X'
            else:
                cls = 'R'
            rows.append((xf, cls, Lf, caller))
            if cls == 'R':
                rk = r_kind(Lf, caller, IRS, mach)
                rkinds[(1 if xf else 0, rk)] += 1
            if Lf == 0x40a3d0 and RP:
                k = N[:i + 1].count(0x40a3d0) - 1   # L の entry が、trace 上で何回目の 0x40a3d0 呼出しか
                if k >= len(RL):
                    rp_stat['count_mismatch'] += 1
                    print('   RAX fn=0x%x xfill=%d k=%d probe_calls=%d (不一致・比較しない)' % (
                        fva, 1 if xf else 0, k, len(RL)))
                else:
                    measured = int(RL[k]['rax'], 16)
                    derived = int(lx[0], 16) >> 48
                    rp_stat['match' if measured == derived else 'differ'] += 1
                    print('   RAX fn=0x%x xfill=%d k=%d measured_rax=0x%x derived_rax=0x%x rsp_delta=%s ret_rva=%s %s' % (
                        fva, 1 if xf else 0, k, measured, derived, RL[k]['rsp_delta'], RL[k]['ret_rva'],
                        'MATCH' if measured == derived else 'DIFF'))
            print('fn=0x%x pat=%s xfill=%d class=%s L_full=%s typeB_full=%s next(native,wasm)=%s native=%s wasm=%s' % (
                fva, pat, 1 if xf else 0, cls,
                ('0x%x' % Lf) if Lf is not None else '-',
                typ,
                tuple(('0x%x' % v) if v is not None else '-' for v in nxt) if nxt else '-',
                rn.get('status'), rw.get('status')))
            print('   L_x0(native,wasm)=%s caller=%s call@%s caller_x0(native,wasm)=%s post=[%s] jcc=%s' % (
                ('%s,%s' % lx) if lx else '-',
                ('0x%x' % caller) if caller is not None else '-',
                ('0x%x' % site) if site is not None else '-',
                ('%s,%s' % cx) if cx else '-',
                post or '-',
                ('%s %s' % jcc) if jcc else '-'))
    print('## 集計 (xfill, class): %s' % sorted(collections.Counter((int(x), c) for x, c, _, _ in rows).items()))
    print('## R 類の D15 判定 (xfill, 判定): %s' % sorted(rkinds.items()))
    if RP:
        print('## rax 直接計測 (LD-220): %s' % sorted(rp_stat.items()))
finally:
    nat.close()
    was.close()
