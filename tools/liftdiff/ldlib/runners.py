"""サブプロセス・ランナ (native / wasm) の駆動: 1 行プロトコルの送受信、ハング/クラッシュ時の再起動。"""
import json, os, select, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
NODE_PATH = os.path.expanduser('~/.local/share/pnpm/bin')


def env():
    e = os.environ.copy()
    e['PATH'] = NODE_PATH + ':' + os.path.expanduser('~/.bun/bin') + ':' + e.get('PATH', '')
    return e


class Runner:
    def __init__(self, name, cmd, init_lines, timeout=10.0, wrap=None):
        self.name, self.cmd, self.init_lines, self.timeout = name, cmd, init_lines, timeout
        self.p = None
        self.buf = b''
        self.restarts = 0
        self.start()

    def start(self):
        cmd = self.cmd
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env(), bufsize=0)
        self.buf = b''
        for l in self.init_lines:
            self._send(l)
            if l == 'SNAPSHOT':
                r = self._recv(120.0)
                if r is None or '"ready"' not in r:
                    raise RuntimeError('%s: SNAPSHOT 応答なし (%r)' % (self.name, r))

    def _send(self, line):
        self.p.stdin.write((line + '\n').encode())

    def _recv(self, timeout):
        fd = self.p.stdout.fileno()
        end = time.time() + timeout
        while True:
            i = self.buf.find(b'\n')
            if i >= 0:
                line, self.buf = self.buf[:i], self.buf[i + 1:]
                return line.decode(errors='replace')
            rem = end - time.time()
            if rem <= 0:
                return None
            r, _, _ = select.select([fd], [], [], min(rem, 1.0))
            if r:
                d = os.read(fd, 1 << 20)
                if not d:
                    return None
                self.buf += d
            elif self.p.poll() is not None:
                return None

    def kill(self):
        try:
            self.p.kill()
            self.p.wait(timeout=5)
        except Exception:
            pass

    def run_cases(self, lines, ids, chunk=1):
        """lines: CASE 行 (プレフィクスなし)。戻り値: [結果 dict]。ハング/クラッシュは status=hang/crash の dict。
        badjson (壊れた応答行) はランナ再起動 + 1 回だけ再試行する (モジュール状態の汚染に対応、CAB-232)。
        各結果には `_elapsed_s` (直前の応答または送信からその応答までの秒。応答が来なかった case は recv 待ちの秒) を付ける。
        chunk=1 (既定): 1 件ずつ送って応答を待つ。chunk>1 だと先行 case の応答がパイプに溜まり、待ち時間が隣の case に計上される。"""
        out = []
        i = 0
        while i < len(lines):
            part = lines[i:i + chunk]
            try:
                for l in part:
                    self._send('CASE ' + l)
                self.p.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            got = []
            bad = []
            waited = None
            t_prev = time.monotonic()
            for k, l in enumerate(part):
                r = self._recv(self.timeout)
                now = time.monotonic()
                if r is None:
                    waited = round(now - t_prev, 3)
                    break
                el = round(now - t_prev, 3)
                t_prev = now
                try:
                    d = json.loads(r)
                except Exception:
                    d = {'id': ids[i + k], 'status': 'badjson', 'detail': r[:200], 'calls': [], 'mem': []}
                    bad.append(k)
                d['_elapsed_s'] = el
                got.append(d)
            out.extend(got)
            if len(got) < len(part):
                # 失敗した case = got の次. ハング/クラッシュとして記録して再起動
                k = len(got)
                alive = self.p.poll() is None
                out.append({'id': ids[i + k], 'status': 'hang' if alive else 'crash', 'detail': 'runner %s' % self.name,
                            'calls': [], 'mem': [], '_elapsed_s': waited})
                self.kill()
                self.restarts += 1
                self.start()
                i += k + 1
                continue
            if bad:
                # 応答行が壊れていた case: ランナを再起動して 1 回だけ再試行する
                self.kill()
                self.restarts += 1
                self.start()
                base = len(out) - len(part)
                for k in bad:
                    try:
                        self._send('CASE ' + part[k])
                        self.p.stdin.flush()
                        t0 = time.monotonic()
                        r = self._recv(self.timeout)
                        if r is not None:
                            out[base + k] = json.loads(r)
                            out[base + k]['_elapsed_s'] = round(time.monotonic() - t0, 3)
                    except Exception:
                        pass
                i += len(part)
                continue
            i += len(part)
        return out

    def close(self):
        try:
            self._send('QUIT')
            self.p.stdin.flush()
            self.p.wait(timeout=5)
        except Exception:
            self.kill()
