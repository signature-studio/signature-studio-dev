# REPORT (SHX-T9h / #2489) — 現行 m11_ov.c で baseline を再生成して unit 23 を比較

> 正本: `tools/shimx/REPORT_SHX-T9.md` §3.3.5 から分割移動した付録 (内容は無変更。§ 番号は親 `REPORT_SHX-T9.md` のもの)。親: `tools/shimx/REPORT_SHX-T9.md`。

## 3.3.5 現行 m11_ov.c で baseline を再生成して unit 23 を比較 (SHX-T9h #2489)

- 結論: 素材 `work-m11` の `m11_boot.cjs`・`obj/ov.o` は現行 main と一致しない旧 snapshot だった (`ov.o` に `function_410320`・`function_40f960`・`function_40fb40`・`function_467c40` が無く、qstore 未適用)。現行 IR から再生成した baseline は unit 23 で shimx 版と同じ経路 (`ret=2`・`0xf960` 進入) を通る。§3.3.3 の baseline 行 (`halt0`) は旧 snapshot の値。どの変更 (ov の差・qstore/ldfix/ld108) が効いたかは未分離。
- 測定 commit: `3f7b7a63` (origin/main `3ef67b40` を取り込んだ merge commit)。前回測定 (`9f403c97`) からのコード差分は probe 2 本の追加のみ (`git diff --stat 9f403c97 3f7b7a63 -- tools/m11/m11_ov.c tools/m11/shimx_link tools/shimx/src` → `probe_lasterr_1985.mjs` 42 行・`probe_miss_units_2489.mjs` 28 行)。`git diff 3f7b7a63 HEAD -- tools/m11/m11_ov.c tools/m11/shimx_link tools/shimx/src` の出力: 0 行 (測定後の変更は REPORT と evidence のみ)。
- 再現手順 (素材 `oc_artifacts: fl-win64 work-m11 work-liftdiff toolchain-retdec toolchain-emsdk`。`FL_WIN64_DIR` は fl-win64 の展開先。ログは `tools/shimx/evidence_2489/`):
  1. `bash tools/m11/m11_gen_ir2.sh` → rc 0・37 秒 (`ldfix=applied`・`ld108=applied`・`ir_sha256` `7c653b0f…`)
  2. `rm work/obj/ov.o; bash tools/m11/m11_build.sh` → rc 0・19 秒 (qstore 適用・`m11_boot.cjs` 5,766,813 B)
  3. `rm -rf work/shimx_link/obj work/shimx_link/gen_fix; bash tools/m11/shimx_link/build.sh --trace --soft --fix` → `[sxlink] OK` (11 秒)
  4. `node tools/m11/shimx_link/probe_flag_1985.mjs <cjs 絶対パス> 22` (exc・trace)、`probe_unit23.mjs` (miss・slot・sxt 計数)、`probe_miss_units_2489.mjs` (unit ごとの miss 累計)
- 受入 1 (`llvm-nm work/obj/ov.o`): 4 つの T シンボルが全て出る。artifact 版は 4 つとも無く T 22 本、再生成版は T 52 本。
- unit 23 (index 22、unit 1〜22 の後に 1 回):

| 版 | unit 23 の結果 | 経路 (非 UStrAsg) | icall-miss (unit 1〜22 / unit 23) |
|---|---|---|---|
| artifact baseline (旧 snapshot) | halt0 | `0x67f00` → FormatMessageW (stub) → Halt0 | 0 / 0 |
| 再生成 baseline (`m11_boot.cjs`) | ret=2 | `0x67f00` → `0xf960` → miss `0x457860` | 0 / 2 |
| shimx `--trace --soft --fix` (clean rebuild) | ret=2 | 同左 | 1 (unit 18, `0x4476d0`) / 2 |

- 負荷 (4 CPU): `uptime` 1 分平均 0.96 (IR 再生成の直前) と 0.57 (probe の直前)。build・probe はすべて直列実行 (並列なし)。
- 再生成 baseline と shimx 版: unit 23 の probe 出力はアドレスを除くと一致 (diff 0 行。UStrAsg 388 件の dest 列も一致)。unit 23 直前の slot `0x11f10e0` は両版とも `0x457860` (fallback)。shimx 版の sxt 計数では unit 23 中の wrapped API 呼出しは 0 件。
- 再測定 (測定 commit `3f7b7a63`・上記 1〜3 を clean rebuild で実行): 3 probe の出力は `evidence_2489/` の既存ファイルと一致 (`probe_flag` の再生成版のみ計測用 `time` 行 4 行の差)。artifact baseline 行は再実行していない: 旧 `m11_boot.cjs` は同梱の `.wasm` を要するが素材 tarball に無く、証跡 (`9f403c97` 時点の測定) を据え置く。
- 未解決 (差): shimx 版のみ unit 18 で icall-miss `0x4476d0` (1 件、closure 外として skip)。再生成 baseline は unit 1〜22 で miss 0 件。機構は未特定。
- 受入 2 の残り (子 issue へ分離): 本ブランチの基底には `tools/m11/shimx_link/probe_lasterr_1985.mjs` が無かったため、`probe_flag_1985.mjs` (同じ引数形式) を使った。main 取り込みで `probe_lasterr_1985.mjs` が追加された (§3.3.4) が、その GetLastError 比較は旧 snapshot の baseline で測られている。再生成 baseline の GetLastError は未取得 (子 #2533)。
- 注意: `m11_image.bin` は素材のもの (再生成していない)。`work-m11` 旧 snapshot を基準にした既存の baseline 値 (§3.3.3 ほか) は同じ影響を受けている可能性がある (未確認)。
