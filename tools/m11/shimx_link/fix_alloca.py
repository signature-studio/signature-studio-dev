#!/usr/bin/env python3
"""alloca 拡幅 (計測用回避。本修正は CAB-129)。

RetDec は Delphi の集成体ローカル (OSVERSIONINFOEXW 284B, 0x188B の record 等) を `alloca i64` (8B) に縮退させる。
M11 の旧 stub (m11_win.c) は構造体を部分書込みしかしなかったので顕在化しなかったが、shimx は Win32 仕様どおり全体を書くため
shadow stack を破壊する (実測: unit 17 の function_454090 が GetVersionExW(284B) で InitUnits のローカルを壊し Halt0 に至る)。
本 pass は「alloca の実体積が使用箇所の要求より小さい」場合だけ alloca を [K x i64] に拡幅する。ポインタ値と他の IR は不変。

  規則 1: 出力パラメータ API 表 (API_OUT) に載る呼出しの引数が alloca (bitcast 経由可) なら、表のサイズ以上へ拡幅
  規則 2: __asm_rep_stos{b,w,d,q}_memset(alloca, v, n) / llvm.memset(alloca,_,n) の定数長 n*幅 以上へ拡幅

  fix_alloca.py <in.ll> <out.ll> [--report report.json]
"""
import json, re, sys

API_OUT = {   # name: {引数 index: 最小バイト}
    'GetVersionExW': {0: 284}, 'GetVersionExA': {0: 156}, 'GetStartupInfoW': {0: 104}, 'GetStartupInfoA': {0: 68},
    'GetSystemInfo': {0: 48}, 'GetNativeSystemInfo': {0: 48}, 'GetLocalTime': {0: 16}, 'GetSystemTime': {0: 16},
    'GetTimeZoneInformation': {0: 172}, 'GetCPInfo': {1: 20}, 'GetCPInfoExW': {2: 560},
    'FindFirstFileW': {1: 592}, 'FindNextFileW': {1: 592}, 'GetFileAttributesExW': {2: 36},
    'GlobalMemoryStatusEx': {0: 64}, 'GlobalMemoryStatus': {0: 32}, 'VirtualQuery': {1: 48},
    'GetLocaleInfoW': {}, 'GetSystemTimeAsFileTime': {0: 8}, 'QueryPerformanceCounter': {0: 8},
    'QueryPerformanceFrequency': {0: 8}, 'GetFileTime': {1: 8}, 'GetFileInformationByHandle': {1: 52},
    'GetDiskFreeSpaceExW': {1: 8}, 'GetOverlappedResult': {2: 4}, 'FormatMessageW': {},
}
STOS = {'__asm_rep_stosb_memset': 1, '__asm_rep_stosw_memset': 2, '__asm_rep_stosd_memset': 4, '__asm_rep_stosq_memset': 8}
SZ = {'i1': 1, 'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'float': 4, 'double': 8, 'ptr': 8}


def tsize(t):
    t = t.strip()
    if t in SZ:
        return SZ[t]
    m = re.match(r'^\[(\d+) x (\w+)\]$', t)
    if m and m.group(2) in SZ:
        return int(m.group(1)) * SZ[m.group(2)]
    return None


def main():
    src = open(sys.argv[1], errors='replace').read()
    out_path = sys.argv[2]
    rep_path = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
    funcs = list(re.finditer(r'^define [^\n]*@([\w.$-]+)\([^\n]*\{\n.*?^\}\n', src, re.S | re.M))
    report = []
    widened = []
    pieces, last = [], 0
    for fm in funcs:
        body = fm.group(0)
        name = fm.group(1)
        if 'alloca' not in body:
            continue
        allocas = {}
        for m in re.finditer(r'^(\s*)(%[\w.$-]+) = alloca ([^,\n]+), align (\d+)', body, re.M):
            allocas[m.group(2)] = (tsize(m.group(3)), m.group(3), m.start())
        if not allocas:
            continue
        cast = {m.group(1): m.group(2) for m in re.finditer(r'^\s*(%[\w.$-]+) = bitcast ptr (%[\w.$-]+) to ptr', body, re.M)}
        need = {}
        def root(v):
            seen = 0
            while v in cast and seen < 8:
                v = cast[v]; seen += 1
            return v
        for m in re.finditer(r'call [^\n@]*@([\w.$-]+)\(([^\n]*)\)', body):
            callee, argtxt = m.group(1), m.group(2)
            args = re.split(r',\s*(?=(?:i\d+|ptr|float|double)\b)', argtxt)
            def argval(i):
                if i >= len(args): return None
                mm = re.search(r'(%[\w.$-]+)\s*$', args[i].strip())
                return mm.group(1) if mm else None
            def num(i):
                if i >= len(args): return None
                mm = re.search(r'\b(-?\d+)\s*$', args[i].strip())
                return int(mm.group(1)) if mm else None
            if callee in API_OUT:
                for idx, sz in API_OUT[callee].items():
                    r = root(argval(idx) or '')
                    if r in allocas: need[r] = max(need.get(r, 0), sz); report.append((name, callee, r, sz))
            elif callee in STOS:
                r = root(argval(0) or ''); n = num(2)
                if r in allocas and n: need[r] = max(need.get(r, 0), n * STOS[callee]); report.append((name, callee, r, n * STOS[callee]))
            elif callee.startswith('llvm.memset'):
                r = root(argval(0) or ''); n = num(2)
                if r in allocas and n: need[r] = max(need.get(r, 0), n); report.append((name, callee, r, n))
        nb = body
        for v, sz in need.items():
            cur = allocas[v][0]
            if cur is not None and cur >= sz:
                continue
            k = (sz + 7) // 8
            widened.append({'function': name, 'alloca': v, 'was_bytes': cur, 'now_bytes': k * 8, 'by': sorted({c for (f, c, vv, z) in report if f == name and vv == v})})
            nb = re.sub(r'(^\s*%s = alloca )[^,\n]+(, align )\d+' % re.escape(v), r'\g<1>[%d x i64]\g<2>8' % k, nb, count=1, flags=re.M)
        if nb != body:
            pieces.append((fm.start(), fm.end(), nb))
    out, pos = [], 0
    for s, e, nb in pieces:
        out.append(src[pos:s]); out.append(nb); pos = e
    out.append(src[pos:])
    open(out_path, 'w').write(''.join(out))
    print('[fix_alloca] 拡幅 alloca %d 個 (%d 関数)' % (len(widened), len(pieces)))
    if rep_path:
        json.dump({'functions_patched': len(pieces), 'widened': widened}, open(rep_path, 'w'), indent=1)


if __name__ == '__main__':
    main()
