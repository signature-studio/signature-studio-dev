"""liftdiff セッション: target のビルド/配置、native+wasm ランナの起動、case 実行、比較。"""
import json, os, subprocess, sys, time, threading
from concurrent.futures import ThreadPoolExecutor

from . import build_wasm, cases, compare, irtool
from .pe import PE, Analyzer
from .runners import Runner, ROOT, env

REPO = build_wasm.REPO


class Session:
    def __init__(self, target_path, build=True, shards=1, timeout=10.0, trace=True, state=None):
        self.t = build_wasm.load_target(target_path)
        self.shards = shards
        self.timeout = timeout
        self.trace = trace
        self.prefix = self.t.get('fn_prefix', 'function_')
        if build:
            build_wasm.build(self.t)
        W = self.t['work']
        self.sigs = json.load(open(W + '/sigs.json'))
        st = json.load(open(W + '/stubs.json'))
        self.stub_info = {n: {'widths': st.get('widths', {}).get(n, [32] * 4)} for n in st['stubs']}
        self.pe = PE(self.t['pe'])
        self.origin = int(str(self.t.get('wasm_origin', '0x0')), 16)
        self.delta = self.pe.base - self.origin
        self.wasm_js = W + '/ld_wasm.cjs'
        self.runner_js = self.t.get('runner_js', 'rt/ld_runner.mjs')
        lifted_p = W + '/lifted.json'
        self.lifted = None
        if os.path.exists(lifted_p):   # clift (x64c 等): wasm 側に定義がある関数集合
            self.lifted = {int(v, 16) for v in json.load(open(lifted_p))['vas']}
        self.lay = self._layout()
        wins = [(self.origin, self.origin + self.pe.size),
                (self.lay['arena'], self.lay['arena'] + self.lay['arena_size']),
                (self.lay['heap'], self.lay['heap'] + self.lay['heap_size'])]
        self.wasm_timeout_ms, wasm_slowdown = compare.wasm_timing_params(self.t)
        self.ctx = compare.Ctx(self.delta, wins, (self.lay['stack_end'], self.lay['stack_base']),
                               wasm_timeout_ms=self.wasm_timeout_ms, wasm_slowdown=wasm_slowdown)
        self.analyzer = Analyzer(self.pe)
        self.state = None
        if state:
            self.state = json.load(open(state))

    def _layout(self):
        r = subprocess.run(['node', os.path.join(ROOT, self.runner_js), self.wasm_js, self.t.get('image') or '-', '%x' % self.origin,
                            '%x' % self.delta, '--layout', '--init=' + ','.join(self.t.get('init_exports', []))], capture_output=True, text=True, env=env())
        if r.returncode:
            raise RuntimeError('layout 取得失敗: ' + r.stderr[-500:])
        j = json.loads(r.stdout.strip().splitlines()[-1])
        return {k: int(v, 16) for k, v in j.items()}

    def init_lines(self, kind):
        L = []
        if kind == 'native':
            L.append('LAYOUT %x %x %x %x %x' % (self.delta, self.lay['arena'], self.lay['arena_size'], self.lay['heap'], self.lay['heap_size']))
        for rva, ln in self.pe.write_ranges():
            L.append('WR %x %x' % (rva, ln))
        for name, (seed, pf) in cases.BLOBS.items():
            data, fix = cases.make_blob(seed, pfrac=pf)
            L.append('BLOB %s %s' % (name, data.hex()))
            L.append('FIX %s %s' % (name, ','.join('%x' % f for f in fix)))
        for name, mk in cases.SPECIAL_BLOBS.items():
            data, fix = mk()
            L.append('BLOB %s %s' % (name, data.hex()))
            L.append('FIX %s %s' % (name, ','.join('%x' % f for f in fix)))
        L.append('SNAPSHOT')
        return L

    def tracelines(self):
        return 'TRACESET ' + ','.join('%x' % v for v in self.closure_vas())

    def closure_vas(self):
        import re
        pat = re.compile('^' + re.escape(self.prefix) + '([0-9a-f]+)$')
        return sorted(int(m.group(1), 16) for k, v in self.sigs.items() if v['defined'] for m in [pat.match(k)] if m)

    def _unused(self):
        vas = []
        return 'TRACESET ' + ','.join('%x' % v for v in vas)

    def make_runners(self):
        from .boot import state_lines_for
        ln, lw = [], []
        if self.state:
            ln, _ = state_lines_for('native', self.state['state'], self)
            lw, _ = state_lines_for('wasm', self.state['state'], self)
        nat = Runner('native', ['setarch', '-R', os.path.join(ROOT, 'work/ld_native'), self.t['pe']],
                     self.init_lines('native') + ln + [self.tracelines()], timeout=self.timeout)
        was = Runner('wasm', ['node', '--stack-size=4000', os.path.join(ROOT, self.runner_js), self.wasm_js, self.t.get('image') or '-',
                              '%x' % self.origin, '%x' % self.delta, '--init=' + ','.join(self.t.get('init_exports', [])),
                              '--timeout-ms=%d' % self.wasm_timeout_ms], self.init_lines('wasm') + lw,
                  timeout=max(self.timeout, self.wasm_timeout_ms / 1000.0 + 5.0))
        return nat, was

    def thunks(self):
        """import thunk (先頭が jmp [rip+IAT]) の VA 集合: lift 側では import 直呼びになるため entry トレース比較から除外"""
        if getattr(self, '_thunks', None) is None:
            import capstone
            th = set()
            for va in self.closure_vas():
                ins = self.analyzer._dis(va - self.pe.base)
                if ins is not None and ins.mnemonic == 'jmp' and ins.operands and ins.operands[0].type == capstone.CS_OP_MEM \
                        and ins.operands[0].mem.base == capstone.x86_const.X86_REG_RIP \
                        and self.pe.in_iat(va - self.pe.base + ins.size + ins.operands[0].mem.disp):
                    th.add(va)
            th |= {int(k[len(self.prefix):], 16) for k, v in self.sigs.items() if v.get('c') and k[len(self.prefix):].isalnum()}
            self._thunks = frozenset(th)
        return self._thunks

    def fn_name(self, va):
        return '%s%x' % (self.prefix, va)

    def run_functions(self, vas, patterns=None, progress=None, with_refine=True):
        """vas: VA 列。戻り: {va: record}"""
        patterns = patterns or cases.PATTERN_NAMES
        shards = max(1, min(self.shards, len(vas)))
        parts = [vas[i::shards] for i in range(shards)]
        results = {}
        lock = threading.Lock()
        done = [0]

        def work(part):
            nat, was = self.make_runners()
            try:
                for va in part:
                    rec = self._run_one(nat, was, va, patterns, with_refine)
                    with lock:
                        results[va] = rec
                        done[0] += 1
                        if progress and done[0] % 50 == 0:
                            progress(done[0], len(vas))
            finally:
                nat.close(); was.close()
        with ThreadPoolExecutor(shards) as ex:
            list(ex.map(work, parts))
        return results

    def _run_one(self, nat, was, va, patterns, with_refine):
        name = self.fn_name(va)
        sig = self.sigs.get(name)
        rec = {'va': hex(va), 'name': name, 'sig': sig}
        if not sig or not sig['defined']:
            rec['verdict'] = 'unexec'; rec['reason'] = 'no_wasm_definition'
            return rec
        if not cases.supported_sig(sig):
            rec['verdict'] = 'unexec'; rec['reason'] = 'unsupported_sig'
            return rec
        if self.lifted is not None and va not in self.lifted:
            rec['verdict'] = 'unexec'; rec['reason'] = 'no_wasm_definition'   # clift: lift 集合外
            return rec
        extra = 'blk=1' if self.t.get('block_trace') else ''
        lines = [cases.case_line(va, name, p, sig, trace=self.trace, extra=extra) for p in patterns]
        ids = ['%x:%s' % (va, p) for p in patterns]
        rn = nat.run_cases(lines, ids)
        keep = [i for i, n in enumerate(rn) if n.get('status') not in ('timeout', 'hang', 'crash')]
        rw = [{'id': ids[i], 'status': 'hang', 'detail': 'skipped (native timeout)', 'calls': [], 'mem': []} for i in range(len(lines))]
        if keep:
            for i, w in zip(keep, was.run_cases([lines[i] for i in keep], [ids[i] for i in keep])):
                rw[i] = w
        rec['cases'] = []
        for p, n, w in zip(patterns, rn, rw):
            try:
                c = compare.compare_case(n, w, self.ctx, self.sigs, self.stub_info, self.thunks())
            except Exception as e:  # 壊れた応答 (パイプ切断等) は比較不能として記録
                c = {'outcome': 'hang', 'native': n.get('status'), 'wasm': w.get('status'), 'compare_error': repr(e)[:120]}
            c['pattern'] = p
            c['native_status'] = n.get('status')
            c['wasm_status'] = w.get('status')
            c['_n'] = n; c['_w'] = w
            rec['cases'].append(c)
        if not any(c['outcome'] in ('equal', 'diff', 'wasm_trap') for c in rec['cases']):
            rec['cases'] += self._fvm_cases(nat, was, va, sig, rec['cases'])
        if with_refine:
            refined = False
            for c in rec['cases']:
                if c['outcome'] in ('diff', 'wasm_trap') and not refined and c.get('wasm_status') != 'timeout' and c['pattern'] in patterns:
                    refined = True
                    i = patterns.index(c['pattern'])
                    l1 = cases.case_line(va, name, c['pattern'], sig, trace=False, stkfill=0x00)
                    l2 = cases.case_line(va, name, c['pattern'], sig, trace=False, stkfill=0xa5)
                    a = was.run_cases([l1, l2], [ids[i]] * 2)
                    if len(a) == 2 and a[0].get('status') == 'ok' and a[1].get('status') == 'ok':
                        same = all(a[0].get(k) == a[1].get(k) for k in ('rax', 'x0', 'mem', 'calls'))
                        c['wasm_uninit_dependent'] = not same
                    elif len(a) == 2 and a[0].get('status') != a[1].get('status'):
                        c['wasm_uninit_dependent'] = True
        return rec

    def _fvm_cases(self, nat, was, va, sig, cases_done):
        """LD-23 (#975): 全 pattern が未実行 (equal/diff/wasm_trap 無し) の関数で、's' の native fault addr から
        this 候補の引数を推定し、その引数だけ VMT 付き疑似オブジェクトにした case を実行する。戻りは追加 case 列。"""
        fault = None
        for c in cases_done:
            if c.get('pattern') == 's' and c.get('fault'):
                fault = c['fault']
                break
        cand = cases.fvm_candidates(fault, cases.kinds_of(sig['params']))
        if not cand:
            return []
        lines = [cases.fvm_line(va, self.fn_name(va), i, sig, trace=self.trace) for i in cand]
        ids = ['%x:fvm%d' % (va, i) for i in cand]
        rn = nat.run_cases(lines, ids)
        keep = [i for i, n in enumerate(rn) if n.get('status') not in ('timeout', 'hang', 'crash')]
        rw = [{'id': ids[i], 'status': 'hang', 'detail': 'skipped (native timeout)', 'calls': [], 'mem': []} for i in range(len(lines))]
        if keep:
            for i, w in zip(keep, was.run_cases([lines[i] for i in keep], [ids[i] for i in keep])):
                rw[i] = w
        out = []
        for arg, n, w in zip(cand, rn, rw):
            try:
                c = compare.compare_case(n, w, self.ctx, self.sigs, self.stub_info, self.thunks())
            except Exception as e:
                c = {'outcome': 'hang', 'native': n.get('status'), 'wasm': w.get('status'), 'compare_error': repr(e)[:120]}
            c['pattern'] = 'fvm'
            c['fvm_arg'] = arg
            c['native_status'] = n.get('status')
            c['wasm_status'] = w.get('status')
            c['_n'] = n; c['_w'] = w
            out.append(c)
        return out

    def static_info(self, va):
        return self.analyzer.analyze(va)
