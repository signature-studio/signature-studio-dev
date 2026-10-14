#!/usr/bin/env python3
"""FLEngine (win PE) の Python4Delphi メソッド表と各ラッパーの PyArg_ParseTupleAndKeywords 呼出しから、
書式文字列 (`i|ii` 等) と kwlist (引数名) を静的に復元する。実機不要 (PY-9 (b))。

  python3 analysis/flapi_kwargs.py [FLEngine PE]   -> analysis/flapi/flapi_kwargs.json

方式 (rodata の並び順ではなくコードの参照関係を使う):
  1. .data 内の PyMethodDef 相当表 (32B 刻み: name*, fn*, flags, doc*) を走査。
  2. 各 fn の冒頭を逆アセンブルし、最初の call までの `lea reg,[rip+disp]` を回収。
     呼出し形式は kw_form で決める (PY-116 #2952):
     kw 形式 (flags=3 は必ず、flags=1 は `mov rdx, r8` がある場合): PyArg_ParseTupleAndKeywords 相当。r8=書式, r9=kwlist (char* 配列, NULL 終端)
     非 kw 形式 (flags=1 の大半)  : PyArg_ParseTuple 相当。rdx=書式。kwlist 無し (実 FL はキーワード引数を受けない)
     flags=4 (NOARGS)          : 引数なし (PyArg_Parse* を呼ばないので書式は復元しない)
     最初の間接 call (= PyArg_Parse* のインポート表呼出し) 直前までの lea [rip+x] を見る。
     その前に ret / int3 に当たったら (= 関数末尾を越えて隣の関数の lea を拾うことになる) 書式無しとする。
  3. 表ごとに flapi_table.json の module と名前集合の重なりで module を決定。
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "flapi")
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from paths import FL_WIN64_DIR  # noqa: E402

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FMT = re.compile(r"^[A-Za-z|:;$!#*()\[\]]{0,24}$")


class Image:
    def __init__(self, path):
        global capstone, pefile, X86_OP_MEM, X86_REG_RIP
        import capstone  # 遅延 import (flapi_table.py が kwsig_of だけ使うとき不要)
        import pefile
        from capstone.x86 import X86_OP_MEM, X86_REG_RIP
        self.b = open(path, "rb").read()
        self.pe = pefile.PE(data=self.b, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.secs = self.pe.sections
        self.text = next(s for s in self.secs if s.Name.startswith(b".text"))
        self.data = next(s for s in self.secs if s.Name.startswith(b".data"))
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True

    def off(self, va):
        r = va - self.base
        for s in self.secs:
            if s.VirtualAddress <= r < s.VirtualAddress + s.SizeOfRawData:
                return r - s.VirtualAddress + s.PointerToRawData
        return None

    def cstr(self, va, maxlen=200):
        if not va:
            return None
        o = self.off(va)
        if o is None:
            return None
        e = self.b.find(b"\0", o, o + maxlen)
        return None if e < 0 else self.b[o:e].decode("latin1")

    def u64(self, va):
        o = self.off(va)
        return struct.unpack_from("<Q", self.b, o)[0]

    def in_text(self, va):
        r = va - self.base
        return self.text.VirtualAddress <= r < self.text.VirtualAddress + self.text.Misc_VirtualSize

    def method_tables(self):
        """[(table_va, [(name, fn_va, flags, doc)])] — 32B 刻みで連続する有効エントリ列。"""
        s = self.data
        lo, hi = s.PointerToRawData, s.PointerToRawData + s.SizeOfRawData
        ok = {}
        for o in range(lo, hi - 32, 8):
            nm, fn, fl, doc = struct.unpack_from("<QQQQ", self.b, o)
            if not self.in_text(fn) or fl not in (1, 3, 0x13, 0x11, 0x2, 0x4):
                continue
            n = self.cstr(nm, 64)
            if n is None or not IDENT.match(n):
                continue
            d = self.cstr(doc) if doc else ""
            if d is None:
                continue
            ok[o] = (n, fn, fl, d)
        tables, cur = [], []
        for o in sorted(ok):
            if cur and o != cur[-1][0] + 32:
                tables.append(cur)
                cur = []
            cur.append((o, ok[o]))
        if cur:
            tables.append(cur)
        va0 = self.base + s.VirtualAddress - s.PointerToRawData
        return [(va0 + t[0][0], [e for _, e in t]) for t in tables]

    def pyarg_setup(self, fn):
        """PyArg_Parse* の直前 (前の direct call より後) の命令列。間接 call に届かない・関数末尾に当たったら None。"""
        o = self.off(fn)
        seq = []
        for i in self.md.disasm(self.b[o:o + 0x200], fn):
            if i.mnemonic in ("ret", "int3"):
                return None
            if i.mnemonic == "call":
                if i.op_str.startswith("qword ptr ["):
                    return seq  # PyArg_Parse* はインポート表経由の間接 call
                seq = []
                continue
            seq.append(i)
        return None

    def kw_form(self, fn, flags):
        """PyArg_Parse* へ kwargs を渡す形式か (rdx = r8 の kwargs・r8 = 書式・r9 = kwlist)。
        flags&2 (METH_KEYWORDS) は全件この形式。flags=1 (VARARGS のみ) でこの形式なのは plugins.getPresetCount の 1 件だけ
        (PY-116 #2952)。CPython は VARARGS 呼出しで r8 を設定しないので、その関数の kwargs は呼出し元の不定値になる。"""
        seq = self.pyarg_setup(fn) or []
        return bool(flags & 2) or any(i.mnemonic == "mov" and i.op_str == "rdx, r8" for i in seq)

    def wrapper_args(self, fn, flags):
        """ラッパー冒頭 (最初の間接 call まで) の lea [rip+x] を回収し (fmt, kwlist) を返す。"""
        if flags & 4:
            return None, None  # METH_NOARGS
        o = self.off(fn)
        lea = {}
        parsed = False
        for i in self.md.disasm(self.b[o:o + 0x200], fn):
            if i.mnemonic == "call" and i.op_str.startswith("qword ptr ["):
                parsed = True
                break  # PyArg_Parse* はインポート表経由の間接 call
            if i.mnemonic in ("ret", "int3"):
                break
            if i.mnemonic == "lea" and len(i.operands) == 2 and i.operands[1].type == X86_OP_MEM \
                    and i.operands[1].mem.base == X86_REG_RIP:
                lea[i.reg_name(i.operands[0].reg)] = i.address + i.size + i.operands[1].mem.disp
        if not parsed:
            return None, None
        kw = self.kw_form(fn, flags)
        fmt_reg = "r8" if kw else "rdx"
        fmt = self.cstr(lea.get(fmt_reg), 40) if fmt_reg in lea else None
        if fmt is not None and not FMT.match(fmt):
            fmt = None
        names = None
        if kw and "r9" in lea:
            names = []
            va = lea["r9"]
            while len(names) < 40:
                p = self.u64(va + 8 * len(names))
                if p == 0:
                    break
                s = self.cstr(p, 64)
                if s is None or not IDENT.match(s):
                    names = None
                    break
                names.append(s)
        return fmt, names

    def wrapper_outs(self, fn, flags):
        """PyArg_Parse* の直前 (前の call より後) に渡される非 0 の出力ポインタ数。書式が消費する数と比べる (PY-116 #2952)。
        非 kw: r8, r9, [rsp+0x20].. が出力 (rdx=書式)。kw: [rsp+0x20].. が出力 (r8=書式, r9=kwlist)。NULL (0) の引数は数えない。"""
        if flags & 4:
            return None
        seq = self.pyarg_setup(fn)
        if seq is None:
            return None
        kw = self.kw_form(fn, flags)
        slots = []
        for i in seq:
            m = re.match(r"qword ptr \[rsp \+ (0x[0-9a-f]+)\], r[a-z0-9]+$", i.op_str)
            if i.mnemonic == "mov" and m:
                slots.append((int(m.group(1), 16) - 0x20) // 8 + (0 if kw else 2))
            m = re.match(r"(r8|r9), (.+)$", i.op_str)
            if m and not kw and i.mnemonic in ("lea", "mov") and not re.match(r"-?(0x[0-9a-f]+|\d+)$", m.group(2)):
                slots.append(0 if m.group(1) == "r8" else 1)
        return max(slots) + 1 if slots else 0


def fmt_ptrs(fmt):
    """書式が消費するポインタ数 (単位の文字 1 つ = 1、`#` `!` `&` は各 +1)。`:` `;` 以降は関数名なので数えない。"""
    n = 0
    for c in fmt:
        if c in ":;":
            break
        if c.isalpha() or c in "#!&":
            n += 1
    return n


def fmt_units(fmt):
    """書式から (必須数, 全数)。`|` 以降が省略可。単純な 1 文字 = 1 引数のみ数える (`O!` 等は 1 単位)。"""
    req, opt, seen_bar = 0, 0, False
    i = 0
    while i < len(fmt):
        c = fmt[i]
        if c == "|":
            seen_bar = True
        elif c in ":;":
            break
        elif c in "!#*&":
            pass
        else:
            if seen_bar:
                opt += 1
            else:
                req += 1
        i += 1
    return req, req + opt


def kwsig_of(e):
    """flapi_table.json の関数エントリに載せる `kwsig` (実バイナリ由来の引数仕様)。"""
    s = {"flags": e["flags"], "fmt": e["fmt"]}
    if e.get("kwlist") is not None and e["flags"] & 2:  # flags=1 の kwlist は記録のみ (CPython は VARARGS 呼出しの kwargs を拒否する)
        s["kwlist"] = e["kwlist"]
    if "max" in e:
        s["required"], s["max"] = e["required"], e["max"]
    return s


def merge_into_table(table_path, kw):
    """flapi_table.json の各関数に `kwsig` を追記 (冪等)。flapi_table.py も同じ JSON から再生成時に取り込む。"""
    t = json.load(open(table_path))
    for m, funcs in kw["modules"].items():
        for n, e in funcs.items():
            t["modules"][m][n]["kwsig"] = kwsig_of(e)
    json.dump(t, open(table_path, "w"), indent=1, ensure_ascii=False)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else f"{FL_WIN64_DIR}/extracted/block00031_PE.bin"
    img = Image(path)
    table = json.load(open(os.path.join(OUT, "flapi_table.json")))
    mods = {m: set(v) for m, v in table["modules"].items()}
    out = {"source": "${FL_WIN64_DIR}/extracted/block00031_PE.bin", "modules": {}, "unassigned": []}
    for tbl_va, tbl in img.method_tables():
        names = [e[0] for e in tbl]
        # module 決定: 表中の (name,doc) が table の module と一致する数
        score = {}
        for m, funcs in table["modules"].items():
            score[m] = sum(1 for n, _, _, d in tbl if n in funcs and (not d or funcs[n]["doc"] == d or not funcs[n]["doc"]))
        best = max(score, key=score.get)
        if score[best] == 0:
            out["unassigned"].append({"table_va": hex(tbl_va), "names": names[:6]})
            continue
        tops = [m for m, s in score.items() if s == score[best]]
        for n, fn, fl, d in tbl:
            cands = [m for m in tops if n in mods[m]] or [m for m in mods if n in mods[m] and score[m] > 0]
            if not cands:
                continue
            m = cands[0]
            fmt, kws = img.wrapper_args(fn, fl)
            ent = {"flags": fl, "fmt": fmt, "kwlist": kws, "fn_va": hex(fn), "outs": img.wrapper_outs(fn, fl)}
            if fmt is not None:
                ent["required"], ent["max"] = fmt_units(fmt)
                ent["ptrs"] = fmt_ptrs(fmt)
            out["modules"].setdefault(m, {})[n] = ent
    json.dump(out, open(os.path.join(OUT, "flapi_kwargs.json"), "w"), indent=1, ensure_ascii=False)
    merge_into_table(os.path.join(OUT, "flapi_table.json"), out)
    tot = sum(len(v) for v in out["modules"].values())
    withkw = sum(1 for v in out["modules"].values() for e in v.values() if e["kwlist"] is not None)
    print(json.dumps({m: len(v) for m, v in out["modules"].items()}), tot, "kwlist:", withkw,
          "unassigned tables:", len(out["unassigned"]))


if __name__ == "__main__":
    main()
