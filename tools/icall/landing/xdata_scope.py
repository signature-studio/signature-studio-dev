#!/usr/bin/env python3
"""xdata_scope.py — x64 PE の .pdata/.xdata (UNWIND_INFO) 全数走査 + Delphi scope table 抽出器 (CAB-227).

  python3 xdata_scope.py --pe <PE> [--json out.json] [--handler-json out.json] [--label NAME]

背景 (実測):
- FLEngine_x64.dll (Delphi, ImageBase 0x400000) は .xdata section を持たず、UNWIND_INFO は
  UnwindData RVA が指す独立領域 (.text の後ろ) に置かれる (pefile でそのまま読める)。
- 言語別 handler は全 10,837 関数が同一関数 (FLEngine: VA 0x4112c0, System の Delphi frame handler)。
- handler data は **UNWIND_INFO に inline** (MSVC のような .rdata への RVA ではない)。
  DISPATCHER_CONTEXT.HandlerData = inline 領域の絶対 VA で handler に渡る
  (handler の逆汇编で確認: `mov rcx,[r9+0x38]` 後 `mov ebx,[rcx]` = Count)。

Delphi scope table (inline, 16B/entry; handler 0x4112c0 の逆汇编より):
  dword N (entry 数)
  N × { dword beginRVA; dword endRVA; dword kind; dword jumpTarget; }
  kind の意味 (handler 逆汇编 + 実バイト照合):
    0  = handler で処理しない (スキップ)。try 範囲の記録のみ
    1  = try..finally: landing pad = endRVA (finally コードは try 範囲の直後に置かれる)
    2  = try..except (catch-all): landing pad = jumpTarget
    >2 = try..except on E:... : kind = 例外 descriptor list の RVA。
         descriptor list = { dword n; n × { dword classVMT_RVA(0 = catch-all); dword handlerRVA; } }
         landing pad = ImageBase + handlerRVA (一致した class の entry)
UNW_FLAG_CHAININFO 関数 (fragment) は parent RUNTIME_FUNCTION へ辿り、親の scope table をそのまま使う
(D11: RetDec は断片を単独関数として扱い frame が壊れる — 本抽出器では親に attach して報告)。

出力 JSON:
  functions[] : {va, begin, end, unwind_rva, version, flags, prolog, codes, frame_reg, frame_off,
                 handler_va, chained_parent, scopes[]}
  scopes[]    : {idx, kind, kind_name, begin, end, landing (RVA), landing_va, descs[] (kind>2 のみ),
                 descs: [{class_va, class_rva, handler_rva, landing_va}]}
"""
import argparse
import json
import struct
import collections

import pefile

# UNWIND_INFO byte0 の flags は >>3 後の値で扱う (1=EHANDLER 2=UHANDLER 4=CHAININFO)
UNW_FLAG_EHANDLER = 1
UNW_FLAG_UHANDLER = 2
UNW_FLAG_CHAININFO = 4
KIND_NAME = {0: 'none', 1: 'finally', 2: 'except_catchall'}


class UwInfo:
    __slots__ = ('rva', 'version', 'flags', 'prolog', 'n_codes', 'frame_reg', 'frame_off',
                 'codes', 'handler_rva', 'data_rva', 'chain_rva')


def parse_unwind_info(pe, rva):
    """UNWIND_INFO 1 件をパース (RVA 単位)。破損/範囲外は None。"""
    hdr = pe.get_data(rva, 4)
    if not hdr or len(hdr) < 4:
        return None
    u = UwInfo()
    u.rva = rva
    u.version = hdr[0] & 7
    u.flags = hdr[0] >> 3          # 1=EH 2=UH 4=CHAININFO
    u.prolog = hdr[1]
    u.n_codes = hdr[2]
    u.frame_reg = hdr[3] & 0x0F
    u.frame_off = (hdr[3] >> 4) * 8
    codes_raw = pe.get_data(rva + 4, u.n_codes * 2)
    if codes_raw is None or len(codes_raw) < u.n_codes * 2:
        return None
    u.codes = [struct.unpack_from('<H', codes_raw, i * 2)[0] for i in range(u.n_codes)]
    tail = (rva + 4 + u.n_codes * 2 + 3) & ~3
    if u.flags & UNW_FLAG_CHAININFO:
        d = pe.get_data(tail, 4)
        u.chain_rva = struct.unpack('<I', d)[0] if d and len(d) == 4 else None
        u.handler_rva = None
        u.data_rva = None
    elif u.flags & (UNW_FLAG_EHANDLER | UNW_FLAG_UHANDLER):
        # EHANDLER=0x08 / UHANDLER=0x10 は生バイト値。ここは >>3 後 (1/2) のビット和
        d = pe.get_data(tail, 8)
        if not d or len(d) < 8:
            u.handler_rva = u.data_rva = None
        else:
            u.handler_rva, u.data_rva = struct.unpack('<II', d)
            # Delphi: data_rva は使われない (scope table は tail+8 に inline)。
            # MSVC 形式の場合 data_rva は scope table への RVA。両方を受理するため
            # 呼び出し側で handler_data_pos (= tail+8) と data_rva の両方を返す。
        u.chain_rva = None
    else:
        u.handler_rva = u.data_rva = u.chain_rva = None
    return u


def u32_at(pe, rva):
    d = pe.get_data(rva, 4)
    return struct.unpack('<I', d)[0] if d and len(d) == 4 else None


def parse_scope_table(pe, table_rva, max_entries=4096):
    """inline Delphi scope table をパース → [entry dict]。破損時は None。"""
    n = u32_at(pe, table_rva)
    if n is None or not (0 <= n <= max_entries):
        return None
    out = []
    for i in range(n):
        raw = pe.get_data(table_rva + 4 + i * 16, 16)
        if not raw or len(raw) < 16:
            return None
        bg, en, kind, jt = struct.unpack('<IIII', raw)
        e = {'idx': i, 'begin': bg, 'end': en, 'kind': kind, 'jump_target': jt, 'descs': None}
        if kind > 2:
            descs = parse_desc_list(pe, kind)
            e['descs'] = descs   # 破損時 None のまま残す
        out.append(e)
    return out


def parse_desc_list(pe, list_rva, max_entries=256):
    """kind>2 の例外 descriptor list: { dword n; n × { dword classRVA; dword handlerRVA; } }"""
    n = u32_at(pe, list_rva)
    if n is None or not (0 <= n <= max_entries):
        return None
    out = []
    for i in range(n):
        raw = pe.get_data(list_rva + 4 + i * 8, 8)
        if not raw or len(raw) < 8:
            return None
        cls, hnd = struct.unpack('<II', raw)
        out.append({'class_rva': cls, 'handler_rva': hnd})
    return out


def extract(path, label=''):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pdata = b''
    pdata_rva = 0
    for s in pe.sections:
        if s.Name.rstrip(b'\0').decode('latin1') == '.pdata':
            pdata = s.get_data()
            pdata_rva = s.VirtualAddress
    entries = []
    n = len(pdata) // 12
    for i in range(n):
        b, e, u = struct.unpack_from('<III', pdata, i * 12)
        entries.append((b, e, u))
    # RVA → function VA の索引 (chain 解決用)
    by_begin = {b: (b, e, u) for b, e, u in entries if b}

    funcs = []
    handlers = collections.Counter()
    chain_of = {}
    for b, e, u in entries:
        if u == 0:
            continue
        ua = u & ~1
        uw = parse_unwind_info(pe, ua)
        if uw is None:
            continue
        f = {'begin_rva': b, 'end_rva': e, 'unwind_rva': ua,
             'version': uw.version, 'flags': uw.flags, 'prolog': uw.prolog,
             'n_codes': uw.n_codes, 'frame_reg': uw.frame_reg, 'frame_off': uw.frame_off,
             'codes': uw.codes, 'handler_rva': uw.handler_rva, 'chained_parent': None,
             'scopes': None, 'handler_data_inline': None}
        if uw.flags & UNW_FLAG_CHAININFO and uw.chain_rva in by_begin:
            pb, pe_, pu = by_begin[uw.chain_rva]
            f['chained_parent'] = pu & ~1
            chain_of[ua] = pu & ~1
        if uw.handler_rva is not None:
            handlers[base + uw.handler_rva] += 1
            # handler data は handler RVA の直後 (tail+4) から inline。Delphi はここに
            # scope table を直接置く (先頭 dword = entry 数)。MSVC なら scope table RVA。
            tail_rva = (ua + 4 + uw.n_codes * 2 + 3) & ~3
            f['handler_data_inline'] = tail_rva + 4
            st = parse_scope_table(pe, tail_rva + 4)
            f['scopes'] = st
        funcs.append(f)
    return {'label': label, 'pe': path, 'image_base': base, 'n_pdata': n,
            'functions': funcs, 'handlers': {('0x%x' % k): v for k, v in handlers.most_common()},
            'chain_of': {'0x%x' % k: v for k, v in chain_of.items()}}


def summarize(res):
    nf = len(res['functions'])
    with_handler = sum(1 for f in res['functions'] if f['handler_rva'] is not None)
    chain = sum(1 for f in res['functions'] if f['chained_parent'] is not None)
    scopes = []
    n_scope_fn = 0
    kind_c = collections.Counter()
    bad = collections.Counter()
    for f in res['functions']:
        st = f['scopes']
        if not st:
            continue
        if st:
            n_scope_fn += 1
        for e in st:
            kind_c['kind_%d' % (0 if e['kind'] == 0 else 1 if e['kind'] == 1 else 2 if e['kind'] == 2 else 3)] += 1
            # 妥当性: begin/end が親関数内, landing が実行域
            if not (f['begin_rva'] <= e['begin'] <= e['end'] <= f['end_rva']):
                bad['range_out_of_fn'] += 1
            if e['kind'] == 1 and not (f['begin_rva'] <= e['end'] < f['end_rva']):
                bad['finally_pad_out'] += 1
            if e['kind'] == 2 and not (f['begin_rva'] <= e['jump_target'] < f['end_rva']):
                bad['except_pad_out'] += 1
            if e['kind'] > 2 and e['descs'] is None:
                bad['desc_unparsable'] += 1
            scopes.append((f, e))
    return {'n_functions': nf, 'n_with_handler': with_handler, 'n_chaininfo': chain,
            'n_with_scopes': n_scope_fn, 'n_scope_entries': len(scopes),
            'kind_counts': dict(kind_c), 'invalid': dict(bad)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--json')
    ap.add_argument('--handler-json')
    ap.add_argument('--label', default='')
    a = ap.parse_args()
    res = extract(a.pe, a.label)
    s = summarize(res)
    print('== %s: pdata=%d funcs(parsed)=%d handler=%d chaininfo=%d scope_fn=%d scope_entries=%d' % (
        a.label or a.pe, res['n_pdata'], s['n_functions'], s['n_with_handler'], s['n_chaininfo'],
        s['n_with_scopes'], s['n_scope_entries']))
    print('   kind counts:', s['kind_counts'], ' invalid:', s['invalid'])
    print('   handlers:', res['handlers'])
    if a.json:
        slim = {k: v for k, v in res.items()}
        slim['summary'] = s
        json.dump(slim, open(a.json, 'w'), indent=0)
        print('   ->', a.json)
    if a.handler_json:
        # scope table のみをフラットに (landing pad 検証用)
        flat = []
        for f in res['functions']:
            if not f['scopes']:
                continue
            for e in f['scopes']:
                r = {'fn_rva': f['begin_rva'], 'fn_end_rva': f['end_rva'], 'fn_unwind': f['unwind_rva']}
                r.update({k: e[k] for k in ('idx', 'begin', 'end', 'kind', 'jump_target')})
                if e['descs']:
                    r['descs'] = e['descs']
                flat.append(r)
        json.dump(flat, open(a.handler_json, 'w'), indent=0)
        print('   ->', a.handler_json, '(scope entries: %d)' % len(flat))


if __name__ == '__main__':
    main()
