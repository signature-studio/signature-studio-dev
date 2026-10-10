#!/usr/bin/env python3
"""Ghidra-free xrefs: callers of selected imports (via IAT call/jmp [rip+x]) and users of selected strings (rip-relative lea/mov).
usage: xref_scan.py <pe>"""
import sys, struct, bisect, re, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
pe = pefile.PE(sys.argv[1]); IMG = pe.OPTIONAL_HEADER.ImageBase
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
T = S['.text']; TB = T.get_data(); TVA = T.VirtualAddress
pd = S['.pdata'].get_data(); funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, u = struct.unpack_from('<III', pd, i)
    if b and TVA <= b < TVA + len(TB): funcs.append((b, e))
funcs.sort(); starts = [b for b, e in funcs]
fidx = lambda r: (bisect.bisect_right(starts, r) - 1)
WANT = {'CryptAcquireContextA','CryptCreateHash','CryptHashData','CryptGetHashParam','RegOpenKeyExA','RegQueryValueExW','InternetOpenA','InternetOpenUrlA','InternetReadFile',
        'HttpQueryInfoW','WSAStartup','socket','bind','listen','accept','send','recv','WSAPoll','IsDebuggerPresent','OutputDebugStringA','OutputDebugStringW','CoCreateGuid',
        'ShellExecuteW','ShellExecuteExA','LoadLibraryA','LoadLibraryW','LoadLibraryExW','GetProcAddress','GetVersionExW','VirtualProtect','DeviceIoControl','GetTickCount64','FindResourceA'}
iat = {}
for imp in pe.DIRECTORY_ENTRY_IMPORT:
    for i in imp.imports:
        if i.name and i.name.decode() in WANT: iat[i.address - IMG] = i.name.decode()
# strings of interest
d = pe.get_memory_mapped_image()
STR = [b'demoVersion', b'Locate License', b'Download Update', b'Update Available from Your Account on xferrecords.com: ', b'Software\\XferRecords\\Serum2InstallerPrefs',
       b'OfflineRender', b'https://xferrecords.com/', b'https://xferrecords.com', b'\\Xfer\\Serum\\SerumPrefs.json', b'Serum2Prefs.json', b'\\Xfer\\Serumpresetdb.dat', b'MTS_RegisterClient',
       b'com.xferrecords.serum2.factory-content', b'Expire', b'productVersion', b'Last Update Version']
saddr = {}
for s in STR:
    for m in re.finditer(re.escape(s) + b'\x00', d):
        saddr.setdefault(m.start(), s.decode(errors='replace'))
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
api_callers = collections.defaultdict(set); str_users = collections.defaultdict(set)
for fi, (b, e) in enumerate(funcs):
    for i in md.disasm(TB[b - TVA:e - TVA], b):
        for o in i.operands:
            if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                t = i.address + i.size + o.mem.disp
                if t in iat: api_callers[iat[t]].add(b)
                if t in saddr: str_users[saddr[t]].add(b)
print("== import callers (function entry RVAs + VA)")
for k in sorted(api_callers): print(f"{k:22} n={len(api_callers[k]):3} {[hex(IMG + x) for x in sorted(api_callers[k])[:12]]}")
print("== string users")
for k in sorted(str_users): print(f"{k[:60]:60} n={len(str_users[k]):3} {[hex(IMG + x) for x in sorted(str_users[k])[:8]]}")
print("== strings found at (rva)")
for a, s in sorted(saddr.items()): print(hex(a), s)
