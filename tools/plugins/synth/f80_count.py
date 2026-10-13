#!/usr/bin/env python3
"""final.ll の `x86_fp80` を含む define 数。 ファイルが無ければ -1。 usage: f80_count.py <final.ll>"""
import re, sys
try:
    s = open(sys.argv[1]).read()
except OSError:
    print(-1)
    sys.exit()
print(sum(1 for f in re.split(r'\n(?=define )', s) if f.startswith('define') and 'x86_fp80' in f))
