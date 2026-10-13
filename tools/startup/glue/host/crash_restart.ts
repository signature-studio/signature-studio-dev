// crash_restart.ts — G12 クラッシュレポータの代替 (ST-T10 / #117)。
//   1. クラッシュログを VFS の <UserData>\Crash\<ts>.log に保存 (FL 実機と同じ Win パス → wvfs 写像)
//   2. ブラウザのダウンロードとして提示 (download コールバック。browser 既定は browserDownload)
//   3. Send は WinInet オフライン (ERROR_INTERNET_DISCONNECTED=12163) と同じ失敗表示。ネットワークは触らない
//   4. `fldiagnostic /restartfl` を winstubs が検知したらページ再ロード (GlueHost.onRestart 経由)
import type { GlueHost } from './glue_host.ts';

export const CRASH_DIR_WIN = (user: string) => `C:\\Users\\${user}\\Documents\\Image-Line\\FL Studio\\Crash`;
export const ERROR_INTERNET_DISCONNECTED = 12163;

export interface CrashInfo {
  /** 例外メッセージ / trap 理由 */
  message: string;
  stack?: string;
  /** 'trap' (wasm trap) / 'js' (JS 例外) / 'engine' (FL の SEH 相当) など */
  kind?: string;
}

export interface CrashLog { winPath: string; mount: string; path: string; name: string; bytes: Uint8Array; }
export interface SendResult { ok: false; error: number; message: string; }

export interface CrashReporterOptions {
  now?: () => Date;
  /** ダウンロード提示。既定 = browserDownload (DOM が無ければ何もしない) */
  download?: (name: string, bytes: Uint8Array) => void;
  appTitle?: string;
}

const pad = (n: number, w = 2) => String(n).padStart(w, '0');
/** UTC の `YYYYMMDD-HHMMSS-mmm` (ファイル名に使える・並べ替え可能) */
export function crashStamp(d: Date): string {
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}-` +
    `${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}-${pad(d.getUTCMilliseconds(), 3)}`;
}

export function browserDownload(name: string, bytes: Uint8Array): void {
  const g: any = globalThis;
  if (!g.document || !g.Blob || !g.URL?.createObjectURL) return;
  const url = g.URL.createObjectURL(new g.Blob([bytes], { type: 'text/plain' }));
  const a = g.document.createElement('a');
  a.href = url; a.download = name;
  g.document.body.appendChild(a); a.click(); a.remove();
  g.URL.revokeObjectURL(url);
}

export class CrashReporter {
  readonly logs: CrashLog[] = [];
  downloads = 0;
  sends = 0;
  private host: GlueHost;
  private o: Required<CrashReporterOptions>;
  private seq = 0;

  constructor(host: GlueHost, o: CrashReporterOptions = {}) {
    this.host = host;
    this.o = {
      now: o.now ?? (() => new Date()),
      download: o.download ?? browserDownload,
      appTitle: o.appTitle ?? 'FL Studio',
    };
  }

  /** ログを <UserData>\Crash\ に書いて flush する。同一ミリ秒でも名前が衝突しない */
  async saveCrashLog(info: CrashInfo): Promise<CrashLog> {
    const d = this.o.now();
    const name = `${crashStamp(d)}-${this.seq++}.log`;
    const text = [
      `${this.o.appTitle} has encountered an error and needs to restart`,
      `time: ${d.toISOString()}`,
      `kind: ${info.kind ?? 'js'}`,
      `message: ${info.message}`,
      `stage: ${this.host.stages.map((s) => s.name).join('>') || '(none)'}`,
      `stack:`,
      info.stack ?? '(none)',
      '',
    ].join('\n');
    const bytes = new TextEncoder().encode(text);
    const winPath = `${CRASH_DIR_WIN(this.host.o.username)}\\${name}`;
    const r = this.host.writeWin(winPath, bytes);
    await this.host.onYield();
    const log: CrashLog = { winPath, mount: r.mount, path: r.path, name, bytes };
    this.logs.push(log);
    return log;
  }

  /** 保存済みログを VFS から読み直してダウンロードに提示する (提示内容 = 永続された内容) */
  offerDownload(log: CrashLog): void {
    this.o.download(log.name, this.host.readWin(log.winPath));
    this.downloads++;
  }

  /** ダイアログの Send。WinInet はオフライン (G11) なので必ず失敗を返す。ネットワークは使わない */
  send(_log: CrashLog): SendResult {
    this.sends++;
    return { ok: false, error: ERROR_INTERNET_DISCONNECTED, message: 'Could not send the report: no internet connection (ERROR_INTERNET_DISCONNECTED 12163).' };
  }

  /** クラッシュ時の一括処理: 保存 → ダウンロード提示。Send は UI のボタンから send() を呼ぶ */
  async report(info: CrashInfo): Promise<CrashLog> {
    const log = await this.saveCrashLog(info);
    this.offerDownload(log);
    return log;
  }
}
