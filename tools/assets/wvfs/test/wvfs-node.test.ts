// wvfs 単体テスト (node fs バックエンド)。
//   node wvfs/test/wvfs-node.test.ts
// Chrome (OPFS) 実機 e2e は wvfs/test/wvfs-e2e.ts。node 側で論理層 (ジャーナル再生 / torn 復元 /
// compaction / flush 契約 / pathreg 経路) を全て検証し、Chrome 側は OPFS 固有の永続のみを見る。
import fs from 'node:fs';
import path from 'node:path';
import { Wvfs, WvfsError, NodeBackend, createPathRouter, storeDir } from '../index.ts';
import type { SyncFile } from '../../vfs/types.ts';

const ROOT = path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'work', 'wvfs-test');
fs.rmSync(ROOT, { recursive: true, force: true });
fs.mkdirSync(ROOT, { recursive: true });

let pass = 0;
let failed = 0;
const ok = (cond: boolean, msg: string) => {
  console.log(cond ? '  ok  ' : '  FAIL', msg);
  if (cond) pass++;
  else failed++;
};
const throwsCode = async (fn: () => unknown, code: string): Promise<boolean> => {
  try {
    await fn();
    return false;
  } catch (e) {
    return e instanceof WvfsError && e.code === code;
  }
};
const dir = (name: string) => path.join(ROOT, name);

// ------------------------------------------------ 1. 基本操作 (case-insensitive / unicode / 空ファイル)
{
  const w = await Wvfs.open(new NodeBackend(dir('basic')));
  w.mkdirpSync('/Documents/Image-Line/FL Studio/Settings');
  w.writeFileSync('/Documents/Image-Line/FL Studio/Settings/Manifest.xml', new TextEncoder().encode('<manifest v="2"/>'));
  w.mkdirpSync('/日本語/設定');
  w.writeFileSync('/日本語/設定/ファイル.txt', new TextEncoder().encode('こんにちは'));
  w.writeFileSync('/empty.bin', new Uint8Array(0));
  ok(new TextDecoder().decode(w.readFileSync('/documents/image-line/fl studio/settings/MANIFEST.XML')) === '<manifest v="2"/>', 'case-insensitive read (Win32 相当)');
  ok(new TextDecoder().decode(w.readFileSync('/日本語/設定/ファイル.TXT')) === 'こんにちは', 'unicode path + case-insensitive');
  ok(w.readFileSync('/empty.bin').length === 0 && w.statSync('/empty.bin')?.size === 0, 'empty file');
  ok(w.statSync('/Documents')?.type === 'dir' && w.readdirSync('/Documents/Image-Line/FL Studio').join(',') === 'Settings', 'stat/readdir');
  ok(w.readdirSync('/Documents/Image-Line/FL Studio/Settings')[0] === 'Manifest.xml', 'readdir keeps original case');
  ok(await throwsCode(() => w.readFileSync('/nope.txt'), 'ENOENT'), 'ENOENT');
  ok(await throwsCode(() => w.writeFileSync('/no-such-dir/x.txt', new Uint8Array(1)), 'ENOENT'), 'write into missing dir = ENOENT (POSIX)');
  ok(await throwsCode(() => w.mkdirSync('/Documents'), 'EEXIST'), 'mkdir EEXIST');
  ok(await throwsCode(() => w.readFileSync('/Documents'), 'EISDIR'), 'read dir = EISDIR');
  w.writeFileSync('/Documents/Image-Line/FL Studio/Settings/Manifest.xml', new TextEncoder().encode('<manifest v="3"/>'));
  ok(new TextDecoder().decode(w.readFileSync('/Documents/Image-Line/FL Studio/Settings/Manifest.xml')) === '<manifest v="3"/>', 'overwrite');
  w.truncateSync('/Documents/Image-Line/FL Studio/Settings/Manifest.xml', 9);
  ok(w.readFileSync('/Documents/Image-Line/FL Studio/Settings/Manifest.xml').length === 9, 'truncate');
  await w.close();
  const w2 = await Wvfs.open(new NodeBackend(dir('basic')));
  ok(new TextDecoder().decode(w2.readFileSync('/Documents/Image-Line/FL Studio/Settings/Manifest.xml')).length === 9, 'reload after truncate');
  ok(w2.readdirSync('/日本語').join(',') === '設定', 'unicode tree after reload');
  await w2.close();
  console.log('[1] basic CRUD');
}

// ------------------------------------------------ 2. fd (部分書込 / append / unlink-while-open)
{
  const w = await Wvfs.open(new NodeBackend(dir('fd')));
  w.mkdirpSync('/log');
  const fd = w.openSync('/log/app.log', { create: true });
  w.writeSync(fd, new TextEncoder().encode('HEAD'));
  w.writeSync(fd, new TextEncoder().encode('|TAIL'), 0, 5);
  w.seekSync(fd, 0);
  const buf = new Uint8Array(9);
  w.readSync(fd, buf);
  ok(new TextDecoder().decode(buf) === 'HEAD|TAIL', 'fd partial writes + read-your-writes');
  // append mode
  const fda = w.openSync('/log/app.log', { append: true });
  w.writeSync(fda, new TextEncoder().encode('+APP'));
  w.closeSync(fda);
  ok(new TextDecoder().decode(w.readFileSync('/log/app.log')) === 'HEAD|TAIL+APP', 'O_APPEND');
  // unlink 中の fd は書き戻さない (POSIX 風)
  const fdu = w.openSync('/log/tmp.dat', { create: true });
  w.writeSync(fdu, new Uint8Array([1, 2, 3]));
  w.unlinkSync('/log/tmp.dat');
  w.writeSync(fdu, new Uint8Array([9]));
  w.closeSync(fdu);
  ok(!w.existsSync('/log/tmp.dat'), 'unlink while open: fd close does not resurrect');
  // sync (fsync) で途中 flush
  const fds = w.openSync('/log/synced.dat', { create: true });
  w.writeSync(fds, new Uint8Array([4, 5, 6]));
  w.fsyncSync(fds);
  w.writeSync(fds, new Uint8Array([7]));
  w.closeSync(fds);
  ok(w.readFileSync('/log/synced.dat').length === 4, 'fsync mid-write + close');
  // rename / rmdir
  w.mkdirSync('/d1');
  w.writeFileSync('/d1/a.txt', new TextEncoder().encode('A'));
  w.renameSync('/d1/a.txt', '/d1/b.txt');
  ok(w.existsSync('/d1/b.txt') && !w.existsSync('/d1/a.txt'), 'rename file');
  w.renameSync('/d1', '/d2');
  ok(w.existsSync('/d2/b.txt') && !w.existsSync('/d1'), 'rename dir with content');
  w.mkdirSync('/d2/empty-dir');
  w.writeFileSync('/d2/.keep', new Uint8Array(0));
  w.renameSync('/d2', '/d3');
  ok(w.existsSync('/d3/empty-dir') && w.existsSync('/d3/.keep'), 'rename dir keeps empty explicit dir + dotfile');
  ok(await throwsCode(() => w.rmdirSync('/d3'), 'ENOTEMPTY'), 'rmdir non-empty = ENOTEMPTY');
  w.unlinkSync('/d3/b.txt');
  w.unlinkSync('/d3/.keep');
  w.rmdirSync('/d3/empty-dir');
  w.rmdirSync('/d3');
  ok(!w.existsSync('/d3'), 'rmdir after emptying');
  await w.close();
  const w2 = await Wvfs.open(new NodeBackend(dir('fd')));
  ok(new TextDecoder().decode(w2.readFileSync('/log/app.log')) === 'HEAD|TAIL+APP', 'fd content after reload');
  ok(!w2.existsSync('/log/tmp.dat') && w2.readdirSync('/log').join(',') === 'app.log,synced.dat', 'deleted file stays deleted');
  await w2.close();
  console.log('[2] fd semantics');
}

// ------------------------------------------------ 3. flush 契約 (onYield / onPageHide / sync)
{
  const w = await Wvfs.open(new NodeBackend(dir('flush')));
  ok(w.onYield() === undefined, 'onYield on clean store = undefined (no-op)');
  w.mkdirpSync('/x');
  w.writeFileSync('/x/a.txt', new Uint8Array([1]));
  ok(w.journal.stats.seq > 0 && w.stats.flushes === 0, 'write appends journal without physical flush (flush 点契約)');
  w.onPageHide();
  ok(w.stats.flushes === 1, 'onPageHide flushes');
  ok(w.onYield() === undefined, 'onYield after flush = undefined');
  await w.close();
  const w2 = await Wvfs.open(new NodeBackend(dir('flush')));
  ok(w2.readFileSync('/x/a.txt').length === 1, 'content survives via onPageHide');
  await w2.close();
  console.log('[3] flush contract (onYield/onPageHide/sync)');
}

// ------------------------------------------------ 4. torn tail 復元 (末尾書きかけ + 中間レコード破損)
{
  const be = new NodeBackend(dir('torn'));
  const w = await Wvfs.open(be);
  w.writeFileSync('/keep.txt', new TextEncoder().encode('KEEP ME'));
  const v1 = w.readFileSync('/keep.txt');
  await w.close();
  // (1) 末尾 torn: クラッシュで「書きかけたが commit されなかった」状態を捏造
  const torn = await Wvfs.open(be);
  torn.writeFileSync('/second.txt', new TextEncoder().encode('S'));
  const endBefore = torn.journal.logicalEnd;
  await torn.close();
  const jf = path.join(dir('torn'), 'jrn-1.bin');
  fs.appendFileSync(jf, Buffer.from([0xff, 0xff, 0xff, 0x7f, 1, 2, 3, 4, 5, 6, 7, 8]));
  fs.appendFileSync(jf, crypto.getRandomValues(new Uint8Array(4096)));
  const w2 = await Wvfs.open(be);
  ok(w2.journal.stats.tornTails === 1, `torn tail detected (${w2.journal.stats.tornTails})`);
  ok(Buffer.from(w2.readFileSync('/keep.txt')).equals(Buffer.from(v1)), 'pre-torn record intact');
  ok(w2.existsSync('/second.txt'), 'committed record before the torn tail survives');
  ok(w2.journal.logicalEnd === endBefore, 'logical end rewound to last valid record');
  // torn の後も追記を継続できる (torn バイト領域を上書き)
  w2.writeFileSync('/third.txt', new TextEncoder().encode('T3'));
  await w2.close();
  const w2b = await Wvfs.open(be);
  ok(new TextDecoder().decode(w2b.readFileSync('/third.txt')) === 'T3' && new TextDecoder().decode(w2b.readFileSync('/keep.txt')) === 'KEEP ME', 'append after torn recovery');
  await w2b.close();
  // (2) 中間レコードの破損: レコードを自前で走査し 'S' (second.txt の本体 PUT) の crc 領域を壊す
  //     → そのレコード以降 (second.txt / third.txt) は捨てられ、それ以前 (keep.txt) は生きる
  const recs: Array<{ off: number; len: number }> = [];
  {
    const buf = fs.readFileSync(jf);
    let pos = 4096;
    while (pos + 27 <= buf.length) {
      const recLen = buf.readUInt32LE(pos);
      if (recLen < 27 || pos + recLen > buf.length) break;
      recs.push({ off: pos, len: recLen });
      pos += recLen;
    }
  }
  const bodyOf = (i: number) => {
    const buf = fs.readFileSync(jf);
    const { off, len } = recs[i];
    const pathLen = buf.readUInt16LE(off + 13);
    const dataLen = buf.readUInt32LE(off + 15);
    return { path: buf.subarray(off + 27, off + 27 + pathLen).toString(), data: buf.subarray(off + 27 + pathLen, off + 27 + pathLen + dataLen), dataOff: off + 27 + pathLen };
  };
  const si = recs.findIndex((_r, i) => i > 0 && bodyOf(i).path === '/second.txt' && bodyOf(i).data.toString() === 'S');
  ok(si > 0, `journal records parsed (${recs.length} recs, target idx ${si})`);
  {
    const fd = fs.openSync(jf, 'r+');
    const b = Buffer.from([0x00]);
    fs.writeSync(fd, b, 0, 1, bodyOf(si).dataOff); // データ 1 バイトを反転 → crc 不一致
    fs.closeSync(fd);
  }
  const w3 = await Wvfs.open(be);
  ok(w3.journal.stats.tornTails === 1, 'mid-record corruption detected as torn');
  ok(new TextDecoder().decode(w3.readFileSync('/keep.txt')) === 'KEEP ME', 'records before the broken one survive');
  ok(!w3.existsSync('/third.txt') && w3.statSync('/second.txt')!.size === 0, 'records from the broken one are dropped (create rec before it stays)');
  w3.writeFileSync('/fourth.txt', new TextEncoder().encode('T4'));
  await w3.close();
  const w4 = await Wvfs.open(be);
  ok(new TextDecoder().decode(w4.readFileSync('/fourth.txt')) === 'T4' && new TextDecoder().decode(w4.readFileSync('/keep.txt')) === 'KEEP ME', 'append after mid-record recovery');
  await w4.close();
  console.log('[4] torn tail recovery');
}

// ------------------------------------------------ 5. スーパーブロック A/B 復元
{
  const be = new NodeBackend(dir('sb'));
  const w = await Wvfs.open(be);
  w.writeFileSync('/a.txt', new Uint8Array([1]));
  await w.close();
  {
    const w2 = await Wvfs.open(be);
    w2.debugState; // touch
    await w2.close();
  }
  // 2 回 commit が済んだ状態 (slot 0 → 1) で active slot (=1) を壊す
  const root = path.join(dir('sb'), 'root');
  const sb = new Uint8Array(4096);
  {
    const fd = fs.openSync(root, 'r+');
    fs.readSync(fd, sb, 0, 4096, 0);
    // active = gen 最大の正当 slot。slot1 に garbage を上書き
    crypto.getRandomValues(sb.subarray(2048));
    fs.writeSync(fd, sb, 0, 4096, 0);
    fs.closeSync(fd);
  }
  const w3 = await Wvfs.open(be);
  ok(w3.existsSync('/a.txt') && w3.journal.journalId === 1, 'recover via other slot (gen-1), same journal');
  await w3.close();
  // 両スロット破損 → ジャーナル本体から復活 (resurrection)
  crypto.getRandomValues(sb);
  {
    const fd = fs.openSync(root, 'r+');
    fs.writeSync(fd, sb, 0, 4096, 0);
    fs.closeSync(fd);
  }
  const w4 = await Wvfs.open(be);
  ok(w4.existsSync('/a.txt'), 'resurrect journal when both slots are corrupt (journal header intact)');
  await w4.close();
  // 両スロット破損 + ジャーナルヘッダも破損 → 空 store として再出発 (anomaly 記録)
  crypto.getRandomValues(sb.subarray(0, 4096));
  {
    const fd = fs.openSync(root, 'r+');
    fs.writeSync(fd, sb, 0, 4096, 0);
    fs.closeSync(fd);
  }
  {
    const jfd = fs.openSync(path.join(dir('sb'), 'jrn-1.bin'), 'r+');
    const jgarbage = crypto.getRandomValues(new Uint8Array(4096));
    fs.writeSync(jfd, jgarbage, 0, 4096, 0); // ヘッダ頁を壊す (末尾 junk だけなら復活する)
    fs.closeSync(jfd);
  }
  const w5 = await Wvfs.open(be);
  ok(w5.journal.stats.anomalies >= 1 && !w5.existsSync('/a.txt'), 'fresh start after total corruption (anomaly recorded)');
  w5.writeFileSync('/new.txt', new Uint8Array([9]));
  await w5.close();
  const w6 = await Wvfs.open(be);
  ok(w6.existsSync('/new.txt'), 'fresh store is writable');
  await w6.close();
  console.log('[5] superblock A/B');
}

// ------------------------------------------------ 6. quota / 上限の挙動
{
  // (a) EFBIG: ファイル上限
  {
    const w = await Wvfs.open(new NodeBackend(dir('cap')), { maxFileBytes: 1024 });
    const big = new Uint8Array(2048);
    ok(await throwsCode(() => w.writeFileSync('/big.bin', big), 'EFBIG'), 'file cap = EFBIG');
    ok(w.existsSync('/big.bin') && w.statSync('/big.bin')!.size === 0, 'failed write leaves an empty file (POSIX)');
    await w.close();
  }
  // (b) ENOSPC: quota 超過 (QuotaExceededError) を write の呼出層で変換。
  //     wrap 対象はレコード領域 (at >= 4096) のみ (boot のヘッダ/スーパーブロック書込は壊さない)
  const makeFailing = (d: string, failFromRecord: number) => {
    const be = new NodeBackend(d);
    const origOpen = be.open.bind(be);
    let recordWrites = 0;
    be.open = async (name: string, opts?: { create?: boolean; truncate?: boolean }) => {
      const f: SyncFile = await origOpen(name, opts);
      return {
        ...f,
        write: (buf: Uint8Array, at: number) => {
          if (at >= 4096 && recordWrites++ >= failFromRecord) {
            const e = new Error('quota');
            (e as Error & { name: string }).name = 'QuotaExceededError';
            throw e;
          }
          return f.write(buf, at);
        },
      };
    };
    return be;
  };
  {
    const w2 = await Wvfs.open(makeFailing(dir('quota2'), 1)); // レコード書込 1 回目は成功 (create の空 PUT)、2 回目で死ぬ
    let enospc = false;
    try {
      w2.writeFileSync('/too-big.bin', new Uint8Array(300 * 1024));
    } catch (e) {
      enospc = e instanceof WvfsError && e.code === 'ENOSPC';
    }
    ok(enospc, 'QuotaExceededError → WvfsError ENOSPC');
    try {
      await w2.close(); // dirty の再試行も quota で死ぬが、state は保持される
    } catch (e) {
      ok(e instanceof WvfsError && e.code === 'ENOSPC', 'close rethrows persistent ENOSPC (dirty kept for retry)');
    }
  }
  // 部分書込 (レコード半分で死ぬ) → 次回起動は torn tail として復元
  {
    const be3 = new NodeBackend(dir('quota3'));
    const w3 = await Wvfs.open(be3);
    w3.writeFileSync('/good.txt', new TextEncoder().encode('GOOD'));
    await w3.close();
    const be4 = new NodeBackend(dir('quota3'));
    const origOpen4 = be4.open.bind(be4);
    be4.open = async (name: string, opts?: { create?: boolean; truncate?: boolean }) => {
      const f: SyncFile = await origOpen4(name, opts);
      let recWrites = 0;
      return {
        ...f,
        write: (buf: Uint8Array, at: number) => {
          if (at >= 4096 && recWrites++ >= 1) {
            const half = Math.max(1, Math.floor(buf.length / 2));
            f.write(buf.subarray(0, half), at); // 半分だけ書いて死ぬ = torn write
            const e = new Error('quota mid-write');
            (e as Error & { name: string }).name = 'QuotaExceededError';
            throw e;
          }
          return f.write(buf, at);
        },
      };
    };
    const w4 = await Wvfs.open(be4);
    let enospc2 = false;
    try {
      w4.writeFileSync('/died.bin', new Uint8Array(64 * 1024));
    } catch (e) {
      enospc2 = e instanceof WvfsError && e.code === 'ENOSPC';
    }
    ok(enospc2, 'mid-record quota death = ENOSPC');
    try {
      await w4.close(); // dirty 保持 → 再試行も失敗するが state は壊れない
    } catch (e) {
      ok(e instanceof WvfsError && e.code === 'ENOSPC', 'close rethrows persistent ENOSPC (retry contract)');
    }
    const w5 = await Wvfs.open(be4);
    ok(new TextDecoder().decode(w5.readFileSync('/good.txt')) === 'GOOD' && (!w5.existsSync('/died.bin') || w5.statSync('/died.bin')!.size === 0), 'partial (torn) write recovers, prior state intact');
    await w5.close();
    const w6 = await Wvfs.open(new NodeBackend(dir('quota3'))); // 素の backend で再開 (retry path)
    w6.writeFileSync('/after.bin', new Uint8Array([1, 2]));
    ok(w6.readFileSync('/after.bin').length === 2, 'write after quota failure works (retry path)');
    await w6.close();
  }
  // (d) 実 quota の目安 (node では取得不可 → chrome e2e で navigator.storage.estimate を報告)
  console.log('[6] quota / cap behaviour');
}

// ------------------------------------------------ 7. compaction
{
  const rnd = (n: number) => {
    const out = new Uint8Array(n);
    for (let o = 0; o < n; o += 65536) crypto.getRandomValues(out.subarray(o, Math.min(n, o + 65536)));
    return out;
  };
  const be = new NodeBackend(dir('compact'));
  const w = await Wvfs.open(be);
  w.mkdirSync('/explicit-empty');
  const data = rnd(128 * 1024);
  for (let i = 0; i < 40; i++) {
    data[0] = i;
    w.writeFileSync('/churn.bin', data);
  }
  w.writeFileSync('/keep2.txt', new TextEncoder().encode('K2'));
  ok(w.journal.shouldCompact(w.debugState().liveBytes), 'journal bloated → compaction needed');
  const before = w.journal.logicalEnd;
  const r = await w.compactNow();
  ok(r.after < r.before && r.before === before, `journal shrunk ${r.before} → ${r.after} bytes`);
  ok(!w.journal.shouldCompact(w.debugState().liveBytes), 'post-compact: no compaction needed');
  ok(Buffer.from(w.readFileSync('/churn.bin')).equals(Buffer.from(data)), 'data intact after compaction');
  ok(w.existsSync('/explicit-empty'), 'explicit empty dir survives compaction');
  await w.close();
  const w2 = await Wvfs.open(be);
  ok(Buffer.from(w2.readFileSync('/churn.bin')).equals(Buffer.from(data)) && w2.existsSync('/explicit-empty') && w2.existsSync('/keep2.txt'), 'reload after compaction');
  ok(w2.journal.journalId === 2, `active journal switched (${w2.journal.journalId})`);
  await w2.close();
  // compaction 後に active slot を壊す → 両 slot とも新 journalId に更新済みゆえ data 無傷
  // (旧 journalId slot への fallback は削除済み journal を拾うので、これは回帰テストになる)
  {
    const w3 = await Wvfs.open(be);
    w3.journal.debugCorruptActiveSlot();
    await w3.close();
    const w4 = await Wvfs.open(be);
    ok(w4.journal.journalId === 2 && Buffer.from(w4.readFileSync('/churn.bin')).equals(Buffer.from(data)), 'post-compact slot corruption recovers via refreshed slot (not removed journal)');
    await w4.close();
  }
  console.log('[7] compaction');
}

// ------------------------------------------------ 8. pathreg 経路 (JS 契約 / 15 fixture)
{
  const router = createPathRouter();
  const fixtures: Array<[string, 'home' | 'tmp' | null]> = [
    ['C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp', null], // /fl (RO asset)
    ['C:\\PROGRAM FILES\\Image-Line\\FL Studio 2026\\Plugins\\Fruity\\Effects\\Fruity Send\\Fruity Send_x64.dll', null],
    ['C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Effects\\VST\\Xfer Records, OTT.nfo', 'home'],
    ['C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\VerifiedIDs.nfo', 'home'],
    ['C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml', 'home'],
    ['C:\\Users\\user\\AppData\\Roaming\\Image-Line\\Shared\\config.xml', 'home'],
    ['C:\\Users\\user\\AppData\\Local\\Temp\\Image-Line\\9-2\\zip\\inner.bin', 'tmp'],
    ['C:\\Users\\user\\AppData\\Local\\Image-Line\\QuickFontCache.dat', 'home'],
    ['C:\\Windows\\notepad.exe', null], // /c 直下 = 対象外 (glue 裁量)
    ['C:\\foo\\..\\bar\\./x', null], // /c/bar/x = 対象外
    ['D:\\unmapped\\path.txt', null],
    ['/posix/abs/path', null],
    ['relative\\win\\path', null],
    ['\\\\?\\C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\x.wav', null],
    ['\\\\srv\\share\\folder\\file.dat', null],
  ];
  let agree = 0;
  for (const [win, want] of fixtures) {
    const r = router.route(win);
    const got = r ? r.mount : null;
    if (got === want) agree++;
    else console.log(`    route mismatch: ${win} → ${got ?? 'null'} (want ${want ?? 'null'})`);
  }
  ok(agree === fixtures.length, `pathreg 15 fixture の経路分類一致 (${agree}/${fixtures.length})`);
  // 書込対象の往復: Plugin database 配置 (nfo REPORT §3) に沿ったパスへダミー .fst
  const fst = 'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Effects\\VST\\Xfer Records, OTT\\OTT.fst';
  const r = router.route(fst)!;
  const w = await Wvfs.open(new NodeBackend(dir('router')));
  w.mkdirpSync(r.path.slice(0, r.path.lastIndexOf('/')));
  w.writeFileSync(r.path, new TextEncoder().encode('dummy fst bytes (CAB-216 は本物の generateDb で置換)'));
  // 大小無視で読める (別ケース)
  const upper = r.path.toUpperCase().replace('.FST', '.FST');
  ok(new TextDecoder().decode(w.readFileSync(upper)).startsWith('dummy fst'), 'plugin db .fst roundtrip (case-insensitive)');
  ok(router.route('C:\\Users\\user\\AppData\\Local\\Temp\\Image-Line\\z\\t.bin')!.mount === 'tmp', 'tmp routing');
  await w.close();
  const w2 = await Wvfs.open(new NodeBackend(dir('router')));
  ok(w2.existsSync(r.path), 'routed write persists');
  await w2.close();
  ok(storeDir('home') === 'fl-wvfs/home' && storeDir('tmp') === 'fl-wvfs/tmp', 'store dir naming');
  console.log('[8] pathreg routing');
}

console.log(failed ? `FAILED: ${failed} (pass ${pass})` : `ALL PASS (${pass})`);
process.exit(failed ? 1 : 0);
