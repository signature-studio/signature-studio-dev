/**
 * gui_fonts.ts — GDI テキスト (FreeType; tools/gui/src/gui_ft*.c) 用フォントの遅延取得 + sha256 検証 (GUI-13 #615)。
 *
 * フォント本体はリポジトリにも wasm にも同梱しない。shim が最初に face を open した時点で gui_hostcall (GUI_HC_FETCH_FONT) が
 * HostCallEnv.loadFont → 本ローダを呼び、url から取得 → sha256 (manifest 値) を検証 → wasm heap (_malloc) へ置いて ptr/size を返す。
 * 検証失敗・取得失敗は null (shim は内蔵 8x8 へフォールバックし LOG に残す)。url の実配信元は #22 (VFS) の遅延取得に接続する想定。
 */

export type FontEntry = { name: string; url: string; sha256: string };
export type FontModule = { _malloc(n: number): number; wasmMemory: { buffer: ArrayBufferLike }; _gui_ft_add_face(namePtr: number): number; _gui_ft_add_alias(aliasPtr: number, targetPtr: number): number; _free(p: number): void };

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  let s = ""; for (const b of d) s += b.toString(16).padStart(2, "0");
  return s;
}

export type FontLoaderOptions = { fetch?: (url: string) => Promise<{ ok: boolean; arrayBuffer(): Promise<ArrayBuffer> }>; onEvent?: (msg: string) => void };

/** manifest の各 face 名 (大小無視) → 取得+検証+heap 配置 */
export function createFontLoader(mod: Pick<FontModule, "_malloc" | "wasmMemory">, entries: FontEntry[], o: FontLoaderOptions = {}): (name: string) => Promise<{ ptr: number; size: number } | null> {
  const doFetch = o.fetch ?? ((u: string) => fetch(u));
  const ev = o.onEvent ?? (() => {});
  const byName = new Map(entries.map((e) => [e.name.toLowerCase(), e]));
  return async (name: string) => {
    const e = byName.get(name.toLowerCase());
    if (!e) { ev(`font '${name}': not in manifest`); return null; }
    let buf: ArrayBuffer;
    try {
      const r = await doFetch(e.url);
      if (!r.ok) { ev(`font '${name}': fetch failed ${e.url}`); return null; }
      buf = await r.arrayBuffer();
    } catch (err) { ev(`font '${name}': fetch error ${(err as Error).message}`); return null; }
    const got = await sha256Hex(buf);
    if (got !== e.sha256.toLowerCase()) { ev(`font '${name}': sha256 mismatch (got ${got}, want ${e.sha256})`); return null; }
    const ptr = mod._malloc(buf.byteLength);
    if (!ptr) { ev(`font '${name}': malloc ${buf.byteLength} failed`); return null; }
    new Uint8Array(mod.wasmMemory.buffer as ArrayBuffer).set(new Uint8Array(buf), ptr);
    ev(`font '${name}': loaded ${buf.byteLength} B, sha256 ok`);
    return { ptr, size: buf.byteLength };
  };
}

/** face を遅延登録 (最初の open まで取得しない) し、alias (Windows face 名 → 登録 face) を張る。呼出は GuiHost.attach (= host_ready) より前に行うこと */
export function registerFonts(mod: FontModule & { HEAPU8?: Uint8Array }, faces: string[], aliases: Array<[string, string]>): void {
  const enc = new TextEncoder();
  const put = (s: string): number => { const b = enc.encode(s + "\0"); const p = mod._malloc(b.length); new Uint8Array(mod.wasmMemory.buffer as ArrayBuffer).set(b, p); return p; };
  for (const f of faces) { const p = put(f); mod._gui_ft_add_face(p); mod._free(p); }
  for (const [a, t] of aliases) { const pa = put(a), pt = put(t); mod._gui_ft_add_alias(pa, pt); mod._free(pa); mod._free(pt); }
}
