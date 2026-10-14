#!/usr/bin/env python3
"""#2456: RetDec drc.ll の uselistorder 差を関数単位で集計する (uselist_origin_2456.sh から呼ぶ)。

入力: <dir>/<label>.drc.ll / .drc.bc / .drc.c / .lift.ll。label の接頭辞 on / off / tc で群を分ける。
出力: run ごとの md5、群ごとの distinct 数、run 対の差分 (関数単位・並びのみか有無か・指示の種類)。
"""
import collections
import glob
import hashlib
import os
import re
import sys

D = sys.argv[1]
DEF = re.compile(r"^define\b.*?@([^\s(]+)\(")
DIRECT = re.compile(r"^\s*uselistorder(_bb)?\s")
GLOBAL = "<global>"


def md5(path):
    if not os.path.exists(path):
        return "-"
    return hashlib.md5(open(path, "rb").read()).hexdigest()[:8]


def parse(path):
    """関数名 -> その関数内の uselistorder 行の列 (出現順)。関数外は GLOBAL。"""
    funcs = collections.OrderedDict()
    cur = GLOBAL
    for raw in open(path, errors="replace"):
        line = raw.rstrip("\n")
        m = DEF.match(line)
        if m:
            cur = m.group(1)
        if DIRECT.match(line):
            funcs.setdefault(cur, []).append(line.strip())
        if line.startswith("}"):
            cur = GLOBAL
    return funcs


def kind(line):
    if line.startswith("uselistorder_bb"):
        return "bb"
    head = line.split(",")[0]
    return "global" if "@" in head else "local"


def stripped_md5(path):
    """uselistorder 行・その説明行・空行を除いた drc.ll の md5 (差が directive だけかの検査)。"""
    h = hashlib.md5()
    for raw in open(path, "rb"):
        s = raw.strip()
        if not s or s.startswith(b"uselistorder") or s.startswith(b"; uselistorder"):
            continue
        h.update(raw)
    return h.hexdigest()[:8]


def diff_pair(fa, fb):
    keys = set(fa) | set(fb)
    diff = [k for k in keys if fa.get(k, []) != fb.get(k, [])]
    perm_only = [k for k in diff if sorted(fa.get(k, [])) == sorted(fb.get(k, []))]
    kinds = collections.Counter()
    for k in diff:
        for ln in fa.get(k, []) + fb.get(k, []):
            kinds[kind(ln)] += 1
    return sorted(diff), sorted(perm_only), kinds


labels = sorted({os.path.basename(p)[: -len(".drc.ll")] for p in glob.glob(os.path.join(D, "*.drc.ll"))})
groups = collections.OrderedDict()
for g in ("on", "off", "tc"):
    groups[g] = [l for l in labels if re.fullmatch(g + r"\d+", l)]

info = {}
for l in labels:
    base = os.path.join(D, l)
    funcs = parse(base + ".drc.ll")
    info[l] = {
        "funcs": funcs,
        "ll": md5(base + ".drc.ll"),
        "bc": md5(base + ".drc.bc"),
        "c": md5(base + ".drc.c"),
        "lift": md5(base + ".lift.ll"),
        "strip": stripped_md5(base + ".drc.ll"),
        "n_dir": sum(len(v) for v in funcs.values()),
        "n_fn": len([k for k in funcs if k != GLOBAL]),
    }

print("## run 一覧 (md5 は先頭 8 桁)")
print("label\tdrc.ll\tdrc.bc\tdrc.c\tlift.ll\tstrip(directive除去)\tuselistorder行\t関数数(directive有り)")
for l in labels:
    i = info[l]
    print(f"{l}\t{i['ll']}\t{i['bc']}\t{i['c']}\t{i['lift']}\t{i['strip']}\t{i['n_dir']}\t{i['n_fn']}")

print("\n## 群ごとの distinct 数")
print("group\tn\tdistinct drc.ll\tdistinct drc.bc\tdistinct drc.c\tdistinct lift.ll\tdistinct strip")
for g, ls in groups.items():
    if not ls:
        continue
    d = lambda key: len({info[l][key] for l in ls})
    print(f"{g}\t{len(ls)}\t{d('ll')}\t{d('bc')}\t{d('c')}\t{d('lift')}\t{d('strip')}")

print("\n## run 対の差分 (関数単位。並びのみ = 同じ行の集合で順序だけ違う関数)")
print("pair\tdrc.ll同一\tdiff関数\t並びのみ\t有無が違う\t差分の指示種別 (global/local/bb の行数)\t差分関数の例 (最大5)")
pairs = []
for g, ls in groups.items():
    for other in ls[1:]:
        pairs.append((ls[0], other))
if groups["on"] and groups["off"]:
    pairs.append((groups["on"][0], groups["off"][0]))
if groups["off"] and groups["tc"]:
    pairs.append((groups["off"][0], groups["tc"][0]))
for a, b in pairs:
    ia, ib = info[a], info[b]
    diff, perm_only, kinds = diff_pair(ia["funcs"], ib["funcs"])
    same = "yes" if ia["ll"] == ib["ll"] else "no"
    ks = ",".join(f"{k}={kinds[k]}" for k in ("global", "local", "bb") if kinds[k])
    ex = ",".join(diff[:5])
    print(f"{a}-{b}\t{same}\t{len(diff)}\t{len(perm_only)}\t{len(diff) - len(perm_only)}\t{ks or '-'}\t{ex or '-'}")

print("\n## pass 単位 (--print-after-all の stderr。テキストのみ・use-list の順序は載らない)")
print("file\tmd5\tbytes\tuselistorder行\tIR Dump 件数")
for p in sorted(glob.glob(os.path.join(D, "pass*.stderr"))):
    data = open(p, "rb").read()
    print(f"{os.path.basename(p)}\t{hashlib.md5(data).hexdigest()[:8]}\t{len(data)}\t{data.count(b'uselistorder')}\t{data.count(b'IR Dump')}")

print("\n## 差分の所在: 差が出た関数名の頻度 (全 run 対の合計・上位 10)")
freq = collections.Counter()
for a, b in pairs:
    diff, _, _ = diff_pair(info[a]["funcs"], info[b]["funcs"])
    freq.update(diff)
for k, v in freq.most_common(10):
    print(f"{k}\t{v}")
