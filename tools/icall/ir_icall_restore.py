#!/usr/bin/env python3
"""ir_icall_restore.py — icall_rewrite.py で書換えた PE を RetDec で decode した IR を、元 PE の VA 体系へ戻し、
共有 stub 呼出しを `__icall_dispatch(site_va)` に置換する。

  python3 ir_icall_restore.py --ir oi.drc.ll --map X.icall.map.json --out restored.ll [--report r.json]

やること
  1. `@function_<new>` → `@function_<orig>` (relocated 関数のみ), `!insn.addr` メタデータの VA も new→orig (区間引き)
  2. `call @function_<STUB>()` → `call void @__icall_dispatch(i64 <orig site va>)`  (+ 結果値が使われていれば RET block から load)
     dispatch は C 側 runtime が BLK (target/rcx/rdx/r8/r9/xmm0-3 を memory-ABI で保持) を読み、VA→関数表で呼ぶ
  3. stub 定義/宣言を除去し `declare void @__icall_dispatch(i64)` を追加
  4. 診断: 変換 site 数 / 未変換 stub 参照 / BLK 参照数
"""
import argparse, bisect, json, re, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--map', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report')
    a = ap.parse_args()
    m = json.load(open(a.map))
    text = open(a.ir, errors='replace').read()
    fmap = {int(k, 16): int(v, 16) for k, v in m['func_map'].items()}
    inv = {v: k for k, v in fmap.items()}
    stub = m['stub']
    cstub = m.get('comis_stub')
    blk = m['blk']
    ranges = sorted(m['insn_ranges'])
    starts = [r[0] for r in ranges]

    def orig_of(addr):
        i = bisect.bisect_right(starts, addr) - 1
        if i >= 0:
            n, l, o = ranges[i]
            if n <= addr < n + max(l, 1):
                return o
        return None

    # --- metadata new->orig
    meta = {}
    def meta_sub(mm):
        v = int(mm.group(2))
        o = orig_of(v)
        meta[mm.group(1)] = o if o is not None else v
        return '!%s = !{i64 %d}' % (mm.group(1), o if o is not None else v)
    text = re.sub(r'^!(\d+) = !\{i64 (\d+)\}$', meta_sub, text, flags=re.M)

    # --- 関数名 rename (new->orig)
    def fn_sub(mm):
        v = int(mm.group(1), 16)
        if v == stub or v == cstub:
            return mm.group(0)
        return '@function_%x' % inv[v] if v in inv else mm.group(0)
    text = re.sub(r'@function_([0-9a-f]{6,16})\b', fn_sub, text)

    # --- stub call → dispatch
    stub_name = '@function_%x' % stub
    cstub_name = '@function_%x' % cstub if cstub else None
    cpat = re.compile(r'^(\s*)(?:(%[\w.]+) = )?call [^@]*' + re.escape(cstub_name) + r'\(\)(?:, !insn\.addr !(\d+))?\s*$') if cstub else None
    n_comis = 0
    out = []
    n_conv = 0
    n_res = 0
    lines = text.split('\n')
    i = 0
    skip_def = False
    pat = re.compile(r'^(\s*)(?:(%[\w.]+) = )?call [^@]*' + re.escape(stub_name) + r'\(\)(?:, !insn\.addr !(\d+))?\s*$')
    unconv = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith('define ') and (stub_name + '(' in l or (cstub_name and cstub_name + '(' in l)):
            while i < len(lines) and not lines[i].startswith('}'):
                i += 1
            i += 1
            continue
        if l.startswith('declare ') and (stub_name + '(' in l or (cstub_name and cstub_name + '(' in l)):
            i += 1
            continue
        cm = cpat.match(l) if cpat else None
        if cm:
            tail = ', !insn.addr !%s' % cm.group(3) if cm.group(3) else ''
            out.append('%scall void @__icall_comis()%s' % (cm.group(1), tail))
            if cm.group(2):
                out.append('%s%s = load i64, i64* inttoptr (i64 %d to i64*)%s' % (cm.group(1), cm.group(2), blk + 0xb0, tail))
            n_comis += 1
            i += 1
            continue
        mm = pat.match(l)
        if mm:
            ind, res, md = mm.group(1), mm.group(2), mm.group(3)
            site = meta.get(md) if md else None
            if site is None:
                site = 0
            tail = ', !insn.addr !%s' % md if md else ''
            out.append('%scall void @__icall_dispatch(i64 %d)%s' % (ind, site, tail))
            n_conv += 1
            if res:
                out.append('%s%s = load i64, i64* inttoptr (i64 %d to i64*)%s' % (ind, res, blk + 0x80, tail))
                n_res += 1
        else:
            if stub_name in l:
                unconv += 1
            out.append(l)
        i += 1
    text = '\n'.join(out)
    text = text.replace('\ndeclare ', '\ndeclare void @__icall_dispatch(i64)\ndeclare void @__icall_comis()\n\ndeclare ', 1)
    open(a.out, 'w').write(text)
    rep = {'comis_calls': n_comis, 'dispatch_calls': n_conv, 'result_loads': n_res, 'unconverted_stub_refs': unconv,
           'sites_in_map': len(m['sites']), 'blk': blk, 'blk_refs': len(re.findall(r'i64 %d to' % blk, text))}
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print(json.dumps(rep))


if __name__ == '__main__':
    main()
