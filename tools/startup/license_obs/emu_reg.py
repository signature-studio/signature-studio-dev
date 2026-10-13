#!/usr/bin/env python3
"""FLEngine_x64.dll の登録パーサ 0x10c7cd0 を実機械語のまま unicorn で実行し、レジストリ入力ごとに
byte[0x14f84a8] (登録フラグ) と gradeChar を観測する (lift を介さない動的観測)。

方針: PE を ImageBase=0x400000 に敷設 (再配置不要)。Delphi RTL は無改変で実行。
  - メモリマネージャ (MM_TABLE 0x13a5c90 の 4 関数) だけ Python の bump allocator に差し替える
  - IAT は全スロットを 16B 刻みの `ret` スタブへ向け、スタブ実行時に Python 側 API 実装を呼ぶ
  - レジストリは Python の辞書 (HKCU/HKLM)。ライセンスの生成・偽造はしない (観測のみ)
"""
import os, struct, sys
import pefile
from unicorn import (Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_READ_UNMAPPED, UC_HOOK_MEM_WRITE_UNMAPPED,
                     UC_HOOK_MEM_FETCH_UNMAPPED, UcError)
from unicorn.x86_const import *

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from peidx import DLL  # noqa: E402

BASE = 0x400000
STUB = 0x7e000000
STACK_TOP = 0x7ffe0000
HEAP = 0x30000000
HEAP_SZ = 0x10000000
FLAG, GRADE_SLOT_PTR, MMT = 0x14f84a8, 0x15e4790, 0x13a5c90
TLS_INDEX_VAR = 0x13a9388
# 実機では翻訳オブジェクト (起動時に生成) を引く文字列取得 `_(lit)`: (rcx=&out UnicodeString, rdx=リテラル) → out := lit
OVERRIDE_VAS = (0x8da350,)
ENTRY, SENTINEL_OFF = 0x10c7cd0, 0xfff0


def u16z(s):
    return s.encode('utf-16le') + b'\0\0'


class Reg:
    """HKCU/HKLM の簡易モデル。キーは (hive, 小文字パス)。値は (型, bytes)。"""
    def __init__(self):
        self.keys = {}
        self.log = []

    @staticmethod
    def norm(p):
        return p.replace('/', '\\').strip('\\').lower()

    def put(self, hive, path, name, val):
        k = self.keys.setdefault((hive, self.norm(path)), {})
        if isinstance(val, int):
            k[name.lower()] = (4, struct.pack('<I', val))
        else:
            k[name.lower()] = (1, u16z(val))

    def exists(self, hive, path):
        n = self.norm(path)
        return any(h == hive and (p == n or p.startswith(n + '\\')) for (h, p) in self.keys) or n == ''

    def subkeys(self, hive, path):
        n = self.norm(path)
        out = set()
        for (h, p) in self.keys:
            if h == hive and (p.startswith(n + '\\') if n else True) and p != n:
                rest = p[len(n) + 1:] if n else p
                out.add(rest.split('\\')[0])
        return sorted(out)


class Emu:
    def __init__(self, reg, comp='PC1', appdata='C:\\Users\\u\\AppData\\Roaming', trace=False):
        self.reg, self.comp, self.appdata, self.trace = reg, comp, appdata, trace
        self.api_log = []
        self.pe = pefile.PE(DLL)
        self.uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc = self.uc
        size = (self.pe.OPTIONAL_HEADER.SizeOfImage + 0xfff) & ~0xfff
        uc.mem_map(BASE, size)
        uc.mem_write(BASE, self.pe.header)
        for s in self.pe.sections:
            data = s.get_data()
            uc.mem_write(BASE + s.VirtualAddress, data[:s.Misc_VirtualSize] if s.SizeOfRawData >= s.Misc_VirtualSize else data)
        uc.mem_map(STACK_TOP - 0x800000, 0x800000)
        uc.mem_map(HEAP, HEAP_SZ)
        uc.mem_map(STUB, 0x10000)
        self.heap_ptr = HEAP + 0x1000
        self.sizes = {}
        self.stubs = {}
        self.names = {}
        self.handles = {}
        self.next_h = 0x1000
        self.sent = STUB + SENTINEL_OFF
        uc.mem_write(self.sent, b'\xc3')
        self._patch_iat()
        self._patch_mm()
        uc.hook_add(UC_HOOK_CODE, self._code, begin=STUB, end=STUB + 0xffff)
        self.overrides = {}
        self.ovr_hits = []
        for va in OVERRIDE_VAS:
            uc.hook_add(UC_HOOK_CODE, self._ovr, begin=va, end=va)
        uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED, self._unm)
        self.unmapped = None

    # ---- メモリ ----
    def alloc(self, n, zero=True):
        n = (max(n, 1) + 15) & ~15
        p = self.heap_ptr
        self.heap_ptr += n + 16
        if self.heap_ptr > HEAP + HEAP_SZ:
            raise MemoryError('emu heap exhausted')
        self.sizes[p] = n
        return p

    def _unm(self, uc, access, addr, size, value, ud):
        rip = uc.reg_read(UC_X86_REG_RIP)
        self.unmapped = (access, addr, size, rip)
        return False

    # ---- スタブ ----
    def stub_for(self, name):
        if name in self.stubs:
            return self.stubs[name]
        i = len(self.stubs) + 1
        addr = STUB + 0x100 + i * 16
        self.uc.mem_write(addr, b'\xc3')
        self.stubs[name] = addr
        self.names[addr] = name
        return addr

    def _patch_iat(self):
        self.pe.parse_data_directories([pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        for ent in self.pe.DIRECTORY_ENTRY_IMPORT:
            dll = ent.dll.decode().lower()
            for imp in ent.imports:
                nm = imp.name.decode() if imp.name else f'ord{imp.ordinal}'
                a = self.stub_for(f'{dll}!{nm}')
                self.uc.mem_write(imp.address, struct.pack('<Q', a))
        d = getattr(self.pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', None)

    def _patch_mm(self):
        for off, nm in ((0, 'GetMem'), (8, 'FreeMem'), (0x10, 'ReallocMem'), (0x18, 'AllocMem'), (0x20, 'RegLeak'), (0x28, 'UnregLeak')):
            self.uc.mem_write(MMT + off, struct.pack('<Q', self.stub_for('mm!' + nm)))

    # ---- 文字列/引数 ----
    def r(self, reg):
        return self.uc.reg_read(reg)

    def rd_w(self, p, maxn=520):
        if not p:
            return ''
        b = bytearray()
        for _ in range(maxn):
            c = bytes(self.uc.mem_read(p + len(b), 2))
            if c == b'\0\0':
                break
            b += c
        return b.decode('utf-16le', 'replace')

    def rd_a(self, p, maxn=520):
        if not p:
            return ''
        b = bytearray()
        for _ in range(maxn):
            c = bytes(self.uc.mem_read(p + len(b), 1))
            if c == b'\0':
                break
            b += c
        return b.decode('latin1')

    def stack_arg(self, n):  # n=5 → 第5引数 (ret アドレスの上に shadow 32B)
        rsp = self.r(UC_X86_REG_RSP)
        return struct.unpack('<Q', bytes(self.uc.mem_read(rsp + 8 + 8 * (n - 1), 8)))[0] if n >= 5 else None

    def ret(self, v):
        self.uc.reg_write(UC_X86_REG_RAX, v & 0xffffffffffffffff)

    def _ovr(self, uc, addr, size, ud):
        if addr == 0x8da350:
            rcx, rdx = self.r(UC_X86_REG_RCX), self.r(UC_X86_REG_RDX)
            uc.mem_write(rcx, struct.pack('<Q', rdx))   # リテラルは refcnt=-1 の静的 UnicodeString なのでポインタ複写で等価
            self.ovr_hits.append(addr)
            rsp = self.r(UC_X86_REG_RSP)
            ret = struct.unpack('<Q', self.rd(rsp, 8))[0]
            uc.reg_write(UC_X86_REG_RSP, rsp + 8)
            uc.reg_write(UC_X86_REG_RIP, ret)

    # ---- API ----
    def hkey_path(self, h):
        h &= 0xffffffff
        if h == 0x80000001:
            return ('HKCU', '')
        if h == 0x80000002:
            return ('HKLM', '')
        return self.handles.get(h & 0xffffffffffff)

    def _code(self, uc, addr, size, ud):
        name = self.names.get(addr)
        if name is None:
            return
        rcx, rdx, r8, r9 = (self.r(x) for x in (UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9))
        short = name.split('!')[-1]
        fn = getattr(self, 'api_' + short, None)
        if self.trace and not name.startswith('mm!'):
            print('  api', name, hex(rcx), hex(rdx), hex(r8), hex(r9))
        self.api_log.append(name)
        if fn is None:
            self.unknown = getattr(self, 'unknown', set())
            self.unknown.add(name)
            self.ret(0)
            return
        self.ret(fn(rcx, rdx, r8, r9))

    # mm
    def api_GetMem(self, c, d, r8, r9):
        return self.alloc(c)

    def api_AllocMem(self, c, d, r8, r9):
        return self.alloc(c)

    def api_FreeMem(self, c, d, r8, r9):
        return 0

    def api_ReallocMem(self, c, d, r8, r9):
        if c == 0:
            return self.alloc(d)
        old = self.sizes.get(c, 0)
        p = self.alloc(d)
        n = min(old, d)
        if n:
            self.uc.mem_write(p, bytes(self.uc.mem_read(c, n)))
        return p

    def api_RegLeak(self, *a):
        return 0
    api_UnregLeak = api_RegLeak

    # registry (A/W)
    def _open(self, hk, sub, out, wide, create=False):
        base = self.hkey_path(hk)
        if base is None:
            return 6
        hive, p = base
        path = (p + '\\' + sub).strip('\\') if sub else p
        self.reg.log.append(('open', hive, path))
        if not self.reg.exists(hive, path):
            if not create:
                return 2
            self.reg.keys.setdefault((hive, self.reg.norm(path)), {})
        h = self.next_h
        self.next_h += 4
        self.handles[h] = (hive, path)
        self.uc.mem_write(out, struct.pack('<Q', h))
        return 0

    def api_RegOpenKeyExW(self, c, d, r8, r9):
        return self._open(c, self.rd_w(d), self.stack_arg(5), True)

    def api_RegOpenKeyExA(self, c, d, r8, r9):
        return self._open(c, self.rd_a(d), self.stack_arg(5), False)

    def api_RegCreateKeyExW(self, c, d, r8, r9):
        # (hKey, subKey, Reserved, lpClass, dwOptions, sam, sa, phkResult, disp)
        rsp = self.r(UC_X86_REG_RSP)
        out = struct.unpack('<Q', bytes(self.uc.mem_read(rsp + 8 + 8 * 7, 8)))[0]
        return self._open(c, self.rd_w(d), out, True, create=True)

    def api_RegCloseKey(self, c, d, r8, r9):
        return 0

    def _query(self, hk, name, ptype, pdata, pcb, wide):
        h = self.handles.get(hk & 0xffffffffffff)
        if h is None:
            return 6
        k = self.reg.keys.get((h[0], self.reg.norm(h[1])), {})
        self.reg.log.append(('read', h[0], h[1], name))
        v = k.get(name.lower())
        if v is None:
            return 2
        t, data = v
        if pcb:
            have = struct.unpack('<I', bytes(self.uc.mem_read(pcb, 4)))[0] if pdata else 0
            self.uc.mem_write(pcb, struct.pack('<I', len(data)))
            if pdata and have < len(data):
                return 234
        if ptype:
            self.uc.mem_write(ptype, struct.pack('<I', t))
        if pdata:
            self.uc.mem_write(pdata, data)
        return 0

    def api_RegQueryValueExW(self, c, d, r8, r9):
        return self._query(c, self.rd_w(d), r9, self.stack_arg(5), self.stack_arg(6), True)

    def api_RegQueryValueExA(self, c, d, r8, r9):
        name = self.rd_a(d)
        h = self.handles.get(c & 0xffffffffffff)
        if h is None:
            return 6
        k = self.reg.keys.get((h[0], self.reg.norm(h[1])), {})
        self.reg.log.append(('read', h[0], h[1], name))
        v = k.get(name.lower())
        if v is None:
            return 2
        t, data = v
        data = data.decode('utf-16le').rstrip('\0').encode('latin1') + b'\0' if t == 1 else data
        pdata, pcb = self.stack_arg(5), self.stack_arg(6)
        if pcb:
            have = struct.unpack('<I', bytes(self.uc.mem_read(pcb, 4)))[0] if pdata else 0
            self.uc.mem_write(pcb, struct.pack('<I', len(data)))
            if pdata and have < len(data):
                return 234
        if r9:
            self.uc.mem_write(r9, struct.pack('<I', t))
        if pdata:
            self.uc.mem_write(pdata, data)
        return 0

    def api_RegEnumKeyExW(self, c, d, r8, r9):
        h = self.handles.get(c & 0xffffffffffff)
        if h is None:
            return 6
        subs = self.reg.subkeys(h[0], h[1])
        if d >= len(subs):
            return 259
        s = subs[d]
        if r9:
            self.uc.mem_write(r9, struct.pack('<I', len(s)))
        self.uc.mem_write(r8, u16z(s))
        return 0

    def api_RegEnumValueW(self, c, d, r8, r9):
        return 259

    def api_RegQueryInfoKeyW(self, c, d, r8, r9):
        return 0

    def api_RegSetValueExW(self, c, d, r8, r9):
        return 0

    def api_GetComputerNameExW(self, c, d, r8, r9):
        s = u16z(self.comp)
        if d:
            self.uc.mem_write(d, s)
        if r8:
            self.uc.mem_write(r8, struct.pack('<I', len(self.comp)))
        return 1

    def api_LoadLibraryW(self, c, d, r8, r9):
        return 0x7d000000 + (hash(self.rd_w(c).lower()) & 0xfff) * 0x10000

    def api_GetProcAddress(self, c, d, r8, r9):
        nm = self.rd_a(d) if d > 0xffff else ''
        if not nm:
            nm = 'SHGetFolderPathW'   # FL は SHFolder.dll からのみ名前引きで取得 (§観測: ordinal ではなく名前指定)
        return self.stub_for('dyn!' + nm)

    def api_SHGetFolderPathW(self, c, d, r8, r9):
        buf = self.stack_arg(5)
        self.uc.mem_write(buf, u16z(self.appdata))
        return 0

    def api_FreeLibrary(self, *a):
        return 1

    def api_WideCharToMultiByte(self, c, d, r8, r9):
        cch = r9 & 0xffffffff
        if cch == 0xffffffff:
            w = self.rd_w(r8) + '\0'
        else:
            w = bytes(self.uc.mem_read(r8, cch * 2)).decode('utf-16le')
        out, cb = self.stack_arg(5), self.stack_arg(6) & 0xffffffff
        enc = w.encode('latin1', 'replace')
        if cb == 0:
            return len(enc)
        self.uc.mem_write(out, enc[:cb])
        return min(len(enc), cb)

    def api_GetACP(self, *a):
        return 1252
    api_GetOEMCP = api_GetACP

    def api_GetCPInfo(self, c, d, r8, r9):
        self.uc.mem_write(d, struct.pack('<I2s12s', 1, b'?\0', b'\0' * 12))
        return 1

    def api_IsDBCSLeadByteEx(self, *a):
        return 0
    api_IsDBCSLeadByte = api_IsDBCSLeadByteEx

    def api_MultiByteToWideChar(self, c, d, r8, r9):
        cb = r9 & 0xffffffff
        src = self.rd_a(r8) + '\0' if cb == 0xffffffff else bytes(self.uc.mem_read(r8, cb)).decode('latin1')
        out, cch = self.stack_arg(5), self.stack_arg(6) & 0xffffffff
        enc = src.encode('utf-16le')
        if cch == 0:
            return len(enc) // 2
        self.uc.mem_write(out, enc[:cch * 2])
        return min(len(enc) // 2, cch)

    def api_LoadStringW(self, c, d, r8, r9):
        return 0

    def api_LCMapStringW(self, c, d, r8, r9):
        # (Locale, MapFlags, src, cchSrc, dst, cchDst)
        cch = r9 & 0xffffffff
        src = bytes(self.uc.mem_read(r8, cch * 2))
        dst, cd = self.stack_arg(5), self.stack_arg(6) & 0xffffffff
        txt = src.decode('utf-16le')
        if d & 0x200:
            txt = txt.upper()
        elif d & 0x100:
            txt = txt.lower()
        enc = txt.encode('utf-16le')
        if cd == 0:
            return cch
        self.uc.mem_write(dst, enc[:cd * 2])
        return cch

    def api_CharUpperBuffW(self, c, d, r8, r9):
        t = bytes(self.uc.mem_read(c, d * 2)).decode('utf-16le').upper().encode('utf-16le')
        self.uc.mem_write(c, t[:d * 2])
        return d

    def api_CharLowerBuffW(self, c, d, r8, r9):
        t = bytes(self.uc.mem_read(c, d * 2)).decode('utf-16le').lower().encode('utf-16le')
        self.uc.mem_write(c, t[:d * 2])
        return d

    def api_GetLocalTime(self, c, d, r8, r9):
        self.uc.mem_write(c, struct.pack('<8H', 2026, 10, 2, 13, 3, 0, 0, 0))
        return 0
    api_GetSystemTime = api_GetLocalTime

    def api_GetSystemTimeAsFileTime(self, c, d, r8, r9):
        self.uc.mem_write(c, struct.pack('<Q', 134000000000000000 + 0))
        return 0

    def api_GetLastError(self, *a):
        return 0

    def api_SetLastError(self, *a):
        return 0

    def api_GetTickCount(self, *a):
        return 1000

    def api_QueryPerformanceCounter(self, c, *a):
        self.uc.mem_write(c, struct.pack('<Q', 123456789))
        return 1

    def api_GetCurrentThreadId(self, *a):
        return 4242

    def api_GetCurrentProcessId(self, *a):
        return 1234

    # ---- 実行 ----
    def run(self, entry=ENTRY, cl=0, max_insn=50_000_000):
        uc = self.uc
        sp = STACK_TOP - 0x10000
        sp &= ~0xf
        sp -= 8
        uc.mem_write(sp, struct.pack('<Q', self.sent))
        uc.reg_write(UC_X86_REG_RSP, sp)
        uc.reg_write(UC_X86_REG_RCX, cl)
        uc.reg_write(UC_X86_REG_RDX, 0)
        try:
            uc.emu_start(entry, self.sent, count=max_insn)
            return 'ok'
        except UcError as e:
            rsp = self.r(UC_X86_REG_RSP)
            cand = []
            for i in range(0, 0x400, 8):
                v = struct.unpack('<Q', self.rd(rsp + i, 8))[0]
                if 0x401000 <= v < 0x13a5000:
                    cand.append(hex(v))
            return f'UcError: {e} unmapped={self.unmapped} rip={self.r(UC_X86_REG_RIP):#x} stack_ret_cands={cand[:10]}'

    def rd(self, va, n):
        return bytes(self.uc.mem_read(va, n))

    def setup_teb(self):
        teb = self.alloc(0x1000)
        tls = self.alloc(64 * 8)
        blk = self.alloc(0x20000)
        for i in range(64):
            self.uc.mem_write(tls + 8 * i, struct.pack('<Q', blk))
        self.uc.mem_write(TLS_INDEX_VAR, struct.pack('<I', 0))   # Delphi RTL の threadvar 添字 (実機では起動時に採番)
        self.uc.mem_write(teb + 0x58, struct.pack('<Q', tls))
        self.uc.mem_write(teb + 0x30, struct.pack('<Q', teb))
        self.uc.msr_write(0xC0000101, teb)

    def setup_globals(self):
        self.setup_teb()
        slot = struct.unpack('<Q', self.rd(GRADE_SLOT_PTR, 8))[0]   # 変数 (オブジェクトを指す) へのポインタ
        obj = self.alloc(0x400)
        grade = self.alloc(16)
        self.uc.mem_write(obj + 0xd0, struct.pack('<Q', grade))
        self.uc.mem_write(slot, struct.pack('<Q', obj))
        self.grade_ptr = grade
        self.uc.mem_write(grade, b'\x40')


def standard_seed(reg, il=None, guid='12345678-aaaa-bbbb-cccc-1234567890ab'):
    if guid is not None:
        reg.put('HKLM', 'SOFTWARE\\Microsoft\\Cryptography', 'MachineGuid', guid)
    if il is not None:
        reg.put('HKCU', 'Software\\Image-Line\\Registrations\\FL Studio 26.1', 'ILRegKey', il)


if __name__ == '__main__':
    reg = Reg()
    standard_seed(reg)
    e = Emu(reg, trace=True)
    e.setup_globals()
    print(e.run())
    print('unknown apis', getattr(e, 'unknown', None))
    print('flag', e.rd(FLAG, 1).hex(), 'grade', e.rd(e.grade_ptr, 1).hex())
