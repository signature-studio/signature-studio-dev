#!/usr/bin/env python3
"""UI 側ディスパッチャ 0xfdd2c0 の送出ゲートと mode 源を PE から再現する解析補助 (PY-245 / #3758)。

0xfdd2c0 の引数: op (ecx)・arg (edx)・mode (r8b)・flags (r9d)・fifth (stack。0xd84680 の呼出しは 0)。
判定順 (逆アセンブル VA は tools/python/REPORT_PY245.md):
  1. mode & 2 == 0 なら -1
  2. ゲート 3 (0xfdeaf0 を呼んで status 5): (mode & 0x20 かつ op が Q に入らない) または bl、かつ fifth == 0
  3. ゲート 2 (0x728f50 → 0x72afa0 が 1 を返すと status 4): flags & 4 かつ [0x15f6158] != 0 かつ 0x72afa0 の判定
  4. bl != 0 かつ ((ebx==1 かつ flags & 1) または (ebx==2 かつ flags & 2)) の G1 ブロック (0x60c220 > 0 で status ebx)
  5. flags & 8 == 0 なら status 0 (leaf 無し)。それ以外は switch (0xfdd788〜) を辿る
mode 源: 0xfdd270 が vtbl[+0x80] の戻り値 idx で表 0x1542bec[idx] を引き、0x81c0a0() == 0 なら 0xfdd2b8 の byte を OR する。

静的に決まらない値は引数で与える (未指定は不明として両分岐を出す):
  --bl 0|1     0x40fe90(rsi) の結果 (bl)
  --ebx 1|2    0x40fe90(rsi, [0xf55e80]) の結果 (ebx)
  --ctx 0|1    [0x15f6158] != 0 (0x728f50 の文脈)
  --g1 0|1     0x60c220(rsi, 0x57f, ...) > 0 (既定 0。G1 ブロック内の op 別ゲートは 0 と仮定)

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_dispatch_probe.py --modes
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_dispatch_probe.py --mode 0x22 --flags 0xf --bl 1 --ebx 1 --ctx 1

switch の leaf は 0xfdd788 から分岐を辿った到達集合 (arg に依存する分岐は両方を辿る)。実行時の値ではない。
"""
import argparse
import os
import re

import capstone
import pefile

FN_DISPATCH = 0xFDD2C0
SWITCH_ENTRY = 0xFDD788
MODE_TABLE = 0x1542BEC
MODE_OR_BYTE = 0xFDD2B8
Q_TABLE = 0xFDE910
G2_FN = 0x72AFA0
GATE_CALLS = {0x60C220, 0x728F50, 0xFDEAF0, 0x40FE90}
REG = {
    "rax": "a", "eax": "a", "ax": "a", "al": "a",
    "rbx": "b", "ebx": "b", "bx": "b", "bl": "b",
    "rcx": "c", "ecx": "c", "cx": "c", "cl": "c",
    "rdx": "d", "edx": "d", "dx": "d", "dl": "d",
    "r8": "r8", "r8d": "r8", "r8b": "r8",
    "r9": "r9", "r9d": "r9", "r9b": "r9",
}
BYTE_REG = {"al", "bl", "cl", "dl", "r8b", "r9b"}


class Pe:
    def __init__(self):
        path = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
        self.raw = open(path, "rb").read()
        pe = pefile.PE(data=self.raw, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
        self.base = pe.OPTIONAL_HEADER.ImageBase
        self.ends = {e.struct.BeginAddress: e.struct.EndAddress for e in pe.DIRECTORY_ENTRY_EXCEPTION}
        self.secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
                     for s in pe.sections]

    def v2o(self, va):
        rva = va - self.base
        for vaddr, vsz, praw, rsz in self.secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                return praw + (rva - vaddr)
        raise SystemExit(f"VA {va:#x} はセクションに無い")

    def byte(self, va):
        return self.raw[self.v2o(va)]

    def fn(self, va):
        end_rva = self.ends.get(va - self.base)
        if end_rva is None:
            raise SystemExit(f"fn {va:#x} は .pdata に無い")
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        fo = self.v2o(va)
        return {i.address: i for i in md.disasm(self.raw[fo:fo + (self.base + end_rva - va)], va)}


def s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def val(text, st, mem):
    text = text.strip()
    if text in REG:
        v = st[REG[text]]
        return v & 0xFF if text in BYTE_REG and v is not None else v
    if re.fullmatch(r"-?(0x[0-9a-fA-F]+|\d+)", text):
        return int(text, 0)
    m = re.fullmatch(r"(?:byte|dword|qword) ptr \[rbp \+ (0x[0-9a-fA-F]+)\]", text)
    if m:
        return mem.get(int(m.group(1), 16))
    return None


def cond(mn, fl):
    if fl is None:
        return None
    kind, x, y = fl
    if kind == "cmp":
        if x is None or y is None:
            return None
        ux, uy, sx, sy = x & 0xFFFFFFFF, y & 0xFFFFFFFF, s32(x), s32(y)
        table = {"je": sx == sy, "jz": sx == sy, "jne": sx != sy, "jnz": sx != sy,
                 "jg": sx > sy, "jge": sx >= sy, "jl": sx < sy, "jle": sx <= sy,
                 "ja": ux > uy, "jae": ux >= uy, "jb": ux < uy, "jbe": ux <= uy}
    else:
        if x is None:
            return None
        r, sr = x & 0xFFFFFFFF, s32(x)
        table = {"je": r == 0, "jz": r == 0, "jne": r != 0, "jnz": r != 0,
                 "jg": sr > 0, "jge": sr >= 0, "jl": sr < 0, "jle": sr <= 0,
                 "ja": r != 0, "jae": True, "jb": False, "jbe": r == 0}
    return table.get(mn)


def explore(insns, start, st0, mem, lo_addr=0):
    """到達可能な状態を列挙する。戻り値: call 先 -> 呼出し元 VA の集合、ret 時の (eax, ebx) の集合、状態数。"""
    seen, stack = set(), [(start, st0)]
    calls, rets = {}, set()
    while stack and len(seen) < 400000:
        addr, st = stack.pop()
        key = (addr, tuple(st[k] for k in ("a", "b", "c", "d", "r8", "r9")), st["flags"])
        if key in seen:
            continue
        seen.add(key)
        if addr not in insns:
            continue
        ins = insns[addr]
        mn, ops = ins.mnemonic, ins.op_str
        nxt = addr + ins.size
        parts = ops.split(", ", 1) if ops else []
        dst = parts[0] if parts else ""
        src = parts[1] if len(parts) > 1 else ""
        if mn in ("nop", "push", "leave"):
            stack.append((nxt, st))
            continue
        if mn == "ret":
            rets.add((st["a"], st["b"]))
            continue
        if mn == "jmp":
            tgt = int(dst, 16)
            if lo_addr <= tgt and tgt in insns:
                stack.append((tgt, st))
            continue
        if mn.startswith("j"):
            tgt = int(dst, 16)
            c = cond(mn, st["flags"])
            if c is None:
                stack.append((tgt, dict(st)))
                stack.append((nxt, dict(st)))
            elif c:
                stack.append((tgt, st))
            else:
                stack.append((nxt, st))
            continue
        if mn == "call":
            t = int(dst, 16) if re.fullmatch(r"0x[0-9a-fA-F]+", dst) else dst
            calls.setdefault(t, set()).add(addr)
            st = dict(st)
            for k in ("a", "c", "d", "r8", "r9"):
                st[k] = None
            st["flags"] = None
            stack.append((nxt, st))
            continue
        st = dict(st)
        if mn == "cmp":
            st["flags"] = ("cmp", val(dst, st, mem), val(src, st, mem))
            stack.append((nxt, st))
            continue
        if mn == "test":
            a, b = val(dst, st, mem), val(src, st, mem)
            st["flags"] = ("test", None if a is None or b is None else a & b, None)
            stack.append((nxt, st))
            continue
        r = REG.get(dst)
        if r is None:
            if mn in ("sub", "add", "and", "or", "xor"):
                st["flags"] = None
            stack.append((nxt, st))
            continue
        if mn in ("mov", "movzx", "movsxd"):
            v = val(src, st, mem)
            st[r] = None if dst in BYTE_REG else v
        elif mn == "xor":
            same = dst == src
            st[r] = 0 if same else None
            st["flags"] = ("test", 0, None) if same else None
        elif mn in ("sub", "add", "and", "or"):
            a, b = st[r], val(src, st, mem)
            res = None
            if a is not None and b is not None:
                res = {"sub": a - b, "add": a + b, "and": a & b, "or": a | b}[mn] & 0xFFFFFFFF
            st[r] = res
            if mn == "sub":
                st["flags"] = ("cmp", a, b)
            elif mn in ("and", "or"):
                st["flags"] = ("test", res, None)
            else:
                st["flags"] = None
        else:
            st[r] = None
            st["flags"] = None
        stack.append((nxt, st))
    return calls, rets, len(seen)


def new_state(d=None, r8=None):
    return {"a": None, "b": None, "c": None, "d": d, "r8": r8, "r9": None, "flags": None}


def frame(op=None, arg=None, flags=None, mode=None, fifth=0):
    return {0x40: op, 0x44: arg, 0x48: flags, 0x1A0: mode, 0x1B0: fifth}


def g2_values(insns2, op):
    """0x72afa0(ctx, op, arg) の戻り値 (eax) の集合。arg は不明として両分岐を辿る。"""
    st = new_state(d=op)
    st["b"] = None
    _calls, rets, _n = explore(insns2, G2_FN, st, frame(op=op))
    return {a for a, _b in rets}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modes", action="store_true", help="0xfdd270 の表 0x1542bec と OR 値 0xfdd2b8・Q の byte を出す")
    ap.add_argument("--mode", type=lambda s: int(s, 0), help="r8b の mode (0xfdd270 の戻り値)")
    ap.add_argument("--flags", type=lambda s: int(s, 0), default=0xF, help="r9d (既定 0xf。0xd84680 の呼出し値)")
    ap.add_argument("--fifth", type=int, default=0, help="stack 第 5 引数 (0xd84680 の呼出しは 0)")
    ap.add_argument("--bl", type=int, choices=(0, 1), default=None)
    ap.add_argument("--ebx", type=int, choices=(1, 2), default=None)
    ap.add_argument("--ctx", type=int, choices=(0, 1), default=None)
    ap.add_argument("--g1", type=int, choices=(0, 1), default=0)
    ap.add_argument("--ops", default="0-255", help="op の範囲 (例 0-255 / 0x28-0x36)")
    args = ap.parse_args()

    pe = Pe()
    q_byte = pe.byte(Q_TABLE)
    if args.modes:
        vals = sorted({pe.byte(MODE_TABLE + i) for i in range(256)})
        print(f"表 {MODE_TABLE:#x}[0..255] の byte 値 (distinct {len(vals)}): " + " ".join(f"{v:#04x}" for v in vals))
        print(f"OR 値 byte[{MODE_OR_BYTE:#x}] = {pe.byte(MODE_OR_BYTE):#04x} (0x81c0a0() == 0 のとき mode に OR)")
        print(f"Q の byte[{Q_TABLE:#x}] = {q_byte:#04x} (op 8〜15 のうち bit (op-8) が 1 の op)")
        return
    if args.mode is None:
        ap.error("--mode か --modes が必要")

    insns = pe.fn(FN_DISPATCH)
    insns2 = pe.fn(G2_FN)
    lo, hi = (int(x, 0) for x in args.ops.split("-"))
    mode, flags, fifth = args.mode, args.flags, args.fifth
    p_on = bool(mode & 0x20)
    print(f"mode={mode:#04x} flags={flags:#x} fifth={fifth} bl={args.bl} ebx={args.ebx} ctx={args.ctx} g1={args.g1}")
    print(f"mode&2={'有' if mode & 2 else '無 (-1)'}  mode&0x20={'有' if p_on else '無'}  mode&4={'有' if mode & 4 else '無'}")

    outcome, reached = {}, {}
    for op in range(lo, hi + 1):
        if not mode & 2:
            outcome[op] = "status -1"
            continue
        q = 8 <= op <= 15 and (q_byte >> (op - 8)) & 1
        if p_on and not q or args.bl == 1:
            s5 = True
        elif args.bl is None:
            s5 = None
        else:
            s5 = False
        if fifth == 0 and s5 is True:
            outcome[op] = "status 5 (0xfdeaf0)"
            continue
        if fifth == 0 and s5 is None:
            outcome[op] = "status 5 か続行 (bl 不明)"
            continue
        if flags & 4:
            rets2 = g2_values(insns2, op)
            if args.ctx == 1 and 1 in rets2:
                outcome[op] = "status 4 (0x72afa0 が 1)"
                continue
            if args.ctx is None and 1 in rets2:
                outcome[op] = "status 4 か続行 (ctx 不明)"
                continue
        if args.bl != 0 and (args.ebx == 1 and flags & 1 or args.ebx == 2 and flags & 2):
            if args.g1 == 1:
                outcome[op] = f"status {args.ebx} (0x60c220 > 0)"
                continue
        if not flags & 8:
            outcome[op] = "status 0・switch 不到達 (flags&8 無し)"
            continue
        st = new_state()
        st["a"] = op
        calls, _rets, _n = explore(insns, SWITCH_ENTRY, st, frame(op=op, flags=flags, mode=mode, fifth=fifth),
                                   lo_addr=SWITCH_ENTRY)
        reached[op] = {t for t in calls if isinstance(t, int) and t not in GATE_CALLS}
        outcome[op] = None
    common = set.intersection(*reached.values()) if reached else set()
    if reached:
        print("switch 到達の共通 call (全 op で到達。既定経路の共通部分): " + " ".join(f"{t:#x}" for t in sorted(common)))
    for op, leaves in reached.items():
        own = sorted(leaves - common)
        outcome[op] = "switch leaf " + (" ".join(f"{t:#x}" for t in own) if own else "(固有なし)")

    groups = []
    for op in range(lo, hi + 1):
        if groups and groups[-1][2] == outcome[op]:
            groups[-1][1] = op
        else:
            groups.append([op, op, outcome[op]])
    for a, b, text in groups:
        rng = f"{a:#04x}" if a == b else f"{a:#04x}-{b:#04x}"
        print(f"  op {rng}: {text}")


if __name__ == "__main__":
    main()
