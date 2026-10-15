#!/usr/bin/env python3
"""m6_full_extract.py (M6b): full DLL lift (work/full_t1.drc.ll) から関数を抽出し
m6 build IR (work/ott_memfix0.ll) へ splice する。

背景: closure lift (--select-ranges) は runtime から呼ばれる closure 内関数の
一部しか lift せず (declare-only), 実体は full lift (typed pointer 版 LLVM IR,
旧 RetDec 出力) にある。そこでこのパス:

  (1) define block 抽出
  (2) typed-pointer → ptr (LLVM opaque 対応)
  (3) helper 名 normalize: full lift の番号系列 (suffix) は closure と異なる
      ため, ここでは「signature 同型」の closure declare へ寄せる。寄せ先が
      無い helper名はそのまま残し, その型で memfix 側に declare を追補して
      gen_msimd6.py に実装させる。
  (4) @global_var_18xxxx 名と i64 純値 (VA) を --newbase (既定 0x30000000) 系へ shift
      (ir6_shift.py と同幅: BASE 0x180000000 → NEWBASE を ir6_shift と同処理
      の差替 — ただし抽出分の IR 内では 手動に同code 重複せず ir6_shift スタイル
      の直代入)。
  (5) extract 先関数の内部 call のうち memfix に define / declare が無いものを
      報告 (次の抽出対象)。

使い方: python3 m6_full_extract.py OUT.ll FNAME [FNAME...]
"""
import re
import sys
from typing import Any

FULL = 'work/full_t1.drc.ll'
MEMFIX = 'work/ott_memfix0.ll'

# 外部 helpers: full name → closure name (sig 同型前提)
HELPER_RENAME = {
    'movss': 'movss__17',      # full: (i128)->i64 extract / closure: 同形
    'movss.8': 'movss',        # (i32)->i128 load 形 (closure plain 同形)
    'movsd.4': 'movsd__2',     # (i128)->i64 extract
    'movaps.7': 'movaps__4',   # (i128)->i128 identity
    'mulss.9': 'mulss__18',    # (i128,i32)->i128
    'mulsd.10': 'mulsd__8',    # (i128,i128)->i128
    'divsd.12': 'divsd',       # (i128,i128)->i128 (closure plain)
    'movapd.22': 'movapd__5',
    'movdqa.6': 'movdqa',      # same sig (i128)->i64
    'movdqu.5': 'movdqu__3',
    'movups.3': 'movups__1',
    'subss.19': 'subss__35',   # (i128,i32)->i128
    'addss.14': 'addss__31',
    'addsd.13': 'addsd',       # (i128,i64)->i128
    'subsd.11': 'subsd',
    'vaddsd.25': 'vaddsd',     # (i128,i128)
    'vmulsd.30': 'vmulsd',     # (i128,i64)
    'vsubsd.39': 'vsubsd',
    'vfmadd213sd.27': 'vfmadd213sd',
    'vfmadd231sd.34': 'vfmadd231sd',
    'vfmadd132sd.26': 'vfmadd132sd',
    'vfnmadd231sd.59': 'vfnmadd231sd',
    'vfmsub213sd.58': 'vfmsub213sd',
    'vfmadd213sd__27': 'vfmadd213sd',
    'maxss.47': 'maxss',       # (i128,i32)
    'maxsd.56': 'maxsd',
    'sqrtsd.57': 'sqrtsd',
    'sqrtss.20': 'sqrtss__20',
    'ucomiss.46': 'ucomiss',
    'ucomisd.31': 'ucomisd',
    'comiss.41': 'comiss',
    'vcomisd.28': 'vcomisd',
    'vmovdqa.23': 'vmovdqa__16',
    'vmovdqu.37': 'vmovdqu__33',
    'vmovapd.29': 'vmovapd',
    'vmovaps': 'vmovdqa__16',  # (i128)->i128 identity (closure vmovdqa__16 同形)
    'vmovsd.36': 'vmovsd__',   # blend (i128,i128) → 未実装 (確認対象)
    'vmovq.24': 'vmovq',       # (i64)->i128 load — closure __asm_vmovq(i128)->i64 異!
    'movq.32': 'movq',         # (i128)->i128?? 要確認
    'movd.18': 'vmovd',        # (i128)->i32
    'movd.51': 'vmovd',
    'cvttsd2si.17': 'cvttsd2si',  # (i64)->i32
    'cvttsd2si.40': 'cvttsd2si',  # (i128)->i32? closure は (i128)->i32 ✓
    'cvttss2si.43': 'cvttss2si',
    'cvtsi2sd.45': 'cvtsi2sd',
    'cvtsi2ss.42': 'cvtsi2ss',
    'vcvtsd2ss.31': 'vcvtsd2ss',
    'psrad.50': 'psrad',
    'divss.44': 'divss',
    'cvttps2dq': 'cvttpd2dq',
}

TYPES_FROM_FULL: dict[str, Any] = {}   # %typename = type {...} 定義 (抽出先から現れた場合に 補完)


def carve(full, name):
    pat = re.compile(r'^define .*@' + re.escape(name) + r'\(')
    lines = full.split('\n')
    for i, l in enumerate(lines):
        if pat.match(l):
            for j in range(i + 1, len(lines)):
                if lines[j] == '}':
                    return lines[i:j + 1]
            break
    return None


def full_decls(full):
    d = {}
    for m in re.finditer(r'(?m)^declare (\S+) @(__asm_[\w.\-]+)\((.*?)\) local_unnamed_addr$', full):
        d[m.group(2)[len('__asm_'):]] = (m.group(1), tuple(a.split()[0].rstrip(',') for a in m.group(3).split(',') if a))
    return d


def memfix_decls(memfix):
    d = {}
    for m in re.finditer(r'(?m)^declare (\S+) @(__asm_[\w.\-]+)\((.*?)\) local_unnamed_addr$', memfix):
        d[m.group(2)[len('__asm_'):]] = (m.group(1), tuple(a.split()[0].rstrip(',') for a in m.group(3).split(',') if a))
    return d


def ptrize(text):
    # `i8*/i32*/i64*/i128*/double*/float*` → ptr (opaque pointer 対応)
    text = re.sub(r'\b(i(8|16|32|64|128)|double|float)\*', 'ptr', text)
    return text


def shift_num(fn, newbase=0x30000000):
    """ir6_shift 同幅: VA 直値 0x18xxxxxx / 10-11桁 dec 数値 → SHIFT."""
    BASE, MAXV = 0x180000000, 0x1803FFFFF
    shift = BASE - newbase
    cnt = [0]

    def rep_hex(m):
        v = int(m.group(1), 16)
        if not (BASE <= v <= MAXV):
            return m.group(0)
        cnt[0] += 1
        return 'i64 0x%x' % (v - shift)
    def rep_dec(m):
        v = int(m.group(1), 10)
        if not (BASE <= v <= MAXV):
            return m.group(0)
        cnt[0] += 1
        return 'i64 %d' % (v - shift)
    return fn and (rep_hex, rep_dec, cnt)


def apply_shift(text, newbase=0x30000000):
    """ir6_shift 同幅の VA shift (NEWBASE は pipeline から --newbase=<LB_BASE> で渡す, CAB-220)。
    BASE/MAXV は元 VA 空間の ImageBase と image 範囲なので newbase 非依存。"""
    BASE, MAXV = 0x180000000, 0x1803FFFFF
    shift = BASE - newbase
    def rep_hex(m):
        v = int(m.group(1), 16)
        if not (BASE <= v <= MAXV):
            return m.group(0)
        return 'i64 0x%x' % (v - shift)
    def rep_dec(m):
        v = int(m.group(1), 10)
        if not (BASE <= v <= MAXV):
            return m.group(0)
        return 'i64 %d' % (v - shift)
    def glob(m):
        h = m.group(1)
        v = int(h, 16)
        if not (BASE <= v <= MAXV):
            return m.group(0)
        return '@global_var_%x' % (v - shift)
    text = re.sub("@global_var_(18[0-9a-fA-F]{5,10})\\b", glob, text)
    text = re.sub(r"i64 (0x1[8-9][0-9a-fA-F]{5,10})", rep_hex, text)
    text = re.sub(r"i64 \b(\d{10,11})\b", rep_dec, text)
    return text


def norm_helpers(text, fdecls, mdecls, warns):
    helper_names = set(re.findall(r'@__asm_([\w.\-]+)\b', text))
    pending = []
    def mfix_sig(name):
        return mdecls.get(name)

    for fn in sorted(helper_names, key=lambda x: -len(x)):
        target = None
        full_sig = fdecls.get(fn)
        if fn in mdecls and full_sig and mdecls[fn] == full_sig:
            target = fn                       # 同名 同 sig — 置換不要
        elif fn in HELPER_RENAME and HELPER_RENAME[fn] in mdecls and full_sig and mdecls[HELPER_RENAME[fn]] == full_sig:
            target = HELPER_RENAME[fn]
        elif fn in HELPER_RENAME:
            target = HELPER_RENAME[fn]
            trg = HELPER_RENAME[fn]
            # sig 同型 check
            if fn in fdecls and trg in mdecls:
                if fdecls[fn] == mdecls[trg]:
                    target = trg
                else:
                    warns.append('SIG-DIFF %s: full %s vs memfix %s %s' %
                                 (fn, fdecls[fn], trg, mdecls[trg]))
                    target = trg                 # とりあえず寄せる (手動照合領域)
            else:
                target = trg
        else:
            # succefix 付き → closure の sig 同型 name へ (base 優先, 次点は prefix 同系)
            base = fn
            base = re.sub(r'_{1,2}\d+$', '', base)
            base = re.sub(r'\.\d+$', '', base)
            if base in mdecls and full_sig and mdecls[base] == full_sig:
                target = base
            else:
                cands = [k for k, sg in mdecls.items() if full_sig and sg == full_sig]
                pre = [k for k in cands if k.startswith(base) and k != fn]
                if pre:
                    target = sorted(pre, key=lambda k: -len(k))[0]
                warns.append('NEW-HELPER: %s (full decl: %s) — declare と msimd6 実装が必要'
                             % (fn, fdecls.get(fn)))
                target = fn
        if target and target != fn:
            pending.append((fn, target))
    # 2 段階 rename (target 名が別 fn 名と衝突する問題 (movss.8→movss→movss__17 等) 回避)
    tmps = {}
    for fn, target in pending:
        if target != fn:
            tmp = '@__asm__TMR_' + fn
            tmps.setdefault(fn, tmp)
            text = re.sub('@__asm_' + re.escape(fn) + r'(?![\w.\-])', tmp, text)
    for fn, target in pending:
        text = text.replace(tmps[fn], '@__asm_' + target)
    return text


def main():
    argv = sys.argv[1:]
    newbase = 0x30000000
    if '--newbase' in argv:                    # pipeline (liftlib recipes/ott.py) から LB_BASE を受ける
        i = argv.index('--newbase')
        newbase = int(argv[i + 1], 0)
        argv = argv[:i] + argv[i + 2:]
    outpath = argv[0] if argv else 'work/ott_memfix1.ll'
    names = argv[1:]
    if not names:
        print('usage: m6_full_extract.py OUT.ll FNAME...'); sys.exit(2)
    full = open(FULL).read()
    memfix = open(MEMFIX).read()
    fd = full_decls(full)
    md = memfix_decls(memfix)
    mdefines = set(re.findall(r'(?m)^define .* @(\w+)\(', memfix))
    mdeclnames = set(re.findall(r'(?m)^declare \S+ @(\w+)\(', memfix))

    warns, added = [], []
    for name in names:
        blk = carve(full, name)
        if blk is None:
            print('[extract] MISS define:', name); continue
        text = ptrize('\n'.join(blk))
        # metadata 参照 (full lift の !insn.addr 等) を除去 (定義が block 外にあるので)
        text = re.sub(r',\s*![\w.\-]+\s*!\d+', '', text)
        text = apply_shift(text, newbase)
        text = norm_helpers(text, fd, md, warns)
        # mdecl 内型名の存在 check
        for tv in set(re.findall(r'%(_[A-Za-z0-9_]+)\b', text)):
            if ('%_RTL' in tv or 'type' in tv) and '%_RTL' in tv:
                pass
        added.append((name, text))
        # 内部 call 先の要 concern list
        for callee in set(re.findall(r'(?m)^\s*[^;]*call \S+ @((?:function_|__asm_)?\w[\w.]*)\(', text)):
            if callee in added or callee in mdefines or callee.startswith('__asm_'):
                continue
            if callee not in mdeclnames and callee not in mdefines:
                print('[extract][DEP] %s 内の call 先 %s が memfix に未定義 (要抽出巾)' % (name, callee))
        print('[extract] carved:', name, '/', len(blk), 'lines')

    if not added:
        print('[extract] no defines spliced'); sys.exit(1)
    out = memfix.split('\n')
    # splice 名の declare 行を除去 (LLVM (opaque ptr era) は declare→define 同一モジュールを許容しない)
    keep = []
    splice_names = {n for n, _ in added}
    for l in out:
        if l.startswith('declare '):
            m = re.match(r'(?m)^declare \S+ @(\w+)\(', l)
            if m and m.group(1) in splice_names:
                continue
        keep.append(l)
    # splice 名の closure 側 declare 残りの除去 (declare→define 同一モジュール対策) + call site ret 型 refit
    retypes = {}
    for n, t in added:
        m0 = re.match(r'define (\S+) @' + re.escape(n) + r'\(', t.split('\n')[0])
        if m0:
            retypes[n] = m0.group(1)

    keep, prewrites = [], 0
    for l in out:
        if l.startswith('declare '):
            m = re.match(r'^declare \S+ @(\w+)\(', l)
            if m and m.group(1) in retypes:
                continue                     # declare 削除 (実体を入れるため)
        chg = False
        if ' call ' in l and '@function_' in l:
            for fn, ret in retypes.items():
                m = re.match(r'^(\s*%[\w.\-]+ = call )(\S+)( @' + re.escape(fn) + r'\()', l)
                if m and m.group(2) != ret:
                    l = m.group(1) + ret + m.group(3) + l[m.end():]
                    prewrites += 1
                    chg = True
                    continue
        keep.append(l)
    print('[extract] callsite ret 型 refit:', prewrites)
    memfix = '\n'.join(keep)
    memfix = memfix.rstrip('\n') + '\n\n/* --- spliced from full lift (m6_full_extract.py) --- */\n\n'
    memfix += '\n\n'.join(t for _, t in added) + '\n'
    open(outpath, 'w').write(memfix)
    print('[extract] wrote', outpath, '(-', len(added), 'funcs:', ','.join(n for n, _ in added), ')')
    for w in warns:
        print('[extract] WARN', w)
    # helper 新規 declare list 出力 (そのまま memfix へ追加すべき declare)
    newdecls = set()
    for _, t in added:
        for hn in re.findall(r'@(__asm_[\w.\-]+)\b', t):
            if hn not in md and hn in fd:
                newdecls.add(hn)
    if newdecls:
        print('[extract] 新規 helper declare (memfix に要追加):')
        for hn in sorted(newdecls):
            print('    declare? ' , hn, fd[hn])
    sys.exit(0)


if __name__ == '__main__':
    main()
