#!/usr/bin/env python3
"""LLVM IR (lift 産物) の外部参照を shim の提供面と突き合わせ、未提供の Win32/CRT API に fail-fast スタブを生成する。

  ir_undef.py <ir.ll> [--nm work/nm_MT.txt] [--emit-stubs out.c] [--normalize-dup out.ll] [--json out.json]

分類:
  shimx      : shimx が定義済み (nm, 名前完全一致)
  shimx_dup  : RetDec が別 declare した重複 (NAME.1 / NAME_D1 等, 基名は shimx 定義済み)。
               署名が基名と異なり得るためリンクにはスタブ (--emit-stubs) か IR 正規化 (--normalize-dup) が要る
  libc       : Emscripten libc / compiler-rt 側が解決する既知名 (memset 等) と llvm.* intrinsic
  lifter     : function_*/__asm_*/__zext*/entry_point 等の lift 由来名 (shim の担当外)
  win_other  : FLEngine/プラグイン import 名 (data/imports.json) だが shimx 未提供 (GUI/audio 担当 DLL か、未実装)
  unknown    : 上記以外
--emit-stubs : win_other + unknown + shimx_dup の関数それぞれに「名前を出して abort」するスタブ C を出力
               (署名は IR の declare から導出し、**構造体 by-value 引数は wasm32 規則で各フィールドへ展開**する。
                展開しないと実リンクで signature mismatch になる — M11 の WindowFromPoint(%tagPOINT) 実測 (REPORT §1))
--normalize-dup : shimx_dup を基名 (@NAME) へ正規化した IR を出力する。重複 declare の削除 + 呼出siteの
               引数個数/戻り値型の整合 (不足引数は 0/null 補間, 戻り値型差は zext/trunc/inttoptr/ptrtoint で繋ぐ)。
               正規化後は shimx の実関数に直接リンクできる (fail-fast スタブ不要)
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
LIBC = set('''memset memcpy memmove memcmp memchr strlen strcmp strncmp strcpy strncpy strcat strchr strrchr strstr
malloc free calloc realloc abort exit atexit printf fprintf sprintf snprintf puts putchar fputs fwrite fread fflush
sin cos tan atan atan2 exp log pow sqrt floor ceil fabs fmod log10 log2 sinf cosf tanf expf logf powf sqrtf floorf ceilf fabsf
toupper tolower isalpha isdigit isspace qsort bsearch rand srand time clock getenv
socket bind listen accept connect send recv sendto recvfrom select setsockopt getsockopt getsockname ntohs htons ntohl htonl
gethostbyname getaddrinfo freeaddrinfo shutdown'''.split())
LIFTER = re.compile(r'^(function_|__asm_|__zext|entry_point|m\d+_|sub_|loc_|llvm\.)')
CT = {'i1': 'int', 'i8': 'int', 'i16': 'int', 'i32': 'int', 'i64': 'long long', 'float': 'float', 'double': 'double',
      'ptr': 'void*', 'void': 'void', 'i128': 'void*'}
# LLVM 型 → 0 値リテラル (normalize-dup の引数補間 / emit-stubs の既定戻り値)
ZERO = {'i1': '0', 'i8': '0', 'i16': '0', 'i32': '0', 'i64': '0', 'ptr': 'null',
        'float': '0.000000e+00', 'double': '0.000000e+00'}
CT_BITS = {'i1': 1, 'i8': 8, 'i16': 16, 'i32': 32, 'i64': 64}


def split_args(a):
    out, depth, cur = [], 0, ''
    for ch in a:
        if ch in '<[{(':
            depth += 1
        elif ch in '>]})':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def ctype(t):
    t = t.strip().split()[0] if t.strip() else 'i64'
    return CT.get(t, 'long long')


def parse_structs(src):
    """%name = type { ... } の表 (by-value 引数の wasm32 展開に使用)"""
    structs = {}
    for mt in re.finditer(r'^%([\w.$-]+) = type \{ ([^}]*) \}', src, re.M):
        structs[mt.group(1)] = [x.strip() for x in mt.group(2).split(',')]
    return structs


def flat_fields(t, structs, warn=True):
    """by-value 構造体引数を wasm32 規則 (各フィールドへ分解) で展開した LLVM 型列を返す。
    gen_link.py (M11) と同じ規約。スカラーは 1 要素。"""
    t = t.strip().split()[0] if t.strip() else 'i64'
    if t.startswith('%') and t[1:] in structs:
        out = []
        for f in structs[t[1:]]:
            out.extend(flat_fields(f, structs, warn))
        return out
    if t not in CT and warn:
        print('WARN: 型 %s は i64 扱い' % t, file=sys.stderr)
    return [t if t in CT else 'i64']


def conv_insn(src_t, dst_t):
    """src_t → dst_t への LLVM 変換命令テンプレート ('... %s ...' 形式, %s に %name を挿す)。同型は None"""
    if src_t == dst_t:
        return None
    if src_t in CT_BITS and dst_t in CT_BITS:
        op = 'trunc' if CT_BITS[src_t] > CT_BITS[dst_t] else 'zext'
        return op + ' ' + src_t + ' %s to ' + dst_t
    if src_t in CT_BITS and dst_t == 'ptr':
        return 'inttoptr ' + src_t + ' %s to ptr'
    if src_t == 'ptr' and dst_t in CT_BITS:
        return 'ptrtoint ptr %s to ' + dst_t
    if src_t == 'float' and dst_t == 'double':
        return 'fpext float %s to double'
    if src_t == 'double' and dst_t == 'float':
        return 'fptrunc double %s to float'
    return None   # 非対応 (呼出元でスキップ)


def parse_declares(src):
    decls = {}
    for m in re.finditer(r'^declare\s+(?:[\w.]+\s+)*?(void|i\d+|float|double|ptr|<[^>]+>|%[\w.$-]+|\{[^}]*\})\s+@([\w.$-]+)\((.*?)\)', src, re.M):
        decls.setdefault(m.group(2), (m.group(1), m.group(3)))
    return decls


def normalize_dup(src, structs, decls, shimx_defined, out_path):
    """shimx_dup (NAME.<d>, 基名は shimx 定義) を基名 declare へ正規化した IR を書き出す。
    戻り値: (正規化した重複名, スキップした重複名)"""
    renamed, skipped = {}, []
    for n0, (dret, dargs) in decls.items():
        m1 = re.match(r'^([A-Za-z_]\w*)\.(\d+)$', n0)
        m2 = re.match(r'^([A-Za-z_]\w*)_D(\d+)$', n0)
        m = m1 or m2
        if not m or n0 in shimx_defined:
            continue
        base = m.group(1)
        if base not in shimx_defined or base not in decls:
            continue
        cret, cargs = decls[base]
        cparams = [a.strip() for a in split_args(cargs) if a.strip() != '...']
        if '...' in cargs or '...' in dargs:
            skipped.append(n0)
            continue
        if cret not in CT or dret not in CT or not all(p in CT for p in cparams):
            skipped.append(n0)
            continue
        renamed[n0] = (base, cret, cparams, dret, dargs)
    if not renamed:
        return renamed, skipped

    # 呼出siteの書換 (void 呼出 = 戻り値なし形式も扱う)
    alt = '|'.join(re.escape(n) for n in sorted(renamed, key=len, reverse=True))
    pat = re.compile(r'( *)(?:%([\w.$-]+) = )?call (i\d+|ptr|float|double|void) @(' + alt + r')\(([^)]*)\)')
    arg_ty_re = re.compile(r'^(i\d+|ptr|float|double)\s+(\S+)$')
    out_lines, n_call = [], 0
    done_names = set()
    for line in src.split('\n'):
        mt = pat.match(line)
        if not mt:
            out_lines.append(line)
            continue
        indent, dst, dret_call, name, argstr = mt.group(1), mt.group(2), mt.group(3), mt.group(4), mt.group(5)
        base, cret, cparams, dret, _dargs = renamed[name]
        have = [a.strip() for a in split_args(argstr)] if argstr.strip() else []
        if len(have) > len(cparams):
            skipped.append(name)
            out_lines.append(line)
            continue
        parts, ok = [], True
        for i, p in enumerate(cparams):
            if i < len(have):
                am = arg_ty_re.match(have[i])
                if not am or am.group(1) != p:      # 引数型が一致しない場合は触らない (署名正規化 T7 の領域)
                    ok = False
                    break
                parts.append(have[i])
            else:
                parts.append('%s %s' % (p, ZERO.get(p, '0')))
        if not ok:
            skipped.append(name)
            out_lines.append(line)
            continue
        done_names.add(name)
        if dst:
            newv = '__shxd_' + dst.lstrip('%')
            out_lines.append('%s%%%s = call %s @%s(%s)' % (indent, newv, cret, base, ', '.join(parts)))
            cv = conv_insn(cret, dret)
            if cv:
                out_lines.append('%s%%%s = %s' % (indent, dst, cv % ('%' + newv)))
        else:
            out_lines.append('%scall %s @%s(%s)' % (indent, cret, base, ', '.join(parts)))
        n_call += 1
    src2 = '\n'.join(out_lines)
    # 書換できた重複の declare 行のみ削除 (skipped は declare を残して参照を保つ)
    for n0 in sorted(done_names):
        src2 = re.sub(r'^declare [^\n]*@%s\([^\n]*\)( local_unnamed_addr)?\n' % re.escape(n0), '', src2, flags=re.M)
    open(out_path, 'w').write(src2)
    if skipped:
        print('  --normalize-dup WARN: 未書換 (declare 残存): %s' % ' '.join(sorted(set(skipped))))
    print('  --normalize-dup: %d 名 (呼出 %d site) を基名へ正規化 -> %s' % (len(done_names), n_call, out_path))
    return done_names, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--nm', default=os.path.join(ROOT, 'work', 'nm_MT.txt'))
    ap.add_argument('--emit-stubs')
    ap.add_argument('--normalize-dup')
    ap.add_argument('--json')
    a = ap.parse_args()
    src = open(a.ir, errors='replace').read()
    structs = parse_structs(src)
    decls = parse_declares(src)
    defined = set(re.findall(r'^define\s+[^@\n]*@([\w.$-]+)\(', src, re.M))
    shimx = set()
    for l in open(a.nm):
        p = l.split()
        if len(p) >= 2 and p[-2] in 'TWtw':
            shimx.add(p[-1])
    imp = json.load(open(os.path.join(ROOT, 'data', 'imports.json')))
    winnames = {e['name'] for e in imp['flengine']['static']} | {e['name'] for e in imp['flengine']['delay']}
    for v in imp['plugins'].values():
        winnames |= {e['name'] for e in v['static']} | {e['name'] for e in v['delay']}
    cls = {}
    for n0 in decls:
        m1 = re.match(r'^([A-Za-z_]\w*)\.(\d+)$', n0)     # 'SHGetFolderPathW.1' 形式の重複 declare
        m2 = re.match(r'^([A-Za-z_]\w*)_D(\d+)$', n0)     # 同上の M11 rename 後形式 ('SHGetFolderPathW_D1')
        base = m1.group(1) if m1 else (m2.group(1) if m2 else None)
        if base and base not in shimx:
            base = None                                    # 基名が shimx 定義で無ければただの名前として扱う
        if n0 in defined:
            continue
        if n0 in shimx:
            cls[n0] = 'shimx'
        elif base and base in shimx:
            cls[n0] = 'shimx_dup'     # 基名は shimx 定義済みだが重複 declare は別シンボル (署名不一致になり得る)
        elif LIFTER.match(n0):
            cls[n0] = 'lifter'
        elif n0 in LIBC or (re.sub(r'\.\d+$', '', n0) if re.match(r'^[A-Za-z_]\w*\.\d+$', n0) else n0) in LIBC:
            cls[n0] = 'libc'
        elif n0 in winnames or (re.sub(r'\.\d+$', '', n0) if re.match(r'^[A-Za-z_]\w*\.\d+$', n0) else n0) in winnames:
            cls[n0] = 'win_other'
        else:
            cls[n0] = 'unknown'
    cnt = {}
    for k in cls.values():
        cnt[k] = cnt.get(k, 0) + 1
    print('%s: declare %d (IR 内定義を除く外部参照 %d)' % (os.path.basename(a.ir), len(decls), len(cls)))
    for k in ('shimx', 'shimx_dup', 'libc', 'lifter', 'win_other', 'unknown'):
        names = sorted(n for n, c in cls.items() if c == k)
        print('  %-9s %4d %s' % (k, len(names), (' '.join(names) if k in ('win_other', 'unknown') else '')[:1500]))
    if a.json:
        json.dump({'counts': cnt, 'classes': {k: sorted(n for n, c in cls.items() if c == k) for k in cnt}}, open(a.json, 'w'), indent=1)
    if a.normalize_dup:
        normalize_dup(src, structs, decls, shimx, a.normalize_dup)
    if a.emit_stubs:
        out = ['/* 自動生成: scripts/ir_undef.py — shim 未提供 API の fail-fast スタブ (呼ばれたら名前を出して abort)',
               ' * 構造体 by-value 引数は wasm32 規則で展開済み (R6)。 */',
               '#include <stdio.h>', '#include <stdlib.h>', 'extern void shim_unimplemented(const char*);']
        n = 0
        for name in sorted(cls):
            if cls[name] not in ('win_other', 'unknown', 'shimx_dup'):
                continue
            ret, args = decls[name]
            params = []
            for p in split_args(args):
                p = p.strip()
                if p == '...':
                    continue
                params.extend(flat_fields(p, structs))      # R6: by-value 構造体の wasm32 展開
            plist = ', '.join('%s a%d' % (ctype(t), i) for i, t in enumerate(params)) or 'void'
            rt = ctype(ret)
            safe = re.sub(r'\.(\d+)', r'_D\1', name)
            body = '    shim_unimplemented("%s");' % name
            body += '\n    return;' if rt == 'void' else '\n    return 0;'
            out.append('%s %s(%s) {\n%s\n}' % (rt, safe, plist, body))
            n += 1
        open(a.emit_stubs, 'w').write('\n'.join(out) + '\n')
        print('  -> fail-fast スタブ %d 本を %s に出力' % (n, a.emit_stubs))


if __name__ == '__main__':
    main()
