// Plugin-database entry (.nfo, fileversion=2): model, reader (mirrors fle:0x910cd0 / 0x911e10) and writer (mirrors fle:0x911940 / 0x912d10 + 0x913f40).
// Keys are `ps_*` plus `_<n>` (file index) — see FORMAT.md. Browser-safe.
import { ValueFile, encodeText, decodeText } from './valuefile.ts';
import {
  guidFromString, guidToString, isNullGuid, NULL_GUID, scanFlagsFromDisk, scanFlagsToDisk, expandToken, compressToken,
  delimitedParse, delimitedFormat, slotOf, ARCH_NAMES,
} from './format.ts';

export interface PluginFile {
  /** ps_file_name_<i> — display name of this file */
  name: string;
  /** ps_file_filename_<i> — plugin binary path; `%FLPath%` prefix stands for the FL install dir */
  filename: string;
  /** ps_file_plugclass_<i>; -1 (absent) makes FL drop the file */
  plugclass: number;
  /** ps_file_type_<i>: only 1 or 2 survive the reader (others → 0) */
  type: number;
  /** ps_file_bitsize_<i>: 2 = 32-bit, 3 = 64-bit (anything but "64" reads as 32-bit) */
  bits: 2 | 3;
  /** ps_file_arch_<i> index into ARCH_NAMES (0 = none) */
  arch: number;
  /** ps_file_magic_<i> — VST2 uniqueID (u32; the text is the signed int32) */
  magic: number;
  /** ps_file_guid_<i> — 16 bytes (VST3 class id, `{…}` text); all-zero when absent */
  guid: Uint8Array;
  /** ps_file_date_<i> — int64 (scanner change detection; unit not determined) */
  date: bigint;
  /** ps_file_size_<i> — int64 file size in bytes */
  size: bigint;
  /** ps_file_scanflags_<i> in memory representation (disk 1,2,0x10,0x20 → 1,2,4,0x10; 8 = runtime "new") */
  scanflags: number;
  vendor: string;
  category: string;
  /** ps_file_idstring_<i> — CLAP plugin id */
  idstring: string;
  /** ps_compatibility_<i> — comma separated (TStrings.DelimitedText) */
  compat: string[];
}

export interface PluginEntry {
  /** fileversion: 1 = legacy ps_* single-file form, 2 = indexed form (writer always emits 2) */
  fileVersion: number;
  name: string;
  /** ps_presetfilename — the .fst (with `%FLPluginDBPath%` prefix when inside the DB) */
  presetFilename: string;
  files: PluginFile[];
}

export function newFile(p: Partial<PluginFile> & { plugclass: number }): PluginFile {
  return {
    name: '', filename: '', type: 0, bits: 3, arch: 0, magic: 0, guid: NULL_GUID.slice(), date: 0n, size: 0n,
    scanflags: 0, vendor: '', category: '', idstring: '', compat: [], ...p,
  };
}

export interface ReadCtx {
  /** FL install dir → expands `%FLPath%` in ps_file_filename (FL skips expansion when null) */
  flPath?: string;
  /** plugin database dir → expands `%FLPluginDBPath%` in ps_presetfilename */
  dbPath?: string;
  /** path of the .nfo itself; with `fallbackFst`, `<nfo without ext>.fst` is used when ps_presetfilename is empty (fle:0x910cd0 param_4) */
  nfoPath?: string;
  fallbackFst?: boolean;
  /** existence oracle for the fallback */
  exists?: (path: string) => boolean;
}

export interface ReadResult {
  entry?: PluginEntry;
  /** why FL would discard the entry (undefined when accepted) */
  dropped?: string;
  /** files FL silently drops from an otherwise accepted entry: [index, reason] */
  rejectedFiles: Array<[number, string]>;
}

const TYPE_OK = (t: number): boolean => t === 1 || t === 2; // fle mask byte 0x06

function fileKey(base: string, i: number): string {
  return `${base}_${i}`;
}

/** Mirrors FUN_00910cd0 (and the 911e10 variant that fills the same structure from an INI section). */
export function readEntry(vf: ValueFile, ctx: ReadCtx = {}): ReadResult {
  const rejectedFiles: Array<[number, string]> = [];
  const fileVersion = vf.getInt('fileversion', 1);
  const entry: PluginEntry = { fileVersion, name: vf.getString('ps_name'), presetFilename: vf.getString('ps_presetfilename'), files: [] };
  if (ctx.dbPath) entry.presetFilename = expandToken(entry.presetFilename, ctx.dbPath, '%FLPluginDBPath%');

  if (fileVersion === 1) {
    readLegacy(vf, entry, rejectedFiles);
  } else if (fileVersion === 2) {
    const n = vf.getInt('ps_files', 0);
    for (let i = 0; i < n; i++) {
      let filename = vf.getString(fileKey('ps_file_filename', i));
      if (ctx.flPath) filename = expandToken(filename, ctx.flPath, '%FLPath%');
      let type = vf.getInt(fileKey('ps_file_type', i), 0);
      if (!TYPE_OK(type)) type = 0;
      const archTxt = vf.getString(fileKey('ps_file_arch', i));
      const arch = Math.max(0, ARCH_NAMES.findIndex((a) => a.toUpperCase() === archTxt.toUpperCase()));
      const gtxt = vf.get(fileKey('ps_file_guid', i));
      const guid = gtxt === undefined || gtxt === '' ? NULL_GUID.slice() : (guidFromString(gtxt) ?? NULL_GUID.slice());
      const f: PluginFile = {
        name: vf.getString(fileKey('ps_file_name', i)),
        filename,
        plugclass: vf.getInt(fileKey('ps_file_plugclass', i), -1),
        type,
        bits: vf.getInt(fileKey('ps_file_bitsize', i), 32) === 64 ? 3 : 2,
        arch,
        magic: vf.getInt(fileKey('ps_file_magic', i), 0) | 0,
        guid,
        date: vf.getInt64(fileKey('ps_file_date', i), 0n),
        size: vf.getInt64(fileKey('ps_file_size', i), 0n),
        scanflags: scanFlagsFromDisk(vf.getInt(fileKey('ps_file_scanflags', i), 0)),
        vendor: vf.getString(fileKey('ps_file_vendorname', i)),
        category: vf.getString(fileKey('ps_file_category', i)),
        idstring: vf.getString(fileKey('ps_file_idstring', i)),
        compat: delimitedParse(vf.getString(fileKey('ps_compatibility', i))),
      };
      if (f.plugclass === -1) {
        rejectedFiles.push([i, 'ps_file_plugclass missing (-1)']);
        continue;
      }
      if (slotOf(f.plugclass, f.bits) < 0) {
        rejectedFiles.push([i, `no slot for class ${f.plugclass} / ${f.bits === 3 ? 64 : 32}-bit`]);
        continue;
      }
      entry.files.push(f);
    }
  } else {
    return { dropped: `unsupported fileversion ${fileVersion}`, rejectedFiles };
  }

  if (ctx.fallbackFst && !entry.presetFilename && ctx.nfoPath && ctx.exists) {
    const fst = ctx.nfoPath.replace(/\.[^.\\/]*$/, '') + '.fst';
    if (ctx.exists(fst)) entry.presetFilename = fst;
  }
  if (entry.files.length === 0) return { dropped: 'no usable file (FUN_008f5b40 == 0)', rejectedFiles };
  return { entry, rejectedFiles };
}

/** fileversion=1: one flat record (fle:0x910810). Produces up to 5 files from ps_pluginfilename_*. */
function readLegacy(vf: ValueFile, entry: PluginEntry, rejected: Array<[number, string]>): void {
  const vendor = vf.getString('ps_vendorname');
  const magic = vf.getInt('ps_magic', 0);
  const g = vf.get('ps_guid');
  const guid = g ? (guidFromString(g) ?? NULL_GUID.slice()) : NULL_GUID.slice();
  const cls = vf.getInt('ps_plugclass', 0);
  const category = vf.getString('ps_category');
  const scanflags = vf.getInt('ps_scanflags', 0);
  const isFx = cls >= 0 && cls < 0x10 && ((1 << cls) & 0x0a87) !== 0; // fle DAT_00910bca = 0x0a87
  const slots: Array<[string, number, number]> = [
    ['ps_pluginfilename_fl', 2, 2],
    ['ps_pluginfilename_vst_32', 0, 2],
    ['ps_pluginfilename_vst_64', 0, 3],
    ['ps_pluginfilename_vst3_32', 7, 2],
    ['ps_pluginfilename_vst3_64', 7, 3],
  ];
  for (const [key, baseCls, bits] of slots) {
    const path = vf.getString(key);
    if (!path) continue;
    const c = baseCls === 2 ? (isFx ? 2 : 3) : baseCls === 0 ? (isFx ? 0 : 4) : isFx ? 7 : 8;
    entry.files.push(newFile({ plugclass: c, bits: bits as 2 | 3, filename: path, magic, guid, vendor, category, scanflags: scanFlagsFromDisk(scanflags), name: entry.name }));
  }
  if (!entry.files.length) rejected.push([0, 'legacy record has no ps_pluginfilename_*']);
}

export interface WriteOpts {
  flPath?: string;
  dbPath?: string;
  /** "new plugin" decoration (iconindex/color/tip) FL adds when file 0 carries runtime flag 8 */
  newDecoration?: { tip: string };
}

/** Mirrors FUN_00911940 → FUN_00913f40. Returns a ValueFile with FL's key order and default-omission rules. */
export function writeEntry(entry: PluginEntry, opts: WriteOpts = {}): ValueFile {
  const vf = new ValueFile();
  const putStr = (k: string, v: string): void => { if (v !== '') vf.add(k, v); };
  const putInt = (k: string, v: number | bigint, def: number | bigint): void => { if (v !== def) vf.add(k, String(v)); };
  vf.add('fileversion', '2');
  if (entry.files.length && (entry.files[0].scanflags & 8) !== 0) {
    vf.add('iconindex', '48');
    vf.add('color', '$40B6F6');
    vf.add('tip', opts.newDecoration?.tip ?? '');
  }
  putStr('ps_name', entry.name);
  let preset = entry.presetFilename;
  if (opts.dbPath) preset = compressToken(preset, opts.dbPath, '%FLPluginDBPath%');
  putStr('ps_presetfilename', preset);
  putInt('ps_files', entry.files.length, 0);
  entry.files.forEach((f, i) => {
    const k = (b: string): string => fileKey(b, i);
    putStr(k('ps_file_name'), f.name);
    putStr(k('ps_file_filename'), opts.flPath ? compressToken(f.filename, opts.flPath, '%FLPath%') : f.filename);
    putInt(k('ps_file_plugclass'), f.plugclass, -1);
    putInt(k('ps_file_type'), f.type, 0);
    vf.add(k('ps_file_bitsize'), f.bits === 3 ? '64' : '32');
    putStr(k('ps_file_arch'), ARCH_NAMES[f.arch] ?? '');
    putInt(k('ps_file_magic'), f.magic | 0, 0);
    if (!isNullGuid(f.guid)) vf.add(k('ps_file_guid'), guidToString(f.guid));
    putInt(k('ps_file_date'), f.date, 0n);
    putInt(k('ps_file_size'), f.size, 0n);
    putInt(k('ps_file_scanflags'), scanFlagsToDisk(f.scanflags), 0);
    putStr(k('ps_file_vendorname'), f.vendor);
    putStr(k('ps_file_category'), f.category);
    putStr(k('ps_file_idstring'), f.idstring);
    putStr(k('ps_compatibility'), f.compat.length ? delimitedFormat(f.compat) : '');
  });
  return vf;
}

export function entryToBytes(entry: PluginEntry, opts?: WriteOpts): Uint8Array {
  return encodeText(writeEntry(entry, opts).toString());
}

export function entryFromBytes(b: Uint8Array, ctx?: ReadCtx): ReadResult {
  return readEntry(ValueFile.parse(decodeText(b)), ctx);
}

/** `Plugins\Fruity\{Effects|Generators}\<dir>\Plugin.nfo` (fle:0xabe970): only these two keys are read. `ps_dummy64bit=1` marks a plugin whose _x64.dll is a stand-in. */
export function readNativePluginNfo(vf: ValueFile): { vendor: string; dummy64bit: boolean } {
  return { vendor: vf.getString('ps_vendorname'), dummy64bit: vf.getInt('ps_dummy64bit', 0) !== 0 };
}
