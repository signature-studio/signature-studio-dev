#!/usr/bin/env python3
"""WIN-7 (#2718) 参照実行 spike: hybrid の到達状態で、native の実機械語 CreateFruityInstance を 1 回呼ぶ。

手順: boot.build_state(mode=hybrid) の unit 初期化の後、同じ native プロセスで
  1. THostInstance (0x38 B) を image 末尾の未使用ページへ POKE (ver=1・"FL Studio"・cmdline 空)
  2. CreateFruityInstance(0xC0, 0xEDE95A, host, &iface) を CASE で 1 回呼ぶ
  3. 戻り値・iface・case の status/detail・呼出し import 列を採る
出力: work/flelift/spike_cfi.json。既存の bootstate (mode=hybrid) の挙動は変えない (post フックは既定 None)。
使い方: python3 spike_cfi.py [targets/flelift.json]   (素材: work-liftdiff・work-m11・fl-win64 / FL_WIN64_DIR)
"""
import json, os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import pefile
from ldlib import boot
from ldlib.session import Session

HOST_SZ = 0x38
CALL_HEAD = 60


def export_rva(pe, name):
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if s.name == name:
            return s.address
    raise RuntimeError('export not found: %r' % name)


TEB_TLS_SLOT = 0x58     # 偽 TEB の TLS 配列ポインタ = ld_heap + LD_TLS_OFF (rt/ld_core.h)
LD_TLS_OFF = 0x1000
HEAP_TAIL = 0x100000     # heap 末尾 1 MiB (エンジンの HeapAlloc は上から使わない前提の退避域)


def host_struct(cmd_abs):
    b = bytearray(HOST_SZ)
    struct.pack_into('<I', b, 0x8, 1)                 # host version = 1 (エンジンが != 1 で不一致扱い)
    b[0x18:0x18 + 10] = b'FL Studio\x00'              # 製品名
    struct.pack_into('<Q', b, 0x30, cmd_abs)          # cmdline バッファ (空)
    return bytes(b)


def poke(r, tok, hexs):
    r._send('POKE %s %s' % (tok, hexs))
    r.p.stdin.flush()
    return r._recv(20.0)


def run_cfi(r, sess):
    base = sess.pe.base
    pe = sess.pe.pe
    cfi_rva = export_rva(pe, b'CreateFruityInstance')
    tls = boot._peek_u64(r, 'h:0x%x' % TEB_TLS_SLOT)
    heap_abs = tls - LD_TLS_OFF
    if tls == 0 or heap_abs & 0xfff:
        raise RuntimeError('heap base が取れない (TEB TLS slot=%#x)' % tls)
    hoff = sess.lay['heap_size'] - HEAP_TAIL
    host_abs = heap_abs + hoff
    cmd_abs = host_abs + 0x100
    iface_abs = host_abs + 0x200
    pk = [poke(r, 'h:0x%x' % hoff, host_struct(cmd_abs).hex()),
          poke(r, 'h:0x%x' % (hoff + 0x100), '00' * 0x100),
          poke(r, 'h:0x%x' % (hoff + 0x200), '00' * 8)]
    line = 'id=cfi fn=%x blob=- args=i:0xc0,i:0xede95a,i:0x%x,i:0x%x keep=1 trace=0' % (
        base + cfi_rva, host_abs, iface_abs)
    res = r.run_cases([line], ['cfi'])[0]
    iface = boot._peek_u64(r, 'h:0x%x' % (hoff + 0x200))
    calls = res.get('calls') or []
    return {
        'cfi_rva': '%#x' % cfi_rva, 'cfi_va': '%#x' % (base + cfi_rva),
        'heap_abs': '%#x' % heap_abs, 'heap_size': sess.lay['heap_size'], 'host_heap_off': '%#x' % hoff,
        'poke_ack': pk,
        'status': res.get('status'), 'detail': res.get('detail'),
        'ret': res.get('out0', res.get('ret')), 'iface': '%#x' % iface,
        'calls_n': len(calls), 'calls_over': res.get('calls_over'),
        'calls_head': [c.get('n') for c in calls[:CALL_HEAD]],
        'calls_full': calls, 'raw_keys': sorted(res.keys()),
    }


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else 'targets/flelift.json'
    subprocess.run(['gcc', '-O1', '-g', '-Wall', '-Wno-unused-function', '-o', 'work/ld_native',
                    'rt/ld_native.c', 'rt/ld_ms_call.S', '-lm'], check=True)
    sess = Session(target, shards=1, build=False)
    _, res = boot.build_state(sess, None, mode='hybrid', post=run_cfi)
    d = res['detail']
    spike = d.get('post') or {}
    out = os.path.join(sess.t['work'], 'spike_cfi.json')
    json.dump({'boot': {k: res[k] for k in ('units_run', 'units_total', 'first_fail', 'mode')},
               'entry_status': d.get('entry_status'), 'entry_detail': d.get('entry_detail'),
               'fails_head': d.get('fails_head'), 'cfi': spike}, open(out, 'w'), indent=1)
    print('[spike] units_run=%s/%s first_fail=%s' % (res['units_run'], res['units_total'], res['first_fail']))
    print('[spike] CreateFruityInstance va=%s status=%s detail=%s' % (spike.get('cfi_va'), spike.get('status'), (spike.get('detail') or '')[:200]))
    print('[spike] ret=%s iface=%s calls=%s (over %s)' % (spike.get('ret'), spike.get('iface'), spike.get('calls_n'), spike.get('calls_over')))
    print('[spike] calls: %s' % ' '.join(str(c) for c in (spike.get('calls_head') or [])))
    print('[spike] -> %s' % out)


if __name__ == '__main__':
    main()
