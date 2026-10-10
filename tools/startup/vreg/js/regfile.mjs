// regfile.mjs — Windows .reg (Registry Editor 5.00) の parse / serialize と、永続化用ツリーモデル。
//   model: { HKCU: { "Software\\X": { "ValueName": { t: "REG_SZ", v: "..." }, "": 既定値 } }, HKLM: {...}, ... }
//   v の表現: REG_SZ/REG_EXPAND_SZ=文字列, REG_DWORD=数値, REG_QWORD=10進文字列, REG_MULTI_SZ=文字列配列,
//             REG_BINARY / その他=16進 "aa,bb,.." (その他は t="REG_0x<type>")
// 外部依存なし (node / ブラウザ / Worker 共用)。

export const ROOTS = ['HKCR', 'HKCU', 'HKLM', 'HKU', 'HKCC'];
const ROOT_LONG = { HKEY_CLASSES_ROOT: 'HKCR', HKEY_CURRENT_USER: 'HKCU', HKEY_LOCAL_MACHINE: 'HKLM', HKEY_USERS: 'HKU', HKEY_CURRENT_CONFIG: 'HKCC' };
export const ROOT_NAME = Object.fromEntries(Object.entries(ROOT_LONG).map(([k, v]) => [v, k]));
const TYPE_NUM = { REG_SZ: 1, REG_EXPAND_SZ: 2, REG_BINARY: 3, REG_DWORD: 4, REG_MULTI_SZ: 7, REG_QWORD: 11 };
const NUM_TYPE = Object.fromEntries(Object.entries(TYPE_NUM).map(([k, v]) => [v, k]));

// ---------- バイト列 ⇄ 文字列 ----------
export function decodeRegBytes(bytes) {
  if (typeof bytes === 'string') return bytes.replace(/^\uFEFF/, '');
  const u = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  if (u.length >= 2 && u[0] === 0xff && u[1] === 0xfe) return new TextDecoder('utf-16le').decode(u.subarray(2));
  if (u.length >= 3 && u[0] === 0xef && u[1] === 0xbb && u[2] === 0xbf) return new TextDecoder('utf-8').decode(u.subarray(3));
  // BOM 無し UTF-16LE (ASCII 文字の後に 0x00 が続く) を検出
  if (u.length >= 4 && u[1] === 0 && u[3] === 0) return new TextDecoder('utf-16le').decode(u);
  return new TextDecoder('utf-8').decode(u);
}
export function encodeUtf16le(text, bom = true) {
  const out = new Uint8Array((text.length + (bom ? 1 : 0)) * 2);
  let o = 0;
  if (bom) { out[o++] = 0xff; out[o++] = 0xfe; }
  for (let i = 0; i < text.length; i++) { const c = text.charCodeAt(i); out[o++] = c & 0xff; out[o++] = c >> 8; }
  return out;
}
const hexBytes = (s) => (s.trim() === '' ? [] : s.split(',').map((h) => parseInt(h.trim(), 16)));
const utf16leToStr = (b) => { let s = ''; for (let i = 0; i + 1 < b.length; i += 2) s += String.fromCharCode(b[i] | (b[i + 1] << 8)); return s; };
const strToUtf16le = (s, nul = 1) => { const o = []; for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); o.push(c & 0xff, c >> 8); } for (let i = 0; i < nul * 2; i++) o.push(0); return o; };
const toHex = (b) => b.map((x) => x.toString(16).padStart(2, '0')).join(',');

// ---------- パス ----------
export function splitPath(p) {
  const s = p.replace(/^\\+/, '');
  const i = s.indexOf('\\');
  const head = i < 0 ? s : s.slice(0, i);
  const root = ROOT_LONG[head.toUpperCase()] || (ROOTS.includes(head.toUpperCase()) ? head.toUpperCase() : null);
  if (!root) return null;
  return { hive: root, key: i < 0 ? '' : s.slice(i + 1).replace(/\\+$/, '') };
}

// ---------- parse ----------
// 戻り値: ops[] = {op:'key',hive,key} | {op:'set',hive,key,name,t,v} | {op:'delvalue',hive,key,name} | {op:'delkey',hive,key}
export function parseReg(input) {
  const text = decodeRegBytes(input).replace(/\r\n?/g, '\n');
  const lines = text.split('\n');
  const ops = [];
  let cur = null;
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    while (/\\$/.test(line) && /^\s*("[^"]*"|@)=hex/i.test(line) && i + 1 < lines.length) line = line.slice(0, -1) + lines[++i].trim();
    const s = line.trim();
    if (!s || s[0] === ';') continue;
    if (s[0] === '[') {
      const m = /^\[(-?)(.*)\]\s*$/.exec(s);
      if (!m) continue;
      const pk = splitPath(m[2]);
      if (!pk) { cur = null; continue; }
      if (m[1]) { ops.push({ op: 'delkey', ...pk }); cur = null; } else { cur = pk; ops.push({ op: 'key', ...pk }); }
      continue;
    }
    if (!cur) continue;
    let name, rest;
    if (s[0] === '@') { name = ''; rest = s.slice(1).replace(/^\s*=\s*/, ''); }
    else if (s[0] === '"') {
      let j = 1, n = '';
      while (j < s.length && s[j] !== '"') { if (s[j] === '\\' && j + 1 < s.length) j++; n += s[j++]; }
      name = n; rest = s.slice(j + 1).replace(/^\s*=\s*/, '');
    } else continue;
    if (rest === '-') { ops.push({ op: 'delvalue', ...cur, name }); continue; }
    if (rest[0] === '"') {
      let j = 1, v = '';
      while (j < rest.length && rest[j] !== '"') { if (rest[j] === '\\' && j + 1 < rest.length) j++; v += rest[j++]; }
      ops.push({ op: 'set', ...cur, name, t: 'REG_SZ', v });
    } else if (/^dword:/i.test(rest)) {
      ops.push({ op: 'set', ...cur, name, t: 'REG_DWORD', v: parseInt(rest.slice(6), 16) >>> 0 });
    } else if (/^hex/i.test(rest)) {
      const m = /^hex(?:\(([0-9a-fA-F]+)\))?:(.*)$/i.exec(rest);
      if (!m) continue;
      const type = m[1] === undefined ? 3 : parseInt(m[1], 16);
      const b = hexBytes(m[2]);
      ops.push({ op: 'set', ...cur, name, ...decodeTyped(type, b) });
    }
  }
  return ops;
}
function decodeTyped(type, b) {
  const t = NUM_TYPE[type];
  if (t === 'REG_SZ' || t === 'REG_EXPAND_SZ') return { t, v: utf16leToStr(b).replace(/\0.*$/s, '') };
  if (t === 'REG_MULTI_SZ') { const s = utf16leToStr(b); const parts = s.split('\0'); while (parts.length && parts[parts.length - 1] === '') parts.pop(); return { t, v: parts }; }
  if (t === 'REG_DWORD' && b.length === 4) return { t, v: (b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)) >>> 0 };
  if (t === 'REG_QWORD' && b.length === 8) { let x = 0n; for (let i = 7; i >= 0; i--) x = (x << 8n) | BigInt(b[i]); return { t, v: x.toString() }; }
  if (t === 'REG_BINARY') return { t, v: toHex(b) };
  return { t: `REG_0x${type.toString(16)}`, v: toHex(b) };   // 未知の型、またはサイズ不整合の既知型は生バイトで保持
}
function encodeTyped(t, v) { // → {type, bytes}
  switch (t) {
    case 'REG_SZ': return { type: 1, bytes: strToUtf16le(v) };
    case 'REG_EXPAND_SZ': return { type: 2, bytes: strToUtf16le(v) };
    case 'REG_MULTI_SZ': { const o = []; for (const s of v) o.push(...strToUtf16le(s)); o.push(0, 0); return { type: 7, bytes: o }; }
    case 'REG_DWORD': return { type: 4, bytes: [v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255] };
    case 'REG_QWORD': { let x = BigInt(v); const o = []; for (let i = 0; i < 8; i++) { o.push(Number(x & 255n)); x >>= 8n; } return { type: 11, bytes: o }; }
    case 'REG_BINARY': return { type: 3, bytes: hexBytes(v) };
    default: { const m = /^REG_0x([0-9a-f]+)$/i.exec(t); return { type: m ? parseInt(m[1], 16) : 3, bytes: hexBytes(v) }; }
  }
}

// ---------- serialize ----------
const esc = (s) => s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
export function valueText(name, val) {
  const n = name === '' ? '@' : `"${esc(name)}"`;
  switch (val.t) {
    case 'REG_SZ': return `${n}="${esc(val.v)}"`;
    case 'REG_DWORD': return `${n}=dword:${(val.v >>> 0).toString(16).padStart(8, '0')}`;
    case 'REG_BINARY': return `${n}=hex:${val.v}`;
    default: { const { type, bytes } = encodeTyped(val.t, val.v); return `${n}=hex(${type.toString(16)}):${toHex(bytes)}`; }
  }
}
/** model → .reg テキスト (LF)。hives: 出力するハイブ (既定 HKCU,HKLM) */
export function serializeReg(model, { hives = ['HKCU', 'HKLM'] } = {}) {
  const out = ['Windows Registry Editor Version 5.00', ''];
  for (const h of hives) {
    const keys = model[h] || {};
    for (const key of Object.keys(keys).sort((a, b) => a.toLowerCase() < b.toLowerCase() ? -1 : 1)) {
      out.push(`[${ROOT_NAME[h]}${key ? '\\' + key : ''}]`);
      for (const [name, val] of Object.entries(keys[key])) out.push(valueText(name, val));
      out.push('');
    }
  }
  return out.join('\n');
}
export function regBytes(model, opts = {}) { return encodeUtf16le(serializeReg(model, opts).replace(/\n/g, '\r\n'), true); }

// ---------- model 操作 (キー/値名は大小無視で同一視し、最初に現れた綴りを保持) ----------
export function emptyModel() { return { HKCR: {}, HKCU: {}, HKLM: {}, HKU: {}, HKCC: {} }; }
function findKey(hive, key) { const l = key.toLowerCase(); for (const k of Object.keys(hive)) if (k.toLowerCase() === l) return k; return null; }
function findName(vals, name) { const l = name.toLowerCase(); for (const k of Object.keys(vals)) if (k.toLowerCase() === l) return k; return null; }
export function ensureKey(model, hive, key) {
  const h = (model[hive] ||= {});
  const k = findKey(h, key);
  if (k !== null) return h[k];
  return (h[key] = {});
}
export function setValue(model, hive, key, name, t, v) {
  const vals = ensureKey(model, hive, key);
  const ex = findName(vals, name);
  if (ex !== null && ex !== name) delete vals[ex];
  vals[name] = { t, v };
}
export function getValue(model, hive, key, name) {
  const h = model[hive]; if (!h) return undefined;
  const k = findKey(h, key); if (k === null) return undefined;
  const n = findName(h[k], name); return n === null ? undefined : h[k][n];
}
export function deleteValue(model, hive, key, name) {
  const h = model[hive]; const k = h && findKey(h, key); if (k === null || k === undefined) return false;
  const n = findName(h[k], name); if (n === null) return false; delete h[k][n]; return true;
}
export function deleteKey(model, hive, key) { // サブツリーごと
  const h = model[hive]; if (!h) return 0;
  const l = key.toLowerCase(); let n = 0;
  for (const k of Object.keys(h)) { const kl = k.toLowerCase(); if (kl === l || kl.startsWith(l + '\\')) { delete h[k]; n++; } }
  return n;
}
export function applyOps(model, ops) {
  let n = 0;
  for (const o of ops) {
    if (o.op === 'key') ensureKey(model, o.hive, o.key);
    else if (o.op === 'set') { setValue(model, o.hive, o.key, o.name, o.t, o.v); n++; }
    else if (o.op === 'delvalue') deleteValue(model, o.hive, o.key, o.name) && n++;
    else if (o.op === 'delkey') deleteKey(model, o.hive, o.key) && n++;
  }
  return n;
}
export function parseToModel(input) { const m = emptyModel(); const ops = parseReg(input); applyOps(m, ops); return m; }
export function countModel(model, hives = ROOTS) { let keys = 0, values = 0; for (const h of hives) for (const k of Object.values(model[h] || {})) { keys++; values += Object.keys(k).length; } return { keys, values }; }
/** a に無い値/キーだけ b から補う (非破壊) */
export function fillMissing(a, b) {
  for (const [key, vals] of Object.entries(b || {})) {
    const k = findKey(a, key);
    if (k === null) { a[key] = structuredClone(vals); continue; }
    for (const [n, v] of Object.entries(vals)) if (findName(a[k], n) === null) a[k][n] = structuredClone(v);
  }
  return a;
}
