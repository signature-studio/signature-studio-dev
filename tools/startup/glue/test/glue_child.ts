// glue_child.ts — SIGKILL 跨ぎ e2e の子プロセス (CAB-101)。
//   node tools/startup/glue/test/glue_child.ts --dir <workDir> --mode seed|verify
//
// seed  : glue の規約順に起動し、wvfs (/c/home・/c/tmp) とレジストリに書き込み、
//         **onYield()/onPageHide() だけで flush** してから close せずに終わる。
//         (親プロセスが SIGKILL するので graceful close は走らない = flush 点契約のみ)
// verify: 別プロセスとして同じ dir を開き、全ファイルの sha256 を照合する。
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { GlueHost, makeRouter } from '../host/glue_host.ts';
import { FileStore } from '../../vreg/js/store.mjs';

const A: Record<string, string> = {};
for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const DIR = A.dir!;
const MODE = A.mode ?? 'seed';
const NOFLUSH = A.noflush === '1';      // 陰性対照用: flush 点を呼ばない (CAB-101 規則 41)
const USER = A.username ?? 'webstudio';
const MOD = path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'work/glue_mod.mjs');

const FILES = [
  { win: 'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml', body: '<manifest v="2"/>glue-e2e' },
  { win: 'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Projects\\Demo.flp', body: 'DEMOFLP'.repeat(64) },
  { win: 'C:\\Users\\webstudio\\AppData\\Local\\Temp\\Image-Line\\1-2\\scratch.bin', body: Buffer.alloc(4096, 7).toString('binary') },
];

async function main() {
  const mod = await import(MOD);
  const m = await (mod as any).default();
  const h = new GlueHost(m, { username: USER, store: new FileStore(path.join(DIR, 'vreg')), workDir: path.join(DIR, 'wvfs') });
  await h.runAll('?open=Demo.flp');

  if (MODE === 'seed') {
    // ---- 書込 (pathreg 経路 → /c/home・/c/tmp) ----
    const wrote: Array<{ win: string; mount: string; path: string; sha256: string; size: number }> = [];
    for (const f of FILES) {
      const data = new Uint8Array(Buffer.from(f.body, 'binary'));
      const r = h.writeWin(f.win, data);
      wrote.push({ win: f.win, mount: r.mount, path: r.path, sha256: createHash('sha256').update(f.body, 'binary').digest('hex'), size: data.length });
    }
    // レジストリにも FL 相当の書き込み
    const cstr = (s: string) => { const p = m._malloc(m.lengthBytesUTF8(s) + 1); m.stringToUTF8(s, p, m.lengthBytesUTF8(s) + 1); return p; };
    m._vreg_probe_write_str(cstr('HKCU'), cstr('Software\\Image-Line\\FL Studio 26\\General'), cstr('ProjectPath'), cstr('C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Projects\\Demo.flp'));

    // ---- flush 点契約のみで永続化 (close しない) ----
    if (!NOFLUSH) {
      await h.onYield();                     // yield 点
      await h.reg!.onPageHide();             // pagehide (await: store.save の完了を待つ)
      await h.home!.onYield();
      await h.tmp!.onYield();
    }
    fs.writeFileSync(path.join(DIR, 'expected.json'), JSON.stringify({ files: wrote, stageCount: h.stages.length }, null, 1));
    console.log(`[child:seed] files=${wrote.length} flushes=${h.flushes} trace=${h.trace().length} lines noflush=${NOFLUSH}`);
    process.stdout.write('SEED-FLUSHED\n');
    // graceful close を意図的に省略したまま生存する (親が SIGKILL する = flush 点契約のみの検証)
    await new Promise(() => {});
    return;
  }

  // ---- verify: 新しい Wvfs を開いて (ジャーナル再生) sha256 照合 ----
  const expected = JSON.parse(fs.readFileSync(path.join(DIR, 'expected.json'), 'utf8'));
  const { Wvfs, NodeBackend } = await import('../../../assets/wvfs/index.ts');
  const home = await Wvfs.open(new NodeBackend(path.join(DIR, 'wvfs/home')));
  const tmp = await Wvfs.open(new NodeBackend(path.join(DIR, 'wvfs/tmp')));
  const router = makeRouter(USER);
  let mismatches = 0, checked = 0;
  for (const f of expected.files) {
    const r = router.route(f.win)!;
    const w = r.mount === 'home' ? home : tmp;
    try {
      const got = Buffer.from(w.readFileSync(r.path)).toString('binary');
      const sha = createHash('sha256').update(got, 'binary').digest('hex');
      checked++;
      if (sha !== f.sha256) { mismatches++; console.log(`  MISMATCH ${r.mount} ${r.path}`); }
      else console.log(`  ok ${r.mount} ${r.path} ${sha.slice(0, 12)}`);
    } catch (e: any) { mismatches++; console.log(`  MISSING ${r.mount} ${r.path} (${e.code ?? e.message})`); }
  }
  // レジストリ永続も確認 (FileStore)
  const regRec = JSON.parse(fs.readFileSync(path.join(DIR, 'vreg', encodeURIComponent('default') + '.json'), 'utf8'));
  const regVal = regRec?.hkcu?.['Software\\Image-Line\\FL Studio 26\\General']?.['ProjectPath']?.v;
  const regOk = regVal === 'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Projects\\Demo.flp';
  console.log(`[child:verify] checked=${checked} mismatches=${mismatches} reg=${regOk ? regVal : '(none)'}`);
  fs.writeFileSync(path.join(DIR, 'verify.json'), JSON.stringify({ checked, mismatches, regOk }), );
  process.stdout.write(JSON.stringify({ ok: mismatches === 0 && regOk, checked, mismatches, regOk }) + '\n');
}

main().catch((e) => { console.error(e); process.exit(1); });
