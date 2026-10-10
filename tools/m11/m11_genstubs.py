#!/usr/bin/env python3
# M11 #5: IR の外部 (declare) から runtime stub .c を生成 (Win32 API/CRT/未lift function_*)
# 生成物:
#   work/m11_winstubs.c      : Win32/CRT 系 declare の stub (shim 適合のみ自前実装, その他 fail-fast)
#   work/m11_fnstubs.c       : 未 lift function_* の stub (fail-fast 呼出で名前を吐く)
# 使い方: python3 m11_genstubs.py work/boot_all.ll --out work
import re, sys, os, json


def safe_name(nm):
    """関数名の中 '.' は C identifier 不正 → 'NAME_D1' 形に置換 (呼出側 IR と一致させる)"""
    return re.sub(r'\.(\d+)', r'_D\1', nm)

SHIM_BIND = {  # 既存 tools/shim 実装と結合するもの (m11 側で reimplement しない)
    'GlobalAlloc': None, 'GlobalLock': None, 'GlobalUnlock': None, 'GlobalFree': None,
    'LocalAlloc': None, 'LocalReAlloc': None, 'LocalFree': None,
    'HeapCreate': None, 'HeapAlloc': None, 'HeapReAlloc': None, 'HeapFree': None,
    'GetProcessHeap': None, 'HeapDestroy': None, 'GlobalCompact': None,
    # shim/src/sync.c (重複シンボル → shim 実装に一本化)
    'CreateThread': None, 'ExitThread': None,
    'WaitForSingleObject': None, 'WaitForSingleObjectEx': None,
    'CreateEventW': None, 'CreateEventA': None, 'SetEvent': None, 'ResetEvent': None,
    'InitializeCriticalSection': None, 'InitializeCriticalSectionAndSpinCount': None,
    'EnterCriticalSection': None, 'TryEnterCriticalSection': None,
    'LeaveCriticalSection': None, 'DeleteCriticalSection': None, 'MemoryBarrier': None,
    'InterlockedIncrement': None, 'InterlockedDecrement': None,
    'InterlockedExchange': None, 'InterlockedExchangeAdd': None,
    'TlsAlloc': None, 'TlsFree': None, 'TlsGetValue': None, 'TlsSetValue': None,
    'Sleep': None, 'GetCurrentThreadId': None,
    # shim/src/file.c
    'GetLastError': None, 'SetLastError': None,
    'GetFileSize': None, 'GetFileSizeEx': None, 'SetEndOfFile': None, 'SetFilePointer': None,
    'CloseHandle': None,
    # shim/src/timer.c
    'GetTickCount': None, 'QueryPerformanceCounter': None, 'QueryPerformanceFrequency': None,
    'timeGetTime': None,
    # m11_rt.c / 入手済 (runtime 側で実装)
    'VirtualAlloc': None, 'VirtualFree': None, 'VirtualProtect': None, 'VirtualQuery': None,
}

STRUCTS = {}   # %name -> [field types]  (IR 'type' 定義; by-value 構造体引数は wasm32 で各 field に分解される)


def split_args(args):
    out, depth, cur = [], 0, ''
    for ch in args:
        if ch in '({<[':
            depth += 1
        elif ch in ')}>]':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    res = []
    for a in out:
        if a == '...':
            continue
        t = a.split()[0]
        if t.startswith('%') and t[1:] in STRUCTS:
            res.extend(STRUCTS[t[1:]])
        else:
            res.append(t)
    return res


def ctype(lltype):
    m = {'i1': 'int', 'i8': 'int', 'i16': 'int', 'i32': 'int', 'i64': 'long long',
         'f32': 'float', 'f64': 'double', 'ptr': 'void*', 'i128': 'void*', 'i256': 'void*',
         'void': 'void'}
    return m.get(lltype, 'long long')   # 未知型 (%struct 戻り等) は i64 扱い


def sig_of(ret, args):
    if args == "":
        return ctype(ret) + ' NAME(void)'
    parts = []
    for i, a in enumerate(args.split()):
        if a == ',':
            continue
        parts.append(ctype(a) + ' _a%d' % i)
    return ctype(ret) + ' NAME(' + ', '.join(parts) + ')'

varargs = False

EXCLUDE = set()
if os.environ.get('M11_EXCLUDE') and os.path.exists(os.environ['M11_EXCLUDE']):
    EXCLUDE = set(open(os.environ['M11_EXCLUDE']).read().split())


def main():
    ir = sys.argv[1]
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    src = open(ir).read()
    for mt in re.finditer(r'^%([\w.$-]+) = type \{ ([^}]*) \}', src, re.M):
        STRUCTS[mt.group(1)] = [x.strip() for x in mt.group(2).split(',')]
    decls = []
    for m in re.finditer(r'^declare \S+ @([\w.$-]+)\(([^)]*)\)', src, re.M):
        ret = re.search(r'^declare (\S+) @', m.group(0)).group(1)
        decls.append((m.group(1), ret, m.group(2), m.group(0)))
    decls = sorted(set(decls))
    decls = [(nm.replace('.', '_D'), ret, args, line) for (nm, ret, args, line) in decls]
    defined_fns = set(re.findall(r'^define \S+ @([\w.$-]+)', src, re.M))

    # 未 lift function_*: fail-fast
    wf = ['/* m11 auto-gen: 未 lift function_* fail-fast stubs */',
          '#include <stdint.h>', '#include <stdlib.h>', '#include <emscripten.h>']
    nfns = 0
    for (nm, ret, args, _line) in decls:
        if not nm.startswith('function_') or nm in defined_fns:
            continue
        sig = re.sub(r'NAME', nm, sig_of(ret, args if args != '' else ''))
        params = ', '.join(ctype(a) for a in ([x for x in args.split() if x != ',']) if a) if False else ''
        wf.append('__attribute__((noreturn)) static void m11_fail_fast(const char *n) {')
        wf.append('    fprintf(stderr, "[m11][fail-fast] unresolved lift call: %s\\n", n); fflush(stderr);')
        wf.append('    emscripten_force_exit(101);')
        wf.append('}')
        wf.append('')
        break
    # 1 factory 化: 各 stub は m11_unresolved_function(名前) を呼び, 0 を返すはずだがないので noreturn
    for (nm, ret, args, _line) in decls:
        if not nm.startswith('function_') or nm in defined_fns:
            continue
        pl = split_args(args)
        var = ('...' if '...' in args else '')
        body = sig = None

    # 重複ナシ: 一度 factory を出し, 全转向actually作る
    factory = []
    for (nm, ret, args, _line) in decls:
        if not nm.startswith('function_') or nm in defined_fns:
            continue
        pl = split_args(args)
        var = '...' if ('...' in args) else ''
        line_body = '    m11_unresolved_function("%s");' % nm
        sig = re.sub(r'NAME', nm, sig_of(ret, ''.join(pl).replace('...', '')) if not var else 'unusual')
        # generate
        params = ''
        if var:
            params = ''
        else:
            parts = []
            for i, a in enumerate(pl):
                parts.append(ctype(a) + ' _a%d' % i)
            params = ', '.join(parts) if parts else 'void'
        ftype = ctype(ret)
        decl_line = '%s %s(%s)' % (ftype, nm, params)
        factory.append(decl_line + ' {')
        factory.append('    ' + line_body)
        if ftype == 'void':
            factory.append('    return;')
        elif ftype == 'float':
            factory.append('    return 0.0f;')
        elif ftype == 'double':
            factory.append('    return 0.0;')
        else:
            factory.append('    return 0;')
        factory.append('}')
        nfns += 1

    wf = ['/* m11 auto-gen: 未 lift function_* stubs (fail-fast 呼出を吐く) */',
          '#include <stdint.h>', '#include <stdio.h>', '#include <stdlib.h>', '#include <emscripten.h>',
          'extern void m11_unresolved_function(const char* n);']
    wf.extend(factory)
    open(os.path.join(outdir, 'm11_fnstubs.c'), 'w').write('\n'.join(wf) + '\n')
    print('[genstubs] fn stubs: %d -> %s' % (nfns, os.path.join(outdir, 'm11_fnstubs.c')))

    # Win32 stubs: shim 結合以外を fail-fast or no-op
    wl = ['/* m11 auto-gen: Win32/CRT extern stubs (shim 適合あり以外は fail-fast) */',
          '#include <stdint.h>', '#include <stdio.h>', '#include <stdlib.h>', '#include <emscripten.h>',
          'extern void m11_stub_hit(const char* n);']
    napi = 0
    for (nm, ret, args, _line) in decls:
        if nm.startswith('function_') or nm.startswith('llvm.') or nm.startswith('__asm_') or nm.startswith('__zext') \
                or nm.startswith('m11_') or nm.startswith('entry_point') \
                or nm.startswith('memset') or nm.startswith('memcpy') or nm.startswith('memcmp') \
                or nm.startswith('memmove') or nm.startswith('strlen') or nm.startswith('strcmp') \
                or nm.startswith('strcpy') or nm.startswith('strncmp') or nm.startswith('abort') \
                or nm.startswith('malloc') or nm.startswith('free') or nm.startswith('exit'):
            continue
        if nm in SHIM_BIND or nm in EXCLUDE:
            continue
        params = str(args).replace('...', '')
        pl = split_args(args)
        parts = []
        for i, a in enumerate(pl):
            parts.append(ctype(a) + ' _a%d' % i)
        bodyparams = ', '.join(parts) if parts else 'void'
        ftype = ctype(ret)
        cname = safe_name(nm)
        wl.append('%s %s(%s) {' % (ftype, cname, bodyparams))
        wl.append('    m11_stub_hit("%s");' % cname)
        if ftype == 'void':
            wl.append('    return;')
        elif ftype == 'void*':
            wl.append('    return (void*)0;')
        elif ftype == 'float':
            wl.append('    return 0.0f;')
        elif ftype == 'double':
            wl.append('    return 0.0;')
        else:
            wl.append('    return 0;')
        wl.append('}')
        napi += 1
    open(os.path.join(outdir, 'm11_winstubs.c'), 'w').write('\n'.join(wl) + '\n')
    print('[genstubs] win stubs: %d -> %s' % (napi, os.path.join(outdir, 'm11_winstubs.c')))


if __name__ == '__main__':
    main()
