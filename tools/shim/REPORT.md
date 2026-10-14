# shim REPORT — heap の範囲外ポインタ検査 (LD-132 / #2802)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の D11 と同じく「wasm32 で範囲外を読み OOB trap」の症状だが、原因は shim の検査欠落で lift の類型ではない)。

## 結論

- **受入 1 達成**: `block_ok` が wasm linear memory の外の値を読まずに FALSE にする。測定 commit は `a4a620a9`。
- **受入 2・3 は本 PR で未実行**: 修正後の ott_old wasm で `1801c5e84` u16 の trap が消えること・site trace・12 case 比較は、素材 `work-m6-ott`・`plugins-ott`・`analysis-ott-binaries` が本 run の `$ARTIFACTS_DIR` に無いため実行できなかった。子 #2841 (LD-136) へ移した (§5)。
- **製品 KPI は動かしていない** (§4)。

## 1. 変更

| ファイル | 変更 |
|---|---|
| `tools/shim/src/heap.c` | `block_ok`: ヘッダ `[user - sizeof(ShimMemHdr), user)` が `[0, memory.size)` に収まるかを先に確かめ、収まらなければ FALSE (magic を読まない) |
| `tools/shim/test/test_main.c` | `test_heap_out_of_range` を追加。値 `0x1`・`0x3`・`0xFFFFFFF0`・`0xFFFFFFFC` に対し HeapFree (FALSE・`ERROR_INVALID_FUNCTION`)・GlobalLock (NULL)・HeapReAlloc (NULL)・GlobalFree (同じ値を返す) を確認 |

## 2. 影響範囲 (shim は全 target 共通)

- `block_ok` を使う関数 (heap.c 内の全 user): GlobalLock・GlobalUnlock・GlobalFree・LocalReAlloc・HeapReAlloc・HeapFree。
- 変わるのは範囲外の値だけ。`[sizeof(ShimMemHdr), memory.size]` の値は旧と同じ magic 比較。範囲外は旧コードでは wasm trap (`memory access out of bounds`) し、新コードでは FALSE/NULL。範囲外の境界付近 (`memory.size < u <= memory.size + 8`) だけは、旧コードでも読めてしまい magic 比較が走っていた。
- heap.c を取り込む・参照する build (grep 実測・29 件。各 build を実行しての個別確認はしていない):
  - コマンド: `grep -rl "shim/src" tools --include=*.sh --include=*.json --include=*.py --include=*.mjs --include=*.ts --include=*.js | grep -v "/work/\|/results/\|REPORT\|batch\|/build/"`
  - GUI・m11 本流 (製品経路): `tools/gui/flengine/build.sh`・`tools/m11/m11_build.sh`・`tools/m11/ldfix/stage4.sh`・`tools/m11/m11_genstubs.py`・`tools/plugins/lift/passes/m11_genstubs.py`
  - runtime・perf: `tools/runtime/prod/build_pthread.sh` (`shim/src/*.c` の glob)・`tools/runtime/bench/build_ott_variants.sh`・`tools/runtime/ci/targets/ott.sh`・`tools/perf/lib/inputs.sh` (コピーのみ)
  - liftdiff: `tools/liftdiff/targets/ott_old.json`・`ott_old_blk.json`・`ott_old_blk_off.json`
  - 他: `tools/m5/build_{a9,b,c,c0}.sh`・`tools/m6/m6_build{,_dbg}.sh`・`tools/m7/m7_build.sh`・`tools/m8/m8_{build,quickbuild}.sh`・`tools/m9/m9_build.sh`・`tools/m10/m10_build.sh`・`tools/ott/ott_build.sh`・`tools/liftlib/liftlib/recipes/ott.py`・`tools/hostbridge/{poc/build_plugin_ott.sh,lowbase/retdec/build_m10_lb.sh}`・`tools/shimx/scripts/verify_ott.sh`
  - `tools/assets/vfs/emscripten.ts` は `file.c` への言及のみ (コメント)。

## 3. 検証 (測定 commit `a4a620a9`)

測定 commit は、コードを変えた最後の commit (`fix(shim): reject out-of-range pointers before reading block header (#2802)`)。以後の commit はこの REPORT だけ。

| 検証 | 結果 |
|---|---|
| `bash tools/shim/test.sh` (コミット済み HEAD・ワークツリー clean) | rc=0・所要 2.30 s (wall)・load average 0.05 / 0.19 / 0.11 (19:37 UTC)。MT `ALL PASS`・ST `ALL PASS`・fail-fast PASS (exit=1・stderr に関数名) |
| ネガティブコントロール: 旧 `heap.c` (`a4a620a9^`) + 新 `test_main.c` を ST でビルド | rc=1。`RuntimeError: memory access out of bounds` (stdout は空。`pthread tests skipped` の NOTE 行より前、つまり `test_heap_out_of_range` で trap) |
| liftdiff の既定 flags (`-O0 -g1 -fno-delete-null-pointer-checks`) で `heap.c` を単体コンパイル | rc=0 |
| `git diff a4a620a9 HEAD -- tools/shim/src tools/shim/test` | 0 行 (差分 0。以後の commit は REPORT のみ) |
| 20 MiB 超の blob (`find tools/shim -type f -size +20M -not -path '*/work/*'`) | 0 件 |

fix round 1 (reviewer 指摘 1: emcc が無く test.sh を独立に再実行できなかった件) の再実行。`toolchain-emsdk` が無い run では、上流から `git clone --depth 1 https://github.com/emscripten-core/emsdk.git` → `./emsdk install 6.0.12` → `./emsdk activate 6.0.12` で emsdk を入れ、`EMSDK_ENV` で指す。HEAD `577fae4a` は code が測定 commit `a4a620a9` と同一 (上の差分 0)。

| 再実行 (HEAD `577fae4a`・ワークツリー clean・`emcc --version` = 6.0.12) | 結果 |
|---|---|
| `EMSDK_ENV=<上流 emsdk の emsdk_env.sh> bash tools/shim/test.sh` | rc=0・所要 3.29 s (wall)・load average 0.62 / 0.44 / 0.20 (19:51 UTC)。MT `ALL PASS`・ST `ALL PASS`・fail-fast PASS (exit=1・stderr に関数名) |
| ネガティブコントロール: 旧 `heap.c` (`a4a620a9^`) + 新 `test_main.c` を `tools/shim` の一時コピーで ST ビルド | rc=1・stdout 0 行・stderr `RuntimeError: memory access out of bounds` |

## 4. 製品 KPI (`docs/WORKFLOW.md` §7)

- 本 PR は `tools/gui/flengine/build.sh` と `tools/m11/m11_build.sh` が取り込む shim を変える。
- **動かしていない**: FLEngine 起動の dispatch 数・通過 unit 数・最初のウィンドウの有無は測定していない。`tools/flelift/boot/REPORT.md` の手順 (`fle6_measure.sh`) は m11 IR の再生成 (`m11_e2e.sh --full` は 633 s 規模) を前提とし、本 run の 60 分に収まらないため、子 #2841 の受入に入れた。
- 変わるのは範囲外ポインタの trap を FALSE に変えることだけ。範囲内の判定は不変。KPI の前後差が出るのは、旧で trap していた経路だけと予想する (推定。未測定)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正後の ott_old wasm で `1801c5e84` u16 の trap が消えることの実測・trap 後の site trace・12 case 比較 (差 0) | LD-132 の受入 2・3 が未確認。素材 `work-m6-ott`・`plugins-ott`・`analysis-ott-binaries` が本 run に無い | #2841 (LD-136) |
| 製品 KPI の前後 (FLEngine 起動の dispatch 数・通過 unit 数・最初のウィンドウ) | GUI・m11 本流の shim を変えたが、効果は未測定 | #2841 (LD-136) |
| HeapFree の範囲外の応答 (本 PR は FALSE)。native 参照 `tools/liftdiff/rt/ld_core.h:430` は常に 1 を返すため、応答表の揃え方が未決 | 応答表が決まるまで native と wasm の HeapFree 応答は一致しない | #2821 (LD-133) |
| `tools/liftdiff/REPORT_APPENDIX_LD83.md` と `targets/ott_old_site.json` が本 checkout に無い (#2192 が参照) | site trace の再現材料が無い | #2841 (LD-136) |
