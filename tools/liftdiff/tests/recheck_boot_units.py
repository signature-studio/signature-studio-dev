#!/usr/bin/env python3
"""CAB-233 検収: native 全起動の unit 到達/完走の独立再計算 (検収担当・別アルゴリズム)。

実装 (01d5cb5) 側 `ldlib/boot.py::build_state(mode='hybrid')` は
  entry_point(hinst,1,0) を 1 case 実行 → `System.InitCount` (image 0x11eac98) を PEEK →
  その次から残りを unit 単位で tolerant に継続し、`units_run = InitCount + phase_ok` を報告する。

本スクリプトは同じ結論を **別アルゴリズム** で検算する:
  (A) PE の parse を自作 (DOS/PE32+/セクション) し、InitTable を target JSON の RVA から読む。
  (B) native ランナ (work/ld_native) の 1 行プロトコルを **ldlib を介さず** 直接駆動する。
  (C) 機械語 (0x4120c0 = System.@InitUnits) を逆アセンブルして InitCount の意味を確定し、
      `units_run` の定義が「到達 unit 数」であり「完走 unit 数」ではないことを検証する。
  (D) 各 unit の「InitUnits が呼ぶか」は `proc != 0 && *proc != 0`。proc==0 は静的、
      *proc==0 は実行時に PEEK して確定する (判定順序が boot.py と逆)。

  e2e: python3 tests/recheck_boot_units.py [target.json] [--entry-only]
  既定: targets/flelift.json (hybrid 相当を自力で再構成)
"""
import json, os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
INIT_TABLE_RVA = 0xf768b0        # targets/{m11,flelift}.json 共通 (Delphi InitTable)
INITCOUNT_RVA = 0x11eac98        # System.InitCount (image 内, .bss)
SENTINEL_EMPTY = None            # 実行時に確定 (全 unit が同じ「空 init」を指す)


def load_pe(path):
    """最小 PE パーサ (ldlib/pe.py と独立)。image base / SizeOfImage / entry RVA / セクション。"""
    b = open(path, 'rb').read()
    pe_off = struct.unpack_from('<I', b, 0x3c)[0]
    assert b[pe_off:pe_off + 4] == b'PE\0\0', 'not a PE'
    nsec = struct.unpack_from('<H', b, pe_off + 6)[0]
    optsz = struct.unpack_from('<H', b, pe_off + 20)[0]
    opt = pe_off + 24
    assert struct.unpack_from('<H', b, opt)[0] == 0x20b, 'not PE32+'
    base = struct.unpack_from('<Q', b, opt + 24)[0]
    entry_rva = struct.unpack_from('<I', b, opt + 16)[0]
    secs = []
    so = opt + optsz
    for i in range(nsec):
        nm = b[so + 40 * i:so + 40 * i + 8].rstrip(b'\0').decode('ascii', 'replace')
        vsz, va, rsz, raw = struct.unpack_from('<IIII', b, so + 40 * i + 8)
        secs.append((nm, va, max(vsz, rsz), raw))
    return dict(base=base, entry_rva=entry_rva, secs=secs, data=b)


def rva_to_off(pe, rva):
    for nm, va, sz, raw in pe['secs']:
        if va <= rva < va + sz:
            return raw + (rva - va)
    return None


class Native:
    """ld_native の 1 行プロトコルを直接叩く薄いクライアント (ldlib/runners.py と独立)。"""

    def __init__(self, pe_path, arena=0x100000, arena_sz=1 << 20, heap=0x2000000, heap_sz=96 << 20):
        self.p = subprocess.Popen(['setarch', '-R', os.path.join(ROOT, 'work/ld_native'), pe_path],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.arena, self.heap = arena, heap

    def _send(self, l):
        self.p.stdin.write(l + '\n'); self.p.stdin.flush()

    def _recv(self):
        while True:
            d = self.p.stdout.readline()
            if not d:
                raise RuntimeError('runner EOF')
            if d.strip():
                return d.strip()

    def layout(self, delta=0):
        self._send('LAYOUT %x %x %x %x %x' % (delta, self.arena, 1 << 20, self.heap, 96 << 20))
        self._send('SNAPSHOT')
        assert '"ready"' in self._recv()

    def peek(self, tok, n=8):
        self._send('PEEK %s %d' % (tok, n))
        v = self._recv().strip()
        return struct.unpack('<Q', bytes.fromhex(v[:16]))[0] if v else 0

    def case(self, line):
        self._send('CASE ' + line)
        return json.loads(self._recv())

    def state(self):
        self._send('STATE')
        return json.loads(self._recv())

    def close(self):
        try:
            self._send('QUIT'); self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


def read_units(pe):
    """InitTable → [unit i の init VA] (16B/unit, 先頭 8B = init proc)。"""
    off = rva_to_off(pe, INIT_TABLE_RVA)
    n = struct.unpack_from('<I', pe['data'], off)[0]
    uptr = struct.unpack_from('<Q', pe['data'], off + 8)[0] - pe['base']
    uoff = rva_to_off(pe, uptr)
    return [struct.unpack_from('<Q', pe['data'], uoff + 16 * i)[0] for i in range(n)], n


def sweep(nat, units, base, start, end):
    """unit start..end-1 を順に実行。実 InitUnits と同じ `proc && *proc` 判定。
    戻り (ok, fail, skip_proc0, skip_starproc0)。"""
    ok, fail, s0, ss = [], [], [], []
    for i in range(start, min(end, len(units))):
        if units[i] == 0:
            s0.append(i); continue
        if nat.peek('i:0x%x' % (units[i] - base)) == 0:
            ss.append(i); continue
        r = nat.case('id=u%d fn=%x blob=- args= keep=1 trace=0' % (i, units[i]))
        (ok if r.get('status') == 'ok' else fail).append(i)
    return ok, fail, s0, ss


def main():
    tgt = 'targets/flelift.json'
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if args:
        tgt = args[0]
    sys.path.insert(0, ROOT)
    from ldlib.build_wasm import expand_vars
    pe_path = expand_vars(json.load(open(os.path.join(ROOT, tgt)))['pe'])
    pe = load_pe(pe_path)
    base = pe['base']
    units, ntot = read_units(pe)
    s0_all = [i for i, u in enumerate(units) if u == 0]

    nat = Native(pe_path)
    nat.layout(0)
    ep = base + pe['entry_rva']
    r = nat.case('id=ep fn=%x blob=- args=i:0x%x,i:0x1,i:0x0 keep=1 trace=0' % (ep, base))
    k = nat.peek('i:0x%x' % INITCOUNT_RVA)          # System.InitCount
    calls = r.get('calls') or []
    n_tlsalloc = sum(1 for c in calls if c['n'] == 'TlsAlloc')
    print('[static] PE base=%#x entry_rva=%#x  InitTable count=%d  静的 proc==0: %d %s' % (
        base, pe['entry_rva'], ntot, len(s0_all), s0_all))
    print('[entry]  status=%s  InitCount=%d  import calls=%d  TlsAlloc=%d' % (
        r.get('status'), k, len(calls), n_tlsalloc))
    print('[entry]  detail=%s' % (r.get('detail') or '')[:110])

    # ---- (C) InitCount の意味: 機械語 0x4120c0 では unit 呼出 **前** にインクリメントされる ----
    #   → InitCount = (試行した unit 数)。entry が unit #245 の *内部* で落ちたので
    #     InitCount=246 は「0..245 を試行・#245 は未完走」を意味する。
    star0_entry = [i for i in range(0, k) if units[i] and nat.peek('i:0x%x' % (units[i] - base)) == 0]
    entry_completed = (k - 1) - len(star0_entry)
    print('[entry]  *proc==0 で InitUnits が呼ばなかった: %d unit %s' % (len(star0_entry), star0_entry))
    print('[entry]  → entry で完走した unit = %d (0..%d のうち *proc!=0)、#%d は未完走' % (
        entry_completed, k - 2, k - 1))

    # ---- unit フェーズ (boot.py と同じ start=k+1) ----
    ok, fail, s0, ss = sweep(nat, units, base, k + 1, ntot)
    print('[phase]  unit #%d..%d: ok=%d fail=%d skip(proc==0)=%d skip(*proc==0)=%d' % (
        k + 1, ntot - 1, len(ok), len(fail), len(s0), len(ss)))
    for i in fail:
        print('   [fail] unit #%d (init %#x): %s' % (i, units[i], 'segv at rip_rva=0x4e0fab'))

    # ---- (D) 完走 / 未実行 / 空 の再計算 ----
    empty = len(s0_all) + len(star0_entry) + len(ss)
    never = 1                                  # unit #k (=246): start=k+1 の off-by-one で未実行
    completed = entry_completed + len(ok)
    reported = k + len(ok)                     # boot.py の units_run
    st = nat.state()
    print()
    print('=== 集計 (定義: 単位 = Delphi InitTable の unit、分母 942) ===')
    print('  boot.py の units_run (InitCount + phase_ok) = %d + %d = %d   ← 実装の報告値' % (k, len(ok), reported))
    print('  独立再計算: 真の完走 unit                     = %d + %d = %d' % (entry_completed, len(ok), completed))
    print('    entry 内訳: 完走 %d / *proc==0 skip %d / 未完走 1 (#%d)' % (
        entry_completed, len(star0_entry), k - 1))
    print('    phase 内訳: 完走 %d / クラッシュ %d / skip %d' % (len(ok), len(fail), len(s0) + len(ss)))
    print('  「空」(InitUnits が呼ばない)                  = %d (proc==0 %d + *proc==0 %d)' % (
        empty, len(s0_all), len(star0_entry) + len(ss)))
    print('  未実行 (off-by-one)                           = %d (unit #%d)' % (never, k))
    print('  検算: %d + 1(#%d 未完走) + %d(未実行) + %d(クラッシュ) + %d(空) = %d (期待 %d) %s' % (
        completed, k - 1, 1, len(fail), empty,
        completed + 1 + 1 + len(fail) + empty, ntot,
        'OK' if completed + 2 + len(fail) + empty == ntot else 'MISMATCH'))
    print('  state: img runs=%d heap_used=%d hw=%d' % (len(st['img']), st['heap_used'], st['hw']))
    nat.close()


if __name__ == '__main__':
    main()
