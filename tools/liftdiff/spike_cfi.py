#!/usr/bin/env python3
"""WIN-7 (#2718) 参照実行 spike: hybrid の到達状態で、native の実機械語 CreateFruityInstance を 1 回呼ぶ。

手順: boot.build_state(mode=hybrid) の unit 初期化の後、同じ native プロセスで
  1. THostInstance (0x38 B) を image 末尾の未使用ページへ POKE (ver=1・"FL Studio"・cmdline 空)
  2. CreateFruityInstance(0xC0, 0xEDE95A, host, &iface) を CASE で 1 回呼ぶ
  3. 戻り値・iface・case の status/detail・呼出し import 列を採る
出力: work/flelift/spike_cfi.json。既存の bootstate (mode=hybrid) の挙動は変えない (post フックは既定 None)。
使い方: python3 spike_cfi.py [targets/flelift.json]   (素材: work-liftdiff・work-m11・fl-win64 / FL_WIN64_DIR)
"""
import json, os, re, struct, subprocess, sys

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


FILE_IMPORTS = ('CreateFileW', 'FindFirstFileW', 'GetFileAttributesW', 'SetFilePointer', 'ReadFile')


def wstr(r, heap_abs, heap_size, addr, n=0x200):
    """native の絶対アドレス (heap 内) の UTF-16 文字列を PEEK で読む。heap 外や読めないときは None。"""
    off = addr - heap_abs
    if not (0 <= off < heap_size - n):
        return None
    r._send('PEEK h:0x%x %d' % (off, n))
    r.p.stdin.flush()
    hx = r._recv(20.0)
    if not hx:
        return None
    return bytes.fromhex(hx).decode('utf-16le', 'replace').split('\x00')[0]


def astr(r, base, addr, n=0x200):
    """イメージ内 (DLL の VA) の ANSI 文字列を PEEK で読む (MessageBoxA の text/caption 用)。"""
    if addr < base or addr - base >= 0x2000000:
        return None
    r._send('PEEK i:0x%x %d' % (addr - base, n))
    r.p.stdin.flush()
    hx = r._recv(20.0)
    if not hx:
        return None
    return bytes.fromhex(hx).split(b'\x00')[0].decode('latin-1')


def model_names():
    """rt/ld_core.h の ld_model_call で明示的に応答を決めている import 名 (それ以外は既定の 0 応答)。"""
    txt = open(os.path.join(HERE, 'rt', 'ld_core.h'), encoding='utf-8').read()
    txt = re.sub(r'    if \(ld_cat_on\(\)\) \{.*?\n    \}\n', '', txt, flags=re.S)   # LD_CATALOG_MO 実験分は既定の応答に含めない
    return set(re.findall(r'ld_streq\(n, "([^"]+)"\)', txt))


def import_table(calls, names):
    rows = []
    for i, c in enumerate(calls):
        rows.append({'i': i, 'n': c.get('n'), 'a': c.get('a', [])[:4], 'r': c.get('r'),
                     'kind': 'model' if c.get('n') in names else 'stub0'})
    return rows


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
    paths = []
    msgs = []
    for c in calls:
        if c.get('n') in FILE_IMPORTS and c.get('a'):
            s = wstr(r, heap_abs, sess.lay['heap_size'], int(c['a'][0], 16))
            paths.append({'n': c['n'], 'a0': c['a'][0], 'path': s})
        if c.get('n', '').endswith('MessageBoxA') and c.get('a'):
            msgs.append({'text': astr(r, base, int(c['a'][1], 16)), 'caption': astr(r, base, int(c['a'][2], 16))})
    return {
        'cfi_rva': '%#x' % cfi_rva, 'cfi_va': '%#x' % (base + cfi_rva),
        'heap_abs': '%#x' % heap_abs, 'heap_size': sess.lay['heap_size'], 'host_heap_off': '%#x' % hoff,
        'poke_ack': pk,
        'status': res.get('status'), 'detail': res.get('detail'),
        'ret': res.get('out0', res.get('ret')), 'iface': '%#x' % iface,
        'calls_n': len(calls), 'calls_over': res.get('calls_over'),
        'calls_head': [c.get('n') for c in calls[:CALL_HEAD]],
        'calls_full': calls, 'raw_keys': sorted(res.keys()),
        'import_table': import_table(calls, model_names()), 'file_paths': paths, 'messageboxes': msgs,
    }


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else 'targets/flelift.json'
    subprocess.run(['gcc', '-O1', '-g', '-Wall', '-Wno-unused-function', '-o', 'work/ld_native',
                    'rt/ld_native.c', 'rt/ld_ms_call.S', '-lm'], check=True)
    sess = Session(target, shards=1, build=False)
    _, res = boot.build_state(sess, None, mode='hybrid', post=run_cfi)
    d = res['detail']
    spike = d.get('post') or {}
    cat = os.environ.get('LD_CATALOG_MO')
    out = os.path.join(sess.t['work'], 'spike_cfi_cat.json' if cat else 'spike_cfi.json')
    for p in spike.get('file_paths') or []:
        print('[spike] file %s a0=%s path=%r' % (p['n'], p['a0'], p['path']))
    for m in spike.get('messageboxes') or []:
        print('[spike] MessageBoxA text=%r caption=%r' % (m['text'], m['caption']))
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
