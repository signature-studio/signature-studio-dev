// seed_worker.ts — CAB-216 (HB-H4'): 仮想 FS (OPFS) に生成 DB を書く e2e Worker。
//   ?phase=seed   : generateDb() → pathreg route → wvfs (OPFS) 書込 → onPageHide で flush → driver が SIGKILL
//                   加えて「flush 点を一切呼ばない」店舗 (noflush store) にも書く (ネガティブコントロール)
//   ?phase=verify : 別プロセスで再 open → 全ファイル sha256 照合 (期待値 = specs から自前再生成 + h4-expected.json)
// 依存は直接 import (index.ts は NodeBackend が node:fs を引込むため使わない)。
import { Wvfs } from '../../../assets/wvfs/wvfs.ts';
import { OpfsBackend } from '../../../assets/wvfs/backend-opfs.ts';
import { createPathRouter, storeDir } from '../../../assets/wvfs/pathlink.ts';
import {
  seedPluginDb, readBackPluginDb, auditReadBack, pluginDbRootWin, registryConsistency, type DbFile, type VregSeed,
} from './virtual_fs_seed.ts';
import { buildSpecs, countSpecs } from './specs.ts';
import { generateDb } from '../src/generate.ts';

const g = self as any;
const STORE_ROOT = 'fl-h4-e2e';
const STORE_NOFLUSH = 'fl-h4-e2e-noflush';
const STORE_PROBE = 'fl-h4-probe';
const enc = new TextEncoder();
const hex = (b: ArrayBuffer): string => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');
const sha256 = async (b: Uint8Array): Promise<string> => hex(await crypto.subtle.digest('SHA-256', new Uint8Array(b).buffer as ArrayBuffer));

/** vreg seed (tools/startup/data/vreg_seed.json) と spec 集合を fetch する。 */
async function loadAll(): Promise<{ seed: VregSeed; specsJson: string; khJson: string | null }> {
  const [seed, specsJson, khRaw] = await Promise.all([
    (await fetch('vreg_seed.json')).json() as Promise<VregSeed>,
    (await fetch('specs.json')).text(),
    fetch('kh.json').then((r) => (r.ok ? r.text() : '')).catch(() => ''),
  ]);
  return { seed, specsJson, khJson: khRaw && !khRaw.startsWith('<!') ? khRaw : null };
}

async function run(cfg: { phase: string }, progress: (s: string) => void) {
  const { seed, specsJson, khJson } = await loadAll();
  const dbRootWin = pluginDbRootWin(seed);
  const router = createPathRouter();
  const specs = buildSpecs(specsJson, khJson);
  const r: Record<string, any> = {
    phase: cfg.phase, dbRootWin, counts: countSpecs(specs, khJson),
    reg: registryConsistency(seed, router),
  };

  if (cfg.phase === 'seed') {
    // ---- (a) 本店: 書込 → onPageHide (flush 点契約) → 読戻し ----
    const w = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_ROOT)));
    const gen = generateDb(specs, { dbPath: dbRootWin });
    progress('write');
    const man = await seedPluginDb({ wvfs: w, router, dbRootWin, gen, sha256 });
    progress('flush');
    w.onPageHide(); // pagehide 契約 (fd は開きっぱなし = close しない)
    const back = await readBackPluginDb({ wvfs: w, manifest: man.files, sha256, dbRootPath: man.root.path, caseVariants: true });
    r.files = man.files.map((f) => ({ rel: f.rel, mount: f.mount, path: f.path, size: f.size, sha256: f.sha256 }));
    r.root = man.root;
    r.journal = w.debugState();
    r.readBack = { mismatches: back.mismatches, caseOk: back.caseOk, extra: back.extra, dbRootEntries: back.dbRootEntries };
    r.audit = auditReadBack(back.files, gen);
    r.dbBytes = man.files.reduce((n, f) => n + f.size, 0);
    await w.close();

    // ---- (b) noflush 店舗: flush 点を一切呼ばない (close もしない = SyncAccessHandle は開きっぱなし) ----
    const wn = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_NOFLUSH)), { flushOnClose: false });
    const genN = generateDb(specs, { dbPath: dbRootWin });
    const manN = await seedPluginDb({ wvfs: wn, router, dbRootWin, gen: genN, sha256 });
    r.noflush = { filesWritten: manN.files.length, flushes: wn.stats.flushes, journal: wn.debugState() };
    // close しない (close/flushOnClose=false でも flushDirty は走る)。driver が SIGKILL するまで放置。
    progress('done');
    return r;
  }

  // ---- probe-noflush: 1 ファイルだけ書き flush 点を呼ばない (陰性制御の最小形。SIGKILL は driver 側) ----
  if (cfg.phase === 'probe-noflush') {
    const wp = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_PROBE)), { flushOnClose: false });
    wp.mkdirpSync('/probe');
    wp.writeFileSync('/probe/unflushed.bin', enc.encode('H4-NOFLUSH-PROBE'));
    r.probeWrite = { bytes: wp.readFileSync('/probe/unflushed.bin').length, flushes: wp.stats.flushes, journal: wp.debugState() };
    // close しない = SyncAccessHandle を開いたまま放置。driver が SIGKILL する。
    return r;
  }

  // ---- verify: 別プロセス (driver が Chrome を再起動) で再 open して照合 ----
  const w = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_ROOT)));
  const gen = generateDb(specs, { dbPath: dbRootWin });
  const man = await seedPluginDb({ wvfs: w, router, dbRootWin, gen, sha256 });
  const back = await readBackPluginDb({ wvfs: w, manifest: man.files, sha256, dbRootPath: man.root.path, caseVariants: true });
  const expect: DbFile[] = await (await fetch('h4-expected.json')).json();
  r.files = man.files.map((f) => ({ rel: f.rel, mount: f.mount, path: f.path, size: f.size, sha256: f.sha256 }));
  r.expectCount = expect.length;
  r.matchedByExpected = expect.filter((f) => man.files.find((m) => m.rel === f.rel)?.sha256 === f.sha256).length;
  r.mismatches = back.mismatches;
  r.caseOk = back.caseOk;
  r.extra = back.extra;
  r.dbRootEntries = back.dbRootEntries;
  r.journal = w.debugState();
  r.tornRecovered = w.stats.tornRecovered;
  r.audit = auditReadBack(back.files, gen);
  await w.close();
  // ---- noflush 店舗の照合 (未 flush 書込は失われているべき) ----
  try {
    const wn = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_NOFLUSH)), { flushOnClose: false });
    const rootPath = router.route(dbRootWin)!.path;
    let entries: string[] = [];
    try {
      entries = wn.readdirSync(rootPath);
    } catch { /* dir 無し = 書込が失われた */ }
    r.noflush = {
      filesInStore: wn.stats.files, dirsInStore: wn.stats.dirs,
      dbRootEntries: entries.length, journal: wn.debugState(),
    };
    await wn.close();
  } catch (e) {
    r.noflush = { error: String(e) };
  }
  // ---- flush 点陰性対照の最小形: 1 ファイルだけ・flush 無しで書いたものが残っているか ----
  try {
    const wp = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_PROBE)), { flushOnClose: false });
    let probe: any = { filesInStore: wp.stats.files };
    try {
      probe.bytes = wp.readFileSync('/probe/unflushed.bin').length;
      probe.text = new TextDecoder().decode(wp.readFileSync('/probe/unflushed.bin'));
    } catch { probe.readable = false; }
    r.probeSurvived = probe;
    await wp.close();
  } catch (e) {
    r.probeSurvived = { error: String(e) };
  }
  progress('done');
  return r;
}

g.onmessage = async (e: MessageEvent) => {
  const t0 = Date.now();
  let stage = 'boot';
  try {
    const res = await run(e.data, (s) => {
      stage = s;
      g.postMessage({ ok: 'progress', stage, elapsedMs: Date.now() - t0 });
    });
    g.postMessage({ ok: true, res });
  } catch (err) {
    g.postMessage({ ok: false, error: String((err as Error).stack ?? err), stage, elapsedMs: Date.now() - t0 });
  }
};
