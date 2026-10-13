// helpviewer 共通: FL 素材 (extracted/) から Help 実ファイルを sha256 ピンで特定する + srcdoc の安全性検査。
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const pins = JSON.parse(readFileSync(path.join(here, "help_files.json"), "utf8"));

/**
 * extracted/block*_{DATA,PE}.bin から help_files.json の (size, sha256) に一致するものを探す。
 * 戻り: { help: Map<Help 相対パス, Uint8Array>, errorOffline: Uint8Array, found, missing }
 * 同一内容の別パス (Editions_FL12_*.png 等) は同じ blob を共有する。
 */
export function loadFixture(flWin64Dir) {
  const ext = path.join(flWin64Dir, "extracted");
  const bySize = new Map();
  for (const f of pins.files) (bySize.get(f.size) ?? bySize.set(f.size, []).get(f.size)).push(f);
  const byHash = new Map();
  for (const name of readdirSync(ext)) {
    if (!name.startsWith("block")) continue;
    const full = path.join(ext, name);
    const size = statSync(full).size;
    if (!bySize.has(size)) continue;
    const buf = readFileSync(full);
    const h = createHash("sha256").update(buf).digest("hex");
    if (bySize.get(size).some((f) => f.sha256 === h)) byHash.set(h, new Uint8Array(buf));
  }
  const help = new Map();
  let errorOffline = null;
  const missing = [];
  for (const f of pins.files) {
    const b = byHash.get(f.sha256);
    if (!b) missing.push(f.path);
    else if (f.path.startsWith("Help/")) help.set(f.path.slice(5), b);
    else if (f.path === "System/Internet/error-offline.html") errorOffline = b;
  }
  return { help, errorOffline, found: pins.files.length - missing.length, missing };
}

// srcdoc に残ってはいけないもの (script は bridge の 1 本だけ許可)
export function unsafeFindings(srcdoc, nonce) {
  const f = [];
  const scripts = [...srcdoc.matchAll(/<script\b[^>]*>/gi)].map((m) => m[0]);
  if (scripts.some((s) => !s.includes(`nonce="${nonce}"`))) f.push("script without nonce");
  if (scripts.length > 1) f.push("multiple scripts");
  if (/<(iframe|frame|object|embed|applet|base|form)\b/i.test(srcdoc)) f.push("embedding/base/form tag");
  if (/\son[a-z]+\s*=/i.test(srcdoc)) f.push("event handler attribute");
  if (/(?:src|href|data)\s*=\s*["']?https?:/i.test(srcdoc.replace(/<a\b[^>]*>/gi, ""))) f.push("external reference");
  if (/url\(\s*["']?https?:/i.test(srcdoc)) f.push("external url()");
  if (/@import/i.test(srcdoc)) f.push("@import");
  if (!srcdoc.startsWith('<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy"')) f.push("CSP is not the first element");
  return f;
}
