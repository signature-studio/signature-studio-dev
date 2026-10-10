#!/usr/bin/env python3
"""k80_argfix.py — kernel lift IR の ARG (引数接続) 修復 pass (P0c-2「ARG pass 再適用」)。

  python3 k80_argfix.py IN.ll OUT.ll --abi k80abi.json [--report r.json]

RetDec が落とす引数を機械語 ABI 走査 (k80abi.py: win64 slot の read-before-write) と
突き合わせて再接続する。対象 pattern (m7 ir7/ir8 の F2 系欠陥修復の kernel 版):

  [A] movd-from-zero: `%Z = xor i128 0, 0` が `call iN @__asm_movX*(i128 %Z)` にのみ
      使われる (xmm 読込疑似 call に入力が繋がっていない; 0x5de620/0x5de660/
      0x5dffc0/0x5dfff0/0x5dfa40)。
      → 機械語の xmm slot (読み出し順) を新引数 (i64 = f32 bits) として追加し
        %Z = zext (trunc param) to i128 へ置換 (helper 構造は保持)。

  [B] spill 初期化落ち:
      B1: `alloca T` が load されるが関数内に store が無い (0x5de3e0 の xmm0 spill)
      B2: reg2mem (%rcx.0.reg2mem 等) に entry block の store が無い
          (loop 退避の初期値 = 引数が落ちた; 0x5e03f0 / 0x5e0350)
      → alloca 名がレジスタ名を含む場合はその slot、float/double は機械語の
        未割当 xmm slot に対応する引数を追加し entry block 先頭で store する。

引数は既存 RetDec 引数の **末尾に追記** (既存参照を壊さない; m7 ir7 と同じ規約)。
適用後は llvm-as 通過を推奨 (idempotent: 追加済みの store/引数は再適用しない)。
"""
import argparse
import json
import re

SLOT_GPR = ['rcx', 'rdx', 'r8', 'r9']
SLOT_XMM = ['xmm0', 'xmm1', 'xmm2', 'xmm3']


def func_name(header):
    m = re.search(r'@([\w.$-]+)\(', header)
    return m.group(1) if m else None


def append_param(header, decl):
    """define の引数リスト末尾へ decl (例: 'i64 %in.rcx') を追記。"""
    if decl in header:
        return header
    m = re.search(r'\(([^)]*)\)(\s*(?:local_unnamed_addr|#\d+)?\s*\{)\s*$', header)
    if not m:
        return header
    args = m.group(1).strip()
    newargs = (args + ', ' if args else '') + decl
    return header[:m.start()] + '(' + newargs + ')' + m.group(2) + '\n'


def entry_insert(body, stmts):
    """entry block に stmts を挿入 (既存なら何もしない)。
    alloca はブロック先頭に集める規約に従い, entry 内の最後の alloca 行の後に挿入する。"""
    for s in stmts:
        if s.strip() in body:
            return body
    lines = body.split('\n')
    idx = 0
    for i, ln in enumerate(lines):
        if re.match(r'^[\w.$-]+:\s*(;.*)?$', ln):
            idx = i + 1
            break
    # entry 内の最後の alloca の直後に置く (use-before-def 防止)
    j = idx
    for k in range(idx, len(lines)):
        if re.match(r'\s*[\w.$-]+:\s*(;.*)?$', lines[k]) or re.match(r'\s*(br|switch|ret|call)\b', lines[k]):
            break
        if re.match(r'\s*%[\w.$-]+ = alloca\b', lines[k]):
            j = k + 1
    lines[j:j] = stmts
    return '\n'.join(lines)


def entry_block_lines(lines):
    """最初の br/switch まで (entry block) の行。"""
    out = []
    for ln in lines:
        out.append(ln)
        if re.match(r'\s*br\s', ln) or re.match(r'\s*switch\s', ln):
            break
    return out


def fix_movd_from_zero(header, body, habi, rep, fname):
    """[A] xor i128 0,0 → __asm_movX のみ使用 → xmm slot 引数を追加。"""
    changed = False
    for _round in range(8):
        lines = body.split('\n')
        defs = []
        for ln in lines:
            m = re.match(r'^(\s*)(%[\w.$-]+) = xor i128 0, 0\s*$', ln)
            if m:
                defs.append((m.group(1), m.group(2), ln))
        if not defs:
            break
        fixed_any = False
        for ind, z, dline in defs:
            esc = re.escape(z)
            uses = [l for l in lines if re.search(r'(?<![\w.%-])' + esc + r'(?![\w.-])', l) and l != dline]
            if not uses:
                continue
            calls = [l for l in uses if re.search(r'call (?:i32|i64) @__asm_mov\w*\(i128 ' + esc + r'\)', l)]
            if len(calls) != len(uses):
                continue
            site = rep['movd_sites'].get(fname, 0)
            xs = [x for x in habi.get('xmm_slots', []) if int(x[3:]) < 4]
            xmm = xs[site] if site < len(xs) else SLOT_XMM[min(site, 3)]
            rep['movd_sites'][fname] = site + 1
            pname = '%%in.%s.bits' % xmm
            helper = re.search(r'@(__asm_mov\w*)', calls[0]).group(1)
            if 'movd' in helper:
                stmts = ['  %%trunc.%s = trunc i64 %s to i32' % (pname[1:], pname),
                         '  %s = zext i32 %%trunc.%s to i128' % (z, pname[1:])]
            else:                                          # movq 等は 64bit
                stmts = ['  %s = zext i64 %s to i128' % (z, pname)]
            body = body.replace(dline, '\n'.join(stmts))
            header = append_param(header, 'i64 %s' % pname)
            rep['movd_fixed'] += 1
            changed = True
            fixed_any = True
        if not fixed_any:
            break
    return header, body, changed


def fix_orphan_alloca(header, body, habi, rep, fname):
    """[B] spill 初期化落ち (B1: store 全無し / B2: reg2mem の entry store 無し)。"""
    lines = body.split('\n')
    changed = False
    used_xmm = [x for x in habi.get('xmm_slots', []) if int(x[3:]) < 4]
    entry = entry_block_lines(lines)
    for ln in list(lines):
        m = re.match(r'^\s*(%[\w.$-]+) = alloca (float|double|i64)\s*$', ln)
        if not m:
            continue
        aname, ty = m.group(1), m.group(2)
        esc = re.escape(aname)
        stores = [l for l in lines if re.search(r'store [^,]+, (?:ptr|' + ty + r'\*) ' + esc + r'\s*(,|$)', l)]
        loads = [l for l in lines if re.search(r'= load [\w]+, [\w\*]+ ' + esc + r'\s*(,|$)', l)]
        if not loads or stores:
            # store が有る場合は reg2mem の entry store 欠落のみ見る (B2)
            if stores and not any(re.search(r'store [^,]+, (?:ptr|' + ty + r'\*) ' + esc + r'\s*(,|$)', l) for l in entry):
                reg = None
                for g in SLOT_GPR:
                    if re.match(r'%' + g + r'\.0\.', aname):
                        reg = g
                        break
                if reg is None or ty in ('float', 'double'):
                    continue                               # 名前で slot を決められない GPR case は触らない
                pname = '%%in.%s' % reg
                body = entry_insert(body, ['  store i64 %s, ptr %s' % (pname, aname)])
                header = append_param(header, 'i64 %s' % pname)
                rep['orphan_gpr_fixed'] += 1
                changed = True
            continue
        # B1: store 全無し (orphan spill)
        reg = None
        for x in SLOT_XMM:
            if re.match(r'%' + x + r'(\.|$)', aname[1:]):
                reg = x
                break
        for x in SLOT_GPR:
            if reg is None and re.match(r'%' + x + r'\.0\.', aname):
                reg = x
        if reg is None:
            if ty in ('float', 'double'):
                reg = used_xmm[0] if used_xmm else 'xmm0'
            else:
                reg = habi.get('gpr_slots', ['rcx'])[0] if habi.get('gpr_slots') else 'rcx'
        if reg in SLOT_XMM and ty in ('float', 'double'):
            pname = '%%in.%s' % reg
            body = entry_insert(body, ['  store %s %s, ptr %s' % (ty, pname, aname)])
            header = append_param(header, '%s %s' % (ty, pname))
        elif reg in SLOT_GPR and ty == 'i64':
            pname = '%%in.%s' % reg
            body = entry_insert(body, ['  store i64 %s, ptr %s' % (pname, aname)])
            header = append_param(header, 'i64 %s' % pname)
        else:
            continue                                       # i128 等は非対応 (REPORT 限界)
        rep['orphan_float_fixed' if ty in ('float', 'double') else 'orphan_gpr_fixed'] += 1
        changed = True
    return header, body, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--abi')
    ap.add_argument('--report')
    a = ap.parse_args()
    abi = json.load(open(a.abi)) if a.abi else {}
    rep = {'movd_sites': {}, 'movd_fixed': 0, 'orphan_float_fixed': 0, 'orphan_gpr_fixed': 0, 'funcs': {}}

    text = open(a.src, errors='replace').read()
    starts = [m.start() for m in re.finditer(r'(?m)^define [^\n]*\{', text)]
    head = text[:starts[0]] if starts else text
    chunks = []
    for k, s in enumerate(starts):
        e_next = starts[k + 1] if k + 1 < len(starts) else len(text)
        seg = text[s:e_next]
        nl = seg.index('\n') + 1
        header = seg[:nl]
        rest = seg[nl:]
        mclose = rest.rindex('\n}\n')
        chunks.append([header, rest[:mclose], rest[mclose + 3:]])

    out = [head]
    for header, body, inter in chunks:
        fname = func_name(header)
        va = '0x' + fname.split('_')[1] if fname and fname.startswith('function_') else None
        habi = abi.get(va, {}) if va else {}
        h2, b2, c1 = fix_movd_from_zero(header, body, habi, rep, fname or '')
        h3, b3, c2 = fix_orphan_alloca(h2, b2, habi, rep, fname or '')
        if c1 or c2:
            rep['funcs'][fname] = {'movd': c1, 'orphan': c2}
        out.append(h3 + b3 + '\n}\n' + inter)

    result = ''.join(out)
    open(a.dst, 'w').write(result)
    if a.report:
        r2 = dict(rep)
        r2['movd_sites'] = dict(rep['movd_sites'])
        json.dump(r2, open(a.report, 'w'), indent=1)
    print('[k80_argfix]', json.dumps({k: v for k, v in rep.items() if k != 'movd_sites'}))


if __name__ == '__main__':
    main()
