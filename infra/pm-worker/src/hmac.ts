import { createHmac, timingSafeEqual } from "node:crypto";

const PREFIX = "sha256=";

export function signBody(secret: string, body: string): string {
  return PREFIX + createHmac("sha256", secret).update(body, "utf8").digest("hex");
}

// X-Hub-Signature-256 の検証。署名が無い・形式が違う・長さが違う場合は比較せず false を返す。
export function verifySignature(secret: string, body: string, header: string | null | undefined): boolean {
  if (!secret || typeof header !== "string" || !header.startsWith(PREFIX)) return false;
  const expected = Buffer.from(signBody(secret, body), "utf8");
  const given = Buffer.from(header, "utf8");
  if (given.length !== expected.length) return false;
  return timingSafeEqual(given, expected);
}
