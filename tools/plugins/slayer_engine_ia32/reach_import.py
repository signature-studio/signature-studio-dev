#!/usr/bin/env python3
"""reach_import.py: 入口 (diff_entry.py ENTRIES) から KERNEL32 import へ至る静的な呼出経路を調べる (#3960 PLG-G2-39)。

  python3 reach_import.py            表 (import ごとの入口・ゲート経路の有無) を出す
  python3 reach_import.py --paths    入口から各 import までの最短の呼出し経路 (ゲート無し・有り) を出す
  python3 reach_import.py --check    ゲート無しで入口から静的に到達する import の集合が、期待集合と一致するか確かめ、不一致なら exit 1

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
# 実行の計数 (測定 commit で wasm 側の imp_* 入口を数えた) で、ゲート無しの入口から実際に呼ばれた 4 件。
MEASURED = ['HeapAlloc', 'HeapReAlloc', 'LeaveCriticalSection', 'VirtualAlloc']
# 静的のみ: ゲート無しで静的に到達するが、harness の入力では未実行。値は 直接の呼出し元 (入口の関数)。
# f_1000e1b7 は VirtualAlloc の戻り値が edi (= 0) と等しいときだけ HeapFree を呼ぶ。harness の VirtualAlloc は失敗しないため 0 件。
STATIC_ONLY = {'HeapFree': 'f_1000e1b7'}
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


def path(defs, calls, root, target, block=frozenset()):
    if root not in defs or root in block:
        return None
    prev = {root: None}
    q = collections.deque([root])
    while q:
        f = q.popleft()
        if f in target:
            p = []
            while f is not None:
                p.append(f)
                f = prev[f]
            return p[::-1]
        for g in sorted(calls.get(f, ())):
            if g in defs and g not in block and g not in prev:
                prev[g] = f
                q.append(g)
    return None


def first_path(defs, calls, target, block=frozenset()):
    for e in ENTRY_FUNCS:
        p = path(defs, calls, e, target, block)
        if p:
            return p
    return None


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
    if '--paths' in sys.argv:
        defs, calls, imps = load()
        for w in IMPORTS:
            callers = {f for f in imps if w in imps[f]}
            p = first_path(defs, calls, callers)
            if p is None:
                continue
            q = first_path(defs, calls, callers, GATE)
            print('%-22s 入口→ %s | ゲート無し: %s' % (w, ' > '.join(p), ' > '.join(q) if q else 'なし'))
        return
    if '--check' not in sys.argv:
        for w in IMPORTS:
            callers, any_entry, no_gate = rows[w]
            print('%-26s callers %-3d 入口から静的到達 %-5s ゲート無しで到達 %s' % (w, len(callers), any_entry, no_gate))
        return
    # ゲート無しで入口から静的に到達する import = 実測済みの 4 件 + 静的のみの 1 件 (直接の呼出し元が入口であること)。
    defs, calls, imps = load()
    no_gate = sorted(w for w in IMPORTS if rows[w][2])
    expect = sorted(set(MEASURED) | set(STATIC_ONLY))
    static_ok = all(e in ENTRY_FUNCS and w in imps.get(e, ()) for w, e in STATIC_ONLY.items())
    ok = no_gate == expect and static_ok
    print('[reach_import] %s: ゲート無しで静的到達 %s (実測 %s / 静的のみ %s)' % (
        'PASS' if ok else 'FAIL', ','.join(no_gate), ','.join(MEASURED),
        ','.join('%s<-%s' % kv for kv in STATIC_ONLY.items())))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
