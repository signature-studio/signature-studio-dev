// h4_e2e.ts — CAB-216 (HB-H4') 1 コマンド e2e: generateDb() → pathreg → wvfs 仮想 FS 結線の実行検証。
//   node h4/h4_e2e.ts [--keep] [--fresh] [--no-chrome]
//
// 検証する 5 段 (チケット要件):
//   ① 生成       : OTT + Serum 2 (gen/FX) + Massive X + Kilohearts 45 (+ Fresh Air) = 50 entry / 102 ファイル
//   ② 仮想 FS 書込: generateDb() → createPathRouter().route() → /c/home/... (mkdirp + writeFileSync)
//   ③ round-trip : nfo reader 模型 (fle:0x910cd0) + tools/flp 独立パーサで受理・往復 (831/831 は nfo_e2e.sh 側)
//   ④ 再読込一致 : 仮想 FS から読み戻してバイト一致 + 大文字小文字変え読み + 余剰ファイル 0
//   ⑤ kill/reload: 別プロセスで再 open → 全ファイル sha256 一致 (flush 点契約 onYield/onPageHide)
//   ⑥ レジストリ : vreg seed の HKCU Software\Image-Line\Shared\Paths\Shared data と DB root の整合
//   ⑦ Chrome/OPFS: 実ディスクプロファイルで SIGKILL 越えの永続 + noflush 陰性対照
//
// 規約: 書込は tools/hostbridge/nfo のみ。tools/assets・tools/shimx・tools/startup は読取専用。
import fs from 'node:fs';
import path from 'node:path';
import { spawn, type ChildProcess } from 'node:child_process';
import { createHash } from 'node:crypto';
import { build } from '../../../assets/node_modules/esbuild/lib/main.js';
import { spawnServer } from '../../../assets/test/spawn-server.ts';

const HERE = path.dirname(new URL(import.meta.url).pathname); // tools/hostbridge/nfo/h4
const NFO = path.join(HERE, '..'); // tools/hostbridge/nfo
const WORK = path.join(NFO, 'work', 'h4');
const APP = path.join(WORK, 'app-h4');
const KEEP = process.argv.includes('--keep');
const FRESH = process.argv.includes('--fresh');
const NO_CHROME = process.argv.includes('--no-chrome');
const CHROME = process.env.CHROME ?? 'google-chrome';
const STORE_ROOT = 'fl-h4-e2e';

const sha256hex = (b: Uint8Array): string => createHash('sha256').update(b).digest('hex');
const valLoad = (): string => fs.readFileSync('/proc/loadavg', 'utf8').split(' ').slice(0, 3).join(' ');
const t0 = Date.now();
const t0Load = valLoad();

fs.rmSync(WORK, { recursive: true, force: true });
fs.mkdirSync(APP, { recursive: true });

const results: Record<string, any> = {};

// 子プロセス (kill/reload 用): generateDb → pathreg → wvfs 書込 → flush (or no flush) → SIGKILL 自殺。
const KILL_CHILD = `
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { Wvfs, NodeBackend, createPathRouter, storeDir } from '../../../assets/wvfs/index.ts';
import { generateDb } from '../src/generate.ts';
import { seedPluginDb, pluginDbRootWin } from './virtual_fs_seed.ts';
import { buildSpecs } from './specs.ts';

const [storeRoot_, expectedPath, mode] = [process.argv[2], process.argv[3], process.argv[4] ?? 'flush'];
const expected = JSON.parse(fs.readFileSync(expectedPath, 'utf8'));
const seed = JSON.parse(fs.readFileSync('${path.join(WORK, 'app-h4').replace(/\\\\/g, '/')}/vreg_seed.json', 'utf8'));
const specsJson = fs.readFileSync('${path.join(APP).replace(/\\\\/g, '/')}/specs.json', 'utf8');
const khJson = fs.existsSync('${path.join(APP).replace(/\\\\/g, '/')}/kh.json') ? fs.readFileSync('${path.join(APP).replace(/\\\\/g, '/')}/kh.json', 'utf8') : null;
const specs = buildSpecs(specsJson, khJson);
const dbRootWin = pluginDbRootWin(seed);
const w = await Wvfs.open(new NodeBackend(path.join(storeRoot_, storeDir('home', 'fl-h4-e2e'))), { flushOnClose: false });
const gen = generateDb(specs, { dbPath: dbRootWin });
const manifest = await seedPluginDb({ wvfs: w, router: createPathRouter(), dbRootWin, gen, sha256: (b) => createHash('sha256').update(b).digest('hex') });
if (manifest.files.length !== expected.length) { console.error('manifest mismatch'); process.exit(2); }
if (mode === 'flush') {
  w.onPageHide();                 // pagehide 契約 (同期 flush)
  await w.onYield();              // yield 点契約
} else {
  console.log('[noflush] journal に append したが flush 点を呼ばない (物理 flush 無し)');
}
console.log('[child] flushes=' + w.stats.flushes + ' files=' + w.stats.files + ' -> SIGKILL');
process.kill(process.pid, 'SIGKILL');
`;


// ---------------------------------------------------------------- static fixtures (node)
// bundler へ渡すデータは work/h4 にコピーする (tools/startup は読取専用なので直接読むだけ)。
const VREG_SEED = path.join(NFO, '..', '..', 'startup', 'data', 'vreg_seed.json');
const SPECS = path.join(NFO, 'specs', 'wasm_plugins.json');
const KH_INDEX = '/home/ubuntu/work/webstudio/tools/targets/kilohearts/work/macpkg/product_index.json';

const readText = (p: string): string | null => (fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null);
const seedJson = readText(VREG_SEED) ?? '{}';
const specsJson = readText(SPECS) ?? '{"plugins":[]}';
const khJson = readText(KH_INDEX);

// ---- bundle (Chrome phase 用。--no-chrome でも作っておく = 後の手動実行向け) ----
await build({
  entryPoints: { 'seed-page': 'h4/seed_page.ts', 'seed-worker': 'h4/seed_worker.ts' },
  outdir: APP,
  bundle: true,
  format: 'esm',
  target: 'es2022',
  platform: 'browser',
  external: ['node:*'],
  logLevel: 'warning',
  absWorkingDir: NFO,
});
fs.writeFileSync(path.join(APP, 'vreg_seed.json'), seedJson);
fs.writeFileSync(path.join(APP, 'specs.json'), specsJson);
if (khJson) fs.writeFileSync(path.join(APP, 'kh.json'), khJson);
fs.copyFileSync(path.join(HERE, 'index.html'), path.join(APP, 'index.html'));

// ================================================================ typecheck (h4 のみ)
// h4/tsconfig.json で検査。assets (読取専用) 側の既存エラー (wvfs.ts:177 の未使用 local) は
// 除外して合格判定する (tools/assets 自前の tsconfig では noUnusedLocals が無く PASS 済み)。
{
  const { execFileSync } = await import('node:child_process');
  let out = '';
  try {
    out = execFileSync('../../../node_modules/.bin/tsc', ['-p', 'h4/tsconfig.json'], { encoding: 'utf8' });
  } catch (e: any) {
    out = String(e.stdout ?? '');
    const mine = out.split('\n').filter((l) => l.startsWith('h4/'));
    if (mine.length) { console.error(out); throw new Error(`h4 typecheck: ${mine.length} errors`); }
  }
  console.log('== typecheck: h4/ PASS (assets 側の既存警告は読み取り専用のため除外)');
}

// ================================================================ node phase
import { Wvfs, NodeBackend, createPathRouter, storeDir } from '../../../assets/wvfs/index.ts';
import { generateDb, DEFAULT_DB_PATH } from '../src/generate.ts';import {
  seedPluginDb, readBackPluginDb, auditReadBack, pluginDbRootWin, registryConsistency,
  bytesInvariantToDbPath, type DbFile, type VregSeed,
} from './virtual_fs_seed.ts';
import { buildSpecs, countSpecs } from './specs.ts';

const seed = JSON.parse(seedJson) as VregSeed;
const dbRootWin = pluginDbRootWin(seed);
const specs = buildSpecs(specsJson, khJson);
const router = createPathRouter();

let failed = 0;
const must = (cond: boolean, msg: string): void => {
  console.log(cond ? '  ok  ' : '  FAIL', msg);
  if (!cond) failed++;
};

// ---- ① generation ----
console.log('== ① generate synthetic DB (specs + Kilohearts index)');
const gen = generateDb(specs, { dbPath: dbRootWin });
const counts = countSpecs(specs, khJson);
console.log(`   specs=${counts.total} (specs.json ${counts.fromSpecsJson} + KH index ${counts.fromKiloheartsIndex}) -> entries=${gen.entries.length} files=${gen.files.size} bytes=${[...gen.files.values()].reduce((n, b) => n + b.length, 0)}`);
must(gen.entries.length === 50, `entries = 50 (実測 ${gen.entries.length})`);
must(gen.files.size === 102, `files = 102 (実測 ${gen.files.size})`);
const byName = new Map(gen.entries.map((e: { spec: { name: string } }) => [e.spec.name, e]));
for (const nm of ['OTT', 'Serum 2', 'Serum 2 FX', 'Massive X']) must(byName.has(nm), `spec present: ${nm}`);
must(counts.fromKiloheartsIndex === 45, `KH index 由来 = 45 (実測 ${counts.fromKiloheartsIndex})`);
must(byName.has('Phase Plant'), 'Phase Plant (KH 唯一の generator) が generator として入っている');

// dbPath を差し替えても生成バイト列は不変 (`%FLPluginDBPath%` 圧縮の同一性 = 仮想 FS 配置の影響を受けない)
must(bytesInvariantToDbPath(specs, dbRootWin), 'dbPath を差し替えても生成 .nfo/.fst のバイト列は不変');

// ---- ② write to virtual fs via pathreg ----
console.log('== ② write to virtual fs (pathreg route → wvfs /c/home)');
const homeStore = path.join(WORK, 'home');
const storeRoot = storeDir('home', STORE_ROOT);
const home = await Wvfs.open(new NodeBackend(path.join(homeStore, storeRoot)));
const manifest = await seedPluginDb({ wvfs: home, router, dbRootWin, gen, sha256: sha256hex });
must(manifest.files.length === gen.files.size, `manifest ${manifest.files.length} files (route 失敗 0)`);
must(manifest.root.mount === 'home' && manifest.root.path === '/Documents/Image-Line/FL Studio/Presets/Plugin database',
  `db root → ${manifest.root.mount}:${manifest.root.path}`);
must(manifest.files.every((f) => f.mount === 'home'), '全ファイルが home mount に振られた');
console.log(`   journal: ${JSON.stringify(manifest.journal)}`);

// ---- ③ round-trip audit on the bytes read back ----
console.log('== ③ nfo reader + flp parser audit');
const back = await readBackPluginDb({ wvfs: home, manifest: manifest.files, sha256: sha256hex, dbRootPath: manifest.root.path, caseVariants: true });
must(back.mismatches.length === 0, `読み戻し不一致 0 (実測 ${back.mismatches.length})`);
must(back.caseOk === manifest.files.length, `大文字小文字変え読み一致 ${back.caseOk}/${manifest.files.length}`);
must(back.extra.length === 0, `DB ツリー外の余剰ファイル 0 (実測 ${back.extra.length})`);
const audit = auditReadBack(back.files, gen);
must(audit.nfoFiles === 50, `entry .nfo = 50 (実測 ${audit.nfoFiles})`);
must(audit.nfoAccepted === 50, `nfo reader 受理 50/50 (実測 ${audit.nfoAccepted})`);
must(audit.nfoRejected === 0 && audit.nfoDropped === 0, `rejected ${audit.nfoRejected} / dropped ${audit.nfoDropped}`);
must(audit.fstParsed === 50 && audit.fstRoundTrip === 50, `.fst parseFlp ${audit.fstParsed} / writeFlp byte-exact ${audit.fstRoundTrip}`);
must(audit.fstWrapperPath === 50 && audit.fstName203 === 50, `wrapper chunk path ${audit.fstWrapperPath} / event203 name ${audit.fstName203}`);
must(audit.iniSections === 50 && audit.iniSectionsVerbatim === 50, `.Plugins.ini セクション ${audit.iniSections} / verbatim ${audit.iniSectionsVerbatim}`);
must(audit.verifiedKeys === 50, `VerifiedIDs キー 50 (実測 ${audit.verifiedKeys})`);
must(audit.problems.length === 0, `audit problems 0 (${audit.problems.slice(0, 3).join(' | ')})`);
console.log(`   byFamily: ${JSON.stringify(audit.byFamily)}`);
console.log(`   831 相当 (同梱 corpus) は nfo_e2e.sh 側: work/metrics.json`);

// ---- ④ reload in a new Wvfs instance (journal replay) ----
console.log('== ④ reload (same store, new Wvfs)');
const home2 = await Wvfs.open(new NodeBackend(path.join(homeStore, storeRoot)));
const back2 = await readBackPluginDb({ wvfs: home2, manifest: manifest.files, sha256: sha256hex, dbRootPath: manifest.root.path, caseVariants: true });
must(back2.mismatches.length === 0, `reload 後も不一致 0 (実測 ${back2.mismatches.length})`);
must(back2.caseOk === manifest.files.length, `reload 後の大小変え読み ${back2.caseOk}/${manifest.files.length}`);
must(home2.stats.files === manifest.files.length, `reload 後の index files ${home2.stats.files}/${manifest.files.length}`);
const dbRootEntries = home2.readdirSync(manifest.root.path).sort();
must(dbRootEntries.join(',') === 'Installed', `db root 直下 = Installed (実測: ${dbRootEntries.join(',')})`);
const installed = home2.readdirSync(manifest.root.path + '/Installed').sort();
console.log(`   Installed 直下: ${installed.join(',')}`);
must(installed.includes('.Plugins.ini') && installed.includes('VerifiedIDs.nfo'), 'Installed に .Plugins.ini / VerifiedIDs.nfo');
// FL の探索方式 (大文字 .NFO/.FST 定数) で 1 ファイル読む
const ottNfo = manifest.files.find((f) => f.rel === 'Installed/Effects/VST/OTT.nfo')!;
const upperRead = new TextDecoder().decode(home2.readFileSync(ottNfo.path.toUpperCase()));
must(upperRead.startsWith('fileversion=2'), 'OTT.nfo を大文字パスで読めた');
await home2.close();

// ---- ⑥ registry (vreg seed) consistency ----
console.log('== ⑥ registry (vreg seed) consistency');
const reg = registryConsistency(seed, router);
console.log(`   Shared data = ${reg.sharedData}\n   profile (pathreg 既定) = ${reg.userProfile}\n   CSIDL_PERSONAL = ${reg.personal}`);
must(reg.sharedData === 'C:\\Users\\webstudio\\Documents\\Image-Line\\', 'Shared data = webstudio profile');
must(reg.sharedDataRoute?.mount === 'home', `Shared data → ${reg.sharedDataRoute?.mount}:${reg.sharedDataRoute?.path}`);
must(reg.dbRootRoute?.mount === 'home' && reg.dbRootRoute.path === manifest.root.path, `DB root 経路 = home:${reg.dbRootRoute?.path}`);
must(reg.profileMatchesPathreg, 'vreg seed の USERPROFILE/CSIDL_PERSONAL/Shared data が pathreg 既定 profile と一致');
// 重要な負の所見: DEFAULT_DB_PATH (Public Documents) は pathreg の書込対象外 → dbPath を上書きしなければルート失敗する。
must(reg.defaultDbPathRoutable === false, `DEFAULT_DB_PATH (Public) は pathreg 書込対象外 = ${reg.defaultDbPathRoutable} → dbPath 上書きが必須`);
console.log(`   pathreg raw(DB root) = ${reg.dbRootRaw}`);
results.node = { entries: gen.entries.length, files: gen.files.size, bytes: [...gen.files.values()].reduce((n, b) => n + b.length, 0), audit, counts };

// ---- ⑤ kill/reload: 別プロセスで書き、SIGKILL させる ----
console.log('== ⑤ kill/reload (flush 点契約 onYield/onPageHide, SIGKILL 越え)');
const killStore = path.join(WORK, 'kill-home');
const killChild = path.join(HERE, 'kill_seed.mjs');
await fs.promises.writeFile(killChild, KILL_CHILD);
const expected: Array<Omit<DbFile, 'win'>> = manifest.files.map((f) => ({ rel: f.rel, mount: f.mount, path: f.path, size: f.size, sha256: f.sha256 }));
fs.writeFileSync(path.join(WORK, 'kill-expected.json'), JSON.stringify(expected));

async function runKillChild(store: string, mode: string): Promise<{ code: number | null; signal: string | null }> {
  const cp = spawn(process.execPath, [killChild, store, path.join(WORK, 'kill-expected.json'), mode], { stdio: 'inherit' });
  return await new Promise((res) => cp.on('exit', (code, signal) => res({ code, signal })));
}
const killRun = await runKillChild(killStore, 'flush');
must(killRun.signal === 'SIGKILL', `子プロセスが SIGKILL で死んだ (signal=${killRun.signal}, code=${killRun.code})`);
const killHome = await Wvfs.open(new NodeBackend(path.join(killStore, storeRoot)));
const backK = await readBackPluginDb({ wvfs: killHome, manifest: manifest.files, sha256: sha256hex, dbRootPath: manifest.root.path, caseVariants: true });
must(backK.mismatches.length === 0, `kill/reload 後の不一致 0 (実測 ${backK.mismatches.length})`);
must(backK.caseOk === manifest.files.length, `kill/reload 後の大小変え読み ${backK.caseOk}/${manifest.files.length}`);
must(backK.extra.length === 0, `kill/reload 後の余剰 0 (実測 ${backK.extra.length})`);
const auditK = auditReadBack(backK.files, gen);
must(auditK.nfoAccepted === 50 && auditK.fstRoundTrip === 50, `kill/reload 後の audit: nfo ${auditK.nfoAccepted}/50, fst ${auditK.fstRoundTrip}/50`);
console.log(`   kill/reload journal: ${JSON.stringify(killHome.debugState())}`);
await killHome.close();

// ---- ⑤b negative control 1 (結線そのもの): dbPath を既定 (Public Documents) のままにすると書込先が決まらない ----
console.log('== ⑤b 陰性制御 1: dbPath 未上書き (DEFAULT_DB_PATH) では仮想 FS に置けない');
const pubRouter = createPathRouter();
const pubRoute = pubRouter.route(DEFAULT_DB_PATH);
must(pubRoute === null, `DEFAULT_DB_PATH は pathreg 書込対象外 → route() = null (raw=${pubRouter.mapRaw(DEFAULT_DB_PATH)})`);
const pubStore = path.join(WORK, 'pub-home');
const pubW = await Wvfs.open(new NodeBackend(path.join(pubStore, storeRoot)));
let pubThrow = '';
try {
  await seedPluginDb({ wvfs: pubW, router: pubRouter, dbRootWin: DEFAULT_DB_PATH, gen, sha256: sha256hex });
} catch (e) { pubThrow = String(e); }
must(pubThrow.includes('書込対象外'), `既定 dbPath では seedPluginDb が失敗する (${pubThrow.slice(0, 60)}…)`);
must(pubW.stats.files === 0, `仮想 FS にファイル 0 件 (実測 ${pubW.stats.files})`);
await pubW.close();

// ---- ⑤b 陰性制御 2 (flush 点): node バックエンドでは fs.writeSync = OS page cache 書込のため
//      flush を飛ばしても残る (実測)。OPFS (SyncAccessHandle) では buffer に残るため失われる = フェーズ ⑦ で検証。
console.log('== ⑤b 陰性制御 2: flush 点を飛ばした場合の node バックエンド実測');
const nfStore = path.join(WORK, 'noflush-home');
const nfRun = await runKillChild(nfStore, 'noflush');
void nfRun;
const nfHome = await Wvfs.open(new NodeBackend(path.join(nfStore, storeRoot)));
const backN = await readBackPluginDb({ wvfs: nfHome, manifest: manifest.files, sha256: sha256hex, dbRootPath: manifest.root.path, caseVariants: false });
const nfLive = backN.files.size;
console.log(`   実測: node バックエンドでは flush 無しでも ${nfLive}/${manifest.files.length} ファイルが読める (fs.writeSync は OS page cache へ書くため)`);
console.log('   → node 側では陰性制御として成立しない。OPFS 実機 (フェーズ ⑦) で確認する。');
results.negative = { publicDbPathRoutable: pubRoute === null, filesPlaced: pubW.stats.files, noflushNodeReadable: nfLive };
await nfHome.close();
fs.rmSync(killChild, { force: true });

// ================================================================ Chrome / OPFS phase
if (!NO_CHROME) {
  console.log('== ⑦ Chrome (OPFS) real-disk profile: seed → SIGKILL → verify');
  const profDir = path.join(WORK, 'chrome-profiles');
  fs.mkdirSync(profDir, { recursive: true });
  if (FRESH) {
    for (const d of fs.readdirSync(profDir)) if (d.startsWith('h4-e2e-')) fs.rmSync(path.join(profDir, d), { recursive: true, force: true });
  }
  const existing = fs.readdirSync(profDir).filter((d) => d.startsWith('h4-e2e-'));
  const udd = existing.length ? path.join(profDir, existing[0]) : fs.mkdtempSync(path.join(profDir, 'h4-e2e-'));
  console.log(`   chrome profile (real disk): ${udd}`);

  // seed フェーズの期待値を Chrome 起動前に APP へ置く (driver 側が node で計算したもの)
  fs.writeFileSync(path.join(APP, 'h4-expected.json'), JSON.stringify(expected));
  // seed 側: flushes が 0 のまま browser を kill するため、worker は flush を onPageHide() のみで行う。
  // noflush store は flushOnClose:false かつ close しない (SyncAccessHandle 開きっぱなし)。

  const srv = await spawnServer(APP, { appDir: APP });

  async function runChrome(phase: string): Promise<any> {
    const url = `${srv.url}/app/index.html?phase=${phase}`;
    const dcd = fs.mkdtempSync(path.join(profDir, 'diskcache-'));
    const cp: ChildProcess = spawn(
      CHROME,
      [
        '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        `--user-data-dir=${udd}`, `--disk-cache-dir=${dcd}`, '--remote-debugging-port=0', url,
      ],
      { stdio: ['ignore', 'ignore', 'ignore'], detached: true }
    );
    try {
      return await srv.waitReport(240000);
    } finally {
      try { process.kill(-cp.pid!, 'SIGKILL'); } catch {}
      if (!KEEP) fs.rmSync(dcd, { recursive: true, force: true });
      await new Promise((r) => setTimeout(r, 400));
    }
  }

  // 1) flush 点陰性対照 (最小形): 1 ファイルだけ書いて flush せず SIGKILL → 別プロセスで読む
  const chProbe = await runChrome('probe-noflush');
  if (!chProbe.ok) {
    console.log('  FAIL probe-noflush:', chProbe.error, 'stage=', chProbe.stage);
    failed++;
  } else {
    console.log(`   probe (no flush): write=${JSON.stringify(chProbe.res.probeWrite)}`);
    const chProbeV = await runChrome('verify');
    if (chProbeV.ok) {
      console.log(`   probe 結果 (SIGKILL 後): ${JSON.stringify(chProbeV.res.probeSurvived)}`);
      results.negative.probeWrite = chProbe.res.probeWrite;
      results.negative.probeSurvived = chProbeV.res.probeSurvived;
    }
  }

  const chSeed = await runChrome('seed');  if (!chSeed.ok) {
    console.log('  FAIL seed:', chSeed.error, 'stage=', chSeed.stage);
    failed++;
  } else {
    must(chSeed.res.mismatches === undefined || chSeed.res.mismatches.length === 0, 'seed: pathreg route → wvfs write');
    const chAudit = chSeed.res.audit;
    must(chSeed.res.files.length === 102, `seed: 102 files routed (実측 ${chSeed.res.files.length})`);
    must(chAudit.nfoAccepted === 50, `seed 内 audit: nfo 受理 50 (実測 ${chAudit.nfoAccepted})`);
    must(chAudit.fstRoundTrip === 50, `seed 内 audit: fst 往復 50 (実測 ${chAudit.fstRoundTrip})`);
    must(chSeed.res.readBack.mismatches.length === 0, `seed 内読み戻し不一致 0 (実測 ${chSeed.res.readBack.mismatches.length})`);
    must(chSeed.res.readBack.caseOk === 102, `seed 内 大小変え読み 102 (実測 ${chSeed.res.readBack.caseOk})`);
    must(chSeed.res.readBack.extra.length === 0, `seed 内 余剰 0 (実測 ${chSeed.res.readBack.extra.length})`);
    must(chSeed.res.reg.sharedDataRoute?.mount === 'home', 'vreg seed Shared data → home mount');
    console.log(`   chrome journal: ${JSON.stringify(chSeed.res.journal)}`);

    const chVerify = await runChrome('verify');
    if (!chVerify.ok) {
      console.log('  FAIL verify:', chVerify.error, 'stage=', chVerify.stage);
      failed++;
    } else {
      must(chVerify.res.mismatches.length === 0, `SIGKILL 後の再読込不一致 0 (実測 ${chVerify.res.mismatches.length})`);
      must(chVerify.res.caseOk === 102, `SIGKILL 後の大小変え読み 102 (実測 ${chVerify.res.caseOk})`);
      must(chVerify.res.matchedByExpected === 102 && chVerify.res.expectCount === 102, `node 側 manifest と OPFS 実物の sha256 一致 ${chVerify.res.matchedByExpected}/${chVerify.res.expectCount}`);
      must(chVerify.res.audit.nfoAccepted === 50 && chVerify.res.audit.fstRoundTrip === 50, 'SIGKILL 後の audit も 50/50');
      must(chVerify.res.tornRecovered === 0, `torn tail 0 (実測 ${chVerify.res.tornRecovered})`);
      // flush 点陰性対照: 所定の期待は「失われる」だが、Chrome 154 の SyncAccessHandle 実測では
      // write() だけでも SIGKILL を跨いだ (下記 results.negative.probeSurvived に実測を記録)。
      // 期待と違う結果になった場合は FAIL にせず実測値を報告する (規則 40・41: 主張は実測に合わせる)。
      const nfSurvived = chVerify.res.noflush?.filesInStore ?? -1;
      console.log(`   noflush 店舗 (flush 点無し・102 ファイル書込): SIGKILL 後の files=${nfSurvived} (期待 0、実測を報告)`);
      results.negative.noflushOpfs = chVerify.res.noflush;
      results.negative.expectedNoflushLoss = 0;
      console.log(`   chrome verify: journal=${JSON.stringify(chVerify.res.journal)} noflush=${JSON.stringify(chVerify.res.noflush)}`);
      results.chrome = { seed: chSeed.res, verify: chVerify.res };
    }
  }
  await srv.close();
}

// ================================================================ summary
const metricsPath = path.join(WORK, 'metrics.json');
fs.writeFileSync(metricsPath, JSON.stringify({ generatedAt: new Date().toISOString(), loadStart: t0Load, loadEnd: valLoad(), elapsedMs: Date.now() - t0, results }, null, 1));
// 独立再計算 (規則 37): 実装とは別アルゴリズム (ジャーナル自前デコード + 自前パーサ) で主要数値を再計算
{
  const { execFileSync } = await import('node:child_process');
  const out = execFileSync(process.execPath, [path.join(NFO, 'h4_recount.mjs'), metricsPath], { encoding: 'utf8' });
  const cut = out.indexOf('\n}');
  const rec = JSON.parse(cut >= 0 ? out.slice(0, cut + 2) : out);
  results.recount = rec;
  fs.writeFileSync(metricsPath, JSON.stringify({ generatedAt: new Date().toISOString(), loadStart: t0Load, loadEnd: valLoad(), elapsedMs: Date.now() - t0, results }, null, 1));
  console.log(`== 独立再計算 (h4_recount.mjs, 別アルゴリズム)`);
  console.log(`   journal: ${JSON.stringify(rec.journal)}`);
  console.log(`   dbFiles=${rec.dbFiles} nfo=${rec.nfo} fst=${rec.fst} vregKeys=${rec.verifiedIdKeys} ini=${rec.iniSections}`);
  console.log(`   nfoAccepted=${rec.nfoAccepted} dropped=${rec.nfoDropped} rejectedFiles=${rec.nfoRejectedFiles} | fstParsed=${rec.fstParsed} events=${JSON.stringify(rec.fstEvents)}`);
  console.log(`   family=${JSON.stringify(rec.familyCount)} problems=${rec.problems.length}`);
  must(rec.dbFiles === 102 && rec.nfoAccepted === 50 && rec.fstParsed === 50 && rec.iniSections === 50 && rec.verifiedIdKeys === 50 && rec.problems.length === 0,
    '独立再計算も 102/50/50/50/50 で problems 0');
  must(rec.vreg.routesHome === true, `独立再計算でも vreg seed の DB root → /c/home (${rec.vreg.rawRoute})`);
}

console.log(`\nload average: start ${t0Load} / end ${valLoad()} | elapsed ${((Date.now() - t0) / 1000).toFixed(1)} s`);
console.log(`   metrics: ${metricsPath}`);
console.log(failed ? `FAILED: ${failed}` : 'ALL PASS');
process.exit(failed ? 1 : 0);



