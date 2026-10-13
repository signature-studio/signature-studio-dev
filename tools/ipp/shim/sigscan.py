#!/usr/bin/env python3
"""win64 FL 全モジュールの IPP 呼出箇所から「引数レジスタ使用実績」を採取する (署名の独立証拠)。
入力: ../work/win_refs.json (scan_win.py 生成; 各関数 ≤3 呼出箇所/モジュールの mov r,[slot] 位置 VA)
方法: 呼出箇所 st (mov/lea r,[VAR]) の直前 ≤160B を再同期しつつ逆アセンブル、直前の call/ret/jmp 以降〜対応 call までに
      MS x64 引数レジスタ (rcx/rdx/r8/r9 = GPR, xmm0-3 = FP) と [rsp+0x20..] (スタック引数) へ書かれた位置を集計 (stack[w] = 第 5+w 引数スロットへ書込みのあった呼出箇所数)。
出力: data/callsite_evidence.json = {name: {sites, gp:[slot->回数], xmm:[slot->回数], stack:[w->回数]}}
注意: 静的・局所ヒューリスティック (レジスタ生存は見ない)。arity の下限と float 位置の傍証であり、署名そのものではない。"""
import json, os, sys, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); IPP = os.path.dirname(HERE)
sys.path.insert(0, IPP)
sys.path.insert(0, os.path.join(IPP, '..', 'shared'))
from paths import FL_WIN64_DIR
from scan_x64 import PEImg
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import *
cs = Cs(CS_ARCH_X86, CS_MODE_64); cs.detail = True
EXT = os.path.join(FL_WIN64_DIR, 'extracted')
GP = [{X86_REG_RCX, X86_REG_ECX, X86_REG_CX, X86_REG_CL}, {X86_REG_RDX, X86_REG_EDX, X86_REG_DX, X86_REG_DL},
      {X86_REG_R8, X86_REG_R8D, X86_REG_R8W, X86_REG_R8B}, {X86_REG_R9, X86_REG_R9D, X86_REG_R9W, X86_REG_R9B}]
XM = [{X86_REG_XMM0, X86_REG_YMM0}, {X86_REG_XMM1, X86_REG_YMM1}, {X86_REG_XMM2, X86_REG_YMM2}, {X86_REG_XMM3, X86_REG_YMM3}]
STOP = ('call', 'ret', 'jmp')

def window(m, st):
    """st に正確に着地する最長の逆アセンブル開始点を選ぶ (再同期)。"""
    for back in range(160, 0, -1):
        off = m.va2off(st - back)
        if off is None: continue
        ins = list(cs.disasm(m.d[off:off + back + 16], st - back, 0))
        pre = []
        for i in ins:
            if i.address == st: return pre, ins[len(pre):]
            if i.address > st: break
            pre.append(i)
    off = m.va2off(st); return [], list(cs.disasm(m.d[off:off + 200], st, 0))

def one(m, st):
    pre, post = window(m, st)
    seq = []
    for i in reversed(pre):
        if i.mnemonic in STOP or i.mnemonic.startswith('j'): break
        seq.append(i)
    seq.reverse()
    fwd = []
    for i in post:
        fwd.append(i)
        if i.mnemonic == 'call': break
        if i.mnemonic in ('ret', 'jmp') or i.mnemonic.startswith('j'): return None
    if not fwd or fwd[-1].mnemonic != 'call': return None
    gp, xm, stack = set(), set(), set()
    for i in seq + fwd[:-1]:
        _, w = i.regs_access()
        for k in range(4):
            if GP[k] & set(w): gp.add(k)
            if XM[k] & set(w): xm.add(k)
        if i.operands and i.operands[0].type == X86_OP_MEM and i.operands[0].mem.base == X86_REG_RSP and i.mnemonic in ('mov', 'movss', 'movsd', 'movaps', 'movups', 'movq', 'movd'):
            d = i.operands[0].mem.disp
            if 0x20 <= d < 0x80: stack.add((d - 0x20) // 8)
    return gp, xm, stack

def work(f):
    r = collections.defaultdict(lambda: {'sites': 0, 'gp': [0] * 4, 'xmm': [0] * 4, 'stack': [0] * 12})
    try: m = PEImg(f'{EXT}/{f}')
    except Exception: return {}
    for e in REFS[f].get('table', []):
        for st in e['call_sites']:
            try: res = one(m, st)
            except Exception: res = None
            if not res: continue
            gp, xm, stk = res; x = r[e['name']]; x['sites'] += 1
            for w in stk: x['stack'][w] += 1
            for k in gp: x['gp'][k] += 1
            for k in xm: x['xmm'][k] += 1
    return dict(r)

REFS = json.load(open(f'{IPP}/work/win_refs.json'))
if __name__ == '__main__':
    mods = [f for f, v in REFS.items() if v and v.get('entries')]
    agg = collections.defaultdict(lambda: {'sites': 0, 'gp': [0] * 4, 'xmm': [0] * 4, 'stack': [0] * 12, 'modules': 0})
    with Pool(12) as p:
        for res in p.map(work, mods):
            for n, x in res.items():
                a = agg[n]; a['sites'] += x['sites']; a['modules'] += 1
                for k in range(12): a['stack'][k] += x['stack'][k]
                for k in range(4): a['gp'][k] += x['gp'][k]; a['xmm'][k] += x['xmm'][k]
    json.dump(dict(sorted(agg.items())), open(f'{HERE}/data/callsite_evidence.json', 'w'), indent=0)
    print(f'modules {len(mods)}  functions with evidence {len(agg)}  sites {sum(a["sites"] for a in agg.values())}')
