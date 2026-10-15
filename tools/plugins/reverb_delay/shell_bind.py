#!/usr/bin/env python3
# Delphi 殻 ↔ C++ engine DLL の結合方式を静的に測る (#3446 / PLG-F4-4)。
#   FL_WIN64_DIR=<fl-win64 展開先> python3 tools/plugins/reverb_delay/shell_bind.py <殻 block> <engine block>
#   例: ... shell_bind.py 18999 19000   (Delay 3)   /   ... shell_bind.py 19164 19165   (Multiband Delay)
# 出力の番号は tools/plugins/reverb_delay/REPORT_APPENDIX.md §18 と対応する:
#   [1] 殻の IAT 上の読込系 API を呼ぶ thunk (jmp [IAT]) の呼出位置
#   [2] engine 名 (UTF-16 Delphi UnicodeString) の参照命令と、直接 call で LoadLibrary* に届く経路
#   [3] export 名の候補表 (Delphi UnicodeString へのポインタ配列) と、大文字小文字を区別して最初に一致する名
#   [4] 候補表を参照する関数から GetProcAddress への連鎖 (3 段以内)
#   [5] [2] の経路上の関数の間接呼出 call [rbp+D] (解決した関数ポインタ) の引数準備・戻り値の保存と、dispatcher 候補
#   [6] engine 側の export (序数・RVA) と、先頭命令 (jmp の転送先)
import argparse
import bisect
import os
import re
import struct
import sys
from collections import deque

import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RBP, X86_REG_RIP

LOADERS = ("LoadLibraryA", "LoadLibraryW", "LoadLibraryExW")
ENTRY_LOWER = ("vstpluginmain", "main", "createengine")


class Pe:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        self.pe = pefile.PE(path, fast_load=False)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.iat = {i.address: i.name.decode() for imp in self.pe.DIRECTORY_ENTRY_IMPORT for i in imp.imports if i.name}
        self.text = [s for s in self.pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
        self.tva = self.base + self.text.VirtualAddress
        self.tend = self.tva + self.text.Misc_VirtualSize
        self.funcs = sorted((self.base + e.struct.BeginAddress, self.base + e.struct.EndAddress)
                            for e in self.pe.DIRECTORY_ENTRY_EXCEPTION)
        self.starts = [f[0] for f in self.funcs]
        self.code = [f for f in self.funcs if self.tva <= f[0] < self.tend]
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.detail = True
        self.cache = {}

    def off(self, va):
        rva = va - self.base
        s = self.pe.get_section_by_rva(rva)
        return None if s is None else s.PointerToRawData + (rva - s.VirtualAddress)

    def read(self, va, n):
        o = self.off(va)
        return None if o is None else self.data[o: o + n]

    def dstr(self, va):
        # Delphi UnicodeString: 本体の 4 バイト前が文字数 (UTF-16 の要素数)
        head = self.read(va - 4, 4)
        if head is None:
            return None
        n = struct.unpack("<I", head)[0]
        raw = self.read(va, 2 * n) if 0 < n < 400 else None
        if raw is None:
            return None
        try:
            return raw.decode("utf-16le")
        except UnicodeDecodeError:
            return None

    def func_of(self, va):
        i = bisect.bisect_right(self.starts, va) - 1
        if i >= 0 and self.funcs[i][0] <= va < self.funcs[i][1]:
            return self.funcs[i]
        return None

    def insns(self, f):
        if f not in self.cache:
            o = self.off(f[0])
            self.cache[f] = list(self.md.disasm(self.data[o: o + (f[1] - f[0])], f[0]))
        return self.cache[f]

    def thunks(self):
        # jmp [rip+disp32] (FF 25) で IAT を指す thunk の VA -> API 名
        t = self.text
        raw = self.data[t.PointerToRawData: t.PointerToRawData + t.SizeOfRawData]
        out = {}
        for k in range(len(raw) - 6):
            if raw[k] == 0xFF and raw[k + 1] == 0x25:
                disp = struct.unpack_from("<i", raw, k + 2)[0]
                tgt = self.tva + k + 6 + disp
                if tgt in self.iat:
                    out[self.tva + k] = self.iat[tgt]
        return out

    def exports(self):
        return {e.name.decode(): self.base + e.address for e in self.pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}


def rip_target(ins):
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def direct_target(ins):
    if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_IMM:
        return ins.operands[0].imm
    return None


def refs_into(p, lo, hi):
    out = []
    for f in p.code:
        for ins in p.insns(f):
            t = rip_target(ins)
            if t is not None and lo <= t < hi:
                out.append((f, ins))
    return out


def reach(p, start, depth):
    # 直接 call で depth 段以内に届く関数 -> (呼出元の関数, 呼出位置)
    seen = {start: None}
    q = deque([(start, 0)])
    while q:
        f, d = q.popleft()
        if d == depth:
            continue
        for ins in p.insns(f):
            t = direct_target(ins)
            cf = p.func_of(t) if t is not None else None
            if cf and cf[0] == t and cf not in seen:
                seen[cf] = (f, ins.address)
                q.append((cf, d + 1))
    return seen


def chain(seen, f):
    # 根 (start) から f までの関数列
    out = [f]
    while seen.get(f):
        f = seen[f][0]
        out.append(f)
    return list(reversed(out))


def is_mem_rbp_call(ins):
    return ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X86_OP_MEM \
        and ins.operands[0].mem.base == X86_REG_RBP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shell", type=int)
    ap.add_argument("engine", type=int)
    ap.add_argument("--engine-name", default="engine_x64.dll")
    a = ap.parse_args()
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR を設定する (fl-win64 を展開。docs/WORKFLOW.md §11)")
    sh = Pe(os.path.join(root, "extracted", f"block{a.shell:05d}_PE.bin"))
    en = Pe(os.path.join(root, "extracted", f"block{a.engine:05d}_PE.bin"))
    th = sh.thunks()
    loaders = {k: v for k, v in th.items() if v in LOADERS}
    found = {"load": False, "name": False, "entry": False}

    print(f"[1] 殻 block {a.shell}: thunk 経由の読込系 API の呼出位置")
    cnt = {}
    for f in sh.code:
        for ins in sh.insns(f):
            t = direct_target(ins)
            if t in th and th[t] in LOADERS + ("GetProcAddress",):
                cnt.setdefault(th[t], []).append(ins.address)
    for k in sorted(cnt):
        print(f"    call {k}: {len(cnt[k])} 箇所 {[hex(x) for x in cnt[k]][:10]}")

    print(f"[2] engine 名 {a.engine_name!r} の UnicodeString と参照")
    name_va = []
    for m in re.finditer(re.escape(a.engine_name.encode("utf-16le")), sh.data, re.I):
        for s in sh.pe.sections:
            if s.PointerToRawData <= m.start() < s.PointerToRawData + s.SizeOfRawData:
                va = sh.base + s.VirtualAddress + (m.start() - s.PointerToRawData)
                v = sh.dstr(va)
                if v is not None and v.lower() == a.engine_name.lower():
                    name_va.append((va, v))
    for va, v in name_va:
        print(f"    実体 {va:#x} {v!r}")
        for f, ins in refs_into(sh, va, va + 1):
            print(f"    参照 {ins.address:#x} {ins.mnemonic} {ins.op_str} (関数 {f[0]:#x}-{f[1]:#x})")
            seen = reach(sh, f, 3)
            for g in list(seen):
                for ins2 in sh.insns(g):
                    t = direct_target(ins2)
                    if t in loaders:
                        path = " -> ".join(f"{x[0]:#x}" for x in chain(seen, g))
                        print(f"    LoadLibrary 経路: {path} -> call {loaders[t]} @ {ins2.address:#x} (thunk {t:#x})")
                        found["load"] = True
                        break

    print("[3] export 名候補 (Delphi UnicodeString) の表")
    names = {}
    for lo in ENTRY_LOWER:
        for m in re.finditer(re.escape(lo.encode("utf-16le")), sh.data, re.I):
            for s in sh.pe.sections:
                if s.PointerToRawData <= m.start() < s.PointerToRawData + s.SizeOfRawData:
                    va = sh.base + s.VirtualAddress + (m.start() - s.PointerToRawData)
                    v = sh.dstr(va)
                    if v is not None and v.lower() == lo:
                        names[va] = v
    slots = []
    for va in names:
        for m in re.finditer(re.escape(struct.pack("<Q", va)), sh.data):
            for s in sh.pe.sections:
                if s.PointerToRawData <= m.start() < s.PointerToRawData + s.SizeOfRawData:
                    slots.append((sh.base + s.VirtualAddress + (m.start() - s.PointerToRawData), names[va]))
    slots.sort()
    if not slots:
        sys.exit("[3] 候補表が無い")
    table = [v for _, v in slots]
    exp = en.exports()
    resolved = next((v for v in table if v in exp), None)
    print(f"    要素 {len(slots)} 件 {slots[0][0]:#x}-{slots[-1][0]:#x} (8 バイト間隔)")
    print(f"    順序: {table}")
    print(f"    engine block {a.engine} の export と大文字小文字を区別して最初に一致する名: {resolved!r}")
    found["name"] = resolved is not None

    print("[4] 候補表を参照する関数から GetProcAddress への連鎖")
    gpa = {k for k, v in th.items() if v == "GetProcAddress"}
    scan = refs_into(sh, slots[0][0], slots[-1][0] + 8)
    for f, ins in scan:
        print(f"    表を参照 {ins.address:#x} {ins.mnemonic} {ins.op_str} (関数 {f[0]:#x}-{f[1]:#x})")
        seen = reach(sh, f, 3)
        for g in list(seen):
            for ins2 in sh.insns(g):
                if direct_target(ins2) in gpa:
                    print(f"      -> GetProcAddress 呼出 {ins2.address:#x} (関数 {g[0]:#x}, 経路 {len(chain(seen, g)) - 1} 段)")
                    break

    print("[5] engine 経路 ([2] の経路上の関数) の間接呼出 call [rbp+D] と引数準備・戻り値の保存")
    entry_fns = set()
    for va, _ in name_va:
        for f, ins in refs_into(sh, va, va + 1):
            for g in reach(sh, f, 3):
                if any(is_mem_rbp_call(i2) for i2 in sh.insns(g)):
                    entry_fns.add(g)
    for g in entry_fns:
        ins_list = sh.insns(g)
        for j, ins in enumerate(ins_list):
            if is_mem_rbp_call(ins):
                print(f"    間接呼出 {ins.address:#x} {ins.mnemonic} {ins.op_str} (関数 {g[0]:#x})")
                found["entry"] = True
                for y in ins_list[max(0, j - 6): j]:
                    t = rip_target(y)
                    cb = sh.func_of(t) if (t is not None and y.mnemonic == "lea") else None
                    extra = f"  -> 関数 {cb[0]:#x} (引数 ABI は先頭 8 命令)" if cb else ""
                    print(f"        準備 {y.address:#x} {y.mnemonic} {y.op_str}{extra}")
                    if cb:
                        for z in sh.insns(cb)[:8]:
                            print(f"            callback {z.address:#x} {z.mnemonic} {z.op_str}")
                for y in ins_list[j + 1: j + 3]:
                    print(f"        後続 {y.address:#x} {y.mnemonic} {y.op_str}")
                for k, y in enumerate(ins_list):
                    if y.mnemonic == "call" and y.operands and y.operands[0].type == X86_OP_MEM \
                            and y.operands[0].mem.disp == 8 and y.operands[0].mem.base != X86_REG_RBP:
                        print(f"    dispatcher 呼出 {y.address:#x} {y.mnemonic} {y.op_str} (同じ関数内・[rax+8] = AEffect.dispatcher)")
                        for z in ins_list[max(0, k - 9): k]:
                            t = rip_target(z)
                            fval = ""
                            if t is not None and z.mnemonic == "movss":
                                fval = f"  = float {struct.unpack('<f', sh.read(t, 4))[0]!r}"
                            print(f"        準備 {z.address:#x} {z.mnemonic} {z.op_str}{fval}")
                        break

    print(f"[6] engine block {a.engine} の export (殻の候補表に対応する名前)")
    for k, va in sorted(exp.items(), key=lambda kv: kv[1]):
        if k.lower() not in ENTRY_LOWER and not k.startswith("?CreateEngine"):
            continue
        first = next(en.md.disasm(en.read(va, 16), va))
        print(f"    {k} RVA={va - en.base:#x} 先頭 {first.mnemonic} {first.op_str}")
        if first.mnemonic == "jmp" and first.operands and first.operands[0].type == X86_OP_IMM:
            tn = [n for n, v in exp.items() if v == first.operands[0].imm]
            print(f"      jmp 先 = export {tn}")
    failed = [k for k, v in found.items() if not v]
    print("判定:", "OK (経路・解決名・間接呼出の 3 点を確認)" if not failed else f"FAIL {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
