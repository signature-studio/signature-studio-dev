# REPORT (SHX-T9h / #2489) — 現行 m11_ov.c で baseline を再生成して unit 23 を比較

> 分割元: `tools/shimx/REPORT_SHX-T9.md` §3.3.5 から分割移動した付録 (§ 番号は分割元のもの)。

## 3.3.5 現行 m11_ov.c で baseline を再生成して unit 23 を比較 (SHX-T9h #2489)

- 結論: 素材 `work-m11` の `m11_boot.cjs`・`obj/ov.o` は現行 main と一致しない旧 snapshot だった (`ov.o` に `function_410320`・`function_40f960`・`function_40fb40`・`function_467c40` が無く、qstore 未適用)。現行 IR から再生成した baseline は unit 23 で shimx 版と同じ経路 (`ret=2`・`0xf960` 進入) を通る。§3.3.3 の baseline 行 (`halt0`) は旧 snapshot の値で、本 round で再実行しても `halt0` を再現した。どの変更 (ov の差・qstore/ldfix/ld108) が効いたかは未分離。
- 測定 commit: `4cca6c28` (origin/main `df2f7aaf` を取り込んだ merge commit。コードを変えた最後の commit)。
  - 前回測定 (`3f7b7a63`) からのコード差分 (`git diff --stat 3f7b7a63 4cca6c28 -- tools/m11/m11_ov.c tools/m11/shimx_link tools/shimx/src`):
    ```
     tools/m11/m11_ov.c                             | 70 +++++++++++++++++++++++++++
     tools/m11/shimx_link/build.sh                  |  2 +-
     tools/m11/shimx_link/probe_miss_units_2489.mjs |  7 ++-
     3 files changed, 74 insertions(+), 5 deletions(-)
    ```
  - 測定後の差分 (`git diff 4cca6c28 HEAD -- tools/m11/m11_ov.c tools/m11/shimx_link tools/shimx/src`) の出力: 0 行 (REPORT と evidence のみ変更)。
  - main 取り込み前 (`876f6e27`) の測定と、取り込み後 (`4cca6c28`) の測定は、IR sha256・`m11_boot.cjs` サイズ・unit 23 の結果と miss 数が一致した。
- 再現手順 (素材 `oc_artifacts: fl-win64 work-m11 work-liftdiff toolchain-retdec toolchain-emsdk`。`FL_WIN64_DIR` は fl-win64 の展開先。ログは `tools/shimx/evidence_2489/`):
  1. `$FL_WIN64_DIR/extracted/block00031_PE.bin` の sha256 が `b2c64da4…` であることを確認。artifact 行用に、work-m11 同梱の `tools/m11/work/m11_boot.cjs`・`m11_boot.cjs.wasm` を手順 3 の前に退避する。
  2. `rm -f work/m11_data.c work/obj/data.o && python3 tools/m11/m11_data_gen.py <PE>` (work-m11 同梱の `m11_data.c` は修正前の版。下記)
  3. `bash tools/m11/m11_gen_ir2.sh` → rc 0・34.3 秒 (`ldfix=applied`・`ld108=applied`・gen_ir2 直後の `work/boot_final.ll` sha256 `7c653b0f…`)
  4. `rm work/obj/ov.o; bash tools/m11/m11_build.sh` → rc 0・18.9 秒 (qstore 適用・`m11_boot.cjs` 5,766,813 B)
  5. `rm -rf work/shimx_link/obj work/shimx_link/gen_fix; bash tools/m11/shimx_link/build.sh --trace --soft --fix` → `[sxlink] OK` (10.6 秒)
  6. `node tools/m11/shimx_link/probe_flag_1985.mjs <cjs 絶対パス> 22`、`probe_unit23.mjs <cjs> 22`、`probe_miss_units_2489.mjs <cjs> 22` を、regen (`work/m11_boot.cjs`)・shimx (`work/shimx_link/m11_sx_trace_soft_fix.cjs`)・artifact (退避した旧 snapshot) の 3 本で実行
  7. `llvm-nm work/obj/ov.o` (T 行は `ov_nm_regen.txt`・`ov_nm_artifact.txt`)
- 受入 1 (`llvm-nm work/obj/ov.o`): 4 つの T シンボル (`function_40f960`・`function_40fb40`・`function_410320`・`function_467c40`) が再生成版で全て出る。artifact 版は 4 つとも無く T 22 本、再生成版は T 52 本。
- unit 23 (index 22、unit 1〜22 の後に 1 回):

| 版 | unit 23 の結果 | 経路 (非 UStrAsg) | icall-miss (unit 1〜22 / unit 23) |
|---|---|---|---|
| artifact baseline (旧 snapshot、`m11_boot.cjs` 5,754,665 B) | halt0 | `0x67f00` → FormatMessageW (stub) → Halt0 | 0 / 0 |
| 再生成 baseline (`m11_boot.cjs`) | ret=2 | `0x67f00` → `0xf960` → miss `0x457860` | 0 / 2 |
| shimx `--trace --soft --fix` | ret=2 | 同左 | 1 (unit 18, `0x4476d0`) / 2 |

- artifact 行は本 round で再実行した。`work-m11` には `m11_boot.cjs.wasm` (6,010,853 B) が同梱されており、旧版の「`.wasm` が素材に無いため再実行しない」は誤りだった。再実行で `exc=halt0` を再現した。
- `m11_data.c` の差し替え: 差分はコメント 2 行 (LB_BASE の記述) と `dlld__data[]` 末尾 1 バイト (`.data` 末尾の DIR64 slot, RVA 0x11e5000) の `0x42`→`0x02` (値 `0x425f00`→`0x25f00`)。`tools/m11/REPORT.md` §11 (#572) の修正どおり。修正後に再生成した baseline の 3 probe 出力は、修正前の evidence (`92d14b7d`) と時間行を除いて完全一致した。unit 23 の結果は変わらない。
- `m11_image.bin` は work-m11 同梱の素材を使い、再生成していない。`m11_image_gen.py <PE>` の出力と byte 一致 (22,515,781 B・sha256 `2d10d692…`) を確認済み。
- probe の一致範囲:
  - `probe_flag_*` (regen と shimx): アドレスを正規化 (`0x[0-9a-f]+`→`X`) し時間行を除くと diff 0 行。UStrAsg 388 件 (dest 列を含む) も一致する。
  - `probe_unit23_*` (regen と shimx): **一致しない**。差は (a) PRE 行の GetModuleHandleW/GetProcAddress 計数 (shimx 版のみ)、(b) shimx 版のみの RET 行 35 件、(c) icall-miss 集計 (regen は合計 2・一意 1、shimx 版は合計 3・一意 2)。(c) の差 1 件は unit 18 の `0x4476d0` (shimx 版のみ、`miss_by_unit_shimx_trace_soft_fix.txt` の `MISS_AFTER|unit 18`)。差の理由: shimx 版だけが `--trace` の計数で API 呼出しを記録し、unit 18 で `0x4476d0` の icall-miss を出す (機構は未特定)。
- 負荷 (4 CPU、`uptime` の 1 分平均): IR 再生成の直前 0.31 (15:37:21)、probe の直前 0.70 (15:38:35)。build と probe はすべて直列実行。
- 未解決 (差): shimx 版のみ unit 18 で icall-miss `0x4476d0` (1 件、closure 外として skip)。再生成 baseline は unit 1〜22 で miss 0 件。機構は未特定 (#1985 で追跡)。
- 受入 2 の残り (子 issue へ分離): 本ブランチの基底には `probe_lasterr_1985.mjs` が無かったため、`probe_flag_1985.mjs` (同じ引数形式) を使った。main 取り込みで `probe_lasterr_1985.mjs` が追加された (§3.3.4) が、その GetLastError 比較は旧 snapshot の baseline で測られている。再生成 baseline の GetLastError は未取得 (子 #2533)。
- 注意: `work-m11` 旧 snapshot を基準にした既存の baseline 値 (§3.3.3 ほか) は同じ影響を受けている可能性がある (未確認。PR 本文の未解決表に記載)。
- 検証の commit と差分 (WORKFLOW §6): 測定 commit `4cca6c28`。測定後の差分 (上記) は 0 行。
