#!/usr/bin/env python3
# rss_cap.py — 子プロセス (とその子孫) の VmRSS 合計を 1 秒ごとに監視し、上限超過時にその PID だけを kill する。
#
#   python3 rss_cap.py --cap-mb 13800 --log rss.log -- <command...>
#
# 終了コードは子の終了コード。上限超過で kill した場合は 143 (SIGTERM 相当) で終わり、
# ピーク RSS (MB) と経過秒を標準エラーに出す。kill は子とその子孫 (例: emcc が起動した clang) の
# PID 指定のみ (pkill・kill 0 は使わない)。
import argparse
import os
import signal
import subprocess
import sys
import time


def children_map():
    kids = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            with open(f'/proc/{name}/stat') as f:
                ppid = int(f.read().rsplit(')', 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            continue
        kids.setdefault(ppid, []).append(int(name))
    return kids


def tree_pids(root):
    kids = children_map()
    out, stack = [], [root]
    while stack:
        p = stack.pop()
        out.append(p)
        stack.extend(kids.get(p, []))
    return out


def alive(pid):
    try:
        with open(f'/proc/{pid}/stat') as f:
            return f.read().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False


def kill_pids(pids):
    # 親から順に SIGTERM、猶予 5 秒で残ったものだけ SIGKILL。PID 指定のみ (pkill・kill 0 は使わない)。
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline and any(alive(p) for p in pids):
        time.sleep(0.2)
    for pid in pids:
        if alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def rss_kb(pid):
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def mem_available_mb():
    with open('/proc/meminfo') as f:
        for line in f:
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) // 1024
    return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cap-mb', type=int, required=True)
    ap.add_argument('--log', required=True)
    ap.add_argument('--interval', type=float, default=1.0)
    ap.add_argument('cmd', nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = args.cmd[1:] if args.cmd[:1] == ['--'] else args.cmd
    if not cmd:
        ap.error('command required')

    log = open(args.log, 'w')

    def emit(msg):
        line = f'{time.strftime("%H:%M:%S")} {msg}'
        print(line, file=log, flush=True)

    t0 = time.time()
    proc = subprocess.Popen(cmd)
    emit(f'start pid={proc.pid} cap={args.cap_mb}MB memavail={mem_available_mb()}MB cmd={" ".join(cmd)}')
    peak_kb, killed = 0, False
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        total = sum(rss_kb(p) for p in tree_pids(proc.pid))
        if total > peak_kb:
            peak_kb = total
        emit(f'rss={total // 1024}MB peak={peak_kb // 1024}MB memavail={mem_available_mb()}MB')
        if total // 1024 > args.cap_mb:
            pids = tree_pids(proc.pid)
            emit(f'CAP EXCEEDED rss={total // 1024}MB > {args.cap_mb}MB: kill pids={pids}')
            killed = True
            kill_pids(pids)
            proc.wait()
            rc = 143
            break
        time.sleep(args.interval)
    elapsed = int(time.time() - t0)
    status = 'KILLED(cap)' if killed else ('OK' if rc == 0 else f'FAILED rc={rc}')
    emit(f'end {status} rc={rc} elapsed={elapsed}s peak={peak_kb // 1024}MB')
    print(f'[rss_cap] {status} rc={rc} elapsed={elapsed}s peak_rss={peak_kb // 1024}MB log={args.log}', file=sys.stderr)
    sys.exit(rc)


if __name__ == '__main__':
    main()
