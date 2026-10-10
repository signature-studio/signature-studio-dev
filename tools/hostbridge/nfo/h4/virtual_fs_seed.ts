// virtual_fs_seed.ts — CAB-216 (HB-H4'): `generateDb()` の出力を pathreg 経由で仮想 FS (wvfs) に書く結線、
// および書戻し読みの監査。FL 側コードは無改変 (FL 自身の reader fle:0x910cd0 / 0xaba430 が読む)。
//
//   const gen = generateDb(specs, { dbPath: pluginDbRootWin(seed) });
//   const router = createPathRouter();
//   const manifest = await seedPluginDb({ wvfs: home, router, dbRootWin, gen, sha256 });
//   const back = await readBackPluginDb({ wvfs: home, router, manifest, sha256 });
//   const audit = auditReadBack(back.files, gen);
//
// browser-safe: `node:` import を一切持たない (nfo_e2e.sh の browser-safety step と同じ規約)。
// Wvfs / pathreg pathmap / tools/flp / hostbridge/nfo/src は全て読取のみ参照。
import { Wvfs } from '../../../assets/wvfs/wvfs.ts';
import type { WvfsBackend } from '../../../assets/wvfs/wvfs.ts';
import { createPathRouter, HOME_MOUNT, TMP_MOUNT } from '../../../assets/wvfs/pathlink.ts';
import type { PathRouter, Route } from '../../../assets/wvfs/pathlink.ts';
import { generateDb, DEFAULT_DB_PATH, type GenResult, type GenOptions, type PluginSpec } from '../src/generate.ts';
import { entryFromBytes } from '../src/entry.ts';
import { ValueFile, decodeText } from '../src/valuefile.ts';
import { IniFile } from '../src/ini.ts';
import { parseFlp, writeFlp, firstDiff } from '../../../flp/src/flp.ts';
import { parseWrapperData } from '../../../flp/src/summary.ts';
import { guidToString, tuidFromHex } from '../src/format.ts';

export { HOME_MOUNT, TMP_MOUNT };

/** vreg seed (tools/startup/data/vreg_seed.json, build_seed.py 生成) の読み取りに必要な部分だけ。 */
export interface VregSeed {
  HKCU?: Record<string, Record<string, { t: string; v: unknown }>>;
  HKLM?: Record<string, Record<string, { t: string; v: unknown }>>;
  _known_folders?: Record<string, string>;
  _env?: Record<string, string>;
}

export const SHARED_PATHS_KEY = 'Software\\Image-Line\\Shared\\Paths';
export const SHARED_DATA_NAME = 'Shared data';
/** FL が browser root 0x3fe に登録するユーザ DB の下位パス (FORMAT.md §1 / fle:0x9db5b0)。 */
export const FL_PRESET_DB_SUBPATH = 'FL Studio\\Presets\\Plugin database';

export function seedValue(seed: VregSeed, hive: 'HKCU' | 'HKLM', key: string, name: string): string | null {
  const v = seed[hive]?.[key]?.[name]?.v;
  return typeof v === 'string' ? v : null;
}

/** `Shared data` 値 (vreg seed HKCU)。FL のユーザデータ root = `<Shared data>`。 */
export function sharedDataDirWin(seed: VregSeed): string {
  const v = seedValue(seed, 'HKCU', SHARED_PATHS_KEY, SHARED_DATA_NAME);
  if (!v) throw new Error('vreg seed: HKCU ' + SHARED_PATHS_KEY + '\\' + SHARED_DATA_NAME + ' が無い');
  return v;
}

/** 仮想 FS に DB を置く Win パス (`<Shared data>FL Studio\Presets\Plugin database`)。
 *  実機の実値 (analysis/real_fst_check.mjs のサンプル出所) = `%USERPROFILE%\Documents\Image-Line\FL Studio\Presets\Plugin database`。 */
export function pluginDbRootWin(seed: VregSeed): string {
  return sharedDataDirWin(seed).replace(/[\\/]+$/, '') + '\\' + FL_PRESET_DB_SUBPATH;
}

// ---------------------------------------------------------------- manifest

export interface DbFile {
  /** generateDb の files Map キー (`Installed/…`・`/` 区切り) */
  rel: string;
  /** FL が見る Win 絶対パス (`<dbRootWin>\Installed\…`) */
  win: string;
  /** pathreg が振った mount ('home' / 'tmp') */
  mount: string;
  /** mount ルート基準の絶対パス (`/Documents/Image-Line/…`) */
  path: string;
  size: number;
  sha256: string;
}

export interface SeedResult {
  files: DbFile[];
  /** dbRootWin の経路 (mount / path) */
  root: Route;
  /** generateDb が受けた dbPath (= 圧縮に使う win パス) */
  dbRootWin: string;
  journal: { journalId: number; journalBytes: number; liveBytes: number; files: number; dirs: number; fds: number } | null;
}

type Sha = (b: Uint8Array) => Promise<string> | string;

async function sha(o: { sha256: Sha }, b: Uint8Array): Promise<string> {
  return await o.sha256(b);
}

/** generateDb の出力を pathreg 経由で wvfs に書く (mkdirp + writeFileSync)。flush は呼出側 (onYield/onPageHide)。 */
export async function seedPluginDb(o: {
  wvfs: Wvfs;
  router?: PathRouter;
  dbRootWin: string;
  gen: GenResult;
  sha256: Sha;
  /** 書込をスキップする相対パス (ネガティブコントロール用。既定なし) */
  skip?: (rel: string) => boolean;
}): Promise<SeedResult> {
  const router = o.router ?? createPathRouter();
  const root = router.route(o.dbRootWin);
  if (!root) throw new Error(`dbRoot が pathreg の書込対象外: ${o.dbRootWin} (raw=${router.mapRaw(o.dbRootWin)})`);
  const files: DbFile[] = [];
  for (const [rel, bytes] of o.gen.files) {
    const win = `${o.dbRootWin}\\${rel.replace(/\//g, '\\')}`;
    const r = router.route(win);
    if (!r) throw new Error(`経路失敗 (書込対象外): ${win} (raw=${router.mapRaw(win)})`);
    if (o.skip?.(rel)) continue;
    const dir = r.path.slice(0, r.path.lastIndexOf('/'));
    o.wvfs.mkdirpSync(dir);
    o.wvfs.writeFileSync(r.path, bytes);
    files.push({ rel, win, mount: r.mount, path: r.path, size: bytes.length, sha256: await sha(o, bytes) });
  }
  return { files, root, dbRootWin: o.dbRootWin, journal: o.wvfs.debugState() };
}

export interface ReadBackResult {
  files: Map<string, Uint8Array>;
  mismatches: string[];
  /** 大文字小文字を変えた読み (FL の `.NFO`/`.FST` 大文字探索相当) が一致した件数 */
  caseOk: number;
  /** 読めたが期待に無いファイル (DB ツリー全域 walk) */
  extra: string[];
  /** DB root の一覧 (Installed の direct child) */
  dbRootEntries: string[];
}

/** wvfs から読み戻す。manifest のパス ( mount 相対 ) をそのまま使う。 */
export async function readBackPluginDb(o: {
  wvfs: Wvfs;
  manifest: DbFile[];
  sha256: Sha;
  /** このパスの配下を readdir して余剰ファイルを探す (mount 相対) */
  dbRootPath: string;
  /** FL の大文字探索相当: パスを大文字化して読み直すか */
  caseVariants?: boolean;
}): Promise<ReadBackResult> {
  const files = new Map<string, Uint8Array>();
  const mismatches: string[] = [];
  let caseOk = 0;
  for (const f of o.manifest) {
    let data: Uint8Array;
    try {
      data = o.wvfs.readFileSync(f.path);
    } catch (e) {
      mismatches.push(`${f.rel}: read failed (${String(e)})`);
      continue;
    }
    if (data.length !== f.size) mismatches.push(`${f.rel}: size ${data.length}/${f.size}`);
    const got = await sha(o, data);
    if (got !== f.sha256) mismatches.push(`${f.rel}: sha256 ${got.slice(0, 12)}/${f.sha256.slice(0, 12)}`);
    files.set(f.rel, data);
    if (o.caseVariants !== false) {
      const upper = f.path.toUpperCase();
      if (upper !== f.path) {
        try {
          const up = o.wvfs.readFileSync(upper);
          if ((await sha(o, up)) === f.sha256) caseOk++;
          else mismatches.push(`${f.rel}: case-variant (${upper}) は中身不一致`);
        } catch (e) {
          mismatches.push(`${f.rel}: case-variant read failed (${String(e)})`);
        }
      }
    }
  }
  // DB ツリー全域 walk (余剰ファイルの検出)
  const found: string[] = [];
  const walk = (p: string): void => {
    for (const n of o.wvfs.readdirSync(p).sort()) {
      const c = p === '/' ? `/${n}` : `${p}/${n}`;
      const st = o.wvfs.statSync(c);
      if (st?.type === 'dir') walk(c);
      else found.push(c);
    }
  };
  try {
    walk(o.dbRootPath);
  } catch {
    mismatches.push(`dbRoot が読めない: ${o.dbRootPath}`);
  }
  const expected = new Set(o.manifest.map((f) => f.path));
  const extra = found.filter((p) => !expected.has(p));
  const dbRootEntries = o.wvfs.readdirSync(o.dbRootPath).sort();
  return { files, mismatches, caseOk, extra, dbRootEntries };
}

// ---------------------------------------------------------------- audit (nfo reader + flp parser)

export interface Audit {
  /** manifest に含まれる `.nfo` ファイル数 (VerifiedIDs.nfo は value file だが entry ではないので別数) */
  nfoFiles: number;
  /** entry .nfo を reader 模型 (fle:0x910cd0 準拠) が受理した件数 */
  nfoAccepted: number;
  /** 受理しなかった件数 (rejectedFiles が 1 つでもあれば非受理) */
  nfoRejected: number;
  /** 受理エントリの総ファイル数 (ps_files の和) */
  acceptedFiles: number;
  /** entry .nfo のうち reader が「1 件も残らず破棄」とした件数 */
  nfoDropped: number;
  /** `.fst` を tools/flp parseFlp が読めた件数 */
  fstParsed: number;
  /** parseFlp → writeFlp の lossless 往復が byte 一致した件数 */
  fstRoundTrip: number;
  /** 213 wrapper chunk を parseWrapperData が受理し path が spec.path と一致した件数 */
  fstWrapperPath: number;
  /** 203 (表示名) が entry 名と一致した件数 */
  fstName203: number;
  /** .Plugins.ini セクション数 (nfo 本編と verbatim 一致を別カウント) */
  iniSections: number;
  iniSectionsVerbatim: number;
  /** VerifiedIDs.nfo キー数 */
  verifiedKeys: number;
  /** plugclass 別の entry 数 (family フォルダと整合) */
  byFamily: Record<string, number>;
  /** dbPath を DEFAULT_DB_PATH にしても .nfo/.fst バイト列が不変 (圧縮トークン同一) */
  bytesInvariantToDbPath: boolean;
  /** 監査で拾った異常 */
  problems: string[];
}

/** 読戻しバイト列に対して、FL 側 reader 模型 + tools/flp 独立パーサで round-trip 監査する。 */
export function auditReadBack(files: Map<string, Uint8Array>, gen: GenResult): Audit {
  const problems: string[] = [];
  const a: Audit = {
    nfoFiles: 0, nfoAccepted: 0, nfoRejected: 0, acceptedFiles: 0, nfoDropped: 0,
    fstParsed: 0, fstRoundTrip: 0, fstWrapperPath: 0, fstName203: 0,
    iniSections: 0, iniSectionsVerbatim: 0, verifiedKeys: 0, byFamily: {},
    bytesInvariantToDbPath: true, problems,
  };
  for (const e of gen.entries) {
    a.nfoFiles++;
    const bytes = files.get(e.nfo);
    if (!bytes) { problems.push(`${e.nfo}: 読戻しに無い`); a.nfoRejected++; continue; }
    const r = entryFromBytes(bytes, { dbPath: DEFAULT_DB_PATH });
    if (r.entry) {
      a.nfoAccepted++;
      a.acceptedFiles += r.entry.files.length;
      const f = r.entry.files[0];
      if (r.entry.name !== e.spec.name) problems.push(`${e.nfo}: ps_name ${r.entry.name} != ${e.spec.name}`);
      if (f.filename !== e.spec.path) problems.push(`${e.nfo}: filename ${f.filename} != ${e.spec.path}`);
      if (e.spec.format === 'vst3') {
        if (guidToString(f.guid) !== guidToString(tuidFromHex(e.spec.guid!))) problems.push(`${e.nfo}: CID 不一致`);
      }
      const fam = e.nfo.replace(/^Installed\//, '').replace(/\\/g, '/').split('/')[0];
      const sub = fam + '/' + e.nfo.replace(/^Installed\//, '').replace(/\\/g, '/').split('/')[1];
      a.byFamily[sub] = (a.byFamily[sub] ?? 0) + 1;
    } else {
      a.nfoDropped++;
      problems.push(`${e.nfo}: dropped (${r.dropped})`);
    }
    if (r.rejectedFiles.length) a.nfoRejected++;
    // .fst: tools/flp independent parser
    const fstBytes = files.get(e.fst);
    if (!fstBytes) { problems.push(`${e.fst}: 読戻しに無い`); continue; }
    const fl = parseFlp(fstBytes);
    a.fstParsed++;
    if (firstDiff(fstBytes, writeFlp(fl)) === -1) a.fstRoundTrip++;
    else problems.push(`${e.fst}: parseFlp→writeFlp が byte 不一致`);
    const ev213 = fl.events.find((x) => x.id === 213);
    const ev203 = fl.events.find((x) => x.id === 203);
    if (ev213) {
      const w = parseWrapperData(ev213.data);
      if (w && w.path === e.spec.path) a.fstWrapperPath++;
      else problems.push(`${e.fst}: wrapper chunk path=${w?.path} != ${e.spec.path}`);
    } else problems.push(`${e.fst}: event 213 が無い`);
    if (ev203) {
      const n = new TextDecoder('utf-16le').decode(ev203.data).replace(/\0+$/, '');
      if (n === e.spec.name) a.fstName203++;
      else problems.push(`${e.fst}: event 203 = ${n} != ${e.spec.name}`);
    }
  }
  // VerifiedIDs.nfo
  const vids = files.get('Installed/VerifiedIDs.nfo');
  if (vids) {
    const vf = ValueFile.parse(decodeText(vids));
    a.verifiedKeys = vf.lines.length;
    for (const e of gen.entries) {
      // FL: ChangeFileExt(<fst>, ".NFO"), path relative to Installed\ (fle:0xabb500 + 0x8f15a0)
      const rel = e.nfo.slice('Installed/'.length).replace(/\.nfo$/, '.NFO').replace(/\//g, '\\');
      const found = vf.lines.some((l: string) => {
        const p = l.indexOf('=');
        return p > 0 && l.slice(p + 1).toUpperCase() === rel.toUpperCase();
      });
      if (!found) problems.push(`VerifiedIDs: ${rel} が参照されていない`);
    }
  } else problems.push('Installed/VerifiedIDs.nfo が無い');
  // .Plugins.ini: セクション本編 = .nfo 本編 (fle:0x912d10)
  const iniBytes = files.get('Installed/.Plugins.ini');
  if (iniBytes) {
    const ini = IniFile.fromBytes(iniBytes);
    a.iniSections = ini.sections.length;
    for (const e of gen.entries) {
      const sec = ini.get(e.nfo.replace(/^Installed\//, '').replace(/\.nfo$/, '').replace(/\//g, '\\'));
      const nfoLines = files.get(e.nfo) ? ValueFile.parse(decodeText(files.get(e.nfo)!)).lines : [];
      if (sec && sec.lines.length === nfoLines.length && sec.lines.every((l: string, i: number) => l === nfoLines[i])) a.iniSectionsVerbatim++;
      else problems.push(`${e.nfo}: ini セクションと不一致`);
    }
  } else problems.push('Installed/.Plugins.ini が無い');
  return a;
}

/** dbPath を差し替えても生成バイト列が不変かを調べる (`%FLPluginDBPath%` 圧縮の結果が同じことの確認)。 */
export function bytesInvariantToDbPath(specs: PluginSpec[], dbRootWin: string): boolean {
  const a = generateDb(specs, { dbPath: DEFAULT_DB_PATH });
  const b = generateDb(specs, { dbPath: dbRootWin });
  if (a.files.size !== b.files.size) return false;
  for (const [k, v] of a.files) {
    const w = b.files.get(k);
    if (!w || w.length !== v.length || !w.every((x: number, i: number) => x === v[i])) return false;
  }
  return true;
}

// ---------------------------------------------------------------- registry consistency

export interface RegistryCheck {
  sharedData: string;
  personal: string | null;
  userProfile: string | null;
  dbRootWin: string;
  dbRootRoute: Route | null;
  dbRootRaw: string | null;
  sharedDataRoute: Route | null;
  /** vreg seed の `Shared data` 親フォルダと pathreg の既定 profile が一致するか */
  profileMatchesPathreg: boolean;
  /** DEFAULT_DB_PATH (= Public Documents) は pathreg の書込対象外であること */
  defaultDbPathRoutable: boolean;
  flEnginePath: string | null;
  /** vreg seed のキー集合 (Image-Line 配下) */
  imageLineKeys: string[];
}

/** vreg seed と pathreg 既定表・generateDb の DB root の整合を調べる。 */
export function registryConsistency(seed: VregSeed, router?: PathRouter): RegistryCheck {
  const r = router ?? createPathRouter();
  const sharedData = sharedDataDirWin(seed);
  const dbRootWin = pluginDbRootWin(seed);
  const personal = seed._known_folders?.['CSIDL_PERSONAL(5)'] ?? null;
  const userProfile = seed._env?.USERPROFILE ?? null;
  const keys = new Set<string>();
  for (const hive of ['HKCU', 'HKLM'] as const) {
    for (const k of Object.keys(seed[hive] ?? {})) if (/^Software\\?Image-Line/i.test(k)) keys.add(k);
  }
  return {
    sharedData,
    personal,
    userProfile,
    dbRootWin,
    dbRootRoute: r.route(dbRootWin),
    dbRootRaw: r.mapRaw(dbRootWin),
    sharedDataRoute: r.route(sharedData),
    // `<Shared data>` = `<personal>\Image-Line\` かつ personal の親が USERPROFILE と一致 = pathreg 既定 profile と同一人物
    profileMatchesPathreg:
      sharedData.replace(/[\\/]+$/, '').toLowerCase() === (personal ?? '').replace(/[\\/]+$/, '').toLowerCase() + '\\image-line' &&
      (userProfile ?? '').toLowerCase() === (personal ?? '').replace(/[\\/]+$/, '').toLowerCase().replace(/\\[^\\]*$/, ''),
    defaultDbPathRoutable: r.route(DEFAULT_DB_PATH) !== null,
    flEnginePath: seedValue(seed, 'HKCU', SHARED_PATHS_KEY, 'FL Studio engine'),
    imageLineKeys: [...keys].sort(),
  };
}

export type { Wvfs, WvfsBackend, PathRouter, Route, GenResult, PluginSpec, GenOptions };
export { createPathRouter, generateDb, entryFromBytes, ValueFile };
