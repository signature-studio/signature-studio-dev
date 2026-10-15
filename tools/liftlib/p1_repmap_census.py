#!/usr/bin/env python3
"""p1_repmap_census.py — legacy_p1 の repmap 適用件数を測る (#3067)。

  python3 p1_repmap_census.py [IR] [--module <p1_legacy.py>]

  IR       省略時 tools/m6/work/ott_lift.ll (挿入前の OTT lift IR)
  --module 比較する p1_legacy.py のパス (省略時は liftlib.passes.p1_legacy)

出力 (JSON 1 行):
  entries      repmap の組数 (stats.hits から: br_cf+br_zf+br_pf+br_? + 2*(or_cfzf+or_zfcf))
  br_applied   書換え後の `br i1 %pcN<cf|zf|pf>` の本数 (期待 = br 系の組数)
  or_applied   書換え後の `or i1 %pcN.., %pcN..` の本数 (期待 = or 系の行数)
  double_pct   `%%pc` の出現数 (0 が正)
  br_residual  書換え後に残る `br i1 %<cf|zf|pf>.N` の本数 (comis 挿入の窓外の分岐は残る)
  diff_lines   入力と出力の差分 (difflib, 挿入行を除く) の変更行数 (期待 18 = br 17 + or 1)
  diff_removed 変更行から消えた旧名トークン `%<cf|zf|pf>.N` の数 (期待 19 = entries)
  diff_no_pc   変更行のうち `%pc` を含まない行 (0 が正)

  --residual  窓で書換えられなかった comis 直後の分岐を分類する (#3137)。JSON 1 行。
    br_other     窓内の最初の分岐が cf/zf/pf の名前参照でない
      stale      条件の依存連鎖の葉 (整数比較) が 1 つでも comis より前に定義されている = comis のフラグを読まず前の cmp を読む (D1a 同型)。葉が前後に混在する場合も stale
        clean    間に関数呼出し・フラグ更新 asm が無い
        call     間に関数呼出し・フラグ更新 asm がある (callee がフラグを変えるため IR だけでは決まらない)。フラグ更新 asm の名前は flag_call_re (整数 ALU・bt 系・sahf/popf/clc/stc/cmc/xadd/ptest。SSE の xorpd・subsd 等は含まない)
      fresh      葉が全て comis より後 (分岐のフラグは comis 後の整数比較由来。同型でない)
    no_branch    窓 (13 行) 内に分岐が無い
      next_comis 次のフラグ関連イベントが後続の comis (この comis のフラグは読まれない)
      fn_end     関数末まで分岐が無い (フラグは読まれない)
      beyond_br  窓の外で最初に現れる分岐 (stale / fresh は br_other と同じ判定)
"""
import difflib
import importlib.util
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
mod_path = None
if "--module" in args:
    i = args.index("--module")
    mod_path = args[i + 1]
    del args[i:i + 2]
residual = "--residual" in args
if residual:
    args.remove("--residual")
ir_path = args[0] if args else os.path.join(HERE, "..", "m6", "work", "ott_lift.ll")


def residual_census(text, parse_call):
    lines = text.split("\n")
    comis_re = re.compile(r"call void @__asm_v?u?comis[sd]")
    flag_call_re = re.compile(r"call [\w ]+ @(function_|__asm_(add|adc|sub|sbb|cmp|test|and|or|xor|inc|dec|neg|shl|shr|sar|rol|ror|rcl|rcr|bt[src]?|mul|imul|div|idiv|bsf|bsr|sahf|popf|clc|stc|cmc|xadd|ptest)(?![a-z0-9]))")
    leaf_ok = re.compile(r"^(icmp (eq|ne) i1|or i1|and i1|xor i1)")
    def defpos(name, before):
        pat = re.compile(r"^\s*%" + re.escape(name) + r" = ")
        for k in range(before, max(-1, before - 400), -1):
            if pat.match(lines[k]):
                return k
        return None
    def leaves(name, pos, depth=0):
        d = defpos(name, pos)
        if d is None:
            return [None]
        body = lines[d].split(" = ", 1)[1]
        if depth < 8 and leaf_ok.match(body):
            out = []
            for o in re.findall(r"%([\w.\-]+)", body):
                out += leaves(o, d, depth + 1)
            return out or [d]
        return [d]
    def stale_of(idx, jj, name):
        ls = leaves(name, jj)
        if any(x is None for x in ls):
            return 'unknown'
        if not any(x < idx for x in ls):
            return 'fresh'
        between = [k for k in range(idx + 1, jj) if flag_call_re.search(lines[k])]
        return 'stale_call' if between else 'stale_clean'
    def first_event(idx):
        for k in range(idx + 1, min(idx + 400, len(lines))):
            l = lines[k]
            if l.startswith('}'):
                return 'fn_end', k
            if re.match(r"^  br i1 (i1 )?%", l):
                return 'br', k
            if comis_re.search(l):
                return 'next_comis', k
        return 'fn_end', None
    cnt = Counter()
    sites = [i for i, l in enumerate(lines) if re.match(r"^\s*call void @__asm_", l) and 'comis' in l]
    sites = [i for i in sites if parse_call(lines[i]) is not None]
    for idx in sites:
        j = idx + 1
        cls = None
        while j < min(idx + 13, len(lines)):
            l2 = lines[j]
            if re.match(r"^  br i1 %", l2):
                m2 = re.match(r"^  br i1 (?:i1 )?%([\w.\-]+), label", l2)
                n = m2.group(1) if m2 else ''
                cls = 'br_named' if n.startswith(('cf.', 'zf.', 'pf.')) else 'br_other'
                break
            if re.match(r"^  %[\w.\-]+ = or i1 %[\w.\.-]+, %[\w.\.-]+$", l2):
                mm = re.match(r"^  %([\w.\-]+) = or i1 %([\w.\-]+), %([\w.\-]+)(.*)$", l2)
                a, b = mm.group(2), mm.group(3)
                if ('cf.' in a and 'zf.' in b) or ('zf.' in a and 'cf.' in b):
                    cls = 'or_named'
                    break
            if re.match(r"^  call void @__asm_", l2):
                break
            j += 1
        if cls == 'br_other':
            cnt['br_other.' + stale_of(idx, j, re.match(r"^  br i1 (?:i1 )?%([\w.\-]+)", lines[j]).group(1))] += 1
        elif cls in ('br_named', 'or_named'):
            cnt[cls] += 1
        else:
            ev, k = first_event(idx)
            if ev == 'br':
                m2 = re.match(r"^  br i1 (?:i1 )?%([\w.\-]+)", lines[k])
                n = m2.group(1)
                if n.startswith(('cf.', 'zf.', 'pf.')):
                    cnt['no_branch.beyond_br_named'] += 1
                else:
                    cnt['no_branch.beyond_br_' + stale_of(idx, k, n)] += 1
            elif ev == 'next_comis':
                cnt['no_branch.next_comis'] += 1
            else:
                cnt['no_branch.fn_end'] += 1
    return {"sites": len(sites), **dict(sorted(cnt.items()))}



if mod_path:
    spec = importlib.util.spec_from_file_location("p1_legacy_under_test", mod_path)
    p1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p1)
else:
    sys.path.insert(0, os.path.join(HERE))
    from liftlib.passes import p1_legacy as p1

text = open(ir_path).read()
if residual:
    print(json.dumps(residual_census(text, p1.parse_call), ensure_ascii=False))
    sys.exit(0)
out, st = p1.legacy_p1(text)
h = st["hits"]
entries = h.get("br_cf", 0) + h.get("br_zf", 0) + h.get("br_pf", 0) + h.get("br_?", 0) + 2 * (h.get("or_cfzf", 0) + h.get("or_zfcf", 0))
tok = re.compile(r"%(?:cf|zf|pf)\.\d+")
a, b = text.split("\n"), out.split("\n")
d_lines = d_removed = d_no_pc = 0
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
    if tag != "replace" or i2 - i1 != j2 - j1:
        continue
    for x, y in zip(a[i1:i2], b[j1:j2]):
        if x != y:
            d_lines += 1
            d_removed += len(tok.findall(x)) - len(tok.findall(y))
            d_no_pc += "%pc" not in y
res = {
    "entries": entries,
    "br_applied": len(re.findall(r"br i1 %pc\d+(?:cf|zf|pf)\b", out)),
    "or_applied": len(re.findall(r"= or i1 %pc\d+(?:cf|zf|pf), %pc\d+(?:cf|zf|pf)", out)),
    "double_pct": out.count("%%pc"),
    "br_residual": len(re.findall(r"br i1 %(?:cf|zf|pf)\.\d+", out)),
    "diff_lines": d_lines,
    "diff_removed": d_removed,
    "diff_no_pc": d_no_pc,
}
print(json.dumps(res, ensure_ascii=False))
