// PERF-P7 (#165): ブラウザ別 wasm compile / lazy / 上限 / code cache / AudioWorklet 駆動の再測。
//   xvfb-run -a node tools/perf/p7/p7.mjs [--cfgs chrome-headless,chrome-headful,firefox-headless] [--rounds 3] [--full] [--out results/p7.jsonl]
//   node tools/perf/p7/p7.mjs --negative    判定ロジックの確認 (破壊した期待値で FAIL を検出できれば exit 0)
// 判定 (exit 1): (a) Worker/AudioWorklet の出力 hash が参照モデル (makeRef) と不一致 (b) ページの致命エラー/タイムアウト
//   (c) --require-worklet 指定時に AudioWorklet が process() を回せていない。 SKIP/UNMEASURED は PASS に数えず明示行を出す。
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import cp from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { startServer, SIZES } from './server.mjs';
import { makeRef } from '../loader/gen_wasm.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const a = process.argv.slice(2);
const opt = (k, d) => { const i = a.indexOf('--' + k); return i >= 0 ? a[i + 1] : d; };
const NEG = a.includes('--negative'), FULL = a.includes('--full'), REQ_WL = a.includes('--require-worklet');
const ROUNDS = +opt('rounds', 3);
const CFGS = opt('cfgs', 'chrome-headless,chrome-headful,firefox-headless').split(',');
const OUT = path.resolve(HERE, opt('out', 'results/p7.jsonl'));
const TMP = path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'p7');
const TIMEOUT_MS = +opt('timeout', 240000);
fs.mkdirSync(TMP, { recursive: true });

// ---- 参照モデル (worker.js / worklet.js と同じ入力・同じ FNV) ----
const inputAt = (b, i) => { const x = (Math.imul(b * 128 + i, 1103515245) + 12345) & 0xffff; return Math.fround(x / 32768 - 1); };
function refHash(stages, blocks) {
  const step = makeRef(stages); let h = 2166136261; const raw = [];
  for (let b = 0; b < blocks; b++) {
    const inp = new Float32Array(128); for (let i = 0; i < 128; i++) inp[i] = inputAt(b, i);
    const o = step(inp); const u = new Uint32Array(o.buffer, o.byteOffset, 128);
    for (let i = 0; i < 128; i++) h = Math.imul(h ^ u[i], 16777619) >>> 0;
    if (b < 8) raw.push(Array.from(o));
  }
  return { h, raw };
}
const sameRaw = (x, y) => Array.isArray(x) && x.length === y.length && x.every((r, i) => r.length === y[i].length && r.every((v, j) => Math.fround(v) === Math.fround(y[i][j])));

// ---- 判定 (純関数; --negative で破壊入力を与えて FAIL になることを確認) ----
export function judge(results, { corrupt = false } = {}) {
  const checks = [];
  const add = (name, status, detail = '') => checks.push({ name, status, detail });
  for (const [cfg, r] of Object.entries(results)) {
    if (r.__skip) { add(`${cfg}`, 'SKIP', r.__skip); continue; }
    if (r.__error) { add(`${cfg}`, 'FAIL', r.__error); continue; }
    if (!r.done) add(`${cfg}: page completed`, 'FAIL', 'done 通知なし (タイムアウト/クラッシュ)');
    for (const c of ['small', 'mid', 'large']) for (let rep = 0; rep < 3; rep++) {
      const w = r[`worker_${c}_${rep}`]; const name = `${cfg}: worker ${c}#${rep} bit-exact`;
      if (!w) { add(name, 'FAIL', '結果なし'); continue; }
      if (w.error) { add(name, 'FAIL', w.error.slice(0, 120)); continue; }
      const ref = refHash(SIZES[c].stages, w.blocks);
      const expect = corrupt ? (ref.h ^ 1) >>> 0 : ref.h;
      add(name, w.hash === expect && sameRaw(w.raw8, ref.raw) ? 'PASS' : 'FAIL', `hash=${w.hash} ref=${expect}`);
    }
    const wl = r.worklet;
    if (!wl || wl.error || wl.available === false) add(`${cfg}: worklet`, 'UNMEASURED', JSON.stringify(wl || {}).slice(0, 160));
    else if (!wl.result || wl.result.error || !wl.result.calls) add(`${cfg}: worklet process() ran`, REQ_WL ? 'FAIL' : 'UNMEASURED', `ctx=${wl.stateAfterResume} result=${JSON.stringify(wl.result || null).slice(0, 120)}`);
    else {
      const ref = refHash(SIZES.small.stages, wl.result.hashBlocks);
      const expect = corrupt ? (ref.h ^ 1) >>> 0 : ref.h;
      add(`${cfg}: worklet bit-exact (${wl.result.hashBlocks} blocks)`, wl.result.hash === expect && sameRaw(wl.result.raw8, ref.raw) ? 'PASS' : 'FAIL', `hash=${wl.result.hash} ref=${expect}`);
    }
    if (wl && wl.available !== false && !wl.error) {
      const name = `${cfg}: worklet postMessage(Module)`;
      if (wl.modRecv) add(`${name} 受信`, wl.modRecv.isModule ? 'PASS' : 'FAIL', `isModule=${wl.modRecv.isModule}`);
      if (wl.msgerr) add(`${name} messageerror`, 'INFO', 'worklet 側で messageerror (Module 直接 post は不可・判定外の記録)');
      if (!wl.modRecv && !wl.msgerr) add(`${name} 受信`, REQ_WL ? 'FAIL' : 'UNMEASURED', '受信・messageerror とも通知なし (worklet が稼働していない可能性)');
    }
  }
  return checks;
}

// ---- ブラウザ起動 ----
function launch(cfg, url, srvPort) {
  const ud = fs.mkdtempSync(path.join(TMP, `${cfg}-`));
  let cmd, args;
  if (cfg.startsWith('chrome')) {
    cmd = process.env.CHROME || '/usr/bin/google-chrome';
    args = ['--no-sandbox', '--no-first-run', '--no-default-browser-check', `--user-data-dir=${ud}`, '--autoplay-policy=no-user-gesture-required', '--disable-features=Translate,MediaRouter'];
    if (cfg === 'chrome-headless') args.push('--headless=new', '--disable-gpu');
    args.push(url);
  } else {
    cmd = process.env.FIREFOX || '/usr/bin/firefox';
    fs.writeFileSync(path.join(ud, 'user.js'), [
      'user_pref("media.autoplay.default", 0);', 'user_pref("media.autoplay.blocking_policy", 0);', 'user_pref("browser.shell.checkDefaultBrowser", false);',
      'user_pref("datareporting.policy.dataSubmissionEnabled", false);', 'user_pref("browser.tabs.warnOnClose", false);', 'user_pref("app.update.enabled", false);',
      'user_pref("browser.startup.homepage_override.mstone", "ignore");', 'user_pref("startup.homepage_welcome_url", "");',
    ].join('\n'));
    args = ['--headless', '--no-remote', '--profile', ud, url];
  }
  const proc = cp.spawn(cmd, args, { stdio: ['ignore', 'ignore', 'pipe'], env: { ...process.env, MOZ_HEADLESS: cfg.startsWith('firefox') ? '1' : undefined } });
  let err = ''; proc.stderr.on('data', (d) => { err = (err + d).slice(-2000); });
  return { proc, ud, stderr: () => err };
}
const killAndWait = (proc) => new Promise((res) => { if (proc.exitCode !== null) return res(); proc.once('exit', res); proc.kill('SIGTERM'); setTimeout(() => { try { proc.kill('SIGKILL'); } catch {} }, 8000); });
const ls = (dir, root) => { try { return cp.execSync(`find ${JSON.stringify(dir)} -type f -printf '%P %s\\n' 2>/dev/null | sort`, { cwd: root }).toString().trim().split('\n').filter(Boolean); } catch { return []; } };
const versionOf = (cfg) => { try { return cp.execSync(`${cfg.startsWith('chrome') ? (process.env.CHROME || '/usr/bin/google-chrome') : (process.env.FIREFOX || '/usr/bin/firefox')} --version`).toString().trim(); } catch { return 'unknown'; } };

async function runCfg(cfg, srv) {
  if (cfg === 'chrome-headful' && !process.env.DISPLAY) return { __skip: 'DISPLAY 無し (xvfb-run -a で起動すること)' };
  const url = `${srv.url}/p7.html?cfg=${cfg}&rounds=${ROUNDS}${FULL ? '&full=1' : ''}`;
  const la = os.loadavg()[0];
  const b = launch(cfg, url, srv.port);
  const t0 = Date.now();
  while (Date.now() - t0 < TIMEOUT_MS && !srv.results[cfg]?.done && b.proc.exitCode === null) await new Promise((r) => setTimeout(r, 500));
  const wallMs = Date.now() - t0;
  const crashed = b.proc.exitCode !== null && !srv.results[cfg]?.done;
  await new Promise((r) => setTimeout(r, 1500));   // cache flush 待ち
  const snap = cfg.startsWith('chrome') ? ls('Default/Code Cache/wasm', b.ud) : ls('cache2', b.ud).filter((l) => /entries\//.test(l)).slice(-40);
  const snapAll = cfg.startsWith('chrome') ? { wasmCodeCache: snap } : { cache2Entries: snap };
  await killAndWait(b.proc);
  // Chrome: 終了後の最終状態 (flush 後)
  const finalSnap = cfg.startsWith('chrome') ? ls('Default/Code Cache/wasm', b.ud) : ls('cache2', b.ud).filter((l) => /entries\//.test(l)).slice(-40);
  const r = { ...(srv.results[cfg] || {}), loadavg: la, wallMs, version: versionOf(cfg), cacheObserved: snapAll, cacheFinal: finalSnap };
  if (!srv.results[cfg]?.done) r.__error = crashed ? `browser exited: ${b.stderr().slice(-300)}` : `timeout ${TIMEOUT_MS}ms (done 未到達)`;
  fs.rmSync(b.ud, { recursive: true, force: true });
  return r;
}

if (NEG) {
  // ネガティブコントロール: 正しい出力 (参照モデルそのもの) を与えて PASS、1 bit 壊した期待値で FAIL を確認
  const fake = {};
  for (const c of ['small', 'mid', 'large']) for (let rep = 0; rep < 3; rep++) { const blocks = 50; const ref = refHash(SIZES[c].stages, blocks); fake[`worker_${c}_${rep}`] = { blocks, hash: ref.h, raw8: ref.raw }; }
  const good = judge({ x: { done: true, ...fake } });
  const bad = judge({ x: { done: true, ...fake } }, { corrupt: true });
  const missing = judge({ x: { done: false } });
  const goodFails = good.filter((c) => c.status === 'FAIL').length, badFails = bad.filter((c) => c.status === 'FAIL').length, missFails = missing.filter((c) => c.status === 'FAIL').length;
  const okPos = goodFails === 0 && good.filter((c) => c.status === 'PASS').length === 9;
  console.log(`positive (正しい出力): FAIL=${goodFails} PASS=${good.filter((c) => c.status === 'PASS').length} → ${okPos ? 'OK' : 'BAD'}`);
  console.log(`negative (期待 hash を 1 bit 破壊): FAIL=${badFails}/9 → ${badFails === 9 ? 'OK (検出)' : 'BAD (見逃し)'}`);
  console.log(`negative (done 無し/結果欠落): FAIL=${missFails} → ${missFails > 0 ? 'OK (検出)' : 'BAD (見逃し)'}`);
  process.exit(okPos && badFails === 9 && missFails > 0 ? 0 : 1);
}

const srv = await startServer();
const all = {};
for (const cfg of CFGS) {
  console.error(`[p7] ${cfg} ...`);
  all[cfg] = await runCfg(cfg, srv);
  console.error(`[p7] ${cfg} done wall=${all[cfg].wallMs ?? '-'}ms ${all[cfg].__skip ? 'SKIP' : all[cfg].__error ? 'ERROR ' + all[cfg].__error : 'ok'}`);
}
srv.close();
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, Object.entries(all).map(([cfg, r]) => JSON.stringify({ cfg, cpu: os.cpus()[0].model, nproc: os.cpus().length, ...r })).join('\n') + '\n');
const checks = judge(all);
for (const c of checks) console.log(`${c.status} ${c.name} ${c.detail}`);
const n = (s) => checks.filter((c) => c.status === s).length;
console.log(`\nsummary: PASS=${n('PASS')} FAIL=${n('FAIL')} SKIP=${n('SKIP')} UNMEASURED=${n('UNMEASURED')} INFO=${n('INFO')} → ${OUT}`);
process.exit(n('FAIL') ? 1 : 0);
