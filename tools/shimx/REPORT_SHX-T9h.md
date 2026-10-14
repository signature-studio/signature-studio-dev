# REPORT (SHX-T9h / #2489) — 現行 m11_ov.c で baseline を再生成して unit 23 を比較

> 分割元: `tools/shimx/REPORT_SHX-T9.md` の旧 §3.3.5 から分割移動した付録 (main の SHX-T9i が §3.3.5 を使ったため、本付録の節番号は §3.3.7 とする)。

## 3.3.7 現行 m11_ov.c で baseline を再生成して unit 23 を比較 (SHX-T9h #2489)

- 結論: 素材 `work-m11` の `m11_boot.cjs`・`obj/ov.o` は現行 main と一致しない旧 snapshot だった (`ov.o` に `function_410320`・`function_40f960`・`function_40fb40`・`function_467c40` が無く、qstore 未適用)。現行 IR から再生成した baseline は unit 23 で shimx 版と同じ経路 (`ret=2`・`0xf960` 進入) を通る。§3.3.3 の baseline 行 (`halt0`) は旧 snapshot の値で、本 round で再実行しても `halt0` を再現した。どの変更 (ov の差・qstore/ldfix/ld108) が効いたかは未分離。
- 測定 commit: `8ef418e6` (origin/main `2db127a8` を取り込んだ merge commit。コードを変えた最後の commit)。
  - 前回測定 (`3f7b7a63`) からのコード差分 (`git diff --stat 3f7b7a63 4cca6c28 -- tools/m11/m11_ov.c tools/m11/shimx_link tools/shimx/src`):
    ```
     tools/m11/m11_ov.c                             | 70 +++++++++++++++++++++++++++
     tools/m11/shimx_link/build.sh                  |  2 +-
     tools/m11/shimx_link/probe_miss_units_2489.mjs |  7 ++-
     3 files changed, 74 insertions(+), 5 deletions(-)
    ```
  - `4cca6c28` (前回の測定 commit) からのコード差分 (main 取り込みで発生。`git diff --stat 4cca6c28 8ef418e6 -- tools/m11/m11_ov.c tools/m11/shimx_link tools/shimx/src`): 5 files, 55 insertions(+), 6 deletions(-)。`m11_ov.c` は `#ifndef` ガード 2 行 (既定では挙動不変)・`build.sh` は EXPORTS 1 行・`gen_link.py` +45・`probe_unit23.mjs` +4 (RET 行に `site=`・`ord=` を追加)・`trace_rt.c` +8。IR (`boot_final.ll` sha `7c653b0f…`) と regen の `m11_boot.cjs` sha (`49e6cce2…`) は前回と同じ。
  - 測定後の差分 (`git diff 8ef418e6 HEAD -- tools/m11/m11_ov.c tools/m11/shimx_link tools/shimx/src`) の出力: 0 行 (REPORT と evidence のみ変更)。
  - 本節の再測定は HEAD `8ef418e6` (main 取り込み後) の worktree で行った。生出力は `evidence_2489/` に保存した (`m11_data.c` の作り直しを含む。`m11_build.log` に `cc work/m11_data.c` あり)。
- 再現手順 (素材 `oc_artifacts: fl-win64 work-m11 work-liftdiff toolchain-retdec toolchain-emsdk`。`FL_WIN64_DIR` は fl-win64 の展開先。ログは `tools/shimx/evidence_2489/`):
  1. `$FL_WIN64_DIR/extracted/block00031_PE.bin` の sha256 が `b2c64da4…` であることを確認。artifact 行用に、work-m11 同梱の `tools/m11/work/m11_boot.cjs`・`m11_boot.cjs.wasm` を手順 3 の前に退避する。
  2. `rm -f work/m11_data.c work/obj/data.o && python3 tools/m11/m11_data_gen.py <PE>` (work-m11 同梱の `m11_data.c` は修正前の版。`data.o` も消す。消さないと古い `.o` が再利用され `cc work/m11_data.c` が出ない。下記)
  3. `bash tools/m11/m11_gen_ir2.sh` → rc 0・52.0 秒 (`ldfix=applied`・`ld108=applied`・gen_ir2 直後の `work/boot_final.ll` sha256 `7c653b0f…`。`gen_ir2.log` 末尾)
  4. `rm work/obj/ov.o; bash tools/m11/m11_build.sh` → rc 0・26.3 秒 (`cc work/m11_data.c`・qstore 適用・`m11_boot.cjs` 5,766,813 B・`m11_boot.cjs.wasm` 6,029,044 B)
  5. `rm -rf work/shimx_link/obj work/shimx_link/gen_fix; bash tools/m11/shimx_link/build.sh --trace --soft --fix` → `[sxlink] OK` (16.7 秒。`[sxlink] cc m11_data.c` あり。`m11_sx_trace_soft_fix.cjs` 6,169,654 B)
  6. `node tools/m11/shimx_link/probe_flag_1985.mjs <cjs 絶対パス> 22`、`probe_unit23.mjs <cjs> 22`、`probe_miss_units_2489.mjs <cjs> 22` を、regen (`work/m11_boot.cjs`)・shimx (`work/shimx_link/m11_sx_trace_soft_fix.cjs`)・artifact (退避した旧 snapshot) の 3 本で実行
  7. `llvm-nm work/obj/ov.o` (T 行は `ov_nm_regen.txt`・`ov_nm_artifact.txt`)
- 受入 1 (`llvm-nm work/obj/ov.o`): 4 つの T シンボル (`function_40f960`・`function_40fb40`・`function_410320`・`function_467c40`) が再生成版で全て出る。artifact 版は 4 つとも無く T 22 本、再生成版は T 52 本。
- unit 23 (index 22、unit 1〜22 の後に 1 回):

| 版 | unit 23 の結果 | 経路 (非 UStrAsg) | icall-miss (unit 1〜22 / unit 23) |
|---|---|---|---|
| artifact baseline (旧 snapshot、`m11_boot.cjs` 5,754,665 B) | halt0 | `0x67f00` → FormatMessageW (stub) → Halt0 | 0 / 0 |
| 再生成 baseline (`m11_boot.cjs`) | ret=2 | `0x67f00` → `0xf960` → miss `0x457860` | 0 / 2 |
| shimx `--trace --soft --fix` | ret=2 | 同左 | 1 (unit 18, `0x4476d0`) / 2 |

- artifact 行は再実行した。`work-m11` には `m11_boot.cjs.wasm` (6,010,853 B) が同梱されており、旧版の「`.wasm` が素材に無いため再実行しない」は誤りだった。再実行で `exc=halt0` を再現した。
- `m11_data.c` の差し替え: 差分はコメント 2 行 (LB_BASE の記述) と `dlld__data[]` 末尾 1 バイト (`.data` 末尾の DIR64 slot, RVA 0x11e5000) の `0x42`→`0x02` (値 `0x425f00`→`0x25f00`)。`tools/m11/REPORT.md` §11 (#572) の修正どおり。前回の build ログには `cc work/m11_data.c` が無く、古い `data.o` がリンクされたと読める。今回は `data.o` を削除して作り直し、`m11_build.log` に `cc work/m11_data.c` を残した。
- 1 バイトの効果 (`evidence_2489/ab_m11_data_wasm.txt`): `m11_boot.cjs` (JS グルー) の sha256 は新旧とも `49e6cce2…` で変わらない (データは `.wasm` に入るため、`.cjs` の sha は効果の指標にならない)。`m11_boot.cjs.wasm` は 1 バイト変わる (オフセット 6017376、`0x42`→`0x02`。旧 `data.o` で作った control の sha `47fdb4bd…` と新版 `5f94d970…`)。unit 23 の結果は変わらない (下記 probe の値が前回の証跡と一致)。
- 再測定 (`data.o` 作り直し後・HEAD `8ef418e6`) の probe 9 本と `ov_nm_regen.txt`: 時間行を除き前回の証跡と一致。`probe_unit23_shimx_trace_soft_fix.txt` だけは、main 取り込みで `probe_unit23.mjs` が RET 行に `site=`・`ord=` を足したため行が変わる (unit・名前・引数・戻り値・MISS 集計は前回と同一。`site=`・`ord=` を除くと差分 0 行)。
- `m11_image.bin` は work-m11 同梱の素材を使い、再生成していない。`m11_image_gen.py <PE>` の出力と byte 一致 (22,515,781 B・sha256 `2d10d692…`) を確認済み。
- probe の一致範囲:
  - `probe_flag_*` (regen と shimx): アドレスを正規化 (`0x[0-9a-f]+`→`X`) し時間行を除くと diff 0 行。UStrAsg 388 件 (dest 列を含む) も一致する。
  - `probe_unit23_*` (regen と shimx): **一致しない**。差は (a) PRE 行の GetModuleHandleW/GetProcAddress 計数 (shimx 版のみ)、(b) shimx 版のみの RET 行 35 件、(c) icall-miss 集計 (regen は合計 2・一意 1、shimx 版は合計 3・一意 2)。(c) の差 1 件は unit 18 の `0x4476d0` (shimx 版のみ、`miss_by_unit_shimx_trace_soft_fix.txt` の `MISS_AFTER|unit 18`)。差の理由: shimx 版だけが `--trace` の計数で API 呼出しを記録し、unit 18 で `0x4476d0` の icall-miss を出す (機構は未特定)。
- 負荷: gen_ir2・build・shimx build・probe はすべて直列実行 (並列 0)。`uptime` の段階別の記録は無い。
- 未解決 (差): shimx 版のみ unit 18 で icall-miss `0x4476d0` (1 件、closure 外として skip)。再生成 baseline は unit 1〜22 で miss 0 件。機構は未特定 (#1985 で追跡)。
- 参考 (`REPORT_SHX-T9j.md` §2.2): 同じ方式の再生成 IR で、shimx 版 unit 18 は `exc=halt0`・baseline は `ret=1` と記録されている。本節の probe 出力 (`probe_unit23_shimx_trace_soft_fix.txt`・`miss_by_unit_shimx_trace_soft_fix.txt`) には `exc=` 行は無く、unit 18 は icall-miss `0x4476d0` として出る。両者が同じ現象かは未確認 (PR 本文の未解決表)。
- 受入 2 の残り (子 issue へ分離): 本ブランチの基底には `probe_lasterr_1985.mjs` が無かったため、`probe_flag_1985.mjs` (同じ引数形式) を使った。main 取り込みで `probe_lasterr_1985.mjs` が追加された (§3.3.4) が、その GetLastError 比較は旧 snapshot の baseline で測られている。再生成 baseline の GetLastError は #2533 で実測済み (`REPORT_SHX-T9j.md` §2.2)。
- 注意: `work-m11` 旧 snapshot を基準にした既存の baseline 値 (§3.3.3 ほか) は同じ影響を受けている可能性がある (未確認。PR 本文の未解決表に記載)。
- 検証の commit と差分 (WORKFLOW §6): 測定 commit `8ef418e6`。測定は HEAD `8ef418e6` で行った。測定後の差分 (`git diff 8ef418e6 HEAD -- tools/m11/m11_ov.c tools/m11/shimx_link tools/shimx/src`) は 0 行。
