import { createPublicKey, createVerify } from "node:crypto";

// JWT (RS256) の署名を、同じ鍵の公開鍵で検証し、ヘッダーとクレームを返す。
export function verifyJwtShape(jwt: string, privatePkcs8Pem: string): { alg: string; iss: string; iat: number; exp: number } {
  const [h, c, s] = jwt.split(".");
  const pub = createPublicKey(privatePkcs8Pem);
  const v = createVerify("RSA-SHA256");
  v.update(`${h}.${c}`);
  if (!v.verify(pub, Buffer.from(s, "base64url"))) throw new Error("bad jwt signature");
  const head = JSON.parse(Buffer.from(h, "base64url").toString());
  const claims = JSON.parse(Buffer.from(c, "base64url").toString());
  if (claims.exp - claims.iat > 600) throw new Error("jwt lifetime > 10 min");
  return { alg: head.alg, ...claims };
}
