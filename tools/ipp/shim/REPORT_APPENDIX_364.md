# 付録: 環境パス置換 (#364, 親 #294・先行 #312) — tools/ipp/shim/

> **正本**: `tools/ipp/shim/REPORT.md` (本体)。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため、#364 で追記した節を本体から
> **分割移動**した全文 (内容は削除していない)。外部資産は `docs/REFERENCES.md` の `[WIN64]`・環境変数 `FL_WIN64_DIR` で参照する。

## 環境パス置換 (#364): 外部資産の絶対パスを tools/shared へ

既知類型との関係 (DEFECTS.md): 該当なし (パス参照の置換のみ。挙動は変えない = #294 の条件)。

### 変更

`tools/ipp/shim` の旧 VM 絶対パス参照 10 行 (work/ 除く) を置換。既定値は従来と同一で、`tools/shared/env.sh`・`paths.py`・`paths.mjs` の
`ANALYSIS_DIR` 既定値 → `FL_WIN64_DIR=$ANALYSIS_DIR/win64` (`docs/REFERENCES.md` `[WIN64]`) と同じ連鎖。

| ファイル | 置換 |
|---|---|
| `shim_e2e.sh` `fft/fft_e2e.sh` `test/resize_oracle_run.sh` `test/fill3_oracle_run.sh` | `source "$IPP/../shared/env.sh"` + `DLL="$FL_WIN64_DIR/extracted/block24356_PE.bin"` |
| `sigscan.py` | `tools/shared/paths.py` の `FL_WIN64_DIR` から `EXT` を組む |
| `test/{fill3_oracle,resize_oracle,sp57,sweep2,verify_cab262_quirks}.c` | 新規 `test/fl_dll_path.h` の `fl_ipp_dll_path()` |

`fl_ipp_dll_path()` の解決順は env.sh・paths.py と同じ: `$FL_WIN64_DIR` → `$ANALYSIS_DIR/win64` → C 定数 `FL_DLL_DEFAULT_ANALYSIS_DIR` (従来 VM の既定値) の `/win64`。
env を source しなくても (直接起動でも) 従来どおり動く。`resize_oracle` / `fill3_oracle` は argv の `[dll]` が明示されたらそれを優先し、
引数ループの後に `dll` が未設定のときだけヘルパーを呼ぶ (`verify_cab262_quirks` は従来から `argc > 1 ? argv[1] : helper`)。
既定値を変えるときは env.sh・paths.py・paths.mjs・`fl_dll_path.h` の 4 か所を揃える。

### 検証 (検証時点の置換前 `origin/main` = 1353c62、素材は `fl-win64` のみ)

- 受入条件 1: `grep -rn '/home/ubuntu' tools/ipp/shim --include=*.sh --include=*.py --include=*.json --include=*.ts --include=*.mjs --exclude-dir=work | wc -l` → 0。`--include` を外して `work/` 以外を全検索すると `test/fl_dll_path.h:9` の C 既定値定数 (`FL_DLL_DEFAULT_ANALYSIS_DIR`、main 由来) と `REPORT.md` の説明文が残る。`.h` の定数は本 PR の対象外 (別 issue で扱う)。
- 受入条件 2: 置換前 (`origin/main` の detached worktree) と置換後を gcc でビルドし、DLL を開くパスを `strace -e trace=openat` で採取。
  置換前は旧 VM 既定パス (`[WIN64]` への symlink → fl-win64 展開先)、置換後は `$FL_WIN64_DIR/extracted/block24356_PE.bin` を開く。
  3 バイナリ (`verify_cab262_quirks` `resize_oracle` `fill3_oracle`) 全て、置換前後で同一ファイル内容を参照。
- 出力比較 (AVX-512 なし Runner = AMD EPYC 7763): `resize_oracle` (25 行・sha256 先頭 12 桁 18ef187dc344) と `fill3_oracle` (7 行・63f77eb814f9) の stdout は
  1 行目 (`--dump` 出力先パス) を除き置換前後で `cmp` 一致。ただし 3 本とも実 DLL の初期化 (`ippSetCpuFeatures(~0)` の AVX-512 経路) で `Illegal instruction`
  (`/proc/cpuinfo` の avx512 フラグ 0 件)。SIGILL ハンドラ (LD_PRELOAD) で採取した停止命令: rip=0x180c3b2eb・先頭バイト `62 f2 7d 28 7c c5` (0x62 = EVEX プリフィックス)。
  この一致は SIGILL までの出力の一致で、オラクル本体の比較結果 (mismatch 数) は当時 **未検証**。
- ネガティブコントロール: `FL_WIN64_DIR=/nonexistent` → `/nonexistent/extracted/block24356_PE.bin: No such file or directory` (rc=1)。
- 構文: `bash -n` 5 本・`py_compile` `sigscan.py`・gcc ビルド 3 本 OK。所要: ビルド + 実行 各 1 秒未満。load average 0.20–0.27 (1 分値)、直列。

### 検証 (Copilot Code Review 指摘 medium への修正後)

修正: C ヘルパーが env 未設定で exit していた退行 (従来は直接起動できた) を、env.sh と同じ既定値連鎖に直した。`[dll]` 明示時はヘルパーを呼ばない。
Runner = Intel Xeon 6973P (当時の記録: `/proc/cpuinfo` の avx512 フラグあり、このため SIGILL せず完走)。※この記録の採取時 CPU は本ファイルに根拠 (`/proc/cpuinfo`) が残っていないため未確認。下の AMD EPYC 7763 の 2026-10-13 実測 (SIGILL) と同一 Runner かは判定できないので、両者を同一 Runner の結果として扱わない。素材 `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開し、
旧 VM 既定パスを同 dir への symlink で用意して「従来どおりの直接起動」を再現した。ビルドは `gcc -O1 -I src -I test ... -lm` (`*_oracle_run.sh` と同じフラグ)。

| 起動 | 結果 (`strace -e trace=openat` で採取した DLL パス) |
|---|---|
| env なし・引数なし: `sp57` `sweep2` `verify_cab262_quirks` `resize_oracle` `fill3_oracle` | 5 本とも rc=0、旧 VM 既定パス (`$ANALYSIS_DIR` 既定値/win64/extracted/block24356_PE.bin) を open (`resize_oracle` `fill3_oracle` は `loaded <path>` 行にも出力) |
| 明示引数 `[dll]` + `FL_WIN64_DIR=/nonexistent`: `resize_oracle` `fill3_oracle` `verify_cab262_quirks` | 3 本とも引数の DLL を open し、`/nonexistent` は一度も open しない (引数優先・ヘルパー不使用) |
| `FL_WIN64_DIR=<展開先>`: `sweep2` `resize_oracle` `fill3_oracle` | 展開先の DLL を open |
| `FL_WIN64_DIR=/nonexistent` / `ANALYSIS_DIR=/nonexistent`: `sweep2` | それぞれ `/nonexistent/extracted/...`・`/nonexistent/win64/extracted/...` で No such file (env が既定値より優先) |

所要: `sp57` 30.2 s (strace 下)・`resize_oracle` 0.26 s・`fill3_oracle` 0.04 s・`sweep2` 0.23 s・`verify_cab262_quirks` 0.02 s。load average 0.56 (1 分値)、直列。
env なし直接起動 (strace なし) の完走結果: `resize_oracle` rc=0・39 行・
`SUM {"cases":82056,"case_diff":359,"st_mis":0,"byte_diff":55588,"px_diff":55588,"px_tot":5912624}`、`fill3_oracle` rc=0・76 行、`verify_cab262_quirks` rc=0・65 行。
これらは上記 Xeon 6973P 記録 (採取時 CPU 未確認・avx512 あり) の時点での実測で、置換前後の mismatch 数の突き合わせ (origin/main 側の再ビルド比較) は本修正では行っていない (置換行以外の変更なし)。

### 検証 (再検証・受入条件 2 の残り、検証対象 = 置換前 `1353c62` / 置換後 `af8ba9cc`)

- 置換前 = `1353c62` (detached worktree)・置換後 = `af8ba9cc` を、同一の gcc フラグ (`-O1 -g -ffp-contract=off -fno-fast-math`) で
  `resize_oracle` `fill3_oracle` `verify_cab262_quirks` にビルド (`gen_shim.py` は `work/flengine_ipp_names.json` を要するため未実行。gen/ のコミット済み生成物を使用)。
- 既定値 (env 未設定・引数なし) の `openat` を `strace -f -e trace=openat` で採取: 3 本とも置換前後で **同一パス** (旧 VM 既定値 `[WIN64]` 相当の `extracted/block24356_PE.bin`) を開き、
  Runner には存在しないため ENOENT (rc=1)。既定値の同一性はこの一致で確認。
- `FL_WIN64_DIR=$RUNNER_TEMP` (`fl-win64` 展開先 `extracted/`) を与えた実行: 3 本とも rc=132 (SIGILL)、置換前後の stdout は 1 行目 (`--dump` 出力先) を除き `diff` 一致 (`resize_oracle` 26 行・`fill3_oracle` 8 行・`verify_cab262_quirks` 1 行)。
- 所要: 各実行 0〜1 秒、直列。素材 `fl-win64` の展開 10.5 s (`tar --zstd -xf`)。Runner CPU は AMD EPYC 7763 (`/proc/cpuinfo` model name = `AMD EPYC 7763 64-Core Processor`、avx512f フラグ 0 件、nproc 4。2026-10-13 採取)。上の Xeon 6973P 記録 (採取時 CPU 未確認) とは同一視しない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| AVX-512 非対応 Runner で実 DLL オラクルが SIGILL のため、置換前後の mismatch 数 (`SUM` 行) を比較できない | 既定パス・SIGILL 点までの出力の一致のみ確認 | #294 (AVX-512 対応 Runner) |

### 検証範囲 / 範囲外 / 未解決

範囲外: `shim_e2e.sh` `fft_e2e.sh` `*_oracle_run.sh` の通し実行 (emcc = `toolchain-emsdk` と `work-liftlib` 等の生成物が要る)、`sigscan.py` の実行 (`work/win_refs.json` が要る。`EXT` 定義行のみ確認)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 置換前 (`origin/main`) と置換後の mismatch 数 (`SUM` 行) の AVX-512 Runner での突き合わせ | 出力同一性は AVX-512 なし Runner の SIGILL 点までと、置換後単独の完走結果のみ | #294 にコメント |
| shim_e2e.sh 通し実行を `oc_artifacts: fl-win64 toolchain-emsdk work-liftlib` 付きで未実施 | 置換行以外の挙動は未検証 | 本 PR のレビュー run |
