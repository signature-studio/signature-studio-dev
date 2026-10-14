/**
 * gui_hostcall.ts — wasm (shimx/gui) → ブラウザ main thread の同期呼出路の host 側 (tools/gui/include/gui_hostcall.h のミラー)。
 *
 * ShellExecute→window.open、GetOpenFileName/GetSaveFileName→File System Access、Drag&Drop→FS ステージング+gui_drop_files。
 * main thread 専用 API (window.open / showOpenFilePicker / DataTransfer) を、wasm の GUI スレッドから同期で呼ぶための橋。
 *   wasm: req_seq++ → resp_seq == req_seq まで futex wait。 本 host: Atomics.waitAsync(req_seq) で起床 → 処理 → resp_seq 書込+notify。
 * 外部依存を持たない (node の --experimental-strip-types でも単体実行できるよう import 無し)。window/FS は HostCallEnv で注入する。
 */

export const HC = {
  magic: 0x00, version: 0x04, hostReady: 0x08, lock: 0x0c, reqSeq: 0x10, respSeq: 0x14, op: 0x18, flags: 0x1c, result: 0x20,
  inLen: 0x24, outLen: 0x28, in: 0x40, out: 0x840, size: 0x1840,
} as const;
export const HC_MAGIC = 0x43484749;
export const HC_IN = 2048;
export const HC_OUT = 4096;
export const HC_OP = { openUrl: 1, openFile: 2, saveFile: 3, openHelp: 4, fetchFont: 5, fileClosed: 6 } as const;
/** host 側エラーの result 値 (wasm 側の -1/-2/-3 と衝突しない) */
export const HC_ERR = -16;

export const OFN_ALLOWMULTISELECT = 0x200;

export type PickedFile = { name: string; bytes: Uint8Array };
export type SaveTarget = { name: string; write: (bytes: Uint8Array) => Promise<void> };
export type FileType = { description: string; accept: Record<string, string[]> };
export type PickOptions = { title: string; startDir: string; defExt: string; suggestedName: string; multiple: boolean; types: FileType[] };

export interface HostCallEnv {
  /** window.open 相当。ポップアップブロック等で開けなければ false */
  openWindow(url: string): boolean | Promise<boolean>;
  /** FL の Help パス (ShellExecuteW の lpFile) を viewer で開く。window.flHelp.shellExecute(null, path) 相当。表示できれば true (#554) */
  openHelp?(path: string): Promise<boolean>;
  /** face 名のフォントを取得・sha256 検証して wasm heap へ置き、その ptr/size を返す (GUI-13 #615; gui_fonts.ts の createFontLoader)。無し・検証失敗は null */
  loadFont?(name: string): Promise<{ ptr: number; size: number } | null>;
  /** showOpenFilePicker 相当。キャンセルは null */
  pickOpen(o: PickOptions): Promise<PickedFile[] | null>;
  /** showSaveFilePicker 相当。キャンセルは null */
  pickSave(o: PickOptions): Promise<SaveTarget | null>;
  /** Emscripten FS (Module.FS) 相当 */
  fs: { mkdirp(dir: string): void; writeFile(path: string, bytes: Uint8Array): void; readFile(path: string): Uint8Array | null };
}

const URL_SCHEMES = new Set(["http:", "https:", "mailto:"]);

/** Windows フィルタ ("*.wav;*.mp3") → File System Access の types。"*.*" だけなら無制限 (types を付けない) */
export function filterToTypes(pairs: Array<[string, string]>): FileType[] {
  const out: FileType[] = [];
  for (const [desc, pat] of pairs) {
    const exts = pat.split(";").map((s) => s.trim()).filter((s) => /^\*\.[A-Za-z0-9_+-]+$/.test(s)).map((s) => s.slice(1));
    if (exts.length) out.push({ description: desc || exts.join(", "), accept: { "application/octet-stream": exts } });
  }
  return out;
}

export class HostCallBridge {
  /** save ダイアログで返した POSIX パス → 書込先。FL がファイルを書き終えたら flushSaves() で実体へ反映する */
  readonly pendingSaves = new Map<string, SaveTarget>();
  readonly log: string[] = [];
  private stopped = false;
  private handled = 0;
  private done: Promise<void> = Promise.resolve();

  private readonly memory: { buffer: ArrayBufferLike };
  private readonly base: number;
  private readonly env: HostCallEnv;
  constructor(memory: { buffer: ArrayBufferLike }, base: number, env: HostCallEnv) { this.memory = memory; this.base = base; this.env = env; }

  private i32(): Int32Array { return new Int32Array(this.memory.buffer as SharedArrayBuffer, this.base, HC.size >> 2); }
  private u8(): Uint8Array { return new Uint8Array(this.memory.buffer as SharedArrayBuffer, this.base, HC.size); }

  /** host_ready を立てて要求待ちを開始。stop() まで動く */
  start(): void {
    const i = this.i32();
    if (Atomics.load(i, HC.magic >> 2) !== 0 && Atomics.load(i, HC.magic >> 2) !== HC_MAGIC) throw new Error("[hostcall] magic mismatch");
    this.handled = Atomics.load(i, HC.reqSeq >> 2);
    Atomics.store(i, HC.hostReady >> 2, 1);
    Atomics.notify(i, HC.hostReady >> 2);
    this.done = this.loop();
  }
  async stop(): Promise<void> {
    this.stopped = true;
    const i = this.i32();
    Atomics.add(i, HC.reqSeq >> 2, 0);
    Atomics.notify(i, HC.reqSeq >> 2);   // waitAsync を起こす (値は変えない: wait は値不一致でしか即返らないため下で timeout も使う)
    await this.done;
    Atomics.store(i, HC.hostReady >> 2, 0);
  }

  private async loop(): Promise<void> {
    const i = this.i32();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const waitAsync = (Atomics as any).waitAsync as (ta: Int32Array, idx: number, v: number, t?: number) => { async: boolean; value: Promise<string> | string };
    while (!this.stopped) {
      const cur = Atomics.load(i, HC.reqSeq >> 2);
      if (cur !== this.handled) {
        this.handled = cur;
        await this.handle(cur);
        continue;
      }
      const w = waitAsync(i, HC.reqSeq >> 2, cur, 200);   // 200ms で stop 判定に戻る (通常は notify で即起床)
      if (w.async) await w.value;
    }
  }

  private async handle(seq: number): Promise<void> {
    const i = this.i32(), b = this.u8();
    const op = Atomics.load(i, HC.op >> 2), flags = Atomics.load(i, HC.flags >> 2) >>> 0;
    const inLen = Math.min(Atomics.load(i, HC.inLen >> 2) >>> 0, HC_IN);
    const fields = new TextDecoder().decode(b.slice(HC.in, HC.in + inLen)).split("\0");
    let result = 0;
    let out: Uint8Array = new Uint8Array(0);
    try {
      if (op === HC_OP.openUrl) result = (await this.openUrl(fields[0] ?? "")) ? 1 : 0;
      else if (op === HC_OP.openHelp) result = (await this.openHelp(fields[0] ?? "")) ? 1 : 0;
      else if (op === HC_OP.fetchFont) {
        const f = this.env.loadFont ? await this.env.loadFont(fields[0] ?? "") : null;
        if (!this.env.loadFont) this.log.push("fetchFont: no loader");
        if (f) { const o = new Uint8Array(8); const dv = new DataView(o.buffer); dv.setUint32(0, f.ptr >>> 0, true); dv.setUint32(4, f.size >>> 0, true); out = o; result = 1; } else result = 0;
      }
      else if (op === HC_OP.openFile || op === HC_OP.saveFile) {
        const r = await this.dialog(op === HC_OP.saveFile, flags, fields);
        result = r.result; out = r.out;
      } else if (op === HC_OP.fileClosed) result = (await this.fileClosed(fields[0] ?? "")) ? 1 : 0;
      else { result = HC_ERR; this.log.push(`unknown op ${op}`); }
    } catch (e) {
      result = HC_ERR; this.log.push(`op ${op} failed: ${(e as Error).message}`);
    }
    if (out.length > HC_OUT) { out = out.slice(0, HC_OUT); result = HC_ERR; }
    this.u8().set(out, HC.out);
    Atomics.store(i, HC.outLen >> 2, out.length);
    Atomics.store(i, HC.result >> 2, result);
    Atomics.store(i, HC.respSeq >> 2, seq);   // 最後: wasm はこれで完了を知る
    Atomics.notify(i, HC.respSeq >> 2);
  }

  private async openHelp(path: string): Promise<boolean> {
    if (!this.env.openHelp) { this.log.push("openHelp: no viewer"); return false; }
    const ok = await this.env.openHelp(path);
    if (!ok) this.log.push(`openHelp rejected: ${path}`);
    return ok;
  }

  private async openUrl(raw: string): Promise<boolean> {
    let u: URL;
    try { u = new URL(raw); } catch { this.log.push(`openUrl rejected (unparsable): ${raw}`); return false; }
    if (!URL_SCHEMES.has(u.protocol)) { this.log.push(`openUrl rejected (scheme ${u.protocol})`); return false; }
    const ok = await this.env.openWindow(u.href);
    if (!ok) this.log.push(`openUrl blocked: ${u.href}`);
    return ok;
  }

  /** in: title, initialDir, defExt, 現在名, stagePosix, stageWin, flags, filterIndex, (desc, pattern)* */
  private async dialog(save: boolean, flags: number, f: string[]): Promise<{ result: number; out: Uint8Array }> {
    const [title = "", startDir = "", defExt = "", cur = "", stagePosix = "", /* stageWin */, /* flags */, /* filterIndex */, ...rest] = f;
    const pairs: Array<[string, string]> = [];
    for (let k = 0; k + 1 < rest.length; k += 2) pairs.push([rest[k], rest[k + 1]]);
    const o: PickOptions = { title, startDir, defExt, suggestedName: cur.split(/[\\/]/).pop() ?? "", multiple: !save && (flags & OFN_ALLOWMULTISELECT) !== 0, types: filterToTypes(pairs) };
    this.env.fs.mkdirp(stagePosix);
    const enc = new TextEncoder();
    const names: string[] = [];
    if (save) {
      const t = await this.env.pickSave(o);
      if (!t) return { result: 0, out: new Uint8Array(0) };
      if (!/^[^\\/\0]+$/.test(t.name)) throw new Error(`bad file name ${JSON.stringify(t.name)}`);
      this.pendingSaves.set(`${stagePosix}/${t.name}`, t);
      names.push(t.name);
    } else {
      const picked = await this.env.pickOpen(o);
      if (!picked || picked.length === 0) return { result: 0, out: new Uint8Array(0) };
      for (const p of picked) {
        if (!/^[^\\/\0]+$/.test(p.name)) throw new Error(`bad file name ${JSON.stringify(p.name)}`);
        this.env.fs.writeFile(`${stagePosix}/${p.name}`, p.bytes);
        names.push(p.name);
      }
    }
    return { result: 1, out: enc.encode(names.join("\0") + "\0\0") };
  }

  /** FL が書き終えた save 先を実ファイルへ反映する。反映した件数を返す (FS に無い/失敗は log に残して継続) */
  async flushSaves(): Promise<number> {
    let n = 0;
    for (const [path, t] of this.pendingSaves) if (await this.flushOne(path, t)) n++;
    return n;
  }

  /** shimx が書込み用 file を CloseHandle した (#958)。保存待ちの先なら、その時点で実体へ反映する。対象外は false */
  private async fileClosed(path: string): Promise<boolean> {
    const t = this.pendingSaves.get(path);
    return t ? this.flushOne(path, t) : false;
  }

  private async flushOne(path: string, t: SaveTarget): Promise<boolean> {
    const bytes = this.env.fs.readFile(path);
    if (!bytes) { this.log.push(`flush skipped (no file): ${path}`); return false; }
    try { await t.write(bytes); return true; } catch (e) { this.log.push(`flush failed ${path}: ${(e as Error).message}`); return false; }
  }
}

/** ブラウザ実装 (Window + File System Access)。env.fs は Emscripten の FS を包んで渡す */
export function browserEnv(win: Window & typeof globalThis, fs: HostCallEnv["fs"]): HostCallEnv {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = win as any;
  const common = (o: PickOptions) => ({ ...(o.types.length ? { types: o.types } : {}), id: "webstudio" });
  return {
    fs,
    openWindow(url) {
      const p = win.open(url, "_blank");
      if (!p) return false;
      try { p.opener = null; } catch { /* cross-origin 後の代入失敗は無視 */ }
      return true;
    },
    async pickOpen(o) {
      try {
        const hs = await w.showOpenFilePicker({ ...common(o), multiple: o.multiple });
        const out: PickedFile[] = [];
        for (const h of hs) { const file = await h.getFile(); out.push({ name: file.name, bytes: new Uint8Array(await file.arrayBuffer()) }); }
        return out;
      } catch (e) { if ((e as Error).name === "AbortError") return null; throw e; }
    },
    async pickSave(o) {
      try {
        const h = await w.showSaveFilePicker({ ...common(o), suggestedName: o.suggestedName || undefined });
        return { name: h.name, write: async (bytes: Uint8Array) => { const s = await h.createWritable(); await s.write(bytes); await s.close(); } };
      } catch (e) { if ((e as Error).name === "AbortError") return null; throw e; }
    },
  };
}

export type DropModule = {
  _malloc(n: number): number; _free(p: number): void; HEAPU8: Uint8Array;
  _gui_drop_files(x: number, y: number, n: number, names: number): number;
  UTF8ToString(p: number): string; _gui_stage_dir_posix(): number;
};
/** ブラウザの drop を FS のステージングへ書き出し、gui_drop_files で GUI スレッドへ配送要求する。戻りは gui_drop_files の値 (1 = 受理; 配送結果は gui_drop_last_result) */
export async function deliverDrop(mod: DropModule, fs: HostCallEnv["fs"], files: Array<{ name: string; arrayBuffer(): Promise<ArrayBuffer> }>, x: number, y: number): Promise<number> {
  const dir = mod.UTF8ToString(mod._gui_stage_dir_posix());
  fs.mkdirp(dir);
  const names: string[] = [];
  for (const f of files.slice(0, 64)) {
    if (!/^[^\\/\0]+$/.test(f.name)) continue;
    fs.writeFile(`${dir}/${f.name}`, new Uint8Array(await f.arrayBuffer()));
    names.push(f.name);
  }
  if (!names.length) return 0;
  const bytes = new TextEncoder().encode(names.join("\0") + "\0\0");
  const p = mod._malloc(bytes.length);
  try {
    mod.HEAPU8.set(bytes, p);
    return mod._gui_drop_files(Math.round(x), Math.round(y), names.length, p);
  } finally { mod._free(p); }
}

/** el の dragover/drop を接続する (canvas 想定)。座標は el の左上基準の CSS px = desktop 座標 */
export function installDropTarget(el: EventTarget & { getBoundingClientRect(): { left: number; top: number } }, mod: DropModule, fs: HostCallEnv["fs"], onResult?: (r: number) => void): () => void {
  const over = (e: Event) => { e.preventDefault(); };
  const drop = (e: Event) => {
    e.preventDefault();
    const ev = e as unknown as { clientX: number; clientY: number; dataTransfer?: { files: ArrayLike<{ name: string; arrayBuffer(): Promise<ArrayBuffer> }> } };
    const r = el.getBoundingClientRect();
    void deliverDrop(mod, fs, Array.from(ev.dataTransfer?.files ?? []), ev.clientX - r.left, ev.clientY - r.top).then((v) => onResult?.(v));
  };
  el.addEventListener("dragover", over);
  el.addEventListener("drop", drop);
  return () => { el.removeEventListener("dragover", over); el.removeEventListener("drop", drop); };
}
