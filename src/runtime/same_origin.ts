/**
 * same_origin.ts — gui=wasm の glue (script) と app (descriptor) は同一オリジンの URL だけ読む。
 * <script src> は相手が Cross-Origin-Resource-Policy: cross-origin を返せば COEP の下でも読み込まれ、実行されるため、
 * 読込の前に検査する (任意 script の注入を止める)。data: / javascript: は origin が "null"、//host は別 origin になる。
 */
export function resolveSameOriginUrl(raw: string, base: string): string {
  const url = new URL(raw, base);
  const origin = new URL(base).origin;
  if (url.origin === "null" || url.origin !== origin) {
    throw new Error(`同一オリジンの URL だけ読めます (別オリジン・data:・//host は不可): ${raw}`);
  }
  return url.href;
}
