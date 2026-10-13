#!/usr/bin/env python3
"""IPP-11 (#473): FL win64 全モジュールの ippsVectorSlope_32f/_64f 呼出箇所で、出力先 (第 1 引数 rcx) の由来を静的に分類する。
入力: $FL_WIN64_DIR/extracted/block*_PE.bin (fl-win64 素材)。依存: numpy / pefile / capstone (pip)。
方法: scan_x64.analyze (Delphi の ipp 変数表 → 呼出箇所 ≤3 件/関数/モジュール) → sigscan.window で呼出直前の命令列を復元 →
      rcx を最後に書く命令を分類し、`mov rcx,reg` は同一ブロック内を 1 段だけ遡って reg の由来を分類する。
出力: work/vslope_callsite_survey.json (集計) と標準出力。静的・局所ヒューリスティック (実行時アライメントの実測ではない)。
使い方: python3 vslope_callsite_survey.py   (cwd 不問。macho_util は未使用のためスタブを差し込む)"""
import collections, glob, json, os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__)); IPP = os.path.dirname(HERE)
sys.modules['macho_util'] = types.SimpleNamespace(MachO=None)
sys.path.insert(0, IPP); sys.path.insert(0, os.path.join(IPP, '..', 'shared')); sys.path.insert(0, HERE)
import scan_x64
from paths import FL_WIN64_DIR
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_MEM, X86_OP_REG, X86_OP_IMM, X86_REG_RCX, X86_REG_ECX, X86_REG_RSP, X86_REG_RBP, X86_REG_RIP

cs = Cs(CS_ARCH_X86, CS_MODE_64); cs.detail = True
STOP = ('call', 'ret', 'jmp')
CALLEE_SAVED = {'rbx', 'rbp', 'rdi', 'rsi', 'r12', 'r13', 'r14', 'r15', 'ebx', 'edi', 'esi', 'r12d', 'r13d', 'r14d', 'r15d'}
RCX = {X86_REG_RCX, X86_REG_ECX}
NAMES = ('ippsVectorSlope_32f', 'ippsVectorSlope_64f')

def window(m, st):
    """st に正確に着地する最長の逆アセンブル開始点を選ぶ (sigscan.window と同じ)。"""
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

def writes(i, regs):
    try: _, w = i.regs_access()
    except Exception: return False
    return bool(set(w) & regs)

def regname(i, r): return i.reg_name(r)

def classify(i, seq, idx, ext=None, depth=0):
    """i = rcx を最後に書いた命令。戻り値 = (カテゴリ, 補足)。"""
    ops = i.operands
    if i.mnemonic == 'lea' and ops[1].type == X86_OP_MEM:
        m = ops[1].mem; b = regname(i, m.base) if m.base else None
        if m.base == X86_REG_RSP: return 'lea rcx,[rsp+d] (stack local)', f'd%16={m.disp % 16}'
        if m.base == X86_REG_RIP: return 'lea rcx,[rip+d] (global)', ''
        if m.index == 0: return f'lea rcx,[{b}+d] (base reg + const)', f'd%16={m.disp % 16}'
        return f'lea rcx,[{b}+idx*{m.scale}+d] (indexed)', f'd%16={m.disp % 16} scale={m.scale}'
    if i.mnemonic == 'mov' and ops[1].type == X86_OP_MEM:
        m = ops[1].mem; b = regname(i, m.base) if m.base else None
        return f'mov rcx,[{b}+d] (pointer load)' if m.base != X86_REG_RIP else 'mov rcx,[rip+d] (global ptr load)', f'd%16={m.disp % 16}'
    if i.mnemonic == 'mov' and ops[1].type == X86_OP_REG:
        if depth >= 1: return 'mov rcx,reg (unresolved)', ''
        src = ops[1].reg; srcs = {src}
        for j in range(idx - 1, -1, -1):
            if writes(seq[j], srcs) and seq[j].operands and seq[j].operands[0].type == X86_OP_REG:
                c, n = classify_src(seq[j])
                return 'mov rcx,reg <- ' + c, n
        # 呼出直前の窓 (前の call まで) に無い場合: callee-saved reg なら call をまたいで遡る
        if ext is not None and regname(i, src) in CALLEE_SAVED:
            k = max(n for n, x in enumerate(ext) if x.address == i.address)
            for j in range(k - 1, -1, -1):
                if writes(ext[j], srcs) and ext[j].operands and ext[j].operands[0].type == X86_OP_REG:
                    c, n = classify_src(ext[j])
                    return 'mov rcx,reg <- ' + c + ' (across call)', n
        return 'mov rcx,reg (source outside window)', ''
    return f'other ({i.mnemonic})', ''

def classify_src(j):
    ops = j.operands
    if j.mnemonic == 'lea' and ops[1].type == X86_OP_MEM:
        m = ops[1].mem
        if m.base == X86_REG_RSP: return 'lea [rsp+d] (stack local)', f'd%16={m.disp % 16}'
        return ('lea [reg+idx*s+d]' if m.index else 'lea [reg+d]'), f'd%16={m.disp % 16}'
    if j.mnemonic == 'mov' and ops[1].type == X86_OP_MEM: return 'mov reg,[mem] (pointer load)', f'd%16={ops[1].mem.disp % 16}'
    if j.mnemonic == 'mov' and ops[1].type == X86_OP_REG: return 'mov reg,reg2', ''
    if j.mnemonic in ('add', 'sub'): return f'{j.mnemonic} reg (pointer arithmetic)', ''
    return f'{j.mnemonic}', ''

def survey(path):
    try: r = scan_x64.analyze(path, 'pe')
    except Exception: return None
    if not r or not r.get('table'): return []
    m = scan_x64.PEImg(path); out = []
    for e in r['table']:
        if e['name'] not in NAMES: continue
        for st in e['call_sites']:
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
                if i.mnemonic in ('ret', 'jmp') or i.mnemonic.startswith('j'): break
            if not fwd or fwd[-1].mnemonic != 'call': out.append((e['name'], 'no call found in window', '', os.path.basename(path), st)); continue
            full = seq + fwd[:-1]
            ext = []
            for i in reversed(pre):
                if i.mnemonic in ('ret', 'jmp'): break
                ext.append(i)
            ext = ext[::-1] + fwd[:-1]
            last = None
            for k in range(len(full) - 1, -1, -1):
                if writes(full[k], RCX): last = k; break
            if last is None: out.append((e['name'], 'rcx not set in window', '', os.path.basename(path), st)); continue
            c, n = classify(full[last], full, last, ext)
            out.append((e['name'], c, n, os.path.basename(path), st))
    return out

if __name__ == '__main__':
    from multiprocessing import Pool
    ext = os.path.join(FL_WIN64_DIR, 'extracted')
    files = sorted(glob.glob(os.path.join(ext, 'block*_PE.bin')))
    with Pool(int(os.environ.get('JOBS', '4'))) as p: res = p.map(survey, files)
    nerr = sum(1 for rr in res if rr is None)
    rows = [r for rr in res if rr for r in rr]
    summ = {n: collections.Counter() for n in NAMES}
    detail = {n: collections.Counter() for n in NAMES}
    for n, c, note, f, st in rows: summ[n][c] += 1; detail[n][(c, note)] += 1
    os.makedirs(os.path.join(IPP, 'work'), exist_ok=True)
    json.dump({'modules': len(files), 'rows': rows}, open(os.path.join(IPP, 'work', 'vslope_callsite_survey.json'), 'w'))
    print('modules scanned:', len(files), ' unanalyzable (no .text etc.):', nerr, ' sites:', {n: sum(summ[n].values()) for n in NAMES}, ' modules with sites:', len({r[3] for r in rows}))
    for n in NAMES:
        print('==', n)
        for c, k in summ[n].most_common(): print(f'  {k:4d}  {c}')
        for (c, note), k in detail[n].most_common(12):
            if note: print(f'        {k:4d}  {c}  [{note}]')
