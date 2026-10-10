// サーバを別プロセスで起動する (同期 read でブロックするスレッドと同一プロセスだとデッドロックするため)。
import { spawn } from 'node:child_process';
import path from 'node:path';

export interface ServerProc {
  url: string;
  stats(): Promise<{ requests: number; bytes: number; byKind: Record<string, number> }>;
  reset(): Promise<void>;
  shape(latencyMs: number, mbps: number): Promise<void>;
  waitReport(timeoutMs: number): Promise<any>;
  close(): Promise<void>;
}

export async function spawnServer(root: string, o: { latencyMs?: number; mbps?: number; appDir?: string; port?: number } = {}): Promise<ServerProc> {
  const script = path.join(path.dirname(new URL(import.meta.url).pathname), 'server.ts');
  const args = [script, root, '--port', String(o.port ?? 0), '--latency', String(o.latencyMs ?? 0), '--mbps', String(o.mbps ?? 0)];
  if (o.appDir) args.push('--appdir', o.appDir);
  const cp = spawn(process.execPath, args, { stdio: ['ignore', 'pipe', 'inherit'] });
  const url = await new Promise<string>((res, rej) => {
    let buf = '';
    cp.stdout!.on('data', (d) => {
      buf += d;
      const m = /at (http:\/\/\S+)/.exec(buf);
      if (m) res(m[1]);
    });
    cp.on('exit', (c) => rej(new Error('server exited ' + c)));
  });
  return {
    url,
    stats: async () => (await fetch(url + '/__stats')).json() as any,
    reset: async () => void (await fetch(url + '/__reset')),
    shape: async (l, m) => void (await fetch(`${url}/__shape?latency=${l}&mbps=${m}`)),
    waitReport: async (ms) => {
      // ロングポール 1 本で受信 (反复 GET ポーリングだと pendingReport を先に消費してしまう競合がある)
      const r = await fetch(`${url}/__report?wait=${Math.min(ms, 110000)}`);
      if (r.status === 200) return r.json();
      throw new Error('report timeout');
    },
    close: async () => void cp.kill(),
  };
}
