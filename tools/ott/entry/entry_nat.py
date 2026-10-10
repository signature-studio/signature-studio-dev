"""entry_nat.py — VST 入口 scenarios を native 実機械語 (tools/ott/native 参照) で実行し結果 JSON を吐く。

usage:
  entry_nat.py --out RESULT.json [--scen SCEN.json] [--replay ALOG.json] [--cov COV.json]
  (ALOG.json = entry_wasm.mjs の出力 {alog: [[ptr,size]..], ...} — native HeapAlloc を同一アドレスで再生)

各 scenario は fork した子プロセスで実行 (native 側 crash / CRT 未初期化経路を scenario 単位で隔離)。
子は親でロード済みの image・.so を fork で共有し、 scenario 間の状態漏れが無い。

結果 schema (entry_wasm.mjs と共通):
  { ok, calls: [{rax, xmm0, buf(hex)|null, out_f|ptrval|ckpt|out, editor_null?}],
    obj(hex|null), eff_ptr, obj_ptr, alog: [[ptr,size]..], am: [64] }
"""
import sys, os, json, struct, ctypes, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
SO = os.path.join(HERE, '..', 'work', 'entrylift', 'libottnatentry.so')
IMG = 0x180000000
STR, OUT_F, CKPT, CHUNK = 0x30320000, 0x30321000, 0x30322000, 0x30323000
IN_A, OU_A, BUF = 0x30330000, 0x30331000, 0x30340000
STR_FILL = b"0.50\x00" + b"\xcc" * 0x1fc

sys.path.insert(0, os.path.join(HERE, '..', 'native'))
import ottnat as N  # ASLR 固定 re-exec を内蔵

LIB = None


def load_lib():
    global LIB
    lib = ctypes.CDLL(SO)
    for fn in ('ott_call', 'ott_call_cov'):
        getattr(lib, fn).restype = ctypes.c_uint64
        getattr(lib, fn).argtypes = [ctypes.c_uint64] + [ctypes.c_void_p] * 5
    lib.ott_am_addr.restype = ctypes.c_uint64
    lib.ott_am_counts.restype = ctypes.c_void_p
    lib.ott_install_segv()
    assert lib.ott_load(b'/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll') == 0
    # editor ctor surrogate: OTTEditor ctor (0x180120ff0) を `xor eax,eax; ret` (48 31 C0 C3) に差し替え
    # → createEffectInstance が editor=NULL を obj+0x10 に保存。GUI 対象外の両側一致置換 (wasm は override)。
    import ctypes as _c
    patch = (ctypes.c_uint8 * 4).from_address(0x180120ff0)
    assert [patch[i] for i in range(4)] == [0x48, 0x89, 0x5c, 0x24], 'editor ctor 先頭 4 byte が想定と不一致 (DLL 差し替わり?)'
    patch[1] = 0x31; patch[2] = 0xC0; patch[3] = 0xC3  # 48 31 C0 C3 = xor eax,eax; ret
    LIB = lib
    return lib


def call(fn, gpr=(), xmm=(), stk=(), cov=False):
    g = (ctypes.c_uint64 * 4)(*(list(gpr) + [0] * (4 - len(gpr))))
    x = (ctypes.c_uint64 * 4)(*(list(xmm) + [0] * (4 - len(xmm))))
    s = (ctypes.c_uint64 * len(stk))(*stk) if stk else None
    o = (ctypes.c_uint64 * 2)()
    (LIB.ott_call_cov if cov else LIB.ott_call)(fn, g, x, s, len(stk), o)
    return o[0], o[1]


def rd(addr, n): return ctypes.string_at(addr, n)
def wr(addr, b): ctypes.memmove(addr, bytes(b), len(b))


def alog_list():
    n = LIB.ott_alog_count()
    out = []
    for i in range(n):
        p = ctypes.c_uint64(); s = ctypes.c_uint64()
        LIB.ott_alog_get(i, ctypes.byref(p), ctypes.byref(s))
        out.append([p.value, s.value])
    return out


def run_steps(steps, am, cov=False):
    calls, eff, obj = [], 0, 0
    for st in steps:
        c = st['c']
        rec = {}
        if c == 'vstmain':
            eff, x0 = call(IMG + 0x128ba0, (am,), cov=cov)
            rec = {'rax': eff, 'xmm0': x0, 'buf': None}
            if eff:
                e = rd(eff, 0xC0)
                u32 = lambda o: struct.unpack_from('<I', e, o)[0]
                u64 = lambda o: struct.unpack_from('<Q', e, o)[0]
                rva = lambda v: v - IMG if IMG <= v < IMG + 0x308000 else v
                rec['eff'] = dict(magic=u32(0), dispatcher_rva=rva(u64(8)), process_rva=rva(u64(0x10)),
                                  setp_rva=rva(u64(0x18)), getp_rva=rva(u64(0x20)),
                                  num_programs=u32(0x28), num_params=u32(0x2c), num_inputs=u32(0x30),
                                  num_outputs=u32(0x34), flags=u32(0x38), initial_delay=u32(0x50),
                                  io_ratio_bits=u32(0x5c), unique_id=u32(0x70), version=u32(0x74),
                                  procr_rva=rva(u64(0x78)), procd_rva=rva(u64(0x80)), obj_ok=u64(0x60) != 0)
                obj = u64(0x60)
        elif c == 'editorctor':
            r, x0 = call(IMG + 0x120ff0, (obj or 0x30350000, 0), cov=cov)
            rec = {'rax': r, 'xmm0': x0, 'buf': None, 'editor_null': r == 0}
        elif c == 'disp':
            if st.get('buf'): wr(STR, STR_FILL)
            fv = st.get('opt', 0.0)
            r, x0 = call(IMG + 0x126c00, (eff, st['op'], st.get('idx', 0), st.get('val', 0)),
                         (0, 0, N.f32b(fv), 0), (STR if st.get('buf') else 0, 0), cov=cov)
            rec = {'rax': r, 'xmm0': x0,
                   'buf': rd(STR, 0x201).hex() if st.get('buf') else None}
        elif c == 'setp':
            r, x0 = call(IMG + 0x127520, (eff, st['idx']), (0, 0, N.f32b(st['fv']), 0), cov=cov)
            rec = {'rax': r, 'xmm0': x0, 'buf': None}
        elif c == 'getp':
            wr(OUT_F, b'\x00' * 4)
            r, x0 = call(IMG + 0x1271a0, (eff, st['idx'], OUT_F), cov=cov)
            rec = {'rax': r, 'xmm0': x0, 'buf': None,
                   'out_f': struct.unpack('<I', rd(OUT_F, 4))[0]}
        elif c == 'virt':
            if st.get('buf'): wr(STR, STR_FILL)
            gpr = [obj, st.get('rdx', 0), st.get('r8', 0), st.get('r9', 0)]
            xmm = [0, 0, 0, 0]
            for pos, fv in (st.get('xmm') or {}).items():
                xmm[int(pos)] = N.f32b(fv)
            r, x0 = call(IMG + st['rva'], gpr, xmm, cov=cov)
            rec = {'rax': r, 'xmm0': x0,
                   'buf': rd(STR, 0x201).hex() if st.get('buf') else None}
            reads = st.get('reads') or []
            if 'out_f' in reads: rec['out_f'] = struct.unpack('<I', rd(OUT_F, 4))[0]
            if 'ckpt' in reads: rec['ckpt'] = struct.unpack('<Q', rd(CKPT, 8))[0]
        elif c == 'proc':
            n = st['n']
            wr(BUF, (bytes(range(256)) * ((n * 8 * 4) // 256 + 1))[:n * 8 * 4])
            wr(BUF + n * 8, b'\x00' * (n * 8))
            wr(IN_A, struct.pack('<QQ', BUF, BUF + n * 4))
            wr(OU_A, struct.pack('<QQ', BUF + n * 8, BUF + n * 12))
            r, x0 = call(IMG + 0x127450, (eff, IN_A, OU_A, n), cov=cov)
            rec = {'rax': r, 'xmm0': x0, 'buf': None, 'out': rd(BUF + n * 8, n * 8).hex()}
        elif c == 'setchunk':
            r, x0 = call(IMG + 0x126c00, (eff, 24, st.get('is_preset', 0), 16), (), (CHUNK, 0), cov=cov)
            rec = {'rax': r, 'xmm0': x0, 'buf': None}
        elif c == 'getchunk':
            wr(CKPT, b'\x00' * 8)
            r, x0 = call(IMG + 0x126c00, (eff, 23, st.get('is_preset', 0), 0), (), (CKPT, 0), cov=cov)
            rec = {'rax': r, 'xmm0': x0, 'buf': None,
                   'ckpt': struct.unpack('<Q', rd(CKPT, 8))[0]}
        else:
            raise RuntimeError('unknown step ' + c)
        rec['kind'] = c
        if st.get('raxok'): rec['raxok'] = True
        calls.append(rec)
    objdump = rd(obj, 0x328) if obj else b''  # operator new(0x328) の object ちょうど (隣接 heap header を読まない)
    return {'calls': calls, 'obj': objdump.hex() if objdump else None,
            'eff_ptr': eff, 'obj_ptr': obj, 'alog': alog_list(),
            'am': list(struct.unpack('<64I', ctypes.string_at(LIB.ott_am_counts(), 256)))}


def child_main(scen, am, cov, replay, out_fd):
    if replay:
        lo = min(p for p, s in replay) & ~0xfffff
        hi = (max(p + s for p, s in replay) + 0xfffff) & ~0xfffff
        assert LIB.ott_map_range(lo, hi) == 0, 'replay range map failed'
        P = (ctypes.c_uint64 * len(replay))(*[a[0] for a in replay])
        S = (ctypes.c_uint64 * len(replay))(*[a[1] for a in replay])
        LIB.ott_replay_set(P, S, len(replay))
    LIB.ott_map_range(0x30300000, 0x30400000)
    r = run_steps(scen['steps'], am, cov=cov)
    d = {'result': r}
    if cov:
        LIB.ott_cov_buf.restype = ctypes.c_void_p
        LIB.ott_cov_ct_buf.restype = ctypes.c_void_p
        b = ctypes.string_at(LIB.ott_cov_buf(), 0x308000)
        ct = ctypes.string_at(LIB.ott_cov_ct_buf(), 0x308000)
        d['insn'] = [i for i, v in enumerate(b) if v]
        d['calltgt'] = [i for i, v in enumerate(ct) if v]
    data = json.dumps(d).encode()
    mv = memoryview(data)
    while mv:
        n = os.write(out_fd, mv); mv = mv[n:]
    os._exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--scen', default=None)
    ap.add_argument('--replay', default=None, help='{scenario名: [[ptr,size]..]} の alog再生表 (entry_wasm.mjs の収集結果)')
    ap.add_argument('--cov', default=None, help='coverage (insn集合) を --cov にも出力')
    ap.add_argument('--only', action='append', default=[])
    a = ap.parse_args()
    if a.scen:
        scens = json.load(open(a.scen))
    else:
        sys.path.insert(0, HERE)
        import entry_scen
        scens = [{'name': n, 'steps': s} for n, s in entry_scen.scen_list()]
    if a.only:
        scens = [s for s in scens if s['name'] in a.only]
    replay_map = json.load(open(a.replay)) if a.replay else None
    load_lib()
    am = LIB.ott_am_addr()
    results, insn, calltgt, per_scen = {}, set(), set(), {}
    for scen in scens:
        r_fd, w_fd = os.pipe()
        pid = os.fork()
        replay = replay_map.get(scen['name']) if replay_map else None
        if pid == 0:
            os.close(r_fd)
            try:
                child_main(scen, am, bool(a.cov), replay, w_fd)
            except BaseException:
                os._exit(3)
        os.close(w_fd)
        chunks = []
        while True:
            ch = os.read(r_fd, 1 << 20)
            if not ch: break
            chunks.append(ch)
        os.close(r_fd)
        _, st = os.waitpid(pid, 0)
        if st != 0:
            results[scen['name']] = {'ok': False, 'status': st >> 8}
            print('[entry_nat] %-16s CRASH st=%d' % (scen['name'], st >> 8))
            continue
        d = json.loads(b''.join(chunks))
        d['result']['ok'] = True
        results[scen['name']] = d['result']
        if a.cov and 'insn' in d:
            insn.update(d['insn'])
            calltgt.update(d.get('calltgt', []))
            per_scen[scen['name']] = d['insn']
        print('[entry_nat] %-16s ok calls=%d obj=%s' % (scen['name'], len(d['result']['calls']),
                                                        'yes' if d['result'].get('obj') else 'no'))
    out = {'scenarios': results}
    if a.cov:
        out['cov'] = {'insn': sorted(insn), 'calltgt': sorted(calltgt), 'per_scen': per_scen}
    json.dump(out, open(a.out, 'w'))
    print('[entry_nat] wrote %s (%d scenarios)' % (a.out, len(results)))


if __name__ == '__main__':
    main()
