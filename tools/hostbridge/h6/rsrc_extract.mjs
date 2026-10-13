// rsrc_extract.mjs — PE .rsrc (IMAGE_RESOURCE_DIRECTORY 3 階層) パーサ + 画像資産抽出 (HB-H6 / G1).
//   依存なし (node ≥ 22, ブラウザでも parsePeResources(ArrayBuffer) がそのまま動く)。
//   CLI: node rsrc_extract.mjs <dll> <outDir>   → <outDir>/index.json + <outDir>/<type>/<name>.<ext>
//   素材 (抽出物) は非再配布: outDir は work/ (gitignore) に置く。commit しない。
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const RT = { 1: 'CURSOR', 2: 'BITMAP', 3: 'ICON', 4: 'MENU', 5: 'DIALOG', 6: 'STRING', 9: 'ACCELERATOR', 10: 'RCDATA', 12: 'GROUP_CURSOR', 14: 'GROUP_ICON', 16: 'VERSION', 24: 'MANIFEST' };
const PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

export function parsePe(buf) {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  if (dv.getUint16(0, true) !== 0x5a4d) throw new Error('not MZ');
  const pe = dv.getUint32(0x3c, true);
  if (dv.getUint32(pe, true) !== 0x4550) throw new Error('not PE');
  const nsec = dv.getUint16(pe + 6, true), optSize = dv.getUint16(pe + 20, true), opt = pe + 24;
  const magic = dv.getUint16(opt, true); // 0x20b = PE32+, 0x10b = PE32
  const ddBase = opt + (magic === 0x20b ? 112 : 96);
  const sections = [];
  for (let i = 0; i < nsec; i++) {
    const s = opt + optSize + i * 40;
    let name = ''; for (let k = 0; k < 8 && buf[s + k]; k++) name += String.fromCharCode(buf[s + k]);
    sections.push({ name, vsize: dv.getUint32(s + 8, true), rva: dv.getUint32(s + 12, true), rawSize: dv.getUint32(s + 16, true), raw: dv.getUint32(s + 20, true) });
  }
  const rsrcDir = { rva: dv.getUint32(ddBase + 2 * 8, true), size: dv.getUint32(ddBase + 2 * 8 + 4, true) };
  const rva2off = (rva) => {
    for (const s of sections) if (rva >= s.rva && rva < s.rva + Math.max(s.vsize, s.rawSize)) return s.raw + (rva - s.rva);
    throw new Error('rva 0x' + rva.toString(16) + ' not in any section');
  };
  return { dv, sections, rsrcDir, rva2off, pe64: magic === 0x20b };
}

// 戻り値: [{type, typeName, name, lang, rva, size, codepage, off}]
export function parsePeResources(buf) {
  const { dv, rsrcDir, rva2off } = parsePe(buf);
  if (!rsrcDir.rva) return [];
  const base = rva2off(rsrcDir.rva), out = [];
  const label = (v) => { // 上位 bit 立ち = UTF-16 名文字列へのオフセット (rsrc 先頭相対), それ以外は整数 ID
    if (!(v & 0x80000000)) return v;
    const p = base + (v & 0x7fffffff), n = dv.getUint16(p, true); let s = '';
    for (let i = 0; i < n; i++) s += String.fromCharCode(dv.getUint16(p + 2 + i * 2, true));
    return s;
  };
  const dir = (off) => {
    const n = dv.getUint16(off + 12, true) + dv.getUint16(off + 14, true), ents = [];
    for (let i = 0; i < n; i++) ents.push({ id: dv.getUint32(off + 16 + i * 8, true), tgt: dv.getUint32(off + 20 + i * 8, true) });
    return ents;
  };
  const seen = new Set();
  for (const t of dir(base)) {
    if (!(t.tgt & 0x80000000)) throw new Error('rsrc: level1 is leaf');
    for (const nm of dir(base + (t.tgt & 0x7fffffff))) {
      if (!(nm.tgt & 0x80000000)) throw new Error('rsrc: level2 is leaf');
      for (const lg of dir(base + (nm.tgt & 0x7fffffff))) {
        if (lg.tgt & 0x80000000) throw new Error('rsrc: level3 is dir');
        if (seen.has(lg.tgt)) continue; seen.add(lg.tgt); // 循環防止
        const de = base + lg.tgt, rva = dv.getUint32(de, true), size = dv.getUint32(de + 4, true), cp = dv.getUint32(de + 8, true);
        const type = label(t.id);
        out.push({ type, typeName: typeof type === 'number' ? (RT[type] || 'T' + type) : type, name: label(nm.id), lang: lg.id, rva, size, codepage: cp, off: rva2off(rva) });
      }
    }
  }
  return out;
}

export function pngInfo(b) { // IHDR のみ読む (サイズ・bit depth・color type)
  if (b.length < 33 || !b.subarray(0, 8).equals(PNG_SIG)) return null;
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), bitDepth: b[24], colorType: b[25] };
}
export function sniff(b) {
  if (pngInfo(b)) return 'png';
  if (b[0] === 0xff && b[1] === 0xd8) return 'jpg';
  if (b.length > 4 && b.subarray(0, 4).equals(Buffer.from([0, 1, 0, 0]))) return 'ttf';
  if (b.length > 4 && b.subarray(0, 4).toString('latin1') === 'RIFF') return 'riff';
  if (b[0] === 0x7b || b[0] === 0x5b) return 'json?';
  return 'bin';
}

export function extract(dllPath) {
  const buf = fs.readFileSync(dllPath), res = parsePeResources(buf);
  return res.map((r) => {
    const data = buf.subarray(r.off, r.off + r.size), kind = sniff(data);
    const e = { type: r.type, typeName: r.typeName, name: r.name, lang: r.lang, rva: r.rva, size: r.size, kind, sha256: crypto.createHash('sha256').update(data).digest('hex'), data };
    if (kind === 'png') Object.assign(e, pngInfo(data));
    return e;
  });
}

const safe = (s) => String(s).replace(/[^A-Za-z0-9_.-]/g, '_');
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [dll, outDir] = process.argv.slice(2);
  if (!dll || !outDir) { console.error('usage: node rsrc_extract.mjs <dll> <outDir>'); process.exit(2); }
  const items = extract(dll), index = [];
  for (const it of items) {
    const ext = it.kind.replace('?', ''), rel = `${safe(it.typeName)}/${safe(it.name)}_${it.lang}.${ext}`;
    fs.mkdirSync(path.join(outDir, path.dirname(rel)), { recursive: true });
    fs.writeFileSync(path.join(outDir, rel), it.data);
    const { data, ...meta } = it; index.push({ ...meta, file: rel });
  }
  fs.writeFileSync(path.join(outDir, 'index.json'), JSON.stringify(index, null, 1));
  const png = index.filter((e) => e.kind === 'png');
  console.log(`resources=${index.length} png=${png.length} pngBytes=${png.reduce((a, e) => a + e.size, 0)} totalBytes=${index.reduce((a, e) => a + e.size, 0)}`);
}
