# REFERENCES — 外部ソース・素材・ツールの台帳

本リポジトリの正史が依存する**リポジトリ外**の一次資料・ツール・素材の所在を管理する唯一のファイル。
リポジトリ内の他の `.md` から外部絶対パスを直接参照してはならない。本ファイルのエントリ ID を使う。

- 管理方針: 正史ドキュメント (`docs/`・`README.md`・`tools/**/REPORT.md`) はリポジトリ外の絶対パスを書かない。
  repo 外パスを書く必要があるのは **このファイルだけ**。
- 読み方: 各エントリは `[ID] 説明` の形式。repo 内からは `docs/REFERENCES.md` の `[WIN64]` のように参照する。

---

## 1. 解析素材・レポート (repo 外)

| ID | 所在 | 内容 |
|---|---|---|
| `[STRATEGY]` | `../analysis/strategy.md` | 実行戦略・技術選定の正本。パイプライン・shim 一覧・マイルストーン M1〜M11 の定義元 |
| `[STRATEGY-SURVEY]` | `../analysis/strategy_survey.md` | 技術選定の調査資料 (lifter 比較) |
| `[TOOLCHAIN]` | `../analysis/toolchain_setup.md` | ツールチェイン整備記録 (RetDec → emcc PoC) |
| `[WIN64]` | `../analysis/win64/` (`REPORT.md`・`extracted/`・`block_manifest.json`・`pe_metadata.json`・`tools/nsis_extract.py`) | FL Studio win64 インストーラ解析。NSIS+Image-Line 独自拡張の抽出、FLEngine_x64.dll 実体 |
| `[MAC]` | `../analysis/mac/` (`REPORT.md`・`pkg_extract/`) | FL Studio mac 解析。dmg 展開・`FLEngine_x64.dylib` |
| `[ANALYSIS-PLUGINS]` | `../analysis/plugins/` (`ott/REPORT.md` 等) | プロプライエタリ plugin の事前解析 |
| `[LEGAL-WORK]` | `../analysis/legal_work/` | EULA/規約の抽出物・NSIS ヘッダ解析スクリプト (`nsis_hdr.py`) |
| `[SUBAGENT-RULES]` | `../analysis/SUBAGENT_RULES.md` | subagent 共通ルールの**原本 (repo 外)**。**repo 内正本は `docs/WORKFLOW.md`** (import 済み。原本は凍結) |
| `[CAB_TO_GH]` | `../analysis/CAB_TO_GH.md` | 旧 Linear `CAB-xxx` → GitHub issue `#N` の対応表 |
| `[RETROSPECTIVE]` | `../analysis/RETROSPECTIVE_2026-10-11.md` | 2026-10-11 レトロスペクティブ (報告訂正 36 commit の分析・規則案の根拠) |
| `[LINEAR-AUDIT]` | `../analysis/LINEAR_AUDIT_LOG.md` | 旧 Linear 運用の定期監査ログ (歴史資料) |
| `[PREFLIGHT]` | `../analysis/preflight.sh` | 環境検査・`--env` / `--lock` ヘルパ (歴史的。repo 内手順は `docs/WORKFLOW.md`) |
| `[MODEL-POLICY]` | `../analysis/MODEL_POLICY.md` | モデル指定・ゾンビ監視の方針 (PM 管理) |

`../analysis/` は **作業用 VM 上のリポジトリ外ディレクトリ**。リポジトリには含めない (`.gitignore` 対象外・クローン先に無い)。
CI や他人の環境では存在しないため、再現手順は本ファイルの所在情報を前提としない。

### 素材 (インストーラ・プラグイン)

| ID | 所在 | 内容 |
|---|---|---|
| `[DOWNLOADS]` | `~/ダウンロード/` | 元インストーラ・プラグイン素材 (FL win/mac、OTT、Kilohearts、Serum2、Fresh Air、Massive X)。Vital / Surge XT / Dexed は対象外 |

### ローカルツール

| ID | 所在 | 版 |
|---|---|---|
| `[EMSDK]` | `/opt/emsdk` | Emscripten 6.0.12 (pin。`tools/m1/flags.sh`) |
| `[RETDEC]` | `/opt/retdec` | RetDec v5.0 (歴史的。現行の主力 lifter は x64c / flelift / liftlib。DESIGN 参照 `docs/DECISIONS.md` D5) |
| `[GHIDRA]` | `/opt/ghidra` | Ghidra 12.1.4 (解析支援) |

---

## 2. Vendored 台帳 (リポジトリ同梱の外部コード)

同梱する外部コードは全てここに登記する。**取得元・版・ハッシュ・改変箇所**を書き、改変は upstream と diff できる形にする。
書式は `tools/ipp/shim/fft/PROVENANCE.md` の方式 (取得元表・同梱ファイル対応表・改変点) に合わせる。

| ID | パス (repo 内) | 取得元 | 版 / commit | 改変 | ライセンス | 詳細 |
|---|---|---|---|---|---|---|
| `[V-PFFFT]` | `tools/ipp/shim/fft/pffft/` | https://github.com/marton78/pffft (Julien Pommier の pffft の主要フォーク) | `aa16fd3db58de4ba5dae8b0438440bb9da46b6fa` (2026-09-29) | CAB-139 で `pffft_priv_impl.h` に `FUNC_SETUP_BYTES` / `FUNC_NEW_SETUP_INTO` を追加 (`PATCH (webstudio ...)` マーカ付き) | BSD 系 (FFTPACK v4/v5、UCAR 再配布条件) | `tools/ipp/shim/fft/PROVENANCE.md` |
| `[V-OTT-RECIPE]` | `tools/liftlib/liftlib/recipes/ott/` | `tools/m6`〜`tools/m10` の OTT 固有 IR pass を**無改変コピー** | m6〜m10 時点 | モジュールパスを環境変数 `OTT_CJS` で受ける形に変更 (判定ロジックは無改変) | 本プロジェクト生成 (OTT 固有 recipe) | 旧 `recipes/ott/README.md` の内容はここに統合。`m6_memfix.py` (CRT memmove/memset define 置換)・`m6_full_extract.py`・`ir7_argpass_fixed.py`・`ir8_valueflow.py`・`ir9_bootstraps.py`・`ir9_outcopy.py` (汎用 F7 が同型を機械検出)・`m10_coefref.py`/`m10_coefdump.mjs` |
| `[V-PYTHON]` | `tools/python/work/Python-3.12.1/`, `tools/python/work/fl-stubs/` | CPython 3.12.1 upstream + FL の `flapi` stub | 3.12.1 | なし | PSF | `tools/python/work/` は gitignore 対象。build 時取得 |
| `[V-VST3SDK]` | `tools/targets/serum2/work/vst3sdk/` | Steinberg VST3 SDK | — | なし | 独自 | `tools/targets/serum2/work/` は gitignore 対象 |
| `[V-SHARED-OSS]` | `tools/shared/work/src/` (`ffmpeg`・`flac`・`asmjit`・`blend2d`・`lame`・`ogg`・`wavpack`) | 各 upstream | 取得時点 | upstream から wasm 再ビルド (lift しない)。FL 由来コードとは別モジュール | LGPL / BSD / zlib 等 (`docs/LEGAL.md` §3) | `tools/shared/work/` は gitignore 対象 |
| `[V-PFFFT-UP]` | `tools/ipp/shim/fft/work/pffft_up/` | 同上 `[V-PFFFT]` の比較用 upstream 複製 | — | なし | BSD 系 | 差分確認用 |
| `[V-MASSIVEX]` | `tools/targets/massivex/work/{innoextract,issrc}/` | Inno Setup 抽出ツール類 | — | なし | 各種 | gitignore 対象 |
| `[V-ICALL]` | `tools/icall/disp_size/work/capnext/` | capstone next | — | なし | BSD | gitignore 対象 |
| `[V-FLP]` | `tools/flp/work/venv/...` | Python venv (`nothing` 等) | — | なし | — | gitignore 対象 |

**vendored の共通ルール**:

1. `tools/**/work/` と `tools/**/venv/` は**全て gitignore 対象でありvendored/worktreeスナップ**。
   正史の書換え対象にしない (PM 指示)。誤って commit しないこと。
2. worktree 検証 (`git archive HEAD` → `work/`) は repo 全体を丸写しするため REPORT.md の完全一致コピーが量産される。
   検証スナップショットは用済み後に削除し、commit しない。
3. repo に同梱する vendored コードは必ず本台帳に 1 行載せる。

---

## 3. 参照時の書式

repo 内ドキュメントでの書き方:

```markdown
素材: `docs/REFERENCES.md` `[WIN64]` の `extracted/block00031_PE.bin`
```

悪い例 (禁止): `/home/ubuntu/work/analysis/win64/REPORT.md` と repo 内 .md に直接書く。
