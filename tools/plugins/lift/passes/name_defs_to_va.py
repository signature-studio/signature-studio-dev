#!/usr/bin/env python3
"""RetDec が名前 (PE export 名 / PE entry の `entry_point`) で出した define を `function_<VA>` に改名する (#1537)。

  name_defs_to_va.py <final.ll> <PE> <ranges(file|"0xA-0xB,...")> [--report JSON]

RetDec は export 表に載る関数を export 名で、PE entry 関数を `entry_point` で出力し、`function_<VA>` で出さない。
関数本体は欠けていないので改名だけを行う。改名の対象は、名前の VA (export は ImageBase+RVA、entry は ImageBase+AddressOfEntryPoint)
が ranges の開始 VA にあり、かつ final.ll に `define ... @<名前>(` がある組だけ。参照 `@<名前>` も同じ名前に書き換える。
改名先の `function_<VA>` が既に出力中にある場合は衝突として異常終了する (黙って上書きしない)。
"""
import argparse, json, os, re, sys
import pefile

ap = argparse.ArgumentParser()
ap.add_argument('ll')
ap.add_argument('pe')
ap.add_argument('ranges')
ap.add_argument('--report', default='')
a = ap.parse_args()

pe = pefile.PE(a.pe, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
base = pe.OPTIONAL_HEADER.ImageBase
rs = open(a.ranges).read() if os.path.exists(a.ranges) else a.ranges
want = {int(r.split('-')[0], 16) for r in rs.strip().split(',') if r}

named = {}
if pe.OPTIONAL_HEADER.AddressOfEntryPoint:
    named['entry_point'] = base + pe.OPTIONAL_HEADER.AddressOfEntryPoint
exp = getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None)
for e in (exp.symbols if exp is not None else []):
    if e.name:
        named.setdefault(e.name.decode('ascii', 'replace'), base + e.address)

text = open(a.ll).read()
out, log = text, {}
for name, va in sorted(named.items(), key=lambda kv: kv[1]):
    if va not in want:
        continue
    if not re.search(r'^define [^\n]*@%s\(' % re.escape(name), out, re.M):
        continue
    new = 'function_%x' % va
    if re.search(r'@%s\b' % new, out):
        sys.exit('[name_defs_to_va] 改名先 @%s が既に存在する (衝突)' % new)
    out, n = re.subn(r'@%s\b' % re.escape(name), '@' + new, out)
    log[name] = {'va': hex(va), 'new': new, 'refs_renamed': n}

open(a.ll, 'w').write(out)
if a.report:
    json.dump(log, open(a.report, 'w'), indent=1)
print('[name_defs_to_va] renamed %d: %s' % (len(log), ', '.join('%s->%s' % (k, v['new']) for k, v in log.items()) or '-'))
