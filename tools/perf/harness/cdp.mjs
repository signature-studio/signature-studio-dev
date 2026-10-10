// 依存なし Chrome 起動 + CDP クライアント (node 26 組込 WebSocket 使用)。
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const CHROME = process.env.CHROME || '/usr/bin/google-chrome';

export function readProcStatus(pid) {
  try {
    const t = fs.readFileSync(`/proc/${pid}/status`, 'utf8');
    const g = (k) => { const m = t.match(new RegExp(`^${k}:\\s+(\\d+) kB`, 'm')); return m ? +m[1] / 1024 : null; };
    return { rssMB: g('VmRSS'), hwmMB: g('VmHWM'), vmsizeMB: g('VmSize'), vmpeakMB: g('VmPeak') };
  } catch { return null; }
}

// ud (user-data-dir) を持つ chrome 関連プロセスの RSS を種別ごとに集計
export function chromeProcs(ud) {
  const out = [];
  for (const d of fs.readdirSync('/proc')) {
    if (!/^\d+$/.test(d)) continue;
    let cmd; try { cmd = fs.readFileSync(`/proc/${d}/cmdline`, 'utf8').replace(/\0/g, ' '); } catch { continue; }
    if (!cmd.includes('chrome') || !cmd.includes(ud)) continue;
    const type = (cmd.match(/--type=([\w-]+)/) || [0, 'browser'])[1];
    const st = readProcStatus(d);
    if (st) out.push({ pid: +d, type, ...st });
  }
  return out;
}

export async function launchChrome({ jsFlags = '', extraArgs = [], cpus = null, headless = 'new', keepUd = false, ud: udIn = null } = {}) {
  const ud = udIn || fs.mkdtempSync(path.join(process.env.PERF_TMP || '/tmp/opencode/perf', 'ud-'));
  if (udIn) try { fs.rmSync(path.join(ud, 'DevToolsActivePort')); } catch {}
  const args = [
    `--headless=${headless}`, '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    `--user-data-dir=${ud}`, '--remote-debugging-port=0', '--autoplay-policy=no-user-gesture-required',
    '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows',
    '--disable-features=Translate,MediaRouter', ...(jsFlags ? [`--js-flags=${jsFlags}`] : []), ...extraArgs, 'about:blank',
  ];
  const cmd = cpus ? 'taskset' : CHROME;
  const cargs = cpus ? ['-c', cpus, CHROME, ...args] : args;
  const proc = spawn(cmd, cargs, { stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = ''; proc.stderr.on('data', (d) => { stderr += d; });
  const apf = path.join(ud, 'DevToolsActivePort');
  for (let i = 0; i < 400 && !(fs.existsSync(apf) && fs.readFileSync(apf, 'utf8').trim().split('\n').length >= 2); i++) await new Promise((r) => setTimeout(r, 25));
  if (!fs.existsSync(apf)) throw new Error('chrome did not start: ' + stderr.slice(0, 500));
  const [port, wspath] = fs.readFileSync(apf, 'utf8').trim().split('\n');
  const ws = new WebSocket(`ws://127.0.0.1:${port}${wspath}`);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const pending = new Map(); const listeners = [];
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); }
    else for (const l of listeners) l(m);
  };
  const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
    const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const browser = { proc, ud, send, ws, stderr: () => stderr, on: (f) => listeners.push(f) };
  browser.version = await send('Browser.getVersion');
  browser.procs = () => chromeProcs(ud);
  browser.newPage = async (url) => {
    const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    const page = { targetId, sessionId, logs: [] };
    listeners.push((m) => {
      if (m.sessionId !== sessionId) return;
      if (m.method === 'Runtime.consoleAPICalled') page.logs.push(m.params.args.map((a) => a.value ?? a.description).join(' '));
      if (m.method === 'Runtime.exceptionThrown') page.logs.push('EXC ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    });
    page.send = (method, params) => send(method, params, sessionId);
    await page.send('Runtime.enable'); await page.send('Page.enable');
    page.goto = async (u) => { await page.send('Page.navigate', { url: u }); await waitLoad(); };
    const waitLoad = () => new Promise((res) => { const f = (m) => { if (m.sessionId === sessionId && m.method === 'Page.loadEventFired') { listeners.splice(listeners.indexOf(f), 1); res(); } }; listeners.push(f); });
    page.eval = async (expr, { timeout = 600000 } = {}) => {
      const r = await Promise.race([
        page.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }),
        new Promise((_, rej) => setTimeout(() => rej(new Error('eval timeout')), timeout)),
      ]);
      if (r.exceptionDetails) throw new Error('eval exception: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
      return r.result.value;
    };
    if (url) await page.goto(url);
    return page;
  };
  browser.close = async () => {
    try { await send('Browser.close'); } catch {}
    let tm; await new Promise((r) => { proc.once('exit', r); tm = setTimeout(() => { try { proc.kill('SIGKILL'); } catch {} }, 5000); });
    clearTimeout(tm); try { ws.close(); } catch {} try { proc.stderr.destroy(); } catch {}
    if (!keepUd) fs.rmSync(ud, { recursive: true, force: true });
  };
  browser.rendererPid = async (page) => {
    const info = await send('SystemInfo.getProcessInfo');
    return info.processInfo;
  };
  return browser;
}

export const loadavg = () => os.loadavg()[0];
