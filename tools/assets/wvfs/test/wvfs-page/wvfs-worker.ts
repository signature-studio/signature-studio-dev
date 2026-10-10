// wvfs e2e Worker (OPFS SyncAccessHandle 実機)。シナリオは URL ?phase= で切替:
//   seed   : pathreg 経路で書込 (writeFileSync / fd+onPageHide / onYield) → manifest を報告
//   verify : 再起動後の読み照合 → torn tail / superblock 復元 / compaction → 再 reload 照合
// manifest は /app/wvfs-expected.json (driver が seed の報告から生成) を使う。
// 注意: index.ts 経由でなく各モジュールを直接 import する (NodeBackend が node:fs を
// bundle に引き込まないように。browser bundle は backend-opfs のみで組む)。
import { Wvfs } from '../../wvfs.ts';
import { OpfsBackend } from '../../backend-opfs.ts';
import { createPathRouter, storeDir } from '../../pathlink.ts';

const g = self as any;
const hex = (b: ArrayBuffer) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');
const enc = new TextEncoder();

const STORE_ROOT = 'fl-wvfs-e2e';
const WIN = {
  manifest: 'C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml',
  ottFst: 'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Effects\\VST\\Xfer Records, OTT\\OTT.fst',
  ottNfo: 'C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Effects\\VST\\Xfer Records, OTT\\OTT.nfo',
  verifiedIds: 'C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\VerifiedIDs.nfo',
  configXml: 'C:\\Users\\user\\AppData\\Roaming\\Image-Line\\Shared\\config.xml',
  innerBin: 'C:\\Users\\user\\AppData\\Local\\Temp\\Image-Line\\9-2\\zip\\inner.bin',
};

async function sha256(b: Uint8Array): Promise<string> {
  const copy = new Uint8Array(b.length);
  copy.set(b);
  return hex(await crypto.subtle.digest('SHA-256', copy.buffer as ArrayBuffer));
}

const openStores = async (): Promise<{ home: Wvfs; tmp: Wvfs }> => ({
  home: await Wvfs.open(new OpfsBackend(storeDir('home', STORE_ROOT))),
  tmp: await Wvfs.open(new OpfsBackend(storeDir('tmp', STORE_ROOT))),
});

async function run(cfg: { phase: string }, progress: (s: string) => void) {
  const router = createPathRouter();
  const stores = await openStores();
  const r: Record<string, any> = { phase: cfg.phase };

  if (cfg.phase === 'seed') {
    progress('route-check');
    // pathreg 15 fixture 相当の経路分類 (対象外は null を期待)
    const routes = Object.fromEntries(Object.entries(WIN).map(([k, v]) => [k, router.route(v)]));
    r.routes = routes;
    for (const [k, v] of Object.entries(routes) as Array<[string, { mount: string; path: string } | null]>) {
      if (!v) throw new Error(`route failed: ${k}`);
      if (v.mount === 'home' && !v.path.startsWith('/Documents') && !v.path.startsWith('/AppData')) {
        throw new Error(`unexpected home path: ${v.path}`);
      }
    }

    progress('write-direct');
    // (1) writeFileSync 経路 (直列) → 最後に onYield で物理 flush
    const mk = (key: keyof typeof WIN) => {
      const rt = router.route(WIN[key])!;
      stores[rt.mount].mkdirpSync(rt.path.slice(0, rt.path.lastIndexOf('/')));
      return rt;
    };
    const manifestXml = enc.encode(`<?xml version="1.0"?>\n<manifest v="e2e" ts="${Date.now()}"/>`);
    const rManifest = mk('manifest');
    stores[rManifest.mount].writeFileSync(rManifest.path, manifestXml);
    const fst = enc.encode(`;FL Studio plugin state (dummy, CAB-216 が generateDb で置換)\n[plugin]\nname=OTT\nmarker=wvfs-e2e\nts=${Date.now()}\n`);
    const rFst = mk('ottFst');
    stores[rFst.mount].writeFileSync(rFst.path, fst);
    const rNfo = mk('ottNfo');
    stores[rNfo.mount].writeFileSync(rNfo.path, enc.encode('<nfo>dummy</nfo>'));
    const rVids = mk('verifiedIds');
    stores[rVids.mount].writeFileSync(rVids.path, enc.encode('{"ids":["0x2DDFA232"]}'));
    const rCfg = mk('configXml');
    stores[rCfg.mount].writeFileSync(rCfg.path, enc.encode('<config/>'));
    const bin = new Uint8Array(256 * 1024);
    for (let o = 0; o < bin.length; o += 65536) crypto.getRandomValues(bin.subarray(o, Math.min(bin.length, o + 65536)));
    const rBin = mk('innerBin');
    stores[rBin.mount].writeFileSync(rBin.path, bin);
    const p1 = await stores.home.onYield(); // yield 点 flush (dirty 無しでも Promise)
    await p1;

    progress('write-fd');
    // (2) fd 経路: 部分書込 → close 無しで onPageHide (flush 点契約のみで永続させる)
    const fdPath = '/Documents/Image-Line/FL Studio/Projects/e2e/fdwritten.dat';
    stores.home.mkdirpSync(fdPath.slice(0, fdPath.lastIndexOf('/')));
    const fd = stores.home.openSync(fdPath, { create: true });
    stores.home.writeSync(fd, enc.encode('PART1|'));
    stores.home.writeSync(fd, enc.encode('PART2|'), 0, 6);
    stores.home.seekSync(fd, stores.home.fstatSync(fd).size);
    stores.home.writeSync(fd, enc.encode('PART3'));
    const fdSize = stores.home.fstatSync(fd).size;
    stores.home.onPageHide(); // pagehide 契約 (close しない)

    progress('readback');
    const files = [];
    for (const [key, rt] of Object.entries(routes) as Array<[string, { mount: 'home' | 'tmp'; path: string }]>) {
      const data = stores[rt.mount].readFileSync(rt.path);
      files.push({ key, mount: rt.mount, path: rt.path, size: data.length, sha256: await sha256(data) });
    }
    files.push({ key: 'fdwritten', mount: 'home', path: fdPath, size: fdSize, sha256: await sha256(stores.home.readFileSync(fdPath)) });
    // 大小無視 (別ケース) で読める
    const upper = rFst.path.toUpperCase();
    r.caseOk = new TextDecoder().decode(stores.home.readFileSync(upper)).startsWith(';FL Studio');
    r.readdir = {
      dbInstalled: stores.home.readdirSync('/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed').length,
      ottDir: stores.home.readdirSync('/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/Effects/VST/Xfer Records, OTT').sort(),
      tmpRoot: stores.tmp.readdirSync('/9-2/zip').length,
    };
    r.journal = { home: stores.home.debugState(), tmp: stores.tmp.debugState() };
    const est = await navigator.storage?.estimate?.();
    r.storage = { quota: est?.quota ?? null, usage: est?.usage ?? null };
    r.files = files;
  } else {
    progress('expected');
    const exp = await (await fetch('wvfs-expected.json')).json();
    progress('verify-read');
    // 再起動後の読み照合 (全ファイル sha256 一致 + 大小無視)
    r.mismatches = [];
    for (const f of exp.files as Array<{ mount: 'home' | 'tmp'; path: string; size: number; sha256: string }>) {
      const st = stores[f.mount];
      let data: Uint8Array;
      try {
        data = st.readFileSync(f.path);
      } catch (e) {
        r.mismatches.push(`${f.path}: ${e}`);
        continue;
      }
      const got = await sha256(data);
      if (got !== f.sha256 || data.length !== f.size) r.mismatches.push(`${f.path}: size ${data.length}/${f.size} sha ${got.slice(0, 12)}/${f.sha256.slice(0, 12)}`);
    }
    const upper = exp.files.find((f: any) => f.key === 'ottFst')!.path.toUpperCase();
    r.caseOk = new TextDecoder().decode(stores.home.readFileSync(upper)).startsWith(';FL Studio');
    r.tornRecovered = { home: stores.home.stats.tornRecovered, tmp: stores.tmp.stats.tornRecovered };
    r.journal = { home: stores.home.debugState(), tmp: stores.tmp.debugState() };

    if (cfg.phase === 'verify') {
      // ---- torn tail 注入 → 再 open で復元
      progress('torn-tail');
      const before = stores.home.debugState();
      stores.home.journal.debugTornTail(1024);
      await stores.home.close();
      await stores.tmp.close();
      const home2 = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_ROOT)));
      r.torn = {
        detected: home2.journal.stats.tornTails,
        bytesOk: before.liveBytes === home2.debugState().liveBytes,
        manifestOk: new TextDecoder().decode(home2.readFileSync('/Documents/Image-Line/FL Studio/Settings/Manifest.xml')).includes('<manifest'),
      };
      // ---- superblock active slot 破壊 → 他スロットで復旧
      progress('slot-corrupt');
      home2.journal.debugCorruptActiveSlot();
      await home2.close();
      const home3 = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_ROOT)));
      r.slot = {
        journalId: home3.journal.journalId,
        intact: new TextDecoder().decode(home3.readFileSync('/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/Effects/VST/Xfer Records, OTT/OTT.fst')).includes('marker=wvfs-e2e'),
      };
      // ---- compaction: 生存 set のみの新ジャーナルへ
      progress('compact');
      const churn = new Uint8Array(128 * 1024);
      home3.mkdirpSync('/AppData/Local/Image-Line');
      for (let i = 0; i < 40; i++) {
        churn[0] = i;
        home3.writeFileSync('/AppData/Local/Image-Line/churn.bin', churn);
      }
      const beforeC = home3.journal.logicalEnd;
      const c = await home3.compactNow();
      r.compact = { before: c.before, after: c.after, shrunk: c.after < c.before, churnSha: await sha256(home3.readFileSync('/AppData/Local/Image-Line/churn.bin')), churnLen: home3.statSync('/AppData/Local/Image-Line/churn.bin')!.size };
      r.journalAfterCompact = home3.debugState();
      void beforeC;
      await home3.close();
      // ---- compaction 後の durability (この Chrome 起動内で再 open)
      const home4 = await Wvfs.open(new OpfsBackend(storeDir('home', STORE_ROOT)));
      r.postCompact = {
        churnOk: (await sha256(home4.readFileSync('/AppData/Local/Image-Line/churn.bin'))) === r.compact.churnSha,
        fstOk: new TextDecoder().decode(home4.readFileSync('/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/Effects/VST/Xfer Records, OTT/OTT.fst')).includes('marker=wvfs-e2e'),
        dirs: home4.readdirSync('/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/Effects/VST/Xfer Records, OTT').length,
      };
      const est = await navigator.storage?.estimate?.();
      r.storage = { quota: est?.quota ?? null, usage: est?.usage ?? null };
      await home4.close();
      progress('done');
      return r;
    }
  }
  await stores.home.close();
  await stores.tmp.close();
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
