#!/usr/bin/env python3
"""fw_table.py — icall dispatch 表 (VA → lifted 関数) の C 生成. tools/icall/ir_flatten.py --table の拡張版.

  python3 fw_table.py --ir fw_flat.ll --map fw_map.json --imports fw_imports.json --out fw_table.c --blk 0x8A1000

* 0-arg i64 define      → 直接表登録 (ret は lifted 側の ABI ret store が BLK+0x80 に書く)
* param 付き define     → wrapper: BLK (rcx/rdx/r8/r9[/xmm]) から引数を復元して呼び, 戻り値を BLK+0x80/+0x88 に
                          store (RetDec が entry の ABI reload を parameter promote した関数; dispatch 呼び元は
                          BLK reload が正本なので wrapper が返り値を BLK に書く必要がある)
* 非 i64 戻り値         → i128/double/float は BLK+0x88 (xmm0), それ以外は (long long) 変換で BLK+0x80
* IR に call があるが define 無し (decode 漏れ) → weak fail-fast stub を C 側に生成
* import (IAT 合成 VA)  → imp_<name>: BLK-ABI から引数復元 → fw_rt.c の平 C 関数 → 戻り値を BLK+0x80/+0x88
表は VA 昇順 (lookup は二分探索; function VA < import VA を前提 = image top < 0xE000000)。
"""
import argparse, json, re


def cident(s):
    return re.sub(r'[^A-Za-z0-9_]', '_', s)


CT = {'i64': 'long long', 'i32': 'int', 'i16': 'short', 'i8': 'signed char',
      'i1': 'int', 'i128': 'unsigned __int128', 'float': 'float', 'double': 'double',
      'void': 'void', 'ptr': 'void*'}
# RetDec の戻り値/引数型 → C (wasm32 ABI 整合): ポインタ系は全て void* (wasm i32), i64 は long long (wasm i64)


def ctype(t):
    if t in CT:
        return CT[t]
    if re.match(r'^i\d+\*$', t) or t.startswith('%') or t == 'ptr':
        return 'void*'
    return 'long long'

# BLK-ABI から引数を復元する C 式 (rcx/rdx/r8/r9 → +8/+0x10/+0x18/+0x20, xmm → +0x28..)
ARG_SLOTS = ('8', '0x10', '0x18', '0x20')

# fw_rt.c 側で void を返す import (imp wrapper は 呼んで 0 を返す)
VOID_IMPLS = {
    'SetLastError', 'Sleep', 'GetSystemTimeAsFileTime', 'InitializeCriticalSection',
    'DeleteCriticalSection', 'EnterCriticalSection', 'LeaveCriticalSection',
    'InitializeSRWLock', 'AcquireSRWLockExclusive', 'AcquireSRWLockShared',
    'ReleaseSRWLockExclusive', 'ReleaseSRWLockShared', 'GetSystemInfo',
    'GetStartupInfoW', 'GetStartupInfoA', 'SysFreeString', 'CoUninitialize',
    'OleUninitialize',
}

# fw_rt.c に実装がある import → BLK からの引数復元式 (無いものは fail-fast)
IMPL = {
    'VirtualAlloc':      '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned)BLKQ(0x18), (unsigned)BLKQ(0x20)',
    'VirtualFree':       '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned)BLKQ(0x18)',
    'VirtualProtect':    '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned)BLKQ(0x18), (unsigned*)(uintptr_t)BLKQ(0x20)',
    'VirtualQuery':      '(void*)(uintptr_t)BLKQ(8), (void*)(uintptr_t)BLKQ(0x10), (unsigned)BLKQ(0x18)',
    'GetProcessHeap':    '',
    'HeapAlloc':         '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned long long)BLKQ(0x18)',
    'HeapFree':          '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (void*)(uintptr_t)BLKQ(0x18)',
    'HeapSize':          '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (void*)(uintptr_t)BLKQ(0x18)',
    'HeapReAlloc':       '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (void*)(uintptr_t)BLKQ(0x18), (unsigned long long)BLKQ(0x20)',
    'GetLastError':      '',
    'SetLastError':      '(unsigned)BLKQ(8)',
    'GetCurrentThreadId': '',
    'GetCurrentProcessId': '',
    'GetCurrentProcess': '',
    'Sleep':             '(unsigned)BLKQ(8)',
    'SwitchToThread':    '',
    'GetTickCount':      '',
    'GetTickCount64':    '',
    'GetSystemTimeAsFileTime': '(void*)(uintptr_t)BLKQ(8)',
    'QueryPerformanceCounter': '(void*)(uintptr_t)BLKQ(8)',
    'QueryPerformanceFrequency': '(void*)(uintptr_t)BLKQ(8)',
    'InitializeCriticalSectionAndSpinCount': '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10)',
    'InitializeCriticalSection': '(void*)(uintptr_t)BLKQ(8)',
    'DeleteCriticalSection': '(void*)(uintptr_t)BLKQ(8)',
    'EnterCriticalSection': '(void*)(uintptr_t)BLKQ(8)',
    'LeaveCriticalSection': '(void*)(uintptr_t)BLKQ(8)',
    'TryEnterCriticalSection': '(void*)(uintptr_t)BLKQ(8)',
    'InitializeSRWLock': '(void*)(uintptr_t)BLKQ(8)',
    'AcquireSRWLockExclusive': '(void*)(uintptr_t)BLKQ(8)',
    'AcquireSRWLockShared': '(void*)(uintptr_t)BLKQ(8)',
    'ReleaseSRWLockExclusive': '(void*)(uintptr_t)BLKQ(8)',
    'ReleaseSRWLockShared': '(void*)(uintptr_t)BLKQ(8)',
    'GetACP':            '',
    'GetOEMCP':          '',
    'GetConsoleCP':      '',
    'GetConsoleOutputCP': '',
    'GetThreadLocale':   '',
    'SetThreadLocale':   '(unsigned)BLKQ(8)',
    'GetSystemDefaultUILanguage': '',
    'GetUserDefaultUILanguage': '',
    'GetUserDefaultLangID': '',
    'GetSystemDefaultLangID': '',
    'IsValidLocale':     '(unsigned)BLKQ(8), (unsigned)BLKQ(0x10)',
    'IsValidLanguageName': '(const unsigned short*)(uintptr_t)BLKQ(8)',
    'GetCPInfo':         '(unsigned)BLKQ(8), (void*)(uintptr_t)BLKQ(0x10)',
    'GetLocaleInfoW':    '(unsigned)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned short*)(uintptr_t)BLKQ(0x18), (int)BLKQ(0x20)',
    'SetThreadUILanguage': '(unsigned)BLKQ(8)',
    'LCIDToLocaleName':  '(unsigned)BLKQ(8), (unsigned short*)(uintptr_t)BLKQ(0x10), (int)BLKQ(0x18), (unsigned)BLKQ(0x20)',
    'GetFullPathNameW':  '(const unsigned short*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned short*)(uintptr_t)BLKQ(0x18), (unsigned short**)(uintptr_t)BLKQ(0x20)',
    'GetTempPathW':      '(unsigned)BLKQ(8), (unsigned short*)(uintptr_t)BLKQ(0x10)',
    'GetModuleHandleW':  '(const unsigned short*)(uintptr_t)BLKQ(8)',
    'GetModuleHandleA':  '(const char*)(uintptr_t)BLKQ(8)',
    'GetModuleFileNameW': '(void*)(uintptr_t)BLKQ(8), (unsigned short*)(uintptr_t)BLKQ(0x10), (unsigned)BLKQ(0x18)',
    'GetModuleFileNameA': '(void*)(uintptr_t)BLKQ(8), (char*)(uintptr_t)BLKQ(0x10), (unsigned)BLKQ(0x18)',
    'GetVersion':        '',
    'GetVersionExW':     '(void*)(uintptr_t)BLKQ(8)',
    'VerSetConditionMask': '(unsigned long long)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned char)BLKQ(0x18)',
    'VerifyVersionInfoW': '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned long long)BLKQ(0x18)',
    'GetSystemInfo':     '(void*)(uintptr_t)BLKQ(8)',
    'GetStartupInfoW':   '(void*)(uintptr_t)BLKQ(8)',
    'GetStartupInfoA':   '(void*)(uintptr_t)BLKQ(8)',
    'GetCommandLineW':   '',
    'GetCommandLineA':   '',
    'SetErrorMode':      '(unsigned)BLKQ(8)',
    'IsDebuggerPresent': '',
    'IsProcessorFeaturePresent': '(unsigned)BLKQ(8)',
    'CreateThread':      '(void*)(uintptr_t)BLKQ(8), (unsigned long long)BLKQ(0x10), (void*)(uintptr_t)BLKQ(0x18), (void*)(uintptr_t)BLKQ(0x20), (unsigned)BLKQ(0x28), (unsigned*)(uintptr_t)BLKQ(0x30)',
    'SetTimer':          '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (unsigned)BLKQ(0x18), (void*)(uintptr_t)BLKQ(0x20)',
    'KillTimer':         '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10)',
    'CreateEventW':      '(void*)(uintptr_t)BLKQ(8), (int)BLKQ(0x10), (int)BLKQ(0x18), (const unsigned short*)(uintptr_t)BLKQ(0x20)',
    'SetEvent':          '(void*)(uintptr_t)BLKQ(8)',
    'ResetEvent':        '(void*)(uintptr_t)BLKQ(8)',
    'CloseHandle':       '(void*)(uintptr_t)BLKQ(8)',
    'FormatMessageW':    '(unsigned)BLKQ(8), (const void*)(uintptr_t)BLKQ(0x10), (unsigned)BLKQ(0x18), (unsigned)BLKQ(0x20), (unsigned short*)(uintptr_t)BLKQ(0x28), (unsigned)BLKQ(0x30), (void*)(uintptr_t)BLKQ(0x38)',
    'WideCharToMultiByte': '(unsigned)BLKQ(8), (unsigned)BLKQ(0x10), (const unsigned short*)(uintptr_t)BLKQ(0x18), (int)BLKQ(0x20), (char*)(uintptr_t)BLKQ(0x28), (int)BLKQ(0x30), (const char*)(uintptr_t)BLKQ(0x38), (int*)(uintptr_t)BLKQ(0x40)',
    'MultiByteToWideChar': '(unsigned)BLKQ(8), (unsigned)BLKQ(0x10), (const char*)(uintptr_t)BLKQ(0x18), (int)BLKQ(0x20), (unsigned short*)(uintptr_t)BLKQ(0x28), (int)BLKQ(0x30)',
    'CompareStringW':    '(unsigned)BLKQ(8), (unsigned)BLKQ(0x10), (const unsigned short*)(uintptr_t)BLKQ(0x18), (int)BLKQ(0x20), (const unsigned short*)(uintptr_t)BLKQ(0x28), (int)BLKQ(0x30)',
    'LCMapStringW':      '(unsigned)BLKQ(8), (unsigned)BLKQ(0x10), (const unsigned short*)(uintptr_t)BLKQ(0x18), (int)BLKQ(0x20), (unsigned short*)(uintptr_t)BLKQ(0x28), (int)BLKQ(0x30)',
    'GetStringTypeW':    '(unsigned)BLKQ(8), (const unsigned short*)(uintptr_t)BLKQ(0x10), (int)BLKQ(0x18), (unsigned short*)(uintptr_t)BLKQ(0x20)',
    'RegOpenKeyExW':     '(void*)(uintptr_t)BLKQ(8), (const unsigned short*)(uintptr_t)BLKQ(0x10), (unsigned)BLKQ(0x18), (unsigned)BLKQ(0x20), (void**)(uintptr_t)BLKQ(0x28)',
    'RegQueryValueExW':  '(void*)(uintptr_t)BLKQ(8), (const unsigned short*)(uintptr_t)BLKQ(0x10), (void*)(uintptr_t)BLKQ(0x18), (void*)(uintptr_t)BLKQ(0x20), (void*)(uintptr_t)BLKQ(0x28), (void*)(uintptr_t)BLKQ(0x30)',
    'RegCloseKey':       '(void*)(uintptr_t)BLKQ(8)',
    'RegEnumKeyExW':     '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (void*)(uintptr_t)BLKQ(0x18), (void*)(uintptr_t)BLKQ(0x20), (void*)(uintptr_t)BLKQ(0x28), (void*)(uintptr_t)BLKQ(0x30), (void*)(uintptr_t)BLKQ(0x38), (void*)(uintptr_t)BLKQ(0x40)',
    'RegEnumValueW':     '(void*)(uintptr_t)BLKQ(8), (unsigned)BLKQ(0x10), (void*)(uintptr_t)BLKQ(0x18), (void*)(uintptr_t)BLKQ(0x20), (void*)(uintptr_t)BLKQ(0x28), (void*)(uintptr_t)BLKQ(0x30), (void*)(uintptr_t)BLKQ(0x38), (void*)(uintptr_t)BLKQ(0x40)',
    'RegQueryInfoKeyW':  '(void*)(uintptr_t)BLKQ(8), (void*)(uintptr_t)BLKQ(0x10), (void*)(uintptr_t)BLKQ(0x18), (void*)(uintptr_t)BLKQ(0x20), (void*)(uintptr_t)BLKQ(0x28), (void*)(uintptr_t)BLKQ(0x30), (void*)(uintptr_t)BLKQ(0x38), (void*)(uintptr_t)BLKQ(0x40), (void*)(uintptr_t)BLKQ(0x48), (void*)(uintptr_t)BLKQ(0x50), (void*)(uintptr_t)BLKQ(0x58), (void*)(uintptr_t)BLKQ(0x60)',
    'SysFreeString':     '(void*)(uintptr_t)BLKQ(8)',
    'CoInitialize':      '(void*)(uintptr_t)BLKQ(8)',
    'CoUninitialize':    '',
    'OleInitialize':     '(void*)(uintptr_t)BLKQ(8)',
    'OleUninitialize':   '',
}


def ptypes(pstr):
    pstr = (pstr or '').strip()
    if not pstr or pstr == 'void':
        return []
    out = []
    for p in [p.strip() for p in pstr.split(',') if p.strip()]:
        mm = re.match(r'^(i\d+\*|%[\w.$]+\*|i\d+|float|double|ptr|void)\b', p)
        out.append(mm.group(1) if mm else 'i64')
    return ['i64' if t == 'void' else t for t in out]   # void 引数 (RetDec の placeholder) は i64 扱い


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--imports', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--blk', type=lambda x: int(x, 0), default=0x8A1000)
    a = ap.parse_args()
    im = json.load(open(a.imports))
    defines = {}
    cur = None
    with open(a.ir, errors='replace') as f:
        for line in f:
            if line.startswith('define '):
                m = re.match(r'define (.+?) @function_([0-9a-f]+)\(([^)]*)\)', line)
                cur = int(m.group(2), 16) if m else None
                if cur is not None and cur not in defines:
                    defines[cur] = (m.group(1), m.group(3).strip())
                continue
            if cur is not None and line.startswith('}'):
                cur = None
    calls = set()
    call_arity = {}
    with open(a.ir, errors='replace') as f:
        for line in f:
            for m in re.finditer(r'call [^@]*@function_([0-9a-f]+)\(', line):
                va = int(m.group(1), 16)
                calls.add(va)
                # 引数個数 (括弧 depth 考慮) を記録 (decode 漏れ stub の署名用)
                j = line.index('@function_' + m.group(1) + '(')
                start = j + len('@function_' + m.group(1))
                depth, k = 0, start
                for k in range(start, len(line)):
                    if line[k] == '(':
                        depth += 1
                    elif line[k] == ')':
                        depth -= 1
                        if depth == 0:
                            break
                n = len([p for p in line[start + 1:k].split(',') if p.strip()])
                call_arity[va] = max(call_arity.get(va, 0), n)
    missing = sorted(v for v in calls if v not in defines and 0x401000 <= v < 0xd02000)
    missing_set = set(missing)

    lines = ['/* generated by fw_table.py: VA -> lifted function dispatch table (sorted by VA) */',
             '#include <stdint.h>', '#include <stddef.h>', '#include <string.h>',
             '#ifndef FW_BLK', '#define FW_BLK 0x%xu' % a.blk, '#endif',
             '#define BLKQ(off) (*(volatile uint64_t*)(uintptr_t)(FW_BLK + (off)))',
             '#include "fw_rt.h"', '']
    OVERRIDES = {0x4189c0: 'fw_ov_startlib', 0x40db20: 'fw_ov_initlib', 0x40e130: 'fw_ov_restorectx', 0x40e0b0: 'fw_ov_restorectx_run', 0x40e130: 'fw_ov_restorectx'}
    wrappers, entries, fns = [], [], []

    def is_floaty(t):
        return t in ('i128', 'float', 'double')

    def arg_expr(ty, k, nfloaty):
        if ty in ('i128', 'float', 'double'):
            return '((%s)BLKQ(0x28 + 8 * %d))' % (ctype(ty), nfloaty)
        if k < 4:
            v = 'BLKQ(%s)' % ARG_SLOTS[k]
        else:
            v = '0'      # 5 引数目以降は BLK 未対応 (fail-fast ではなく 0; smoke で顕在化時に拡張)
        if ty == 'i64':
            return v
        if ty == 'ptr' or re.match(r'^(i\d+|%[\w.$]+)\*$', ty):
            return '(void*)(uintptr_t)%s' % v
        return '(%s)(uint32_t)%s' % (ctype(ty), v)

    for va in sorted(defines):
        if va in OVERRIDES:
            lines.append('extern long long %s(void);' % OVERRIDES[va])
            fns.append(OVERRIDES[va])
            entries.append(va)
            continue
        ret, pstr = defines[va]
        rt = ctype(ret)
        tys = ptypes(pstr)
        nf = 0
        args = []
        for k, t in enumerate(tys):
            args.append(arg_expr(t, k, nf))
            if is_floaty(t):
                nf += 1
        astr = ', '.join(args)
        if not tys and ret == 'i64':
            fns.append('function_%x' % va)
            entries.append(va)
            continue
        if ret in ('i128', 'double', 'float'):
            ct = ctype(ret)
            wrappers.append('static long long w_%x(void){ %s v = function_%x(%s); '
                            'uint64_t lo; memcpy(&lo, &v, 8); '
                            '*(volatile uint64_t*)(uintptr_t)(FW_BLK + 0x88) = lo; '
                            '*(volatile uint64_t*)(uintptr_t)(FW_BLK + 0x80) = lo; return 0; }'
                            % (va, ct, va, astr))
        elif rt == 'void':
            wrappers.append('static long long w_%x(void){ function_%x(%s); BLKQ(0x80) = 0; return 0; }' % (va, va, astr))
        elif rt == 'void*':
            wrappers.append('static long long w_%x(void){ void* v = function_%x(%s); '
                            'BLKQ(0x80) = (uint64_t)(uintptr_t)v; return 0; }' % (va, va, astr))
        else:
            wrappers.append('static long long w_%x(void){ long long v = (long long)function_%x(%s); '
                            'BLKQ(0x80) = (uint64_t)v; return 0; }' % (va, va, astr))
        fns.append('w_%x' % va)
        entries.append(va)
    # decode 漏れ stub: IR の declare (cleanup が署名衝突を 1 本に絞済み) に合わせて C 側署名を作る
    decl_sig = {}
    with open(a.ir, errors='replace') as f:
        for line in f:
            if line.startswith('declare '):
                m = re.match(r'declare (\S+) @function_([0-9a-f]+)\(([^)]*)\)', line)
                if m and int(m.group(2), 16) in missing_set:
                    decl_sig[int(m.group(2), 16)] = (m.group(1), m.group(3))
    for va in missing:
        ret, pstr = decl_sig.get(va, ('i64', ''))
        rt = ctype(ret)
        tys = ptypes(pstr)
        ps = ', '.join(ctype(t) for t in tys)
        lines.append('long long function_%x(%s){ fw_ff("function_%x (decode 漏れ)"); '
                     'BLKQ(0x80) = 0; return 0; }' % (va, ps, va))
        if tys:
            # 表は long long(void) 一様なので 0-arg wrapper を挟む
            lines.append('static long long w_%x(void){ fw_ff("function_%x (decode 漏れ)"); BLKQ(0x80) = 0; return 0; }' % (va, va))
            fns.append('w_%x' % va)
        else:
            fns.append('function_%x' % va)
        entries.append(va)
    for imp in im['imports']:
        nm = cident(imp['name'])
        if imp['name'] in IMPL:
            if imp['name'] in VOID_IMPLS:
                lines.append('static long long imp_%s(void){ %s(%s); BLKQ(0x80) = 0; return 0; }'
                             % (nm, imp['name'], IMPL[imp['name']]))
            else:
                lines.append('static long long imp_%s(void){ long long v = (long long)(uintptr_t)%s(%s); '
                             'BLKQ(0x80) = (uint64_t)v; return 0; }'
                             % (nm, imp['name'], IMPL[imp['name']]))
        else:
            lines.append('static long long imp_%s(void){ fw_ff("import %s (未実装)"); BLKQ(0x80) = 0; return 0; }'
                         % (nm, imp['name'].replace('"', '')))
        fns.append('imp_%s' % nm)
        entries.append(imp['syn_va'])
    # ---- RetDec が IAT thunk を名前解決した「直接 named import」の C 定義
    #      (fw_rt.c 実装済み = fw_rt.h 宣言名は除外, 未実装は fail-fast)
    have_rt = set()
    for srcf in (__file__.replace('fw_table.py', 'fw_rt.h'), __file__.replace('fw_table.py', 'fw_rt.c')):
        with open(srcf) as f:
            for l in f:
                for mm in re.finditer(r'\b([A-Za-z_]\w*)\s*\(', l):
                    have_rt.add(mm.group(1))
    named = {}
    with open(a.ir, errors='replace') as f:
        for line in f:
            if not line.startswith('declare '):
                continue
            m = re.match(r'declare (\S+) @([A-Za-z_][\w]*)\(([^)]*)\)', line)
            if not m:
                continue
            nm6 = m.group(2)
            if nm6.startswith(('function_', '__asm_', 'llvm.', 'fw_', '__icall', '__frontend', '__readgsqword', 'imp_')):
                continue
            if nm6 in have_rt or nm6 in IMPL:
                continue
            if nm6 in ('memset', 'memcpy', 'memmove', 'memcmp', 'strlen', 'strcmp', 'memset_s'):
                continue   # C 標準 = emcc が提供 (emcc 側関数として解決される)
            named.setdefault(nm6, (m.group(1), m.group(3)))
    gen = 0
    for nm6, (ret, pstr) in sorted(named.items()):
        if cident(nm6) != nm6:
            continue
        tys = ptypes(pstr)
        ps = ', '.join(ctype(t) for t in tys)
        rt6 = ctype(ret)
        if rt6 == 'void':
            lines.append('void %s(%s){ fw_ff("import %s (headless 未対応)"); }' % (nm6, ps, nm6))
        else:
            lines.append('%s %s(%s){ fw_ff("import %s (headless 未対応)"); return 0; }' % (rt6, nm6, ps, nm6))
        gen += 1

    # defines の extern 宣言 (wrapper より前に置く)
    for va in sorted(defines):
        ret, pstr = defines[va]
        rt = ctype(ret)
        tys = ptypes(pstr)
        ps = ', '.join(ctype(t) for t in tys)
        lines.append('extern %s function_%x(%s);' % (rt, va, ps))

    lines += wrappers
    lines.append('const uint32_t icall_tbl_va[] = {' + ','.join('0x%xu' % e for e in entries) + '};')
    lines.append('long long (*const icall_tbl_fn[])(void) = {' + ','.join(fns) + '};')
    lines.append('const unsigned icall_tbl_n = %d;' % len(entries))
    lines.append('const uint32_t icall_cfg_va[] = {0};')
    lines.append('const unsigned icall_cfg_n = 0;')
    open(a.out, 'w').write('\n'.join(lines) + '\n')
    print('[table] entries %d (direct %d / wrapper %d / missing-stub %d / import %d)'
          % (len(entries),
             sum(1 for v in defines if not ptypes(defines[v][1]) and defines[v][0] == 'i64'),
             len(wrappers), len(missing), len(im['imports'])))


if __name__ == '__main__':
    main()
