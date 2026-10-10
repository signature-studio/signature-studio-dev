#!/usr/bin/env python3
"""feparse.py — FLEngine_x64.dll (block00031) PE parser + capstone helpers for CAB-213.

静的解析の共通ライブラリ:
  - PE セクション / ImageBase / RVA<->offset 変換
  - 指定 VA の関数逆アセンブル (capstone) + rip 相対の文字列/IAT 解決
  - 全 .text の E8 (call rel32) 走査で callers/callees を作る
  - UTF-16LE / ASCII 文字列テーブル (.rdata/.data) の構築

入力は読取専用: analysis/win64/extracted/block00031_PE.bin (FLEngine_x64.dll 22,227,016 B)
"""
import struct, os, json, bisect

PE_PATH = '/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin'

_IMAGE_BASE = None
_SECTIONS = None
_RAW = None
_STRINGS = None  # list of (va, kind, text) sorted by va


def load():
    global _RAW, _SECTIONS, _IMAGE_BASE
    if _RAW is not None:
        return
    _RAW = open(PE_PATH, 'rb').read()
    import pefile
    pe = pefile.PE(data=_RAW, fast_load=True)
    _IMAGE_BASE = pe.OPTIONAL_HEADER.ImageBase
    _SECTIONS = []
    for s in pe.sections:
        _SECTIONS.append({'name': s.Name.decode().rstrip('\0'), 'va': s.VirtualAddress,
                          'vsize': s.Misc_VirtualSize, 'roff': s.PointerToRawData,
                          'rsize': s.SizeOfRawData})
    # entry / imports
    _ENTRY_RVA = pe.OPTIONAL_HEADER.AddressOfEntryPoint
    globals()['_ENTRY_RVA'] = _ENTRY_RVA


def image_base():
    load()
    return _IMAGE_BASE


def sections():
    load()
    return _SECTIONS


def rva2off(rva):
    load()
    for s in _SECTIONS:
        if s['va'] <= rva < s['va'] + max(s['vsize'], s['rsize']):
            d = rva - s['va']
            if d < s['rsize']:
                return s['roff'] + d
            return None
    return None


def va2off(va):
    return rva2off(va - _IMAGE_BASE)


def read_va_bytes(va, n):
    off = va2off(va)
    if off is None:
        return None
    return _RAW[off:off + n]


def read_cstr(va, maxlen=512):
    """ASCII (Delphi utf-8) null-terminated"""
    off = va2off(va)
    if off is None:
        return None
    end = _RAW.find(b'\0', off, off + maxlen)
    if end < 0:
        return None
    b = _RAW[off:end]
    try:
        t = b.decode('utf-8')
    except UnicodeDecodeError:
        return None
    return t if t and all(31 < ord(c) < 0xFFFD or c in '\t' for c in t) else None


def read_utf16(va, maxlen=1024):
    off = va2off(va)
    if off is None:
        return None
    end = off
    while end + 2 <= off + maxlen:
        if _RAW[end:end + 2] == b'\0\0':
            break
        end += 2
    else:
        return None
    if end >= off + maxlen:
        return None
    try:
        t = _RAW[off:end].decode('utf-16-le')
    except UnicodeDecodeError:
        return None
    return t if t and all(31 < ord(c) < 0xFFFD or c == '\t' for c in t) else None


def entry_rva():
    load()
    return _ENTRY_RVA


_IAT_CACHE = {}


def iat_names():
    """import table -> {iat_va: 'dll!name'}"""
    load()
    if _IAT_CACHE:
        return _IAT_CACHE
    import pefile
    pe = pefile.PE(data=_RAW, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
                                           pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
    out = {}
    for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        dll = entry.dll.decode()
        for imp in entry.imports:
            if imp.address and imp.name:
                out[imp.address] = '%s!%s' % (dll, imp.name.decode())
    for entry in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
        dll = entry.dll.decode()
        for imp in entry.imports:
            if imp.address and imp.name:
                out[imp.address] = '%s!%s' % (dll, imp.name.decode())
    _IAT_CACHE.update(out)
    return out


def text_range():
    load()
    for s in _SECTIONS:
        if s['name'] == '.text':
            return _IMAGE_BASE + s['va'], s['vsize']
    return None


# ---------------- strings table ----------------

def _printable(t):
    return bool(t) and all((31 < ord(c) < 0xFFFD) or c == '\t' for c in t)


def build_strings(force=False):
    """(va, kind, text) — .rdata/.data の ASCII/UTF-16LE 文字列 (>=3 文字, 印字可能)"""
    global _STRINGS
    if _STRINGS is not None and not force:
        return _STRINGS
    load()
    out = []
    for s in _SECTIONS:
        if s['name'] not in ('.rdata', '.data', '.text'):
            continue
        data = _RAW[s['roff']:s['roff'] + s['rsize']]
        n = len(data)
        i = 0
        # ASCII runs
        while i < n:
            j = i
            while j < n and 32 <= data[j] < 127:
                j += 1
            if j < n and data[j] == 0 and j - i >= 3:
                t = data[i:j].decode('ascii')
                if _printable(t):
                    out.append((_IMAGE_BASE + s['va'] + i, 'a', t))
            i = j + 1
        # UTF-16LE runs
        i = 0
        while i + 1 < n:
            j = i
            while j + 1 < n and 32 <= data[j] < 127 and data[j + 1] == 0:
                j += 2
            if j + 1 < n and data[j] == 0 and data[j + 1] == 0 and (j - i) // 2 >= 3:
                try:
                    t = data[i:j].decode('utf-16-le')
                except UnicodeDecodeError:
                    t = ''
                if _printable(t):
                    out.append((_IMAGE_BASE + s['va'] + i, 'w', t))
                i = j + 2
            else:
                i += 2
    out.sort(key=lambda t: t[0])
    _STRINGS = out
    return _STRINGS


class StrTab:
    """VA -> text の二分探索 (長い一致も返す)"""

    def __init__(self):
        self.tab = build_strings()
        self.vas = [t[0] for t in self.tab]

    def at(self, va):
        i = bisect.bisect_right(self.vas, va) - 1
        if i < 0:
            return None
        sva, kind, text = self.tab[i]
        # 文字列が切れていないか (完全一致または va が te 内)
        return (kind, text, va - sva, sva)

    def exact(self, va):
        i = bisect.bisect_left(self.vas, va)
        if i < len(self.tab) and self.tab[i][0] == va:
            return self.tab[i][2]
        return None


# ---------------- capstone ----------------

_md = None


def md():
    global _md
    if _md is None:
        import capstone
        _md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        _md.detail = True
        _md.skipdata = True
    return _md


def disasm_func(va, max_bytes=0x8000, stop_on_ret_padding=True):
    """VA から命令列を生成 (連続解码; ret+int3/pad で止めない — 呼び出し側で範囲管理)"""
    load()
    off = va2off(va)
    if off is None:
        return []
    data = _RAW[off:off + max_bytes]
    return list(md().disasm(data, va))


def find_func_end(va, max_bytes=0x20000):
    """ret (c3) + 次が int3 pad (cc) or 新関数アライン境界で終了とみなす簡易推定"""
    ins = disasm_func(va, max_bytes)
    end = va
    for k, i in enumerate(ins):
        end = i.address + i.size
        if i.mnemonic == 'ret' and i.bytes[0] == 0xc3:
            # look ahead: pad or new prologue
            nxt = ins[k + 1] if k + 1 < len(ins) else None
            if nxt is None or (nxt.bytes[0] in (0xcc, 0x90)) or (nxt.mnemonic in ('push', 'mov', 'sub', 'int3') ):
                if nxt is None or nxt.bytes[0] in (0xcc, 0x90):
                    break
    return end


# ---------------- call xrefs ----------------

_callers_cache = {}


def build_call_graph(force=False):
    """全 .text の E8 rel32: {callee_va: [(site_va, caller_guess)]} — caller は site から上流の関数境界推定不要のため site のみ返す"""
    global _callers_cache
    if _callers_cache and not force:
        return _callers_cache
    load()
    tva, tsize = text_range()
    off = va2off(tva)
    data = _RAW[off:off + tsize]
    graph = {}
    n = len(data)
    i = 0
    # E8 xx xx xx xx を素朴に走査 (誤検出は文字列中の 0xE8 だが、rel が .text 内に飛ぶ条件で大部分除去)
    tlo, thi = tva, tva + tsize
    while True:
        i = data.find(b'\xe8', i)
        if i < 0:
            break
        if i + 5 <= n:
            rel = struct.unpack_from('<i', data, i + 1)[0]
            site = tva + i
            target = site + 5 + rel
            if tlo <= target < thi:
                graph.setdefault(target, []).append(site)
        i += 1
    _callers_cache = graph
    return graph


def callers_of(va):
    g = build_call_graph()
    return sorted(g.get(va, []))


if __name__ == '__main__':
    import sys
    load()
    print('image base: 0x%x' % image_base())
    for s in sections():
        print('%-8s va=0x%-8x vsize=0x%-8x roff=0x%x' % (s['name'], s['va'], s['vsize'], s['roff']))
    print('entry rva: 0x%x' % entry_rva())
