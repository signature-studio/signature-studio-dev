#!/usr/bin/env python3
# M6 共通ライブラリ:
#  - PE32+/Mach-O x86_64 の関数境界と命令フィーチャ抽出 (capstone 5.0.x)
#  - mac 符号 (nm log) 由来のクラス閉包シード選定用の最小 disasm セット
#
# 読取のみ前提: 対象バイナリは analysis/plugins/ott/binaries/ 配下 (変更禁止).
import struct
import sys
from collections import defaultdict

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
except ImportError:
    Cs = None

PAGE = 0x1000


def f32hex(b):
    return b.hex()


def align(n, a=PAGE):
    return (n + a - 1) & ~(a - 1)


class Bin:
    """x86_64 イメージ (PE32+ / Mach-O x86_64 slice 共通)。
    sections: list of (name, lo_va, data(bytes mapped at lo_va))
    fns:      list of (va, size) 関数境界 (.pdata または symbol 開始)
    func_names: dict va -> name (mac のみ実符号 / win64 は空)
    """

    def __init__(self, path):
        self.path = path
        self.sections = []       # (name, lo_va, bytes)
        self.fns = []            # [(start_va, size)]
        self.ind_secs = []       # (name, va, data, stride) stub/ptr section
        self.func_names = {}     # va -> name
        self.image_lo = None
        self.image_hi = 0
        self.b = open(path, 'rb').read()
        if self.b[:2] == b'MZ':
            self._load_pe()
        else:
            self._load_macho()

    # ---------- data access ----------
    def read_at(self, va, n):
        for name, lo, data in self.sections:
            hi = lo + len(data)
            if lo <= va and va + n <= hi:
                off = va - lo
                return data[off:off + n]
        return None

    def read_le32(self, va):
        b = self.read_at(va, 4)
        return None if b is None else struct.unpack('<I', b)[0]

    def read_cstr(self, va, cap=256):
        for name, lo, data in self.sections:
            if lo <= va < lo + len(data):
                off = va - lo
                end = data.find(b'\0', off, off + cap)
                return data[off:end]
        return None

    # ---------- secs ----------
    def sec_find(self, name):
        for n, lo, data in self.sections:
            if n == name:
                return lo, data
        return None, None

    # ---------- PE ----------
    def _load_pe(self):
        b = self.b
        pe_off = struct.unpack_from('<I', b, 0x3c)[0]
        assert b[pe_off:pe_off + 4] == b'PE\0\0'
        nsec = struct.unpack_from('<H', b, pe_off + 6)[0]
        optsz = struct.unpack_from('<H', b, pe_off + 20)[0]
        sec_off = pe_off + 24 + optsz
        for i in range(nsec):
            e = sec_off + i * 40
            name = b[e:e + 8].rstrip(b'\0').decode('utf-8', 'replace')
            vsize, vaddr, rawsz, rawptr = struct.unpack_from('<IIII', b, e + 8)
            if vsize == 0 or vaddr == 0:
                continue
            raw = b[rawptr:rawptr + min(rawsz, vsize)] if rawsz else b''
            raw = raw + bytes(max(0, vsize - len(raw)))
            self.sections.append((name, vaddr, raw))
            if self.image_lo is None or vaddr < self.image_lo:
                self.image_lo = vaddr
            self.image_hi = max(self.image_hi, vaddr + vsize)
        # .pdata → RUNTIME_FUNCTION 表 [Begin, End, Unwind]
        pv, pd = self.sec_find('.pdata')
        if pd:
            n = len(pd) // 12
            for i in range(n):
                beg, end, _u = struct.unpack_from('<III', pd, i * 12)
                if beg and end > beg:
                    self.fns.append((beg, end - beg))
        self.fns.sort()

    # ---------- Mach-O ----------
    def _load_macho(self):
        b = self.b
        magic = struct.unpack_from('<I', b, 0)[0]
        assert magic == 0xFEEDFACF, hex(magic)
        ncmds, cmdoff = struct.unpack_from('<I', b, 16)[0], 32
        symtab = None
        for _ in range(ncmds):
            cmd, size = struct.unpack_from('<II', b, cmdoff)
            if cmd == 0x19:  # LC_SEGMENT_64
                name = b[cmdoff + 8:cmdoff + 24].rstrip(b'\0').decode('utf-8', 'replace')
                nsegs = struct.unpack_from('<I', b, cmdoff + 64)[0]
                for j in range(nsegs):
                    e = cmdoff + 72 + j * 80
                    sname = b[e:e + 16].rstrip(b'\0').decode('utf-8', 'replace')
                    vaddr, vsize = struct.unpack_from('<QQ', b, e + 32)
                    soff = struct.unpack_from('<I', b, e + 48)[0]
                    flags = struct.unpack_from('<I', b, e + 64)[0]
                    resv2 = struct.unpack_from('<H', b, e + 72)[0]
                    if vaddr == 0 or vsize == 0:
                        continue
                    raw = b[soff:soff + vsize]
                    raw = raw + bytes(max(0, vsize - len(raw)))
                    self.sections.append((sname, vaddr, raw))
                    ttype = flags & 7
                    if ttype in (7, 8, 9):  # NON_LAZY/LAZY ptr / SYMBOL_STUBS
                        stride = resv2 if ttype == 9 else 8
                        data2 = raw[:vsize - (vsize % stride if stride else 0)]
                        self.ind_secs.append((sname, vaddr, data2, stride))
                    if sname in ('__text',):
                        self.text_lo, self.text_data = vaddr, raw
                    if self.image_lo is None or vaddr < self.image_lo:
                        self.image_lo = vaddr
                    self.image_hi = max(self.image_hi, vaddr + vsize)
            elif cmd == 0x2:  # LC_SYMTAB
                symtab = struct.unpack_from('<IIII', b, cmdoff + 8)
            elif cmd == 0xb:  # LC_DYSYMTAB
                self.dysymtab = struct.unpack_from('<18I', b, cmdoff + 8)
            cmdoff += size
        # symtab (nlist_64: u32 strx, u8 type, u8 sect, u16 desc, u64 value)
        if symtab:
            symoff, nsyms, stroff, strsize = symtab
            self.syms = []  # (idx, val, name)
            for i in range(nsyms):
                e = symoff + i * 16
                if e + 16 > len(b):
                    break
                strx, typ, sect, desc, val = struct.unpack_from('<IBBHQ', b, e)
                if val == 0:
                    continue
                e2 = stroff + strx
                sname = b[e2:b.find(b'\0', e2, e2 + 160)].decode('utf-8', 'replace')
                self.syms.append((i, val, sname))
                kind = typ & 0x0E
                if kind == 0x0E and (val, sname) not in self.func_names.items():
                    # N_SECT: sect==__text(sect番号は後で照合) → いったん全部記録し呼出で絞る
                    self.func_names.setdefault(val, sname)
        for va, sname in self.func_names.items():
            # 外部 _ 前除去と mangled 保持
            if sname.startswith('_'):
                self.func_names[va] = sname
        secs_text = [(lo, data, n) for (n, lo, data) in self.sections if n == '__text']
        if secs_text:
            alo, adata, _ = secs_text[0]
            fns = sorted(va for va in self.func_names if alo <= va < alo + len(adata))
            for i, va in enumerate(fns):
                sz = (fns[i + 1] - va) if i + 1 < len(fns) else 0x200
                self.fns.append((va, sz))
        self.fns.sort()
        # --- 間接シンボル表: stub/GOT/ラズー ptr va → dyld 名 ---
        # section 順序 (__stubs: 6B stride=reserved2, pointer 用: 8B) で indirectsyms を消費
        self.stub_names = {}
        if getattr(self, 'dysymtab', None) and getattr(self, 'syms', None):
            symoff, _symn, stroff, _strn = symtab
            indoff, nind = self.dysymtab[12], self.dysymtab[13]
            base = 0
            for (n, lo, data, stride) in self.ind_secs:
                cnt = len(data) // stride
                for j in range(cnt):
                    sidx = struct.unpack_from('<I', self.b, indoff + 4 * (base + j))[0] \
                        if base + j < nind else 0xFFFFFFFF
                    if sidx == 0xFFFFFFFF or sidx >= _symn:
                        base += cnt
                        break
                    e = symoff + sidx * 16
                    strx = struct.unpack_from('<I', self.b, e)[0]
                    e2 = stroff + strx
                    nm = self.b[e2:self.b.find(b'\0', e2, e2 + 200)].decode('utf-8', 'replace')
                    self.stub_names[lo + j * stride] = nm
                base += cnt


# ---------------- disasm / features ----------------
class Dis:
    def __init__(self, binobj):
        self.bin = binobj
        self.cs = Cs(CS_ARCH_X86, CS_MODE_64)
        self.cs.detail = True

    def bytes_at(self, va, n):
        return self.bin.read_at(va, n)

    def rip_target(self, ins, op):
        if op.type == 3:  # MEM
            if op.mem.base == 41:  # rip
                return ins.address + ins.size + op.mem.disp
        return None

    def features(self, va, size):
        """→ dict(features). data_refs: rip 相対 or 絶対 data 参照の読出ビット列 hex,
        imms: 32bit 即値, calls: 呼出先 va, calls_ind: 間接呼出フラグ"""
        data, imms, calls, ind = defaultdict(int), defaultdict(int), [], 0
        code = self.bytes_at(va, size)
        if code is None:
            return None
        for ins in self.cs.disasm(code[:size], va):
            for op in ins.operands:
                t = self.rip_target(ins, op)
                if t is not None:
                    n = ins.size  # movss/oreads は命令幅で 近似 (2/4/8)
                    if ins.mnemonic in ('movss', 'movlps', 'vinsertps'):
                        n = 4
                    elif ins.mnemonic in ('movsd',):
                        n = 8
                    raw = self.bin.read_at(t, max(n, 4))
                    if raw:
                        data[raw[:8].hex()] += 1  # float/immed は 4B 単位で残す
                        for k in range(0, len(raw)):
                            pass
                        # 4B granularity: float 即値定数は .rdata 上 4B 単位配置のことが多い
                        raw4 = raw[:4].hex()
                        if raw4 != '00000000':
                            data[('4:' + raw4)] += 1
                elif op.type == 2 and ins.mnemonic in ('mov', 'cmp', 'test', 'add', 'sub',
                                                       'and', 'or', 'xor', 'imul'):
                    imm = op.imm if op.imm >= 0 else op.imm & 0xffffffff
                    if abs(imm) > 8 and abs(imm) < 0x40000000:
                        imms[imm] += 1
            m = ins.mnemonic
            if m == 'call' and ins.operands and ins.operands[0].type == 2:
                calls.append(ins.operands[0].imm)   # capstone: 絶対ターゲット済み
            elif m == 'call':
                ind += 1
            elif m == 'jmp' and any(o.type == 3 and o.mem.base == 41 for o in ins.operands):
                pass
        return {'va': va, 'size': size, 'data': dict(data), 'imms': dict(imms),
                'calls': calls, 'indirect': ind}


def match_score(f_w, f_m):
    """win64 関数 f_w と mac 関数 f_m のフィーチャ一致スコア (0..1)。"""
    dw = f_w['data']
    dm = f_m['data']
    if not dw or not dm:
        return 0.0
    common = set(k for k in dw.keys() if k in dm)
    common = set(k for k in common if not k.startswith('4:0000'))
    nmin = min(sum(dw.values()), sum(dm.values())) or 1
    w_common = sum(min(dw[k], dm[k]) for k in common)
    s_data = w_common / nmin
    # call 構造は後段で付加呼び (この段では data のみ)
    return s_data
