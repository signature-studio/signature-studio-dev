#!/usr/bin/env python3
"""strip_decls.py <in> <out>: drop Ghidra local-variable declaration lines to shrink committed evidence."""
import re, sys
decl = re.compile(r'^  (undefined\d*|longlong|char|int|uint|byte|ulonglong|code|short|ushort|bool|wchar_t|LPCWSTR|LPWSTR|LCID)\b.*;$')
src = open(sys.argv[1], encoding='utf-8', errors='replace').read().split('\n')
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(l for l in src if not decl.match(l)))
