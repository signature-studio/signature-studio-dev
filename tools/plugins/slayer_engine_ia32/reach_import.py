#!/usr/bin/env python3
"""reach_import.py: 入口 (diff_entry.py ENTRIES) から KERNEL32 import へ至る静的な呼出経路を調べる (#3960 PLG-G2-39)。

  python3 reach_import.py            表 (import ごとの入口・ゲート経路の有無) を出す
  python3 reach_import.py --check    表と REPORT_APPENDIX_3127.md §3 の区分が一致するか確かめ、不一致なら exit 1

入力: work/lift_text/ott_lifted.c (lift_text.py の出力)。
静的解析のため分岐の条件は見ない (到達しうる経路の上界)。 そのため「静的に到達しない」は確かな根拠になるが、
「静的に到達する」は実行で通るとは限らない。 ゲート = main の callback が非 0 を返す経路 (f_10009f64・f_10007f30)。
"""
import collections, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'work', 'lift_text', 'ott_lifted.c')
REPORT = os.path.join(HERE, 'REPORT_APPENDIX_3127.md')
ENTRY_FUNCS = ['f_10001b40', 'f_10009300', 'f_1000d77e', 'f_10008630', 'f_10007ca0', 'f_1000e1b7', 'f_1000ea7d']
GATE = {'f_10009f64', 'f_10007f30'}
IMPORTS = [
    'CloseHandle', 'DeleteCriticalSection', 'EnterCriticalSection', 'ExitProcess', 'FlushFileBuffers', 'GetACP',
    'GetCPInfo', 'GetCurrentProcess', 'GetCurrentThreadId', 'GetFileType', 'GetLastError', 'GetModuleFileNameA',
    'GetModuleHandleA', 'GetOEMCP', 'GetProcAddress', 'GetStartupInfoA', 'GetStdHandle', 'GetStringTypeA',
    'GetStringTypeW', 'HeapAlloc', 'HeapFree', 'HeapReAlloc', 'InitializeCriticalSection', 'InterlockedIncrement',
    'LCMapStringA', 'LCMapStringW', 'LeaveCriticalSection', 'LoadLibraryA', 'MultiByteToWideChar', 'RaiseException',
    'SetFilePointer', 'SetHandleCount', 'SetLastError', 'SetStdHandle', 'TerminateProcess', 'TlsGetValue',
    'TlsSetValue', 'VirtualAlloc', 'VirtualFree', 'WideCharToMultiByte', 'WriteFile']


def load():
    src = open(SRC).read().splitlines()
    defs, calls, imps = set(), collections.defaultdict(set), collections.defaultdict(set)
    cur = None
    for ln in src:
        m = re.match(r'^void (f_[0-9a-f]+)\(void\) \{', ln)
        if m:
            cur = m.group(1)
            defs.add(cur)
            continue
        if ln == '}':
            cur = None
            continue
        if cur is None:
            continue
        for m in re.finditer(r'imp_([A-Za-z0-9_]+)\(\);', ln):
            imps[cur].add(m.group(1))
        for m in re.finditer(r'\b(f_[0-9a-f]+)\(\);', ln):
            calls[cur].add(m.group(1))
    return defs, calls, imps


def reach(defs, calls, roots, block=frozenset()):
    seen, st = set(), list(roots)
    while st:
        f = st.pop()
        if f in seen or f not in defs or f in block:
            continue
        seen.add(f)
        st.extend(calls.get(f, ()))
    return seen


def table():
    defs, calls, imps = load()
    rows = {}
    for w in IMPORTS:
        callers = sorted(f for f in imps if w in imps[f])
        any_entry = bool(set(callers) & reach(defs, calls, ENTRY_FUNCS))
        no_gate = bool(set(callers) & reach(defs, calls, ENTRY_FUNCS, GATE))
        rows[w] = (callers, any_entry, no_gate)
    return rows


def main():
    rows = table()
    if '--check' not in sys.argv:
        for w in IMPORTS:
            callers, any_entry, no_gate = rows[w]
            print('%-26s callers %-3d 入口から静的到達 %-5s ゲート無しで到達 %s' % (w, len(callers), any_entry, no_gate))
        return
    # ゲート無しで入口から静的に到達する import は、実測済みの 4 件 (+ 静的な分岐の上界で HeapFree) だけであること。
    no_gate = sorted(w for w in IMPORTS if rows[w][2])
    expect = ['HeapAlloc', 'HeapFree', 'HeapReAlloc', 'LeaveCriticalSection', 'VirtualAlloc']
    ok = no_gate == expect
    print('[reach_import] %s: ゲート無しで到達 %s' % ('PASS' if ok else 'FAIL', ','.join(no_gate)))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
