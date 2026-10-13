# REPORT (SHX-T12 / #789) — shimx の構造化 file trace (JSON Lines)

> 親: `tools/shimx/REPORT.md` (#105 ST-T5 の子)。本ファイルは SHX-T12 の実測のみを持つ。
> 検証起点: 本ブランチ `789-shimx-file-trace` (base `origin/main` = `3418333a`)。

## 1. 結論

- `SHIMX_TRACE_FILE=<path>` (または API `shimx_set_trace_file(path)`) で、file API の呼出を **1 行 1 イベントの JSON** として出力する。
- 対象は CreateFileW / CreateFileA / GetFileAttributesW / FindFirstFileW / FindFirstFileExW / FindNextFileW / ReadFile (open 起点の読み出し)。
- 既存の `SHIMX_TRACE=1` (stderr の自由文) は**変更なし**。`test.sh` は HEAD と同じく全 PASS (rc=0)。
- 単体テスト `test/ftrace/ftrace_test.sh` は PASS (実測 3.97 s)。ネガコン (無効時 0 行) を含む。

## 2. 出力仕様

1 行 1 JSON。キーは固定 (欠ける値は `null`):

| キー | 型 | 内容 |
|---|---|---|
| `seq` | int | 0 始まりの連番 (プロセス内 / 出力ファイル単位) |
| `api` | str | 呼出 API 名 (`CreateFileW` 等) |
| `guest` | str / null | guest が渡した元の文字列 (UTF-8 化。ReadFile は null) |
| `posix` | str / null | 仮想 FS で解決したパス (解決失敗は null) |
| `name` | str / null | FindFirst/Next が返したエントリ名 (失敗時 null) |
| `access` / `disp` / `flags` | str/int/str / null | CreateFile の引数。`access`・`flags` は `0x%08x` 文字列 |
| `write` | bool | 書込系 open か (GENERIC_WRITE/ALL または CREATE_NEW/CREATE_ALWAYS/OPEN_ALWAYS/TRUNCATE_EXISTING) |
| `ok` | bool | 成功か |
| `err` | int | 失敗時の Win32 エラーコード (成功時 0) |
| `attr` | str / null | GetFileAttributesW の結果 (`0x%08x`) |

**ReadFile の数え方**: 同一ハンドルの **初回 read** と **失敗した read** のみ出力する (成功した 2 回目以降は省く)。ファイルごとの読出しの有無を示すのが目的のため。

## 3. 実装

- `src/trace.c` (新規): JSON Lines の書出し。`g_ftr_lk` で直列化し、1 イベントごとに `fflush`。
- `src/shimx_internal.h`: `ShxFtrEv` 構造体・`SHX_FTRACE_ON()`。既存の `SHX_TRACE` マクロは**未変更**。
- `src/file.c`: 上記 API の末尾に `ftr_*` を追加。引数の変換は `SHX_FTRACE_ON()` が真のときだけ行う (トレース無効時のコストを抑える)。
- `src/handles.c`: 遅延初期化時に `shx_ftrace_open_env()` を呼ぶ。
- `src/shimx.h`: `shimx_set_trace_file()` を公開。
- `data/sigs.json`: `gen_sigs.py` で再生成 (新規 3 シンボルのみ追加。`sig_gate` が要求)。

## 4. 数え方の定義と再計算

`scripts/ftrace_summary.py <trace.jsonl>` が集計する。定義:

- `events`: 行数 (空行は除く)。JSON として読めない行があれば exit 2
- `by_api`: `api` ごとの件数
- `ok` / `fail`: `ok` が true / false の件数
- `write`: `write` が true の件数
- `fail_err`: fail の `err` ごとの件数
- `distinct_posix_opened`: `api` が CreateFile* かつ `ok` かつ `posix` 非 null の一意パス数

再計算: `python3 tools/shimx/scripts/ftrace_summary.py <file> --json out.json`

## 5. 実測 (テストドライバ `test/ftrace/ftrace_main.c` の `ops` 操作)

| 項目 | 値 |
|---|---|
| events | 10 |
| by_api | CreateFileW 2 / CreateFileA 1 / GetFileAttributesW 2 / FindFirstFileW 2 / FindNextFileW 2 / ReadFile 1 |
| ok / fail | 6 / 4 |
| write | 1 (CREATE_ALWAYS の out.txt) |
| fail_err | {2: 3, 18: 1} (ERROR_FILE_NOT_FOUND ×3 / ERROR_NO_MORE_FILES ×1) |
| distinct_posix_opened | 2 |

`ftrace_test.sh` の結果: rc=0 / 3.97 s / load 0.18 0.25 0.22 / PASS 4 段 (✓ 4 件 + 完了行)。

`bash test.sh` (既存の全体テスト): rc=0 / 37 s。

## 6. ネガティブコントロール

- トレース無効 (`shimx_set_trace_file` 未呼出) の同一操作: 出力に `--TRACE-BEGIN--` が無い。
- 環境変数 `SHIMX_TRACE_FILE` 無しの NODERAWFS ビルド: トレースファイルが生成されない。
- 不正 JSON 行を含む入力: `ftrace_summary.py` が exit 2。

## 7. 既知の制約 (未解決)

- **既定 (MEMFS) ビルドでは guest の `getenv` から host の環境変数が見えない**。`SHIMX_TRACE_FILE` は NODERAWFS ビルドでのみ効く (実測: `env=(null)` / `env=/tmp/x`)。既存の `SHIMX_TRACE` も同じ制約で、`tools/m11/shimx_link/run_trace.mjs` は `_shimx_set_trace(1)` の export で回避している。
  - 本件では `run_trace.mjs` を変更していない。m11 の本番 wasm に `shimx_set_trace_file` を export するには wasm の再ビルドが必要で、m8/m11 素材の再生成を伴うため本 run では検証できない。**未起票: m11 harness (`run_trace.mjs`) に `shimx_set_trace_file` の export を足す作業。PM に起票を依頼する**。
- 対象 API は受入条件どおり 6 種 + FindFirstFileExW。`CreateFileA` は `ftr_create` 内で `MultiByteToWideChar` による元文字列の復元を行う (トレース有効時のみ)。
- 本 run では m11 本番 (`run_trace.mjs`) の実 boot で JSON を収集していない (素材の再生成が必要)。受入条件の「実 boot の open() trace」の実測は、上記の未起票分で行う。

## 8. 再現

```
bash tools/shimx/test/ftrace/ftrace_test.sh   # 単体テスト (約 4 s)
bash tools/shimx/test.sh                       # 既存の全体テスト (約 37 s)
python3 tools/shimx/scripts/ftrace_summary.py <trace.jsonl>
```

注: `test.sh` は実行の副産物として `exports.txt` / `inventory.md` / `BACKLOG.md` / `data/coverage.json` / `data/inventory.csv` を書き換えるが、m8/m11 素材が無いと closure が欠けるため**コミットしていない** (HEAD に戻した)。`data/sigs.json` のみ `gen_sigs.py` で意図的に更新している。
