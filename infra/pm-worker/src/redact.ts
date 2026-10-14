// /status とログに出す自由文 (エラー文・ログの note) から、secret・token・PEM を取り除く。
// /status は集計だけを返すので通常は自由文が無い。これは『エラー文に混ざった場合』の最後の防壁。
const MASK = "[redacted]";

const PATTERNS: RegExp[] = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)/g,
  /\b(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,})/g,
  /\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}/g,
  /\bBearer\s+[\w.~+/=-]{8,}/gi,
  /\bsha(?:1|256)=[0-9a-f]{40,}/gi,
];

// literals は実行時に分かっている secret (webhook secret・PEM・installation token・STORE_KEY)。短すぎるものは対象外。
export function redact(s: string, literals: readonly string[] = []): string {
  let out = s;
  for (const lit of literals) if (lit && lit.length >= 8) out = out.split(lit).join(MASK);
  for (const re of PATTERNS) out = out.replace(re, MASK);
  return out;
}
