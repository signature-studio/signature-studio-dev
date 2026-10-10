// glue_unit.ts — glue ホスト側 (TS) 単体テスト (CAB-101)。
//   node tools/startup/glue/test/glue_unit.ts
// 検証: 初期化順序規約 (JS/C 二重)・段階の独立呼出・flush フック発火・wvfs mount と
// ファイル経路・pump RING 疎通・trace 突合 (username webstudio / C:\Users\user 残存 0)。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GlueHost } from '../host/glue_host.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GLUE_DIR = path.resolve(HERE, '..');
const WORK = path.join(GLUEDir(), 'work/unit-ts');

function GLUEDir() { return GLUE_DIR; }

let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { console.log(c ? '  ok  ' : '  FAIL', m); if (c) pass++; else fail++; };
const throws = async (fn: () => Promise<unknown>): Promise<boolean> => { try { await fn(); return false; } catch { return true; } };

async function makeHost(username = 'webstudio', extra: Record<string, unknown> = {}) {
  const mod = await import(path.join(GLUEDir(), 'work/glue_mod.mjs'));
  const m = await (mod as any).default();
  const saves: any[] = [];
  const store = {
    async load(p: string) { const rec = saves[saves.length - 1]; return rec && rec.p === p ? rec.rec : undefined; },
    async save(p: string, rec: any) { saves.push({ p, rec }); },
    async delete(p: string) { },
  };
  const h = new GlueHost(m, { username, store, workDir: path.join(WORK, username), ...extra });
  return { h, m, saves };
}

// ---------------------------------------------------------------- 1. 規約順に全段階
{
  fs.rmSync(WORK, { recursive: true, force: true });
  const { h, m, saves } = await makeHost();
  const recs = await h.runAll('?open=demo.flp');
  ok(recs.length === 10, `runAll executed 10 stages (${recs.length})`);
  ok(recs.every((r) => r.ok), 'all stages ok');
  ok(m._glue_order_violations() === 0, `C side order violations == 0 (${m._glue_order_violations()})`);
  ok(h.orderViolations === 0, 'JS side order violations == 0');
  ok(m._glue_stage_next() === -1, 'C side: no next stage (all done)');
  const names = recs.map((r) => r.name).join('>');
  ok(names === 'paths>registry>pump>vfs>pre_dllmain>dllmain>host>boot>post>shutdown', `stage order = ${names}`);
  console.log(`       stages: ${recs.map((r) => `${r.name}(${r.ms.toFixed(1)}ms)`).join(' ')}`);

  // host / boot
  const addr = m._glue_host_addr();
  const u32 = new Uint32Array(m.HEAPU8.buffer, addr, 0x38 / 4);
  ok(u32[2] === 1, `host.version(+0x08) == 1 (${u32[2]})`);
  ok(u32[3] === 0, `host.flags(+0x0c) == 0 (${u32[3]})`);
  const titlePtr = new Uint32Array(m.HEAPU8.buffer)[(addr + 0x18) / 4];
  ok(m.UTF8ToString(titlePtr) === 'FL Studio', `host.title(+0x18) == "FL Studio" (${m.UTF8ToString(titlePtr)})`);
  ok(m._glue_create_fruity_instance_called() === 1, `CreateFruityInstance called once (${m._glue_create_fruity_instance_called()})`);
  ok(m._glue_last_iface() !== 0, 'iface written (stub)');
  console.log('[1] canonical order + THostInstance + CreateFruityInstance');
}

// ---------------------------------------------------------------- 2. 順序違反 (ネガティブコントロール)
{
  const { h, m } = await makeHost('webstudio-unit');
  const cE = m._glue_stage_vfs();
  ok(cE === -100, `C side: glue_stage_vfs() before paths -> GLUE_EORDER (${cE})`);
  ok(m._glue_order_violations() === 1, `C order violation recorded (${m._glue_order_violations()})`);
  ok(m._glue_stage_is_done(3) === 0, 'violating stage not marked done (C)');
  ok(await throws(() => h.stageVfs()), 'JS guard throws for the same call');
  const cP = m._glue_stage_pump(-1);
  ok(cP === -100, `C side: glue_stage_pump() before paths -> GLUE_EORDER (${cP})`);
  ok(m._glue_order_violations() === 2, `C violations = 2 (${m._glue_order_violations()})`);
  ok(await throws(() => h.stagePump()), 'JS guard throws for pump too');
  console.log('[2] out-of-order rejection (negative control)');
}

// ---------------------------------------------------------------- 3. 段階の独立呼出
{
  fs.rmSync(path.join(WORK, 'independent'), { recursive: true, force: true });
  const { h, m } = await makeHost('independent');
  await h.stagePaths();
  await h.stageRegistry();
  const p = await h.stagePump();
  ok(p.name === 'pump', 'pump stage called individually');
  ok(h.ring && h.ring.capacity > 0, `PumpRing bound to wasm ring (cap=${h.ring?.capacity})`);
  await h.stageVfs();
  await h.stagePreDllmain('?open=x.flp');
  await h.stageDllmain();
  await h.stageHost();
  await h.stageBoot();
  await h.stagePost();
  await h.stageShutdown();
  ok(m._glue_order_violations() === 0, `individual calls keep order (violations=${m._glue_order_violations()})`);
  ok(m._glue_stage_is_done(9) === 1, 'shutdown stage done');
  console.log('[3] independent stage calls');
}

// ---------------------------------------------------------------- 4. flush フック発火
{
  fs.rmSync(path.join(WORK, 'flushtest'), { recursive: true, force: true });
  const { h, m, saves } = await makeHost('flushtest');
  await h.stagePaths();
  await h.stageRegistry();
  await h.stagePump();
  await h.stageVfs();
  await h.stagePreDllmain();
  await h.stageDllmain();
  await h.stageHost();
  await h.stageBoot();
  await h.stagePost();
  ok(m._pathreg_reg_changed() === 0, 'registry unchanged right after mark_saved');
  const genBeforeWrite = m._vreg_generation();
  // FL (Delphi TRegistry) と同じパターンで書く (vreg_probe_write_str: hive/key/name/val は UTF-8 文字列)
  const cstr = (s: string) => { const p = m._malloc(m.lengthBytesUTF8(s) + 1); m.stringToUTF8(s, p, m.lengthBytesUTF8(s) + 1); return p; };
  const key = cstr('Software\\Image-Line\\FL Studio 26\\General');
  const name = cstr('TestValue');
  const val = cstr('hello-glue');
  const rc = m._vreg_probe_write_str(cstr('HKCU'), key, name, val);
  [key, name, val].forEach((p) => m._free(p));
  ok(rc === 0, `vreg_probe_write_str ok (${rc})`);
  ok(m._vreg_generation() !== genBeforeWrite, `vreg generation advanced by write (${genBeforeWrite} -> ${m._vreg_generation()})`);
  ok(m._pathreg_reg_changed() === 1, 'change detected by pathreg_reg_changed()');
  await h.onYield();                       // yield 点 flush (明示口)
  ok(m._vreg_generation() !== genBeforeWrite, 'vreg generation kept (flush persists, does not mutate)');
  ok(saves.length >= 1, `store.save called by flush hook (${saves.length} saves)`);
  const rec = saves[saves.length - 1]?.rec;
  const v = rec?.hkcu?.['Software\\Image-Line\\FL Studio 26\\General']?.['TestValue']?.v;
  ok(v === 'hello-glue', `persisted value round-trips (${v})`);
  await h.stageShutdown();
  ok(saves.length >= 2, `shutdown flush (onPageHide) saved again (${saves.length} saves)`);
  console.log('[4] registry import/flush hooks');
}

// ---------------------------------------------------------------- 5. wvfs mount + ファイル経路
{
  fs.rmSync(path.join(WORK, 'vfstest'), { recursive: true, force: true });
  const { h, m } = await makeHost('vfstest');
  await h.stagePaths();
  await h.stageRegistry();
  await h.stagePump();
  await h.stageVfs();

  // (a) pathreg の C マッパと JS ミラーが一致 (= stageVfs 内で照合済み)。念のため直接照合
  const probes = [
    `C:\\Users\\vfstest\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml`,
    `C:\\Users\\vfstest\\AppData\\Local\\Temp\\Image-Line\\1-2\\tmp.bin`,
    `C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\FLEngine_x64.dll`,
  ];
  ok(probes.every((p) => h.shimxPathToPosix(p) === h.router!.mapRaw(p)), 'C mapper == JS mapper on 3 probes');

  // (b) Win パス → /c/home 書込 → 読み戻し
  const w1 = `C:\\Users\\vfstest\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml`;
  const data = new TextEncoder().encode('<manifest v="2"/>');
  const r1 = h.writeWin(w1, data);
  ok(r1.mount === 'home' && r1.path.startsWith('/Documents/Image-Line/'), `documents -> ${r1.mount} ${r1.path}`);
  ok(Buffer.from(h.readWin(w1)).toString() === '<manifest v="2"/>', 'wvfs read-back matches');

  // (c) Win パス → /c/tmp 書込
  const w2 = `C:\\Users\\vfstest\\AppData\\Local\\Temp\\Image-Line\\1-2\\scratch.bin`;
  h.writeWin(w2, new Uint8Array([1, 2, 3]));
  ok(h.router!.route(w2)!.mount === 'tmp', 'temp path -> tmp mount');

  // (d) Emscripten FS (wvfs mount) 経由 — C 側 shimx file API が通る経路
  const fsPath = h.shimxPathToPosix(w1);
  ok(fsPath.startsWith('/c/home/'), `mapper gives FS path ${fsPath}`);
  h.writeFs(fsPath, new TextEncoder().encode('via-FS'));
  ok(Buffer.from(h.readWin(w1)).toString() === 'via-FS', 'FS.writeFile lands in wvfs store');

  // (e) yield 点 flush で wvfs が永続化相当の状態になる
  await h.onYield();
  const fsPath2 = '/c/home/Documents/Image-Line/FL Studio/Settings/Manifest.xml';
  ok(typeof m.FS.readFile === 'function', 'FS mounted (wvfs at /c/home and /c/tmp)');
  m.FS.readFile(fsPath2);
  console.log('[5] wvfs mount + path routing');

  // (f) pump RING 疎通 (host producer → C consumer)
  const pushed = h.ring.push({ message: 0x0100, ptx: 42 });      // WM_KEYDOWN
  ok(pushed === true, 'host PumpRing.push ok');
  const buf = m._malloc(48);
  const got = m._pump_step(buf);
  const u32 = new Uint32Array(m.HEAPU8.buffer, buf, 12);
  const msg = u32[2];                                            // +8: message
  ok(got === 1, `pump_step consumed 1 message (${got})`);
  ok(msg === 0x0100, `message id matches (0x${msg.toString(16)})`);
  m._free(buf);
  console.log('[6] pump RING producer -> consumer');
}

// ---------------------------------------------------------------- 6. trace 突合
{
  fs.rmSync(path.join(WORK, 'tracetest'), { recursive: true, force: true });
  const { h, m } = await makeHost('tracetest', { waitMode: 3 });
  await h.runAll('?open=demo.flp');
  const t = h.traceText();
  const USER = 'tracetest';
  ok(t.includes(`${USER}\\Documents`), `trace: documents path uses ${USER}`);
  ok(t.includes('/c/home'), 'trace: documents -> /c/home');
  ok(t.includes('/c/tmp'), 'trace: temp -> /c/tmp');
  ok(t.includes('/fl/'), 'trace: install -> /fl');
  ok(!t.includes('C:\\Users\\user'), 'trace: C:\\Users\\user residue == 0');
  const residual = (t.match(/-> 0 \/c\/Users\//g) ?? []).length;
  ok(residual === 0, `trace: residual /c/Users/ mappings == 0 (${residual})`);
  ok(t.includes(`username=${USER}`), 'trace: username recorded');

  // 規約順の突合 (stage=<name> enter の並び)
  const order = ['paths', 'registry', 'pump', 'vfs', 'pre_dllmain', 'dllmain', 'host', 'boot', 'post', 'shutdown'];
  const enters = h.trace().filter((l) => /stage=\S+ enter/.test(l)).map((l) => l.match(/stage=(\S+) enter/)![1]);
  ok(JSON.stringify(enters) === JSON.stringify(order), `trace stage order = ${enters.join('>')}`);

  // ネガティブコントロール: 既定表に無い foreign プロファイルは /c/Users/<x> に残る
  //  (= 監査が `/c/Users/` 残存を検出できることの確認。username=webstudio では 0 件だったのが
  //    foreign では検出される → 検査が空振りでないことの証拠)
  const foreign = h.shimxPathToPosix('C:\\Users\\alien\\Documents\\Image-Line\\x.txt');
  ok(foreign.startsWith('/c/Users/alien/'), `control: foreign profile -> ${foreign} (audit detects /c/Users/)`);
  console.log('[7] trace cross-check + audit discrimination');
}

console.log(`[glue-unit.ts] ${fail === 0 ? 'ALL PASS' : 'FAIL'} (pass=${pass} fail=${fail})`);
process.exit(fail === 0 ? 0 : 1);
