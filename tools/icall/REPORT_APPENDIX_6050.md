# tools/icall 付録 — #6050 (ICALL-124): 0x1803dee20 の xmm0 不一致 1 件の原因と既定化

親: #4348 (ICALL-116/101)。測定基準は #4348 の `6af773cb4` (main 未取り込みの commit)。

## 1. 結論

- **原因: lift / route / 範囲のどれでもなく、harness 側 (`tools/ott/native/ott_native.c` の `k_HeapAlloc`) の順序バグ。**
  `OTT_KEEP_XMM0=1` の経路が `xmm0` を退避する前に `getenv()` を初めて呼んでいた。libc の `getenv` が `xmm0` を書き換え、退避値が環境変数名の断片 `"OTT_KEEP"` (`5045454b5f54544f`) になっていた。
- **修正 (2 commit)**: (a) 退避を `getenv` より前に移す (`dd4e2b602`)、(b) 既定を ON にする。`OTT_KEEP_XMM0=0` で従来 (退避無し) に戻せる (`af7718c92`)。
- 修正の効果: `0x1803dee20` は既定で 0/8 → **8/8**。`fa_sweep.sh 8 60` の bit 一致は 55 → **56** (悪化なし)。

## 2. 事前の再現 (測定 commit `6af773cb4`、`fa_cmp.py 1803dee20 --n 8`)

| 設定 | match | mismatch | 不一致の値 (n=0) |
|---|---|---|---|
| 既定 (env 未設定) | 0 | 8 | native `0000000000000000` / wasm `c000c5300342457c` |
| `OTT_KEEP_XMM0=1` | 7 | 1 | native `5045454b5f54544f` / wasm `c000c5300342457c` |

## 3. 修正後の実測 (測定 commit `2c8816dd9`)

測定 commit `2c8816dd9` の `tools/ott/native` と `tools/icall` のコードは `af7718c92` と同一 (§4)。以下は `2c8816dd9` の worktree で実測した値。

| 設定 | `fa_cmp 1803dee20 --n 8` | `fa_sweep.sh 8 60` (131 関数) |
|---|---|---|
| 既定 (env 未設定) | match 8 / mismatch 0 | bit一致 56 / native crash・timeout 64 / wasm のみ err 10 / 値の不一致 1 |
| `OTT_KEEP_XMM0=0` (従来) | match 0 / mismatch 8 | bit一致 55 / native crash・timeout 64 / wasm のみ err 10 / 値の不一致 2 |

既定と `OTT_KEEP_XMM0=0` の sweep 出力 (`sweep.jsonl`・131 行) の差分は `0x1803dee20` の 1 件だけ (既定 8/8・従来 0/8)。

### 3a. 既定 ON の影響範囲 (reviewer 指摘 1 への回答)

| コマンド | 既定 (env 未設定) | `OTT_KEEP_XMM0=0` | 差分 |
|---|---|---|---|
| `bash tools/icall/icall_e2e.sh` | PASS (matrix 89 scenario・failed 0・cells 50236 中 bit 一致 50236・max_ulp 0・state diff 0。crt_fn_gate PASS) | PASS (同左) | 出力行の差分 0 |
| `bash tools/ott/entry/entry_e2e.sh --quick` | PASS (cmp_entries PASS 10/10・FAIL 0。matrix 89 scenario 同左。ott_e2e PASS) | PASS (同左) | 出力行の差分 0 |

実測時間 (`time`): 既定 `icall_e2e.sh` 1 分 37.690 秒 / `OTT_KEEP_XMM0=0` 1 分 36.838 秒。既定 `entry_e2e.sh --quick` 27.468 秒 / `OTT_KEEP_XMM0=0` 27.230 秒。sweep (既定) 1 分 13.959 秒。計測時の load average 1.31 (4 core)。

### 3b. sweep の内訳 (一次出力 `sweep.jsonl` から再集計)

既定の 131 行を `fa_sweep.sh` の判定ロジックで数えた値 (§3 の表と同一)。

| 分類 | 関数数 | 内訳 |
|---|--:|---|
| bit一致 | 56 | `match` = `n` (8/8) |
| native crash・timeout | 64 | `status` = `crash_or_timeout` (sweep は timeout と crash を区別しない) |
| wasm のみ err | 10 | `missing function` 7 (`0x1803b5500`・`0x1803fb6f0`・`0x18040c950`・`0x180ca1480`・`0x180da5f20`・`0x181057d20`・`0x18106632c`)・`memory access out of bounds` 2 (`0x180c8b280`・`0x181057b38`)・`unreachable` 1 (`0x18100cc50`) |
| 値の不一致 | 1 | `0x180da4030` (native `0000000000000000` / wasm `c000c5300342457c`) |

`missing function` 7 件は wasm のみ err 10 件の部分集合で、表の内訳と矛盾しない。

`0x1803dee20` の wasm 不一致は従来値 (`OTT_KEEP_XMM0=0`) の sweep にのみ現れる (値の不一致 2 = `0x1803dee20`・`0x180da4030`)。

sweep の比較 (同じ 131 関数・既定の値):

| 版 | bit一致 | 値の不一致 | 備考 |
|---|---|---|---|
| `6af773cb4` 既定 | 55 | 2 | 基準 (env 未設定) |
| `6af773cb4` KEEP | 54 | 3 | `getenv` の順序で `0x1803dee20`・`0x180cb5ef0` が不一致 |
| `dd4e2b602` KEEP | 56 | 1 | 順序修正 |
| `2c8816dd9` 既定 (本 PR) | 56 | 1 | 既定化 |

残る不一致 `0x180da4030` (既定・KEEP とも 0/8) は本 issue の範囲外。未解決 (#4348)。

## 4. 変更の範囲と差分

測定 commit: `2c8816dd9`。`af7718c92` から `2c8816dd9` までのコード差分は 0 (`tools/ott/native`・`tools/icall` の `.c`・`.py`・`.sh`・`.cjs` は不変)。
- `git diff --numstat origin/main...HEAD -- tools/ott/native/ott_native.c`: 10 行追加・1 行削除 (変更は `k_HeapAlloc` と `g_keep_x0` のみ)。
- `git diff af7718c92 2c8816dd9 -- tools/ott/native tools/icall | wc -l`: 72 行 (`tools/icall/REPORT.md` 1 行と本付録の docs 差分。コードは 0)。
- PR 本文には結論 1 行とこの付録へのリンクだけを書く (DOC_MAP §2)。

## 5. 検証環境

- 素材 (`$ARTIFACTS_DIR` の実在を確認して展開。`ANALYSIS_DIR` は展開先の解析 dir):
  - `work-icall` → `tools/icall/work/` (`tar --zstd -xf`)。
  - `work-m6-ott` → `tools/m6/work/`・`tools/ott/work/` (`libottnative.so`・`lift_meta.json`・`entrylift/` を含む)。
  - `plugins-freshair` → `tools/targets/freshair/fetch.sh` を `FA_DL` 指定で実行 (SlateCore.core_64 を作成)。
  - `plugins-ott` の `Install_Xfer_OTT_137.exe` を 7z で展開し、`$_13_/OTT_x64.dll` (AMD64・ImageBase 0x180000000) を `$ANALYSIS_DIR/plugins/ott/binaries/OTT_vst2_win64.dll` として配置。REPORT.md の記述 (ImageBase 0x180000000) と一致。
  - `fl-win64` → `$ANALYSIS_DIR/win64`。`toolchain-retdec` は展開のみ (`ott_route` は `/opt/retdec` 既定を使い本 run では未使用)。emsdk は `/opt/emsdk` 既存を使用。
- `bash tools/icall/fa_route_build.sh` rc 0 (`fa_route.cjs` 88,639 B)。`bash tools/ott/native/build.sh` rc 0。
- sweep: `bash tools/icall/diff/fa_sweep.sh 8 60` (既定・従来値とも rc 0)。一次出力は `work/fa_route/sweep.jsonl` (131 行)。
- `icall_e2e.sh`・`entry_e2e.sh --quick` は既定・`OTT_KEEP_XMM0=0` の両方で rc 0・PASS (§3a)。
- 再現: `ANALYSIS_DIR=$HOME/analysis bash tools/icall/diff/fa_sweep.sh 8 60` → `funcs 131 bit一致 56 | native crash/timeout 64 | wasm のみ err 10 | 値の不一致 1`。
