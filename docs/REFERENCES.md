# REFERENCES — 外部ソース・素材・ツールの台帳

本リポジトリの正史が依存する**リポジトリ外**の一次資料・ツール・素材の所在を管理する唯一のファイル。
リポジトリ内の他の `.md` から外部絶対パスを直接参照してはならない。本ファイルのエントリ ID を使う。

- 管理方針: 正史ドキュメント (`docs/`・`README.md`・`tools/**/REPORT.md`) はリポジトリ外の絶対パスを書かない。
  repo 外パスを書く必要があるのは **このファイルだけ**。repo 内の `.md` には上記 ID のみを記す
  (過去の実行環境の記載も同梱・絶対パスそのものは本ファイルに集約する)。
- 読み方: 各エントリは `[ID] 説明` の形式。repo 内からは `docs/REFERENCES.md` の `[WIN64]` のように参照する。

---

## 1. 解析素材・レポート (repo 外)

| ID | 所在 | 内容 |
|---|---|---|
| `[STRATEGY]` | `../analysis/strategy.md` | 実行戦略・技術選定の正本。パイプライン・shim 一覧・マイルストーン `MS1`〜`MS11` の定義元 (`MS12` は repo 内 `docs/STATUS.md` §2 で定義) |
| `[ANALYSIS-DIR]` | `../analysis/` | repo 外の解析作業ディレクトリ根。上記 `[STRATEGY]`・`[WIN64]`・`[MAC]`・`[LEGAL-WORK]`・`[SUBAGENT-RULES]` 等の親 |
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
| `[PM-SCRIPTS]` | `tools/pm/` | PM が VM 上で常駐・実行する PR / Issue / run の運用スクリプト (repo に取込済み。#793)。`watch_runs.sh` (run 監視)・`launch_issues.py` (自動着手)・`rest_heal.py` (担当なし PR の補完)・`sync_status.py` (Project Status 同期)・`heartbeat.sh` ほか。一覧と前提は `tools/pm/README.md`。`sweep_prs.sh` (GraphQL 版) は廃止、後継は `.github/scripts/watchdog.sh` と `rest_heal.py` |

`../analysis/` は **作業用 VM 上のリポジトリ外ディレクトリ**。リポジトリには含めない (`.gitignore` 対象外・クローン先に無い)。
CI や他人の環境では存在しないため、再現手順は本ファイルの所在情報を前提としない。

### 素材 (インストーラ・プラグイン)

| ID | 所在 | 内容 |
|---|---|---|
| `[WORK-M11]` | `$ARTIFACTS_DIR/work-m11.tar.zst` (Actions では `$HOME/artifacts/` に R2 から配置。取得指定は `docs/WORKFLOW.md` §11 の `oc_artifacts: work-m11`。展開先は `tools/m11/work/`) | `tools/m11/` の検証スナップショット (`boot*.drc.config.json` 等)。gitignore 対象で commit しない。#516 以前の生成物を含む (`docs/WORKFLOW.md` §11 #680) |
| `[DOWNLOADS]` | `~/ダウンロード/` | 元インストーラ・プラグイン素材 (FL win/mac、OTT、Kilohearts、Serum2、Fresh Air、Massive X)。Vital / Surge XT / Dexed は対象外 |
| `[PLUGINS-SERUM2]` | `$ARTIFACTS_DIR/plugins-serum2.tar.zst` (Actions では `$HOME/artifacts/` に R2 から配置。取得指定は `docs/WORKFLOW.md` §11 の `oc_artifacts: plugins-serum2`) | Xfer Serum 2 のインストーラ `Install_Xfer_Serum2_2.1.5.exe` を含む `.tar.zst` (展開は `tar --zstd -xf` で行い、展開先は各 REPORT で `work/` 配下に指定) |

### 素材の原本と R2 bundle の対応 (#2434)

R2 の bundle (`artifacts/<name>.tar.zst`) と、その原本の所在。原本が作業 VM のディスクにしか無いものは、VM を止める・消すと失われる。
`[未確認]` は本 run で中身や所在を確認していない項目。R2 上の object の有無は、認証情報を使わないため本 run では見ていない。

| bundle | 原本の所在 (ID) | bundle の中身 | VM だけに残るもの |
|---|---|---|---|
| `fl-win64` | installer の原本は `[DOWNLOADS]`。展開物は `[WIN64]` | 実測 (`tar --zstd -tf`): 最上位に installer `flstudio_win64_26.1.7.5653.exe` と `extracted/`。原本 installer の複製を含む | `block_manifest.json`・`pe_metadata.json` (`docs/WORKFLOW.md` §11: tarball に含まれない) |
| `toolchain-retdec` | 上流 RetDec v5.0 の配布物 (取得元は本台帳に無い `[未確認]`)。展開先は `[RETDEC]` | 実測: 最上位 `retdec/` (install tree) | bundle が唯一の複製かは `[未確認]` |
| `toolchain-emsdk` | 上流 emsdk (版は `tools/m1/flags.sh` の pin)。展開先は `[EMSDK]` | 実測: 最上位 `emsdk/` | 上流からの再取得経路は `[未確認]` |
| `plugins-ott` | `[DOWNLOADS]` (Xfer OTT 1.37。`docs/LEGAL.md`) | `[未確認]` (本 run では展開していない) | `[DOWNLOADS]` は VM 上 (`~/ダウンロード/`)。R2 上の有無は run ごとに変わり得る (`tools/plugins/reverb_delay/REPORT_APPENDIX.md` は不在を記録) |
| `plugins-freshair` | `[DOWNLOADS]` (Fresh Air 1.0.9。`docs/LEGAL.md`) | `docs/WORKFLOW.md` §11 の記述: 最上位 `Fresh Air.Win.zip` / `Fresh Air.pkg` (`[未確認]`) | `[DOWNLOADS]` は VM 上 |
| `plugins-serum2` | `[PLUGINS-SERUM2]` (bundle そのものが原本の複製) | installer `Install_Xfer_Serum2_2.1.5.exe` の記述 (`[未確認]`) | 二次の所在は `[未確認]` |
| `plugins-massivex` | `[DOWNLOADS]` (Massive X) | `[未確認]`。`docs/LEGAL.md` は『未取得』と記す | `[DOWNLOADS]` は VM 上 |
| `plugins-kilohearts` | `[DOWNLOADS]` (Kilohearts Installer 2026-03 release。`docs/LEGAL.md`) | `[未確認]` | `[DOWNLOADS]` は VM 上 |
| `analysis-ott-binaries` | 展開元は `[DOWNLOADS]` の OTT。展開物の所在は `[ANALYSIS-PLUGINS]` の `ott/binaries/` | `OTT_vst2_win64.dll` ほかの実機バイナリ (`docs/WORKFLOW.md` §11 の記述) | 原本 (`[DOWNLOADS]`) は VM 上。R2 の複製の有無は `[未確認]` |
| `analysis-mac-shared` | FL mac 版の原本 (pkg・dmg) は `[DOWNLOADS]`。展開物は `[MAC]` の `pkg_extract/payload_out/` | FL mac の `Shared/` の dylib 25 本 (`docs/WORKFLOW.md` §11 の記述。取得実績は `tools/shared/oss/ilsvg/REPORT.md`) | **VM を止める/消すと失われる**: mac pkg の残り (`Libs/FLEngine_x64.dylib`・MCP pyc・`Resources/FL`) は R2 に無く VM のみ (`#874` [CI-18] が open で、その投入を扱う) |
| `work-*` (9 種) | 派生物で原本ではない。再生成手順は各 REPORT が正本 | 検証スナップショット (gitignore 対象) | 再生成に VM 専用の道具 (例: `[GHIDRA]`) が要るかは `[未確認]` |
| `apt-mingw` | R2 の素材ではない (runner に apt 導入) | — | — |

### ローカルツール

| ID | 所在 | 版 |
|---|---|---|
| `[OPT-TOOLS]` | `/opt/` | ローカルツールのインストール根。配下に `[EMSDK]`・`[RETDEC]`・`[GHIDRA]`・`[_TEST]` |
| `[EMSDK]` | `/opt/emsdk` | Emscripten 6.0.12 (pin。`tools/m1/flags.sh`) |
| `[RETDEC]` | `/opt/retdec` | RetDec v5.0 (歴史的。現行の主力 lifter は x64c / flelift / liftlib。DESIGN 参照 `docs/DECISIONS.md` D5) |
| `[GHIDRA]` | `/opt/ghidra` | Ghidra 12.1.4 (解析支援) |
| `[_TEST]` | `/opt/_test/` | toolchain E2E 実証のスクラッチ領域 (`tools/m1` が参照) |
| `[PNPM-HOME]` | `/home/ubuntu/.local/share/pnpm/bin` | pnpm (と同梱 node) のユーザローカル配置 (`tools/shared`・`tools/audio/asio` が参照) |
| `[APT-MINGW]` | `/usr/bin/x86_64-w64-mingw32-gcc` (apt 導入の MinGW-w64 クロスコンパイラ) | 版は未記録 (`tools/gui/flengine/REPORT_APPENDIX.md` §6i の実行で使用。再現時は `x86_64-w64-mingw32-gcc --version` の出力を REPORT に残す) |

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
| `[V-CP932-BESTFIT]` | `tools/shimx/src/cp932_tab.c` (生成物 192 KB) | https://unicode.org/Public/MAPPINGS/VENDORS/MICSFT/WindowsBestFit/bestfit932.txt (Microsoft / Unicode Consortium) | 取得時点 (入力は `tools/shimx/work/` に取得、非 commit) | `tools/shimx/scripts/gen_cp932.py` による C 配列への機械変換のみ (手編集禁止) | Unicode Terms of Use | `tools/shimx/REPORT_SHX-T8.md` §15.3 |
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

---

## 4. 外部資産の環境変数 (`tools/shared/env.sh` / `paths.py` / `paths.mjs`)

tools/ のスクリプトが repo 外の資産を参照するときの共通定義 (#312、親 #294)。3 つは同じ変数名・同じ既定値を持ち、
**環境変数が設定済みならそれを優先、未設定時のみ既定値**を使う。`tools/shared/test_paths.sh` で一致を検査する。

| 変数 | エントリ ID | 既定値 |
|---|---|---|
| `REPO_ROOT` | (repo 自身) | `git rev-parse --show-toplevel` (git 外では `tools/shared/` の 2 つ上) |
| `ANALYSIS_DIR` | `[ANALYSIS-DIR]` | `/home/ubuntu/work/analysis` |
| `FL_WIN64_DIR` | `[WIN64]` | `$ANALYSIS_DIR/win64` |
| `FL_MAC_DIR` | `[MAC]` | `$ANALYSIS_DIR/mac` |
| `PLUGINS_DIR` | `[ANALYSIS-PLUGINS]` | `$ANALYSIS_DIR/plugins` |

使い方 (既存スクリプトの置換は area ごとの子 issue で行う):

```sh
# bash: スクリプト冒頭で
source "$(git rev-parse --show-toplevel)/tools/shared/env.sh"
PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
```

```python
# python
import sys; sys.path.insert(0, f"{REPO}/tools/shared")   # REPO は __file__ から求める
from paths import FL_WIN64_DIR
PE = f"{FL_WIN64_DIR}/extracted/block00031_PE.bin"
```

```js
// node
import { FL_WIN64_DIR } from '../shared/paths.mjs';   // 呼び出し元からの相対
const PE = `${FL_WIN64_DIR}/extracted/block00031_PE.bin`;
```

Actions では `FL_WIN64_DIR` に fl-win64 の展開先を指定する (`docs/WORKFLOW.md` §11)。
