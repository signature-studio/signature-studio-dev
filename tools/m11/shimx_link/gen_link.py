#!/usr/bin/env python3
"""M11 closure IR の外部参照を分類し、shimx リンク用の生成物を作る (CAB-166)。

  gen_link.py --ir work/boot_final3.ll --shimx-nm X --m11-nm Y --out work/shimx_link

入力: lift 後処理済み IR / shimx オブジェクトの nm (定義済み) / m11 側 C オブジェクトの nm
出力 (--out):
  classes.json          分類 (shimx / gui / audio / lift_c / lift_unresolved / unknown + libc)
  gui_stubs_failfast.c  GUI・audio 未提供 API の fail-fast スタブ (shim_unimplemented 経由; 署名は IR declare)
  gui_stubs_soft.c      同上の 0 返却版 (m11_stub_hit で計数; M11 既存 m11_winstubs.c と同じ流儀)
  trace_wrap.c          shimx/GUI 呼出の計数ラッパ (__sxt_<name>) と名前表
  boot_trace.ll         IR 内の shimx/GUI 参照を __sxt_<name> に改名した IR (トレースビルド用)
"""
import argparse, importlib.util, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHIMX = os.path.abspath(os.path.join(HERE, '..', '..', 'shimx'))
spec = importlib.util.spec_from_file_location('ir_undef', os.path.join(SHIMX, 'scripts', 'ir_undef.py'))
iu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iu)

CT = {'i1': 'int', 'i8': 'int', 'i16': 'int', 'i32': 'int', 'i64': 'long long', 'float': 'float', 'double': 'double',
      'ptr': 'void*', 'void': 'void'}
AUDIO_DLLS = {'dsound.dll'}
SOFT_COMPAT = {'LoadStringW', 'MessageBoxA', 'MessageBoxW'}   # gui_compat.c が --soft で定義する (soft スタブからは除外)
RET_LOG = {'GetModuleHandleW', 'GetProcAddress'}   # 戻り値も sxt_ret で記録する (SHX-T9f #1985)
DEF_RE = re.compile(r'^define\b[^@\n]*@([\w.$-]+)\(')
RET_CALL_RE = re.compile(r'@(%s)\(' % '|'.join(sorted(RET_LOG)))


def nm_defined(path):
    out = {}
    for l in open(path):
        p = l.split()
        if len(p) >= 3 and p[-2] in 'TtWwDdBbRr':
            out[p[-1]] = p[-2]
    return out


def insert_arg(line, pos, extra):
    """pos は開き括弧の直後。対応する閉じ括弧の直前に extra を足す (引数内の括弧を数える)。"""
    depth, i = 1, pos
    while depth:
        depth += {'(': 1, ')': -1}.get(line[i], 0)
        i += 1
    inner = line[pos:i - 1]
    return line[:i - 1] + (', ' if inner.strip() else '') + extra + line[i - 1:]


def site_rewrite(src):
    """RET_LOG の呼出し元を site ID (i32) として wrapper に渡す。
    site = lifted IR の enclosing 関数名 + IR 行番号 (wasm の機械語 PC は C 側から取れないため)。"""
    fn, sites, out = '?', [], []
    for ln, line in enumerate(src.split('\n'), 1):
        m = DEF_RE.match(line)
        if m:
            fn = m.group(1)
        hits = RET_CALL_RE.findall(line)
        if len(hits) > 1:
            raise SystemExit('gen_link: 1 行に RET_LOG 呼出しが 2 つ以上 (line %d)' % ln)
        m = RET_CALL_RE.search(line)
        if m and line.lstrip().startswith('declare '):
            line = insert_arg(line, m.end(), 'i32')
        elif m:
            if ' call ' not in line:
                raise SystemExit('gen_link: RET_LOG 対象が call 以外で参照 (line %d)' % ln)
            sites.append('%s@L%d' % (fn, ln))
            line = insert_arg(line, m.end(), 'i32 %d' % (len(sites) - 1))
        out.append(line)
    return '\n'.join(out), sites


def parse_decls(src):
    decls = {}
    for m in re.finditer(r'^declare\s+(?:[\w.]+\s+)*?(void|i\d+|float|double|ptr|<[^>]+>|%[\w.$-]+|\{[^}]*\})\s+@([\w.$-]+)\((.*?)\)', src, re.M):
        decls.setdefault(m.group(2), (m.group(1), m.group(3)))
    return decls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--shimx-nm', required=True)
    ap.add_argument('--m11-nm', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    src = open(a.ir, errors='replace').read()
    decls = parse_decls(src)
    defined = set(re.findall(r'^define\s+[^@\n]*@([\w.$-]+)\(', src, re.M))
    shimx = nm_defined(a.shimx_nm)
    m11c = nm_defined(a.m11_nm)
    imp = json.load(open(os.path.join(SHIMX, 'data', 'imports.json')))
    dll_of = {}
    def add(e):
        dll_of.setdefault(e['name'], e['dll'].lower())
    for e in imp['flengine']['static'] + imp['flengine']['delay']:
        add(e)
    for v in imp['plugins'].values():
        for e in v['static'] + v['delay']:
            add(e)
    cls = {}
    for n, (ret, args) in decls.items():
        if n in defined:
            continue
        if n.startswith('llvm.'):
            cls[n] = 'intrinsic'
        elif n in shimx:
            cls[n] = 'shimx'
        elif n in m11c:
            cls[n] = 'lift_c'            # simd helper / ov / rt など m11 側 C が提供
        elif iu.LIFTER.match(n):
            cls[n] = 'lift_unresolved'   # function_* 等: fnstubs の fail-fast が受ける
        elif n in iu.LIBC:
            cls[n] = 'libc'
        elif n in dll_of:
            cls[n] = 'audio' if dll_of[n] in AUDIO_DLLS else 'gui'
        else:
            cls[n] = 'unknown'
    names = {k: sorted(n for n, c in cls.items() if c == k) for k in ('shimx', 'lift_c', 'lift_unresolved', 'libc', 'intrinsic', 'gui', 'audio', 'unknown')}
    gui_dll = {}
    for n in names['gui'] + names['audio']:
        gui_dll[dll_of.get(n, '?')] = gui_dll.get(dll_of.get(n, '?'), 0) + 1
    json.dump({'ir': os.path.basename(a.ir), 'total_external': len(cls),
               'counts': {k: len(v) for k, v in names.items()}, 'gui_audio_by_dll': gui_dll,
               'names': names}, open(os.path.join(a.out, 'classes.json'), 'w'), indent=1)

    structs = {}
    for mt in re.finditer(r'^%([\w.$-]+) = type \{ ([^}]*) \}', src, re.M):
        structs[mt.group(1)] = [x.strip() for x in mt.group(2).split(',')]

    def flat(t):   # by-value 構造体引数は wasm32 では各フィールドへ分解される (m11_genstubs.py と同じ扱い)
        t = t.split()[0]
        if t.startswith('%') and t[1:] in structs:
            return [x for f in structs[t[1:]] for x in flat(f)]
        if t not in CT:
            print('WARN: 型 %s は i64 扱い' % t, file=sys.stderr)
        return [CT.get(t, 'long long')]

    def sig(n):
        ret, args = decls[n]
        if '...' in args:
            return None
        ps = [x for p in iu.split_args(args) for x in flat(p)]
        return CT.get(ret, 'long long'), ps

    # ---- GUI/audio/unknown の fail-fast / soft スタブ ----
    stub_names = names['gui'] + names['audio'] + names['unknown']
    ff = ['/* 自動生成 gen_link.py: GUI/audio 未提供 API の fail-fast スタブ (呼ばれたら名前を出して abort) */',
          'extern void shim_unimplemented(const char*);']
    soft = ['/* 自動生成 gen_link.py: GUI/audio 未提供 API の 0 返却スタブ (m11_stub_hit で計数; M11 既存挙動と同じ) */',
            'extern void m11_stub_hit(const char*);']
    for n in stub_names:
        s = sig(n)
        if s is None:
            continue
        rt, ps = s
        pl = ', '.join('%s a%d' % (t, i) for i, t in enumerate(ps)) or 'void'
        for out, body in ((ff, 'shim_unimplemented("%s");' % n), (soft, 'm11_stub_hit("%s");' % n)):
            if out is soft and n in SOFT_COMPAT:
                continue
            out.append('%s %s(%s) {\n    %s\n    %s\n}' % (rt, n, pl, body, 'return;' if rt == 'void' else 'return 0;'))
    open(os.path.join(a.out, 'gui_stubs_failfast.c'), 'w').write('\n'.join(ff) + '\n')
    open(os.path.join(a.out, 'gui_stubs_soft.c'), 'w').write('\n'.join(soft) + '\n')

    # ---- トレースラッパ: lifted コードからの shimx/GUI 呼出のみを計数 ----
    wrap = [n for n in names['shimx'] + stub_names if sig(n) is not None]
    skipped = [n for n in names['shimx'] + stub_names if sig(n) is None]
    wc = ['/* 自動生成 gen_link.py: shimx/GUI 呼出の計数ラッパ。IR 内の @NAME を @__sxt_NAME に改名して挟む */',
          '#include <stdint.h>', 'extern void sxt_enter(int idx);', 'extern void sxt_ret(int idx, unsigned long long a, unsigned long long b, unsigned long long r, int site);']
    tsrc, sites = site_rewrite(src)
    for i, n in enumerate(wrap):
        rt, ps = sig(n)
        pl = ', '.join('%s a%d' % (t, k) for k, t in enumerate(ps)) or 'void'
        al = ', '.join('a%d' % k for k in range(len(ps)))
        wc.append('extern %s %s(%s);' % (rt, n, ', '.join(ps) or 'void'))
        if n in RET_LOG:
            a1 = 'a1' if len(ps) > 1 else '0'
            wc.append('%s __sxt_%s(%s, int site) { sxt_enter(%d); %s r = %s(%s); sxt_ret(%d, (unsigned long long)(uintptr_t)a0, (unsigned long long)(uintptr_t)%s, (unsigned long long)(uintptr_t)r, site); return r; }' % (rt, n, pl, i, rt, n, al, i, a1))
            continue
        wc.append('%s __sxt_%s(%s) { sxt_enter(%d); %s%s(%s); }' % (rt, n, pl, i, '' if rt == 'void' else 'return ', n, al))
    wc.append('const int sxt_n_names = %d;' % len(wrap))
    wc.append('const char* const sxt_names[] = {%s};' % ','.join('"%s"' % n for n in wrap))
    wc.append('const unsigned char sxt_is_gui[] = {%s};' % ','.join('1' if n in set(stub_names) else '0' for n in wrap))
    wc.append('const int sxt_nsite = %d;' % len(sites))
    wc.append('const char* const sxt_site_str[] = {%s};' % ','.join('"%s"' % s for s in sites or ['-']))
    open(os.path.join(a.out, 'trace_wrap.c'), 'w').write('\n'.join(wc) + '\n')
    pat = re.compile(r'@(%s)(?![\w.$-])' % '|'.join(re.escape(n) for n in sorted(wrap, key=len, reverse=True)))
    new = pat.sub(lambda m: '@__sxt_' + m.group(1), tsrc)
    open(os.path.join(a.out, 'boot_trace.ll'), 'w').write(new)
    print('[gen_link] 外部参照 %d: %s' % (len(cls), ' '.join('%s=%d' % (k, len(v)) for k, v in names.items())))
    print('[gen_link] ラッパ %d 本 (varargs で除外 %d: %s) / スタブ %d 本' % (len(wrap), len(skipped), ' '.join(skipped), len(stub_names)))
    print('[gen_link] RET_LOG 呼出し元 site %d 件 (%s)' % (len(sites), ' '.join(sorted(RET_LOG))))


if __name__ == '__main__':
    main()
