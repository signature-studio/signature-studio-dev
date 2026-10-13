// glue_host.ts — startup-glue のホスト (JS/TS) 側結線規約 (CAB-101 / ST-T1)。
//
// 規約 (C 側 glue.c と同じ順序。C は順序違反を GLUE_EORDER で検出する):
//   1 paths      : pathreg マウント表 + マッパ登録        (C: glue_stage_paths / wasm: pathreg_install)
//   2 registry   : vreg seed import + flush フック       (RegBridge.create)
//   3 pump       : RING 起動 + 時計較正                   (C: glue_stage_pump / host: PumpRing + 較正)
//   4 vfs        : wvfs mount (/c/home・/c/tmp・/fl)      (Wvfs.open + FS.mount)
//   5 pre_dllmain: cmdline 投入 (URL クエリ由来)
//   6 dllmain    : m11 closure (未結線)
//   7 host       : THostInstance 生成                     (C: glue_stage_host)
//   8 boot       : CreateFruityInstance 呼出             (C: glue_stage_boot, スタブ)
//   9 post       : iface 検証・run 入口
//  10 shutdown   : flush (onYield/onPageHide) + syncfs + trace dump
//
// 各段階は独立に呼べる (`await host.stagePump()` 等)。runAll() は規約順に全部呼ぶ。
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';

// --- 読取専用 component の結線 (import するだけ・変更はしない) ---
import { Wvfs, NodeBackend, HOME_MOUNT, TMP_MOUNT, WVFS_ROOT } from '../../../assets/wvfs/index.ts';
import { createWvfsFs } from '../../../assets/wvfs/emscripten-wvfs.ts';
import { RegBridge } from '../../../shimx/pathreg/js/regbridge.mjs';
import { createMapper, DEFAULT_PATHS } from '../../../shimx/pathreg/js/pathmap.mjs';
import { MemoryStore, FileStore } from '../../vreg/js/store.mjs';

const require_ = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
export const GLUE_DIR = path.resolve(HERE, '..');                     // tools/startup/glue
export const REPO = path.resolve(GLUE_DIR, '../../..');               // tools/startup/glue → repo root

/** createFruityInstance の差し替え口 (JS)。host=THostInstance アドレス、
 *  ifaceSlot = *iface を書く wasm 内 int32 スロットのアドレス。戻り = exit code。 */
export type CreateFruityJs = (host: number, ifaceSlot: number) => number;

export interface GlueHostOptions {
  /** 既定 "webstudio" (パス表の C:\Users\<username> と vreg seed の両方に効く) */
  username?: string;
  /** レジストリ永続ストア (node: FileStore / browser: IdbStore) */
  store?: { load(p: string): Promise<any>; save(p: string, rec: any): Promise<void>; delete(p: string): Promise<void> };
  profile?: string;
  /** wvfs の実体を置く dir (node: 実ディスク。browser では OPFS なので未使用) */
  workDir?: string;
  /** pump 待機モード (-1 = 既定) */
  waitMode?: number;
  /** FL boot 貫通後は m11 の export 解決結果をここに渡す (未達の間は C 側スタブ) */
  createFruity?: CreateFruityJs;
  /** `fldiagnostic /restartfl` 検知時 (G12)。flush 後に 1 回だけ呼ぶ。browser = location.reload() */
  onRestart?: () => void | Promise<void>;
}

export interface StageRecord { id: number; name: string; ms: number; ok: boolean; detail?: string; }

/** worker_pump.ts (RING ABI の正本) を tsc でトランスパイルして node から import する (pump e2e と同じ方式) */
let _pumpRingMjs: string | null = null;
export function ensurePumpRingMjs(): string {
  if (_pumpRingMjs) return _pumpRingMjs;
  const out = path.join(GLUEDIR(), 'work/worker_pump.mjs');
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const cp = require_('node:child_process');
  const src = path.join(REPO, 'src/runtime/worker_pump.ts');
  const tmp = path.join(GLUEDIR(), 'work/tmp/wp_ts');
  const tsc = path.join(REPO, 'node_modules/typescript/bin/tsc');
  cp.execFileSync(process.execPath, [tsc, src, '--ignoreConfig', '--outDir', tmp, '--module', 'esnext', '--target', 'es2022'], { stdio: 'pipe' });
  fs.copyFileSync(path.join(tmp, 'worker_pump.js'), out);
  return (_pumpRingMjs = out);
}
function GLUEDIR() { return GLUE_DIR; }

/** username を反映した PathRouter 同等のオブジェクト。
 *  wvfs の createPathRouter は既定 username (webstudio) 固定なので、ここでは
 *  pathreg ミラー (pathmap.mjs) の createMapper({paths}) を使って自前で組み立てる
 *  (pathlink.ts / pathmap.mjs は読取専用)。pick ロジックは pathlink.ts と同一。 */
export function makeRouter(username: string) {
  const paths = { ...DEFAULT_PATHS, userProfile: `C:\\Users\\${username}` };
  const mapper = createMapper({ paths });
  const home = HOME_MOUNT.replace(/\/+$/, '');
  const tmp = TMP_MOUNT.replace(/\/+$/, '');
  const pick = (t: string): { mount: 'home' | 'tmp'; path: string } | null => {
    if (t === home || t.startsWith(home + '/')) return { mount: 'home', path: t.slice(home.length) || '/' };
    if (t === tmp || t.startsWith(tmp + '/')) return { mount: 'tmp', path: t.slice(tmp.length) || '/' };
    return null;
  };
  return {
    route: (winPath: string) => { const t = mapper.map(winPath); return t ? pick(t) : null; },
    mapRaw: (winPath: string) => mapper.map(winPath),
    mounts: { home, tmp },
  };
}

export async function loadSeed(): Promise<any> {
  return JSON.parse(fs.readFileSync(path.join(GLUEDIR(), '../vreg/data/seed.json'), 'utf8'));
}

export class GlueHost {
  mod: any;
  o: Required<GlueHostOptions>;
  stages: StageRecord[] = [];
  orderViolations = 0;
  pumpModeReq = -1;
  reg: RegBridge | null = null;
  home: Wvfs | null = null;
  tmp: Wvfs | null = null;
  router: ReturnType<typeof makeRouter> | null = null;
  ring: any = null;
  flushes = 0;
  synced2 = 0;
  nextStage = 0;
  private createFruityFp = 0;

  constructor(mod: any, o: GlueHostOptions = {}) {
    this.mod = mod;
    this.o = {
      username: o.username ?? 'webstudio',
      store: o.store ?? new MemoryStore(),
      profile: o.profile ?? 'default',
      workDir: o.workDir ?? path.join(GLUEDIR(), 'work/wvfs-e2e'),
      waitMode: o.waitMode ?? -1,
      createFruity: o.createFruity as CreateFruityJs,
      onRestart: o.onRestart ?? (() => { (globalThis as any).location?.reload?.(); }),
    };
    // FL boot 貫通後は m11 の export 解決結果を登録する (未達の間は C 側スタブのまま)
    if (this.o.createFruity) {
      this.createFruityFp = this.mod.addFunction(this.o.createFruity as any, 'iii');
      this.mod._glue_set_create_fruity_instance(this.createFruityFp);
    }
  }

  // ------------------------------------------------------------ wasm 補助
  private cstr(s: string): number { const m = this.mod, n = m.lengthBytesUTF8(s) + 1, p = m._malloc(n); m.stringToUTF8(s, p, n); return p; }
  free(p: number): void { this.mod._free(p); }
  /** wasm 側 glue_trace を JS 配列で読む */
  trace(): string[] {
    const m = this.mod, n = m._glue_trace_count(), out: string[] = [];
    for (let i = 0; i < n; i++) {
      const cap = 256, p = m._malloc(cap);
      if (m._glue_trace_line(i, p, cap) >= 0) out.push(m.UTF8ToString(p));
      m._free(p);
    }
    return out;
  }
  traceText(): string { return this.trace().join('\n'); }
  stageName(id: number): string {
    const m = this.mod, p = m._malloc(32);
    m._glue_stage_name(id, p, 32);
    const s = m.UTF8ToString(p);
    m._free(p);
    return s;
  }
  /** C 側マッパ (pathreg) で Win パスを FS パスに写像する */
  shimxPathToPosix(winPath: string): string {
    const m = this.mod, p = this.cstr(winPath), cap = 512, out = m._malloc(cap);
    try {
      if (m._shimx_path_to_posix(p, out, cap) !== 0) return '(fallback)';
      return m.UTF8ToString(out);
    } finally { m._free(p); m._free(out); }
  }
  hostTitle(addr: number): string {
    const u32 = new Uint32Array(this.mod.HEAPU8.buffer);
    const titlePtr = u32[(addr + 0x18) / 4];
    return titlePtr ? this.mod.UTF8ToString(titlePtr) : '(null)';
  }

  /** JS 側記録と C 側カウンタの二重検査付き段階実行 */
  private async step(id: number, fn: () => Promise<string | void> | string | void): Promise<StageRecord> {
    const name = this.stageName(id);
    if (this.nextStage !== id) throw new Error(`glue: out-of-order stage ${name} (expected ${this.stageName(this.nextStage)})`);
    const t0 = performance.now();
    const detail = await fn();
    const rec: StageRecord = { id, name, ms: performance.now() - t0, ok: true, detail: detail ?? undefined };
    this.stages.push(rec);
    this.nextStage++;
    return rec;
  }

  // ------------------------------------------------------------ 段階
  async stagePaths(): Promise<StageRecord> {
    return this.step(0, () => {
      const p = this.cstr(this.o.username);
      try {
        const rc = this.mod._glue_stage_paths(p);
        if (rc !== 0) throw new Error(`glue_stage_paths -> ${rc}`);
      } finally { this.free(p); }
      return `mounts=${this.mod._pathreg_mount_count()} username=${this.o.username}`;
    });
  }

  async stageRegistry(): Promise<StageRecord> {
    return this.step(1, async () => {
      // vreg seed import + flush フック (遅延 flush + 明示 flush 点)。HKCU のみ永続。
      this.reg = await RegBridge.create({
        mod: this.mod,
        store: this.o.store,
        seed: await loadSeed(),
        profile: this.o.profile,
        installMapper: false,               // 1 paths で _pathreg_install 済み
        flushDelayMs: 0,                    // 依存は明示 flush 点だけに (vreg REPORT §8-1)
      });
      const rc = this.mod._glue_stage_registry();
      if (rc !== 0) throw new Error(`glue_stage_registry -> ${rc}`);
      return `vreg gen=${this.mod._vreg_generation()} profile=${this.o.profile}`;
    });
  }

  async stagePump(): Promise<StageRecord> {
    return this.step(2, async () => {
      const rc = this.mod._glue_stage_pump(this.o.waitMode);
      if (rc !== 0) throw new Error(`glue_stage_pump -> ${rc}`);
      this.pumpModeReq = this.mod._glue_pump_mode_req();
      // リングを host の PumpRing (ABI 正本: src/runtime/worker_pump.ts) に露出する
      const { PumpRing } = await import(pathToFileURL(ensurePumpRingMjs()).href);
      this.ring = new PumpRing(this.mod.HEAP32.buffer, this.mod._pump_ring_addr());
      // 時計較正: node では C モジュールが main スレッドなので直接差で誤差 ~0 (pump REPORT §2.6)。
      // browser では page 駆動 ping-pong を使う (ctrl 経由は RTT/2 の偏りで p50 が 130 倍化した実績)。
      const offset = performance.timeOrigin + performance.now() - this.mod._pump_now_raw();
      this.mod._pump_set_clock_offset(offset);
      return `ring cap=${this.ring.capacity} wait_mode=${this.mod._pump_get_wait_mode()} clockOffset=${offset.toFixed(3)}ms`;
    });
  }

  async stageVfs(): Promise<StageRecord> {
    return this.step(3, async () => {
      fs.mkdirSync(path.join(this.o.workDir, 'home'), { recursive: true });
      fs.mkdirSync(path.join(this.o.workDir, 'tmp'), { recursive: true });
      this.home = await Wvfs.open(new NodeBackend(path.join(this.o.workDir, 'home')));
      this.tmp = await Wvfs.open(new NodeBackend(path.join(this.o.workDir, 'tmp')));
      const FS = this.mod.FS;
      if (FS) {
        mkdirp(FS, HOME_MOUNT);
        mkdirp(FS, TMP_MOUNT);
        FS.mount(createWvfsFs(FS, this.home, { stores: [this.home, this.tmp] }), {}, HOME_MOUNT);
        FS.mount(createWvfsFs(FS, this.tmp, { stores: [this.home, this.tmp] }), {}, TMP_MOUNT);
      }
      this.router = makeRouter(this.o.username);
      const rc = this.mod._glue_stage_vfs();
      if (rc !== 0) throw new Error(`glue_stage_vfs -> ${rc}`);
      // C 側マッパ (pathreg_map) と JS 側ミラー (pathmap.mjs) が同じ写像であることを照合
      const probe = `C:\\Users\\${this.o.username}\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml`;
      const cOut = this.shimxPathToPosix(probe);
      const jsRoute = this.router.mapRaw(probe);
      if (cOut !== jsRoute) throw new Error(`mapper mismatch: C=${cOut} JS=${jsRoute}`);
      return `mounts home=${HOME_MOUNT} tmp=${TMP_MOUNT} objfs=${WVFS_ROOT} map=${cOut}`;
    });
  }

  async stagePreDllmain(cmdline = ''): Promise<StageRecord> {
    return this.step(4, () => {
      const p = this.cstr(cmdline);
      try {
        const rc = this.mod._glue_stage_pre_dllmain(p);
        if (rc !== 0) throw new Error(`glue_stage_pre_dllmain -> ${rc}`);
      } finally { this.free(p); }
      return `cmdline=${cmdline.length}B`;
    });
  }

  async stageDllmain(): Promise<StageRecord> {
    return this.step(5, () => {
      const rc = this.mod._glue_stage_dllmain();
      if (rc !== 0) throw new Error(`glue_stage_dllmain -> ${rc}`);
      return 'm11 closure: not wired (FL boot 未達)';
    });
  }

  async stageHost(): Promise<StageRecord> {
    return this.step(6, () => {
      const rc = this.mod._glue_stage_host();
      if (rc !== 0) throw new Error(`glue_stage_host -> ${rc}`);
      const addr = this.mod._glue_host_addr();
      const u32 = new Uint32Array(this.mod.HEAPU8.buffer, addr, 0x38 / 4);
      return `host addr=${addr} ver=${u32[2]} flags=0x${u32[3].toString(16)} title=${this.hostTitle(addr)}`;
    });
  }

  async stageBoot(): Promise<StageRecord> {
    return this.step(7, () => {
      const rc = this.mod._glue_stage_boot();
      if (rc !== 0) throw new Error(`glue_stage_boot -> ${rc}`);
      return `calls=${this.mod._glue_create_fruity_instance_called()} iface=${this.mod._glue_last_iface()}`;
    });
  }

  async stagePost(): Promise<StageRecord> {
    return this.step(8, () => {
      const rc = this.mod._glue_stage_post();
      if (rc !== 0) throw new Error(`glue_stage_post -> ${rc}`);
      return 'iface Destroy called';
    });
  }

  /** 終了処理: レジストリ flush → wvfs flush (onYield/onPageHide) → syncfs → trace dump */
  async stageShutdown(): Promise<StageRecord> {
    return this.step(9, async () => {
      await this.reg?.onPageHide();
      this.flushes++;
      await this.home?.onYield();
      await this.tmp?.onYield();
      this.flushes += 2;
      const FS = this.mod.FS;
      if (FS?.syncfs) await new Promise<void>((res) => FS.syncfs(false, () => { this.synced2++; res(); }));
      const rc = this.mod._glue_stage_shutdown();
      if (rc !== 0) throw new Error(`glue_stage_shutdown -> ${rc}`);
      return `flushes=${this.flushes} synced=${this.synced2}`;
    });
  }

  async runAll(cmdline = ''): Promise<StageRecord[]> {
    await this.stagePaths();
    await this.stageRegistry();
    await this.stagePump();
    await this.stageVfs();
    await this.stagePreDllmain(cmdline);
    await this.stageDllmain();
    await this.stageHost();
    await this.stageBoot();
    await this.stagePost();
    await this.stageShutdown();
    return this.stages;
  }

  /** yield 点 flush (ポンプの yield で呼ぶ規約。vreg REPORT §8-1 / pathreg.h 契約) */
  async onYield(): Promise<void> {
    await this.reg?.onYield();
    await this.home?.onYield();
    await this.tmp?.onYield();
    this.flushes++;
    await this.checkRestart();
  }

  /** winstubs の ShellExecute が `fldiagnostic /restartfl` を検知していれば、flush 済みの状態で onRestart を 1 回呼ぶ */
  restartRequested(): boolean {
    return !!this.mod._winstubs_restart_requested?.();
  }
  restarts = 0;
  async checkRestart(): Promise<boolean> {
    if (this.restarts > 0 || !this.restartRequested()) return false;
    this.restarts++;
    await this.o.onRestart();
    return true;
  }

  // ------------------------------------------------------------ ファイル経路 (wvfs 書込)
  /** Win パス → /c/home|/c/tmp に書く (FL のファイル書込の写像経路) */
  writeWin(winPath: string, data: Uint8Array): { mount: string; path: string } {
    const r = this.router?.route(winPath);
    if (!r) throw new Error(`no wvfs route for ${winPath}`);
    const w = r.mount === 'home' ? this.home! : this.tmp!;
    const dir = path.posix.dirname(r.path);
    if (dir && dir !== '/') w.mkdirpSync(dir);
    w.writeFileSync(r.path, data);
    return { mount: r.mount, path: r.path };
  }
  readWin(winPath: string): Uint8Array {
    const r = this.router?.route(winPath);
    if (!r) throw new Error(`no wvfs route for ${winPath}`);
    const w = r.mount === 'home' ? this.home! : this.tmp!;
    return w.readFileSync(r.path);
  }
  /** Emscripten FS (wvfs mount 経由) に書く。C 側 shimx file API が通る経路 */
  writeFs(fsPath: string, data: Uint8Array): void {
    const FS = this.mod.FS;
    if (!FS) throw new Error('FS not available');
    FS.writeFile(fsPath, data);
  }
}

function mkdirp(FS: any, p: string): void {
  let cur = '';
  for (const part of p.split('/').filter(Boolean)) {
    cur += '/' + part;
    try { FS.mkdir(cur); } catch { /* EEXIST */ }
  }
}
