#!/usr/bin/env python3
"""RetDec の出力 (ci.drc.ll) を ci_ranges.py の範囲と照合し、CreateInstance closure の census を出す (T-SH-62 #3300)。

usage: ci_census.py <ci.drc.ll> <ranges.json>
検査 (欠けると exit 1): 範囲の 36 関数が全て define されていること (entry は export 名 GeneralPitchShifter_CreateInstance で出る)。
出力: 範囲外の追加 define・外部宣言の内訳・範囲内の呼び出し行の件数。
      declare のみの呼び出し先は、x86 の範囲外直接分岐 (ranges.json の outside_targets) の飛び先なら「直接呼び出し先」、そうでなければ「画像内ポインタ」に分ける。
注: 呼び出し行数は x86 の件数と一致しない。例: FlsSetValue の IR 5 行 = function_1801b8820 の 4 行 (x86 の call 4 箇所と一致) + サンク本体 function_1801b9334 の 1 行。
    間接 call の件数の照合は ci_ranges.py (x86 の capstone 走査) で行う。
"""
import re, sys, json, collections

ll = open(sys.argv[1]).read()
rg = json.load(open(sys.argv[2]))
ib = rg["image_base"]
ENTRY_EXPORT = "GeneralPitchShifter_CreateInstance"
want = {f"function_{ib + int(r['rva'], 16):x}" for r in rg["rows"]}
entry_fn = f"function_{ib + int(rg['entry'], 16):x}"
want.discard(entry_fn)
want.add(ENTRY_EXPORT)

defs = re.findall(r"^define [^@]*@([A-Za-z0-9_.]+)\(", ll, re.M)
decls = re.findall(r"^declare [^@]*@([A-Za-z0-9_.]+)\(", ll, re.M)
missing = sorted(want - set(defs))
extra = sorted(set(defs) - want)
extra_ref = sorted(set(extra) & set(re.findall(r"call [^@\n]*@([A-Za-z0-9_.]+)\(", ll)))

# 範囲内の関数本体ごとに呼び出しを数える (定義ブロックを行で区切る)
bodies, cur = {}, None
for line in ll.splitlines():
    m = re.match(r"^define [^@]*@([A-Za-z0-9_.]+)\(", line)
    if m:
        cur = m.group(1); bodies[cur] = []
    elif line.startswith("}"):
        cur = None
    elif cur is not None:
        bodies[cur].append(line)
calls = collections.Counter()
callers = collections.defaultdict(set)
for name in want & set(bodies):
    for line in bodies[name]:
        for c in re.findall(r"call [^@\n]*@([A-Za-z0-9_.]+)\(", line):
            calls[c] += 1
            callers[c].add(entry_fn if name == ENTRY_EXPORT else name)

def rva(name):
    return int(name.split("_", 1)[1], 16) - ib

# x86 の範囲外直接分岐: 飛び先 RVA -> ["飛び元 RVA mnemonic", ...]
outside = collections.defaultdict(list)
for o in rg["outside_targets"]:
    outside[int(o["to"], 16)].append(f"{o['from']} {o['mnem']}")

iat = {n: c for n, c in calls.items() if not n.startswith(("function_", "__asm_"))}
declared = {n: c for n, c in calls.items() if n.startswith("function_") and n in decls}
direct_out = {n: c for n, c in declared.items() if rva(n) in outside}
img_ptr = {n: c for n, c in declared.items() if n not in direct_out}
asm = {n: c for n, c in calls.items() if n.startswith("__asm_")}
ind_total = sum(iat.values()) + sum(img_ptr.values())

print(f"[census] 範囲 {len(want)} 関数 / define {len(defs)} (範囲外の追加 define {len(extra)}・IR 内の call 参照 {len(extra_ref)} 件)")
print(f"[census] 範囲外の追加 define: {', '.join(extra) if extra else '無し'}")
print(f"[census] 範囲内の IAT 呼び出し (件数): " + ", ".join(f"{n} {c}" for n, c in sorted(iat.items())))
print(f"[census] 範囲内の画像内ポインタ呼び出し (declare のみ・範囲外直接分岐の飛び先でない): " + (", ".join(f"{n} {c}" for n, c in sorted(img_ptr.items())) or "無し"))
print(f"[census] 範囲外で define の無い直接呼び出し先 (呼び出し元 RVA / x86 の飛び元): " + (", ".join(
    f"{n} {c} (呼び出し元 {' '.join(hex(rva(x)) for x in sorted(callers[n]))} / 飛び元 {'; '.join(outside[rva(n)])})"
    for n, c in sorted(direct_out.items())) or "無し"))
print(f"[census] 範囲内の __asm_ helper 呼び出し (IR 行): " + ", ".join(f"{n} {c}" for n, c in sorted(asm.items())))
print(f"[census] 範囲内の IAT + 画像内ポインタ呼び出し (IR 行・複製を含む): {ind_total}")

rc = 0
if missing:
    print(f"[census] FAIL: 範囲の関数が define されていない: {missing}")
    rc = 1
print("[census] ALL OK" if rc == 0 else "[census] FAIL")
sys.exit(rc)
