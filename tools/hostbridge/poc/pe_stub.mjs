// pe_stub.mjs — 仮想 FS 用の最小 PE32+ DLL スタブ生成 (export directory のみ). HOSTBRIDGE.md §2.2 R6.
//   Fruity Wrapper は LoadLibrary 前に DLL *ファイル*を読む: export 名検査 (fw:0x5c0200) と bitness 判定 (fw:0x5bfc30)。
//   スタブは検査専用 (LoadLibrary は module 表を引く)。使い方: node pe_stub.mjs <out.dll> <exportName...>
import fs from 'node:fs';

export function makePeStub(exportNames, dllName = 'plugin_x64.dll') {
  const names = [...exportNames].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)); // PE は名前昇順
  const FA = 0x200, SECRVA = 0x1000;
  const buf = Buffer.alloc(FA * 2);
  const w16 = (o, v) => buf.writeUInt16LE(v, o), w32 = (o, v) => buf.writeUInt32LE(v, o), w64 = (o, v) => buf.writeBigUInt64LE(BigInt(v), o);
  buf.write('MZ', 0, 'latin1'); w32(0x3c, 0x40);
  buf.write('PE\0\0', 0x40, 'latin1');
  w16(0x44, 0x8664); w16(0x46, 1); w32(0x48, 0x5f000000); w16(0x54, 0xf0); w16(0x56, 0x2022);
  const O = 0x58; // optional header
  w16(O, 0x20b); w32(O + 0x10, SECRVA + 0x100 /* entry (dummy) */); w64(O + 0x18, 0x180000000n);
  w32(O + 0x20, 0x1000); w32(O + 0x24, 0x200); w16(O + 0x28, 6); w16(O + 0x30, 6); w32(O + 0x38, 0x2000); w32(O + 0x3c, 0x200); w16(O + 0x44, 2);
  w64(O + 0x48, 0x100000); w64(O + 0x50, 0x1000); w64(O + 0x58, 0x100000); w64(O + 0x60, 0x1000); w32(O + 0x6c, 16);
  // section .edata
  const S = O + 0xf0;
  buf.write('.edata', S, 'latin1'); w32(S + 8, 0x200); w32(S + 12, SECRVA); w32(S + 16, FA); w32(S + 20, FA); w32(S + 36, 0x40000040);
  // export directory @ file FA / RVA SECRVA
  const E = FA, n = names.length;
  const rva = (o) => SECRVA + (o - FA);
  const afOff = E + 40, anOff = afOff + 4 * n, aoOff = anOff + 4 * n;
  let str = aoOff + 2 * n;
  const nameRvas = [];
  const dn = str; buf.write(dllName + '\0', str, 'latin1'); str += dllName.length + 1;
  for (const nm of names) { nameRvas.push(rva(str)); buf.write(nm + '\0', str, 'latin1'); str += nm.length + 1; }
  w32(E + 12, rva(dn)); w32(E + 16, 1); w32(E + 20, n); w32(E + 24, n); w32(E + 28, rva(afOff)); w32(E + 32, rva(anOff)); w32(E + 36, rva(aoOff));
  names.forEach((_, i) => { w32(afOff + 4 * i, SECRVA + 0x100); w32(anOff + 4 * i, nameRvas[i]); w16(aoOff + 2 * i, i); });
  // data directory[0] = export
  w32(O + 0x70, SECRVA); w32(O + 0x74, str - E);
  return buf;
}

if (process.argv[1] && process.argv[1].endsWith('pe_stub.mjs') && process.argv.length > 3) {
  fs.writeFileSync(process.argv[2], makePeStub(process.argv.slice(3), process.argv[2].split('/').pop()));
}
