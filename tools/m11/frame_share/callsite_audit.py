#!/usr/bin/env python3
"""SHX-T50 (#5587): 指定の callee を呼ぶ機械語 call site と、その site を含む基本ブロックの入口を判定する。

使い方: callsite_audit.py <m11_image.bin> <callee VA> <関数先頭 VA:関数終端 VA> ...
  例: callsite_audit.py work/m11_image.bin 0x690580 0x6905f0:0x690763

入力: m11_image.bin (file offset = VA - BASE)。
手順:
  1. 画像全体で e8 (call rel32) を走査し、target が callee の site を抽出する。
  2. 各関数を objdump で線形逆アセンブルし、site の所属関数・site が call であることを確認する。
  3. 基本ブロック先頭を「関数先頭・直接分岐の target・無条件転送の直後」で決め、
     site を含むブロック B の入口を判定する:
     - B の直前の命令が無条件転送 (ret/jmp/ud2/hlt) でなければ fall-through で到達しうる。
     - B と site への直接分岐 (rel8/rel32/jcc32) と絶対参照 (4/8 byte) の件数を数える。
限界: switch テーブル (相対オフセット方式) の飛び先は走査しない。
      線形逆アセンブルはデータ混在で同期がずれうる。「入口なし」は上記の範囲での結論。
"""
import re
import struct
import subprocess
import sys
from pathlib import Path

BASE = 0x400000
UNCOND = ("ret", "retn", "jmp", "ud2", "hlt")
INSN = re.compile(r"^\s*([0-9a-f]+):\t[0-9a-f ]+\t(\S+)\s*(.*)$")
BRANCH_TARGET = re.compile(r"^(?:0x)?([0-9a-f]+)(\s|<|$)")


def listing(path: Path, start: int, end: int) -> list[tuple[int, str, str]]:
    out = subprocess.run(
        ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
         f"--start-address={start:#x}", f"--stop-address={end:#x}", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        m = INSN.match(line)
        if m:
            rows.append((int(m.group(1), 16), m.group(2), m.group(3)))
    return rows


def branch_target(mnem: str, ops: str) -> int | None:
    if mnem == "call" or mnem.startswith("j"):
        m = BRANCH_TARGET.match(ops)
        if m:
            return int(m.group(1), 16) + BASE
    return None


def block_starts(rows, start: int, end: int) -> set[int]:
    starts = {start}
    for i, (addr, mnem, ops) in enumerate(rows):
        if mnem.startswith("j") or mnem == "jmp":
            t = branch_target(mnem, ops)
            if t is not None and start <= t < end:
                starts.add(t)
        if mnem in UNCOND and i + 1 < len(rows):
            starts.add(rows[i + 1][0] + BASE)
    return starts


def direct_refs(path: Path, targets: set[int]) -> dict[int, int]:
    # 命令境界で数える (バイト列の全走査は call 命令内の偶然一致を分岐と誤認する: SHX-T57)
    hits = {t: 0 for t in targets}
    for _, mnem, ops in listing(path, 0, path.stat().st_size):
        if mnem == "call" or mnem.startswith("j"):
            t = branch_target(mnem, ops)
            if t in hits:
                hits[t] += 1
    return hits


def abs_refs(img: bytes, targets: set[int]) -> dict[int, int]:
    hits = {}
    for t in targets:
        c = 0
        for fmt in ("<I", "<Q"):
            pat = struct.pack(fmt, t)
            j = img.find(pat)
            while j >= 0:
                c += 1
                j = img.find(pat, j + 1)
        hits[t] = c
    return hits


def find_calls(img: bytes, callee: int) -> list[int]:
    sites = []
    for m in re.finditer(rb"\xe8", img):
        i = m.start()
        if i + 5 <= len(img) and BASE + i + 5 + struct.unpack_from("<i", img, i + 1)[0] == callee:
            sites.append(BASE + i)
    return sites


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    path = Path(argv[1])
    callee = int(argv[2], 16)
    funcs = [tuple(int(x, 16) for x in a.split(":")) for a in argv[3:]]
    img = path.read_bytes()

    sites = find_calls(img, callee)
    lists = {f: listing(path, f[0] - BASE, f[1] - BASE) for f in funcs}
    starts = {f: block_starts(lists[f], f[0], f[1]) for f in funcs}

    def owner(addr: int):
        return next((f for f in funcs if f[0] <= addr < f[1]), None)

    targets = set(sites)
    for s in starts.values():
        targets |= s
    drefs = direct_refs(path, targets)
    arefs = abs_refs(img, targets)

    print(f"callee {callee:#x}: e8 rel32 で callee を指す site {len(sites)} 件 (画像全体)")
    print()
    print("| site | 所属関数 | 呼び出し命令 | ブロック先頭 B | B の直前命令 | 直接参照 B/site | 絶対参照 B/site | 判定 |")
    print("|---|---|---|---|---|---|---|---|")
    for s in sites:
        f = owner(s)
        if f is None:
            print(f"| {s:#x} | (範囲外) | - | - | - | - | - | 範囲指定に含まれない |")
            continue
        rows = lists[f]
        idx = next((k for k, r in enumerate(rows) if r[0] + BASE == s), None)
        if idx is None:
            print(f"| {s:#x} | {f[0]:#x} | (線形走査で見つからず) | - | - | - | - | 判定不能 |")
            continue
        insn = f"{rows[idx][1]} {rows[idx][2]}"
        call_ok = rows[idx][1] == "call" and branch_target("call", rows[idx][2]) == callee
        b = max(x for x in starts[f] if x <= s)
        bi = next(k for k, r in enumerate(rows) if r[0] + BASE == b)
        prev = rows[bi - 1][1] if bi > 0 else None
        fall = bi == 0 or prev not in UNCOND
        rb, rs = drefs[b], drefs[s]
        ab, as_ = arefs[b], arefs[s]
        reachable = fall or rb or rs or ab or as_
        if reachable:
            verdict = "到達しうる (fall-through または参照あり)"
        else:
            verdict = f"入口なし (直前 {prev} は無条件転送・直接参照 0)"
        if not call_ok:
            verdict = "call 命令として確認できず"
        print(f"| {s:#x} | {f[0]:#x} | `{insn.strip()}` | {b:#x} | {prev or '(関数先頭)'} | "
              f"{rb}/{rs} | {ab}/{as_} | {verdict} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
