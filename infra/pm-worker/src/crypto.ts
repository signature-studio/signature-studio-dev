// App の private key・webhook secret を DO に保存するための AES-GCM。鍵 (STORE_KEY) は Worker の secret binding で、
// DO のストレージには置かない。形式: `v1.<iv b64url>.<ciphertext b64url>`。
const enc = new TextEncoder();
const dec = new TextDecoder();

export function b64u(buf: ArrayBuffer | Uint8Array): string {
  const u = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = "";
  for (const b of u) s += String.fromCharCode(b);
  return btoa(s).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

export function fromB64u(s: string): Uint8Array {
  const p = s.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - (s.length % 4)) % 4);
  const bin = atob(p);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function importKey(keyB64u: string): Promise<CryptoKey> {
  const raw = fromB64u(keyB64u);
  if (raw.length !== 32) throw new Error("STORE_KEY must be 32 bytes (base64url)");
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}

export async function sealText(keyB64u: string, plaintext: string): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await importKey(keyB64u), enc.encode(plaintext));
  return `v1.${b64u(iv)}.${b64u(ct)}`;
}

export async function openText(keyB64u: string, sealed: string): Promise<string> {
  const [v, iv, ct] = sealed.split(".");
  if (v !== "v1" || !iv || !ct) throw new Error("bad sealed format");
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: fromB64u(iv) }, await importKey(keyB64u), fromB64u(ct));
  return dec.decode(pt);
}

// 定数時間の文字列比較 (state / nonce 用)。
export function safeEqual(a: string, b: string): boolean {
  const x = enc.encode(a);
  const y = enc.encode(b);
  let d = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) d |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return d === 0;
}

export function randomToken(bytes = 16): string {
  return b64u(crypto.getRandomValues(new Uint8Array(bytes)));
}
