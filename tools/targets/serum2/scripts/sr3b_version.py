#!/usr/bin/env python3
# SR-3b: 版同定の定数・文字列突合 (zlib z_errmsg / muParser エラー文 / zstd・PFFFT・libsfz の版文字列)。
# 判定は「NUL 終端で単独に現れる文字列」のみ (部分一致による偽陽性を除く)。
# usage: sr3b_version.py <Serum2_win64.vst3> <upstream_dir>
#   upstream_dir: muParserError_<tag>.cpp (版ごと, 404 の空ファイルは無視) と zutil.c を置く。
import re, sys, os, glob

V = open(sys.argv[1], 'rb').read()
UP = sys.argv[2]

def standalone(b: bytes) -> int:
    return len(re.findall(rb'(?<=\x00)' + re.escape(b) + rb'\x00', V))

def literals(path):
    src = open(path, 'rb').read().decode('latin-1')
    out = set()
    for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"', src):
        s = m.group(1).replace('\\"', '"')
        if len(s) >= 6 and '\\' not in s and '%' not in s:
            out.add(s)
    return out

print("## zlib z_errmsg (upstream zutil.c の 9 項目, NUL 終端単独の出現数)")
zut = open(os.path.join(UP, 'zutil.c'), 'rb').read().decode('latin-1')
zerr = re.findall(r'\(z_const char \*\)"([^"]+)"', zut)
zerr = [z for z in zerr if z]
hit = 0
for z in zerr:
    n = standalone(z.encode('latin-1'))
    hit += n > 0
    print(f"  {n}  {z}")
print(f"  => {hit}/{len(zerr)} 項目が単独出現")

print("## muParser (upstream muParserError_<tag>.cpp の文字列リテラル, 単独 NUL 終端一致)")
for fn in sorted(glob.glob(os.path.join(UP, 'muParserError_*.cpp'))):
    if os.path.getsize(fn) < 1000:
        print(f"  {os.path.basename(fn)}: 取得不可 (404)")
        continue
    L = literals(fn)
    H = {s for s in L if standalone(s.encode('latin-1')) > 0}
    print(f"  {os.path.basename(fn)}: リテラル {len(L)} / 単独一致 {len(H)} / 不一致 {len(L) - len(H)}")

print("## 判別用 muParser 文言 (NUL 終端単独の出現数)")
for s in ['The "$TOK$" operator must be preceeded by a closing bracket.',
          'The "$TOK$" operator must be preceded by a closing bracket.',
          'Function result is a string.', 'Expression too long.', 'Identifier too long.',
          'Strings must only be used as function arguments!']:
    print(f"  {standalone(s.encode('latin-1'))}  {s}")

print("## zstd・PFFFT・libsfz の版文字列 (0 件 = 版文字列なし)")
for s in ['ZSTD_versionString', 'ZSTD_getErrorString', 'Corrupted block', 'Destination buffer is too small',
          'Input and output buffers overlap', 'libSFZ', 'PFFFT', 'pffft']:
    print(f"  {len(re.findall(re.escape(s.encode()), V))}  {s}")
ver = sorted(set(m.decode() for m in re.findall(rb'(?<=\x00)(1\.[0-9]{1,2}\.[0-9]{1,2})\x00', V)))
print("## 単独の 1.x.y 文字列 (NUL 終端): " + (", ".join(ver) if ver else "0 件"))
