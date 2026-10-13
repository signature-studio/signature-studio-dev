#!/usr/bin/env python3
"""audit_undefload.py — 「機械語のメモリ read が IR で未初期化 alloca の load (= undef → B1 で定数 0) に化けた」site の全数監査 (#564)。

背景 (function_52a7f0 / AllocateHWnd): `cmp [rbp+0x70], rcx` の被 read が RetDec 出力 (drc.ll) の時点で
`%0 = alloca i64` + `%1 = load i64, ptr %0` (store の無い alloca の load = undef) になり、LLVM が undef の自由度で
分岐条件を畳む (`or.cond = icmp eq (x==DWP), registered`)。m5 ir5_patch B1 が undef を 0 に固定して最終 IR の
`%1 = xor i64 0, 0` になる。stage-0 (boot*.norm0.ll = B1 前) が正本入力。

判定 (機械語突合、IR 単独では決めない): norm0 の「store の無い無名 alloca からの load」を site とし、その値の consumer の
`!insn.addr` が指す機械語命令を PE の .pdata 区間 disasm から引く。
  MEMREAD  consumer 命令が rbp/rsp/他 reg ベースのメモリ read オペランドを持つ (= load の脱落が疑わしい)
  RIPREAD  consumer 命令が rip 相対のメモリ read を持つ
  REGLIVE  メモリ read 無し (関数入口 live-in reg など。load 脱落ではない)
  NOADDR   consumer に insn.addr 無し (判定不能)
MEMREAD のうち frame (rbp/rsp ベース) は callee が書く escape 済み stack_var の読出し候補 (ldfix F3 系の対象外)。

使い方: python3 audit_undefload.py PE.bin OUT.json IN.norm0.ll [IN2 ...]
"""
import collections
import json
import re
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine, memops_of  # noqa: E402
from ldframe import is_write_only, frame_model, escaped_stack_vars  # noqa: E402

DEF_RE = re.compile(r'^define [^@]*@(function_([0-9a-f]+))\(([^)]*)\)[^{]*\{', re.M)
ALLOCA_RE = re.compile(r'^  (%[\w.$-]+) = alloca ', re.M)
META_RE = re.compile(r'^!(\d+) = !\{i64 (\d+)\}\s*$', re.M)
INSN_RE = re.compile(r'!insn\.addr !(\d+)')


def scan_text(text, meta):
    """yield dict(fn, va, name, ty, consumers[(line, addr|None)])"""
    for m in DEF_RE.finditer(text):
        end = text.index('\n}', m.end()) + 2
        body = text[m.start():end]
        lines = body.split('\n')
        allocas = set(ALLOCA_RE.findall(body))
        if not allocas:
            continue
        bad = set()
        for a in allocas:
            ea = re.escape(a)
            # 名前が現れる行のうち、load 以外の使われ方 (store 先 / call 引数 / bitcast / gep 等) があれば除外
            for l in lines:
                if a not in l or re.match(r'^  %s = alloca ' % ea, l):
                    continue
                if re.match(r'^  %[\w.$-]+ = load \w+, (?:ptr|\w+\*) %s(?![\w.$-])' % ea.lstrip('%') if False else r'^  %[\w.$-]+ = load [^,]+, [^%]*' + ea + r'(?![\w.$-])', l):
                    continue
                if re.search(ea + r'(?![\w.$-])', l):
                    bad.add(a)
                    break
        for a in sorted(allocas - bad):
            ea = re.escape(a)
            for i, l in enumerate(lines):
                lm = re.match(r'^  (%[\w.$-]+) = load ([^,]+), [^%]*' + ea + r'(?![\w.$-])', l)
                if not lm:
                    continue
                v = lm.group(1)
                cons = []
                for j, l2 in enumerate(lines):
                    if j == i or not re.search(re.escape(v) + r'(?![\w.$-])', l2) or re.match(r'^  %s = ' % re.escape(v), l2):
                        continue
                    im = INSN_RE.search(l2)
                    cons.append((l2.strip()[:120], meta.get(int(im.group(1))) if im else None))
                yield dict(fn=m.group(1), va=int(m.group(2), 16), alloca=a, ty=lm.group(2).strip(), val=v, cons=cons)


def classify(mach, rec, fm=None, svars=None):
    cls = collections.Counter()
    detail = []
    for (txt, addr) in rec['cons']:
        if addr is None:
            cls['NOADDR'] += 1
            continue
        ins = None
        for i in (mach.disasm_fn(rec['va']) or []):
            if i.address == addr:
                ins = i
                break
        if ins is None:
            cls['NOADDR'] += 1
            continue
        reads = [mo for mo in memops_of(mach.cs, ins) if mo['kind'] in ('load', 'rmw', 'other')]
        if is_write_only(ins):
            reads = []
        if not reads:
            cls['REGLIVE'] += 1
        elif any(mo.get('rip_rva') is not None for mo in reads):
            cls['RIPREAD'] += 1
        else:
            mo = reads[0]
            k = 'MEMREAD_FRAME' if mo['base'] in ('rbp', 'rsp') else 'MEMREAD'
            if k == 'MEMREAD_FRAME' and fm is not None and not mo['index']:
                rs, rb = fm.get(addr, (None, None))
                basev = rs if mo['base'] == 'rsp' else rb
                if basev is None:
                    k = 'FRAME_UNRESOLVED'
                else:
                    o = basev + mo['disp']
                    cover = [n for n in svars if -n <= o]
                    n = min(cover, key=lambda n: o + n) if cover else None   # o に最も近い (下側の) 基底
                    if n is not None and svars[n] and o - (-n) < 4096:
                        k = 'FRAME_IN_ESCAPED'
                        detail.append('%x %s %s => stack_var_-%d+%d' % (addr, ins.mnemonic, ins.op_str, n, o + n))
                    else:
                        k = 'FRAME_NOT_ESCAPED'
            cls[k] += 1
            if k in ('MEMREAD', 'MEMREAD_FRAME', 'FRAME_UNRESOLVED', 'FRAME_NOT_ESCAPED'):
                detail.append('%x %s %s [%s%+d]' % (addr, ins.mnemonic, ins.op_str, mo['base'], mo['disp']))
    return cls, detail


def main():
    pe, out = sys.argv[1], sys.argv[2]
    mach = Machine(pe)
    sites = []
    fcache = {}
    for path in sys.argv[3:]:
        text = open(path, errors='replace').read()
        meta = {int(a): int(b) for a, b in META_RE.findall(text)}
        for rec in scan_text(text, meta):
            if rec['fn'] not in fcache:
                mm = re.search(r'^define [^\n]*@%s\(.*?^\}' % rec['fn'], text, re.S | re.M)
                fcache = {rec['fn']: (frame_model(mach.cs, mach.disasm_fn(rec['va']) or []), escaped_stack_vars(mm.group(0)) if mm else {})}
            fm, svars = fcache[rec['fn']]
            cls, detail = classify(mach, rec, fm, svars)
            top = next((k for k in ('FRAME_IN_ESCAPED', 'FRAME_NOT_ESCAPED', 'FRAME_UNRESOLVED', 'MEMREAD_FRAME', 'MEMREAD', 'RIPREAD', 'REGLIVE', 'NOADDR') if cls[k]), 'NOADDR')
            sites.append(dict(fn='%x' % rec['va'], ty=rec['ty'], cls=top, detail=detail[:3], file=os.path.basename(path)))
    tally = collections.Counter(s['cls'] for s in sites)
    fns = collections.defaultdict(set)
    for s in sites:
        fns[s['cls']].add(s['fn'])
    res = dict(sites_total=len(sites), by_class=dict(tally), fns_by_class={k: len(v) for k, v in fns.items()},
               **{k.lower(): sorted([s for s in sites if s['cls'] == k], key=lambda s: s['fn'])
                  for k in ('FRAME_IN_ESCAPED', 'FRAME_NOT_ESCAPED', 'FRAME_UNRESOLVED', 'MEMREAD_FRAME', 'MEMREAD', 'RIPREAD')})
    json.dump(res, open(out, 'w'), indent=1)
    print('sites', len(sites), dict(tally), {k: len(v) for k, v in fns.items()})


if __name__ == '__main__':
    main()
