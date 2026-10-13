// pe_precheck_vfs.mjs — HB-H17 (#787): Fruity Wrapper の PE 事前検査 (fw:0x7a9030 相当) を仮想 FS (wvfs) 経由で満たす実測。
//   使い方: node analysis/pe_precheck_vfs.mjs  (前提: work/wrapper/extracted/block19091_PE.bin = fl-win64 素材の実 Wrapper)
//   1. VST 候補 DLL を wvfs (/c/home 相当) に書き、Wvfs を閉じて開き直す (永続)
//   2. 読み戻したバイト列を検査: MZ → PE32+ → machine==0x8664 → DLL → export 名に main / vstpluginmain (小文字化比較)
//   3. 同じバイト列を pefile (python) で独立に読み、export 名と machine が一致することを確認
//   4. ネガコン: PE を見えなくする / export が違う / 実 Wrapper / x86 / 切り詰め → 検査が必ず落ちること
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { Wvfs, NodeBackend, createPathRouter } from '../../assets/wvfs/index.ts';
import { makePeStub } from '../poc/pe_stub.mjs';

const HB = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const WORK = path.join(HB, 'work', 'pe_precheck');
const WRAPPER = path.join(HB, 'work', 'wrapper', 'extracted', 'block19091_PE.bin');
const VST_WIN = 'C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Plugins\\OTT_x64.dll';

fs.rmSync(WORK, { recursive: true, force: true });
fs.mkdirSync(WORK, { recursive: true });
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');

// ---- 事前検査 (JS 実装。fw:0x5c0200 = export 名列挙, fw:0x437ab0 = 小文字化, fw:0x5bfc30 = bitness) ----
export function peInfo(buf) {
  if (buf.length < 0x40 || buf.toString('latin1', 0, 2) !== 'MZ') throw new Error('no MZ');
  const pe = buf.readUInt32LE(0x3c);
  if (pe + 24 > buf.length || buf.toString('latin1', pe, pe + 4) !== 'PE\0\0') throw new Error('no PE signature');
  const coff = pe + 4;
  const machine = buf.readUInt16LE(coff);
  const nsec = buf.readUInt16LE(coff + 2);
  const optSize = buf.readUInt16LE(coff + 16);
  const chars = buf.readUInt16LE(coff + 18);
  const opt = coff + 20;
  if (buf.readUInt16LE(opt) !== 0x20b) throw new Error('not PE32+');
  const expRva = buf.readUInt32LE(opt + 112);
  const secs = [];
  for (let i = 0; i < nsec; i++) {
    const b = opt + optSize + 40 * i;
    secs.push({ vsize: buf.readUInt32LE(b + 8), va: buf.readUInt32LE(b + 12), rawSize: buf.readUInt32LE(b + 16), raw: buf.readUInt32LE(b + 20) });
  }
  const off = (rva) => {
    for (const s of secs) {
      const size = Math.max(s.vsize, s.rawSize);
      if (rva >= s.va && rva < s.va + size) return rva - s.va + s.raw;
    }
    throw new Error(`rva 0x${rva.toString(16)} not in any section`);
  };
  const names = [];
  if (expRva) {
    const e = off(expRva);
    const n = buf.readUInt32LE(e + 24);
    const namesOff = off(buf.readUInt32LE(e + 32));
    for (let i = 0; i < n; i++) {
      let p = off(buf.readUInt32LE(namesOff + 4 * i));
      let s = '';
      while (buf[p] !== 0) s += String.fromCharCode(buf[p++]);
      names.push(s);
    }
  }
  return { machine, isDll: (chars & 0x2000) !== 0, names };
}

// 事前検査の判定。VST 判定 = 小文字化 export 名が main / vstpluginmain / hint のいずれか、かつ x64 DLL
export function precheck(buf, hint = '') {
  let info;
  try {
    info = peInfo(buf);
  } catch (e) {
    return { pass: false, why: `parse: ${e.message}` };
  }
  if (info.machine !== 0x8664 || !info.isDll) return { pass: false, why: 'bitness/DLL' };
  const low = info.names.map((n) => n.toLowerCase());
  const hit = ['main', 'vstpluginmain', hint.toLowerCase()].filter((h) => h && low.includes(h));
  return { pass: hit.length > 0, why: hit.length ? `export ${hit[0]}` : 'no main/vstpluginmain export', names: info.names };
}

const pyNames = (file) =>
  JSON.parse(
    execFileSync(
      'python3',
      ['-c', 'import pefile,sys,json;p=pefile.PE(sys.argv[1]);print(json.dumps({"m":p.FILE_HEADER.Machine,"dll":p.is_dll(),"n":[e.name.decode() for e in p.DIRECTORY_ENTRY_EXPORT.symbols if e.name]}))', file],
      { encoding: 'utf8' },
    ),
  );

const results = [];
const rec = (kind, id, cond, desc) => {
  const line = `${cond ? 'PASS' : 'FAIL'} ${kind} ${id} ${desc}`;
  results.push({ kind, id, cond, line });
  console.log(line);
};

// ---- 素材 ----
if (!fs.existsSync(WRAPPER)) throw new Error(`missing ${WRAPPER} (bash analysis/pe_precheck_vfs.sh が展開する)`);
const wrapperBytes = fs.readFileSync(WRAPPER);
rec('INFO', 'wrapper', wrapperBytes.length > 0, `実 Wrapper ${path.basename(WRAPPER)} ${wrapperBytes.length} B sha256=${sha(wrapperBytes).slice(0, 16)}`);

const stub = makePeStub(['VSTPluginMain', 'main'], 'OTT_x64.dll');
const stubPath = path.join(WORK, 'stub-src.dll');
fs.writeFileSync(stubPath, stub);
rec('INFO', 'stub-size', stub.length <= 4096, `PE スタブ ${stub.length} B (最小構成の大きさ)`);

// ---- 1. 仮想 FS に書いて開き直す ----
const router = createPathRouter();
const route = router.route(VST_WIN);
rec('P', 'route', route !== null && route.mount === 'home', `pathreg 写像 ${VST_WIN} -> ${JSON.stringify(route)}`);
const storeRoot = path.join(WORK, 'wvfs');
{
  const w = await Wvfs.open(new NodeBackend(storeRoot));
  w.mkdirpSync(path.posix.dirname(route.path));
  w.writeFileSync(route.path, stub);
  await w.close();
}
const w = await Wvfs.open(new NodeBackend(storeRoot));
const readBack = Buffer.from(w.readFileSync(route.path));
rec('P', 'persist', sha(readBack) === sha(stub), `reopen 後の読み戻し sha256 一致 (${readBack.length} B)`);

// ---- 2. 事前検査 (wvfs 読み戻しバイト) ----
const pc = precheck(readBack, 'main');
rec('P', 'precheck', pc.pass, `事前検査 通過 (${pc.why}; exports=${JSON.stringify(pc.names)})`);

// ---- 3. pefile 独立照合 ----
const tmpOut = path.join(WORK, 'readback.dll');
fs.writeFileSync(tmpOut, readBack);
const py = pyNames(tmpOut);
const js = peInfo(readBack);
rec('P', 'pefile', py.m === js.machine && py.dll === js.isDll && JSON.stringify(py.n) === JSON.stringify(js.names), `pefile 照合 (machine 0x${py.m.toString(16)}, dll=${py.dll}, exports=${JSON.stringify(py.n)})`);

// ---- 4. ネガコン (検査が落ちることを確認) ----
const neg = (id, cond, desc) => rec('NEG', id, cond, desc);
{
  const w2 = await Wvfs.open(new NodeBackend(path.join(WORK, 'wvfs-neg')));
  // N1: PE を仮想 FS から見えなくする (書かない)
  let absent = false;
  try {
    w2.readFileSync(route.path);
  } catch {
    absent = true;
  }
  neg('N1', absent && !precheck(Buffer.alloc(0)).pass, 'PE が仮想 FS に無いとき読込が ENOENT で失敗 (事前検査も失敗)');
  // N2: export 名が違う (main/vstpluginmain なし)
  const bad = makePeStub(['Foo', 'Bar'], 'OTT_x64.dll');
  neg('N2', !precheck(bad).pass, `export 名が main/vstpluginmain でない → 不合格 (${precheck(bad).why})`);
  // N3: 実 Wrapper (CreatePlugInstance 系) を VST として置く
  const wp = precheck(wrapperBytes);
  neg('N3', !wp.pass, `実 Wrapper を VST として検査 → 不合格 (${wp.why}; exports=${JSON.stringify(wp.names)})`);
  // N4: x86 (0x14c) に変えた PE → bitness 検査で不合格
  const x86 = Buffer.from(stub);
  x86.writeUInt16LE(0x14c, x86.readUInt32LE(0x3c) + 4);
  neg('N4', !precheck(x86).pass, `machine を x86 に変更 → 不合格 (${precheck(x86).why})`);
  // N5: 切り詰め (MZ のみ)
  neg('N5', !precheck(stub.subarray(0, 0x40)).pass, `先頭 64 B に切り詰め → 不合格 (${precheck(stub.subarray(0, 0x40)).why})`);
}

const failed = results.filter((r) => !r.cond).length;
console.log(`SUMMARY P=${results.filter((r) => r.kind === 'P' && r.cond).length}/${results.filter((r) => r.kind === 'P').length} NEG=${results.filter((r) => r.kind === 'NEG' && r.cond).length}/${results.filter((r) => r.kind === 'NEG').length} failed=${failed}`);
process.exit(failed ? 1 : 0);
