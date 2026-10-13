// crash_restart_unit.ts — G12 クラッシュ保存/Send 失敗/restartfl 再ロードの単体テスト (ST-T10 / #117)。
//   node tools/startup/glue/test/crash_restart_unit.ts   (要 glue.sh のビルド成果 work/glue_mod.mjs)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GlueHost } from '../host/glue_host.ts';
import { CrashReporter, CRASH_DIR_WIN, ERROR_INTERNET_DISCONNECTED, crashStamp } from '../host/crash_restart.ts';

const GLUE_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WORK = path.join(GLUE_DIR, 'work/unit-crash');

let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { console.log(c ? '  ok  ' : '  FAIL', m); if (c) pass++; else fail++; };

async function makeHost(name: string, extra: Record<string, unknown> = {}) {
  const mod = await import(path.join(GLUE_DIR, 'work/glue_mod.mjs'));
  const m = await (mod as any).default();
  const h = new GlueHost(m, { workDir: path.join(WORK, name), ...extra });
  await h.runAll('');
  return { h, m };
}
const shell = (m: any, verb: string, file: string, params: string) => {
  const c = (s: string) => { const n = m.lengthBytesUTF8(s) + 1, p = m._malloc(n); m.stringToUTF8(s, p, n); return p; };
  const a = c(verb), b = c(file), d = c(params);
  try { return m._glue_probe_shell_execute(a, b, d); } finally { m._free(a); m._free(b); m._free(d); }
};

fs.rmSync(WORK, { recursive: true, force: true });

// ---------------------------------------------------------------- 1. ログ保存 (VFS) + ダウンロード提示
console.log('[1] crash log -> <UserData>\\Crash\\ + download');
{
  const { h } = await makeHost('save');
  const dl: { name: string; bytes: Uint8Array }[] = [];
  const t = new Date(Date.UTC(2026, 9, 13, 1, 2, 3, 45));
  const cr = new CrashReporter(h, { now: () => t, download: (name, bytes) => dl.push({ name, bytes }) });
  const log = await cr.report({ message: 'RuntimeError: unreachable', stack: 'at foo\nat bar', kind: 'trap' });
  ok(crashStamp(t) === '20261013-010203-045', `crashStamp = ${crashStamp(t)}`);
  ok(log.winPath === `${CRASH_DIR_WIN('webstudio')}\\20261013-010203-045-0.log`, `winPath = ${log.winPath}`);
  ok(log.mount === 'home' && log.path.startsWith('/Documents/Image-Line/FL Studio/Crash/'), `routed to wvfs home ${log.path}`);
  const back = h.readWin(log.winPath);
  const text = new TextDecoder().decode(back);
  ok(text.includes('message: RuntimeError: unreachable') && text.includes('kind: trap') && text.includes('at bar'), 'log content round-trips via wvfs');
  ok(text.startsWith('FL Studio has encountered an error and needs to restart'), 'log header = FL dialog caption');
  ok(dl.length === 1 && dl[0].name === log.name && Buffer.compare(Buffer.from(dl[0].bytes), Buffer.from(back)) === 0, 'download offered with the persisted bytes');
  ok(cr.downloads === 1, `downloads = ${cr.downloads}`);
  // C 側 FS (FL の fopen 経路) からも同じファイルが見える
  const fsPath = h.shimxPathToPosix(log.winPath);
  ok(Buffer.from(h.mod.FS.readFile(fsPath)).equals(Buffer.from(back)), `visible through Emscripten FS ${fsPath}`);
  // 同一ミリ秒の 2 件目は別名
  const log2 = await cr.saveCrashLog({ message: 'second' });
  ok(log2.name !== log.name && cr.logs.length === 2, `same-ms logs get distinct names (${log2.name})`);
}

// ---------------------------------------------------------------- 2. 永続: 保存後に別インスタンスで読める
console.log('[2] persistence (reopen wvfs)');
{
  const { h } = await makeHost('persist');
  const cr = new CrashReporter(h, { download: () => {} });
  const log = await cr.report({ message: 'persist me' });
  await h.home!.close();
  const { Wvfs, NodeBackend } = await import('../../../assets/wvfs/index.ts');
  const w2 = await Wvfs.open(new NodeBackend(path.join(WORK, 'persist', 'home')));
  const got = new TextDecoder().decode(w2.readFileSync(log.path));
  ok(got.includes('persist me'), 'log survives close/reopen of the backing store');
}

// ---------------------------------------------------------------- 3. Send は失敗表示 (ネットワーク 0)
console.log('[3] Send fails (WinInet offline)');
{
  const { h } = await makeHost('send');
  let fetches = 0;
  const g: any = globalThis, origFetch = g.fetch;
  g.fetch = () => { fetches++; throw new Error('network must not be used'); };
  try {
    const cr = new CrashReporter(h, { download: () => {} });
    const log = await cr.saveCrashLog({ message: 'x' });
    const r = cr.send(log);
    ok(r.ok === false && r.error === ERROR_INTERNET_DISCONNECTED && r.error === 12163, `send -> ok=${r.ok} error=${r.error}`);
    ok(/no internet connection/.test(r.message), 'failure message shown');
    ok(fetches === 0, `fetch calls during send = ${fetches}`);
  } finally { g.fetch = origFetch; }
}

// ---------------------------------------------------------------- 4. /restartfl 検知 → 再ロード
console.log('[4] fldiagnostic /restartfl -> page reload');
{
  let reloads = 0;
  const { h, m } = await makeHost('restart', { onRestart: () => { reloads++; } });
  m._winstubs_init(0);
  ok(h.restartRequested() === false && (await h.checkRestart()) === false && reloads === 0, 'no restart before any ShellExecute');
  // 陰性対照: 他の fldiagnostic 呼出 / 他の exe では再ロードしない
  const r0 = shell(m, 'open', 'C:\\Program Files\\Image-Line\\FL Studio 2026\\fldiagnostic.exe', '/version');
  const r1 = shell(m, 'open', 'C:\\Program Files\\Image-Line\\FL Studio 2026\\ControlCreator.exe', '/restartfl');
  await h.onYield();
  ok(r0 === 2 && r1 === 2 && reloads === 0 && !h.restartRequested(), `non-restart ShellExecute -> ret ${r0}/${r1}, reloads=${reloads}`);
  // 本命
  const before = h.flushes;
  const r2 = shell(m, 'open', 'C:\\Program Files\\Image-Line\\FL Studio 2026\\fldiagnostic.exe', '/restartfl "C:\\Program Files\\Image-Line\\FL Studio 2026\\FL64.exe"');
  ok(r2 === 2 && h.restartRequested(), `/restartfl -> ShellExecute ret ${r2}, flag=${h.restartRequested()}`);
  const cr = new CrashReporter(h, { download: () => {} });
  const log = await cr.saveCrashLog({ message: 'before restart' });
  await h.onYield();          // yield 点で検知 (flush 済みの状態で再ロード)
  ok(reloads === 1, `onRestart called once (${reloads})`);
  ok(h.flushes > before, 'flush happened before reload');
  await h.onYield(); await h.checkRestart();
  ok(reloads === 1, `onRestart not repeated (${reloads})`);
  ok(new TextDecoder().decode(h.readWin(log.winPath)).includes('before restart'), 'crash log still readable after restart request');
}

console.log(`CRASH-RESTART ${fail === 0 ? 'ALL PASS' : 'FAIL'} (pass=${pass} fail=${fail})`);
process.exit(fail === 0 ? 0 : 1);
