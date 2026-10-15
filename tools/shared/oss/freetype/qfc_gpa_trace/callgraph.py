"""PE の直接 call/jmp の逆向き探索 (#3257 / T-SH-55)。関数境界は .pdata から取る。
指定した関数 (RVA) を呼ぶ関数を再帰的にたどり、target (VA) に達する経路を出す。
対象は .pdata を持つ x64 PE32+ (実測は block24350_PE.bin = QuickFontCache_x64)。ImageBase と .pdata の位置は PE ヘッダ・セクション名から読む。
usage: callgraph.py <PE> <target VA hex> <depth> <root VA hex> [<root VA hex> ...]
前提: objdump (-d -M intel) が使えること。出力は PE と同じ dir の dis.txt にキャッシュする。
"""
import bisect
import collections
import os
import re
import struct
import subprocess
import sys

path, target_s, depth_s = sys.argv[1:4]
roots = [int(x, 16) for x in sys.argv[4:]]  # VA (ImageBase + RVA)
target, depth = int(target_s, 16), int(depth_s)

d = open(path, "rb").read()
pe = struct.unpack_from("<I", d, 0x3C)[0]
opt = pe + 24
optsz = struct.unpack_from("<H", d, pe + 20)[0]
nsec = struct.unpack_from("<H", d, pe + 6)[0]
if struct.unpack_from("<H", d, opt)[0] != 0x20B:
    sys.exit("PE32+ (x64) のみ対応: .pdata による関数境界を使う")
IMAGE_BASE = struct.unpack_from("<Q", d, opt + 24)[0]
secs = {}
for i in range(nsec):
    s = opt + optsz + i * 40
    name = d[s:s + 8].rstrip(b"\0").decode("ascii", "replace")
    vsz, va, rsz, rp = struct.unpack_from("<IIII", d, s + 8)
    secs[name] = (va, max(vsz, rsz), rp)
if ".pdata" not in secs:
    sys.exit(".pdata セクションが無い: 関数境界を取れない")
pdata = secs[".pdata"]
funcs = []
for k in range(pdata[1] // 12):
    b, e, _ = struct.unpack_from("<III", d, pdata[2] + k * 12)
    if b:
        funcs.append((IMAGE_BASE + b, IMAGE_BASE + e))
funcs.sort()
starts = [a for a, _ in funcs]
start_set = set(starts)


def containing(va):
    i = bisect.bisect_right(starts, va) - 1
    if i >= 0 and funcs[i][0] <= va < funcs[i][1]:
        return funcs[i][0]
    return None


dis = os.path.join(os.path.dirname(os.path.abspath(path)), "dis.txt")
if not os.path.exists(dis):
    with open(dis, "w") as f:
        subprocess.run(["objdump", "-d", "-M", "intel", "--no-show-raw-insn", path], stdout=f, check=True)
callers = collections.defaultdict(set)
edge = re.compile(r"^  ([0-9a-f]+):\t(?:call|jmp)\s+0x([0-9a-f]+)\s*$")
for line in open(dis):
    m = edge.match(line)
    if not m:
        continue
    a, t = int(m.group(1), 16), int(m.group(2), 16)
    c = containing(a)
    if c is not None and t in start_set:
        callers[t].add(c)

print(f"functions {len(funcs)} (.pdata), direct call edges {sum(len(v) for v in callers.values())}")
for rv in roots:
    print(f"== root {rv:#x}: direct callers {[hex(x) for x in sorted(callers.get(rv, ()))]}")
    frontier = [(rv, [rv])]
    seen = {rv}
    for _ in range(depth):
        nxt = []
        for node, p in frontier:
            for c in sorted(callers.get(node, ())):
                if c in seen:
                    continue
                seen.add(c)
                nxt.append((c, p + [c]))
                if c == target:
                    print("  path:", " <- ".join(f"{x:#x}" for x in p + [c]))
        frontier = nxt
