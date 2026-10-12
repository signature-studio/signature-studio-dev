// 外部資産パスの共通定義 (node)。tools/shared/env.sh と同じ変数名・既定値。
// 使い方: import { FL_WIN64_DIR } from '<repo>/tools/shared/paths.mjs'
// 環境変数が設定済みならそれを優先し、未設定時のみ従来 (作業用 VM) の既定値を使う。
// 変数と docs/REFERENCES.md のエントリ ID の対応は docs/REFERENCES.md §4。
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

function repoRoot() {
  try {
    const out = execFileSync('git', ['-C', here, 'rev-parse', '--show-toplevel'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    if (out) return out;
  } catch {}
  return path.resolve(here, '..', '..');
}

export const REPO_ROOT = process.env.REPO_ROOT || repoRoot();
export const ANALYSIS_DIR = process.env.ANALYSIS_DIR || '/home/ubuntu/work/analysis';
export const FL_WIN64_DIR = process.env.FL_WIN64_DIR || `${ANALYSIS_DIR}/win64`;
export const FL_MAC_DIR = process.env.FL_MAC_DIR || `${ANALYSIS_DIR}/mac`;
export const PLUGINS_DIR = process.env.PLUGINS_DIR || `${ANALYSIS_DIR}/plugins`;

export const ALL = { REPO_ROOT, ANALYSIS_DIR, FL_WIN64_DIR, FL_MAC_DIR, PLUGINS_DIR };

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  for (const [k, v] of Object.entries(ALL)) console.log(`${k}=${v}`);
}
