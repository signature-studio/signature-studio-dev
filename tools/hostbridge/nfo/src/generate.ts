// Synthetic Plugin-database generator: plugin list (JSON) → Presets/Plugin database/Installed/** files (.nfo / .fst / VerifiedIDs.nfo).
// Replaces what PluginManager.exe's scan writes. Layout/semantics: FORMAT.md §4. Browser-safe (returns a Map of path → bytes).
import { newFile, writeEntry, type PluginEntry, type PluginFile } from './entry.ts';
import { ValueFile, encodeText } from './valuefile.ts';
import { buildWrapperFst } from './fst.ts';
import {
  FAMILY_DIR, familyOf, isGenClass, classVariant, sanitizeName, tuidFromHex, vst2PseudoGuid, guidToString, isNullGuid, scanFlagsFromDisk, type Family,
} from './format.ts';

export interface PluginSpec {
  name: string;
  vendor: string;
  format: 'vst2' | 'vst3' | 'clap';
  kind: 'effect' | 'generator';
  /** virtual path of the plugin binary as the Fruity Wrapper will LoadLibrary it */
  path: string;
  bits?: 32 | 64;
  /** vst2: uniqueID as u32 or 4-char string ('XfTT') */
  magic?: number | string;
  /** vst3: class id as 32 hex chars (moduleinfo.json "CID" / FUID::toString, raw TUID memory order) */
  guid?: string;
  /** clap: plugin id string */
  clapId?: string;
  category?: string;
  /** file size / timestamp recorded for the scanner's change detection (0 = omitted) */
  size?: number;
  date?: number;
  /** ps_file_type override: 1 = effect, 2 = generator, 0 = decided by class (default) */
  type?: 0 | 1 | 2;
  /** ps_file_scanflags (disk representation); default 1 */
  scanflags?: number;
  compat?: string[];
}

export interface GenOptions {
  /** Windows-style path of the `Presets\Plugin database` dir as FL sees it (used for %FLPluginDBPath% compression) */
  dbPath?: string;
  /** FL install dir for %FLPath% compression of ps_file_filename */
  flPath?: string;
  /** write Installed/VerifiedIDs.nfo (default true) */
  verifiedIds?: boolean;
}

export const DEFAULT_DB_PATH = 'C:\\Users\\Public\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database';

export interface GenResult {
  /** path relative to the Plugin database dir, forward slashes */
  files: Map<string, Uint8Array>;
  entries: Array<{ spec: PluginSpec; nfo: string; fst: string; entry: PluginEntry }>;
}

export function magicOf(m: number | string | undefined): number {
  if (m === undefined) return 0;
  if (typeof m === 'number') return m | 0;
  if (m.length !== 4) throw new Error(`VST2 magic string must be 4 chars: ${m}`);
  return ((m.charCodeAt(0) << 24) | (m.charCodeAt(1) << 16) | (m.charCodeAt(2) << 8) | m.charCodeAt(3)) | 0;
}

function plugclassOf(s: PluginSpec): number {
  const gen = s.kind === 'generator';
  const fx = s.format === 'vst2' ? 0 : s.format === 'vst3' ? 7 : 11;
  return classVariant(!gen, fx);
}

function fileOf(s: PluginSpec): PluginFile {
  const cls = plugclassOf(s);
  return newFile({
    name: s.name,
    filename: s.path,
    plugclass: cls,
    type: s.type ?? 0,
    bits: (s.bits ?? 64) === 32 ? 2 : 3,
    magic: s.format === 'vst2' ? magicOf(s.magic) : 0,
    guid: s.format === 'vst3' ? tuidFromHex(s.guid ?? '') : new Uint8Array(16),
    size: BigInt(s.size ?? 0),
    date: BigInt(s.date ?? 0),
    scanflags: scanFlagsFromDisk(s.scanflags ?? 1),
    vendor: s.vendor,
    category: s.category ?? '',
    idstring: s.format === 'clap' ? (s.clapId ?? '') : '',
    compat: s.compat ?? [],
  });
}

function installedDir(s: PluginSpec): string {
  const fam: Family = familyOf(plugclassOf(s))!;
  return `Installed/${isGenClass(plugclassOf(s)) ? 'Generators' : 'Effects'}/${FAMILY_DIR[fam]}`;
}

/** VerifiedIDs.nfo key: `<VST|VST3|CLAP>:<id>:<32|64>`; id = GUID text for VST2 (pseudo-GUID) / VST3, CLAP id string. (key shape fle:0x8f16d0 = certain; id text per format = inferred) */
function verifiedKey(s: PluginSpec, f: PluginFile): string {
  const fam = s.format === 'vst2' ? 'VST' : s.format === 'vst3' ? 'VST3' : 'CLAP';
  let id: string;
  if (s.format === 'vst3') id = guidToString(f.guid);
  else if (s.format === 'vst2') id = guidToString(vst2PseudoGuid(s.name, f.magic, false));
  else id = f.idstring;
  return `${fam}:${id}:${f.bits === 3 ? '64' : '32'}`;
}

export function generateDb(specs: PluginSpec[], opts: GenOptions = {}): GenResult {
  const dbPath = opts.dbPath ?? DEFAULT_DB_PATH;
  const files = new Map<string, Uint8Array>();
  const entries: GenResult['entries'] = [];
  const verified = new ValueFile();
  const groups = new Map<string, PluginSpec[]>();
  for (const s of specs) {
    const k = `${installedDir(s)}/${sanitizeName(s.name)}`;
    const g = groups.get(k);
    if (g) g.push(s);
    else groups.set(k, [s]);
  }
  for (const [base, group] of groups) {
    const first = group[0];
    const pf = group.map(fileOf);
    const fstRel = `${base}.fst`;
    const nfoRel = `${base}.nfo`;
    const entry: PluginEntry = {
      fileVersion: 2,
      name: first.name,
      presetFilename: `${dbPath}\\${fstRel.replace(/\//g, '\\')}`,
      files: pf,
    };
    const has32 = pf.some((f) => f.bits === 2);
    const has64 = pf.some((f) => f.bits === 3);
    const single = pf.length === 1;
    const fst = buildWrapperFst({
      plugclass: pf[0].plugclass,
      displayName: first.name,
      filename: single ? pf[0].filename : '',
      vendor: pf[0].vendor,
      magic: pf[0].magic,
      guid: isNullGuid(pf[0].guid) ? undefined : pf[0].guid,
      idstring: pf[0].idstring,
      has32,
      has64,
    });
    files.set(fstRel, fst);
    files.set(nfoRel, encodeText(writeEntry(entry, { dbPath, flPath: opts.flPath }).toString()));
    entries.push({ spec: first, nfo: nfoRel, fst: fstRel, entry });
    if (opts.verifiedIds !== false) {
      group.forEach((s, i) => {
        const key = verifiedKey(s, pf[i]);
        // FL: ChangeFileExt(<fst>, ".NFO"), path relative to Installed\ (fle:0xabb500 + 0x8f15a0)
        verified.add(key, nfoRel.slice('Installed/'.length).replace(/\.nfo$/, '.NFO').replace(/\//g, '\\'));
      });
    }
  }
  if (opts.verifiedIds !== false && verified.lines.length) files.set('Installed/VerifiedIDs.nfo', encodeText(verified.toString()));
  return { files, entries };
}
