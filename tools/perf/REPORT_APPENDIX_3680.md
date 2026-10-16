> **正本**: `tools/perf/REPORT_P15.md` §8 の付録。PERF-P23 (#3680): Fresh Air と OTT を 1 link・1 Memory の wasm に畳み、両 plugin の署名を単独 instance の基準と照合する。

## 1. 結論

Fresh Air (`fa_` 改名版・impbase `0x1F00000`) と OTT (`tools/ott` の lift 産物) を 1 つの emcc link (`tools/perf/p20/build_fold.sh`) にして 1 instance (Memory 1 本) で駆動した。両 plugin の署名は単独 instance の基準と一致した (Fresh Air `5e5287b5`・OTT `6b1696f0`)。ネガティブコントロールとして、Fresh Air の入力だけ・OTT のパラメタだけを変えると、対応する側だけが FAIL した。

## 2. 測定

| 項目 | 結果 (実測) |
|---|---|
| 畳み込みの build | `bash tools/perf/p20/build_fold.sh` (EMSDK=/opt/emsdk)。FA 4 TU・OTT 5 TU を `emcc -c` 後、1 回の link。wasm 3,209,860 B。real 4.26 s |
| 定義シンボルの重なり | FA (`fa_` 改名後) と OTT の extern 定義シンボル: OTT 113 件・FA 156 件・重なり **0 件** (`llvm-nm --defined-only --extern-only`) |
| 畳み込み後の署名 (400 シナリオ・seed 64030) | Fresh Air `5e5287b5` (一致・unique 400/400・out_changed 371)、OTT `6b1696f0` (一致・nonzeroOut 256) |
| NC-1 (Fresh Air の入力 `ga`+0.5) | FA `40290578` (不一致)・OTT `6b1696f0` (一致)。FA だけ FAIL |
| NC-2 (OTT のパラメタ 0.5→0.6) | FA `5e5287b5` (一致)・OTT `2ff0390` (不一致)。OTT だけ FAIL |
| malloc 領域 (400 回確保) | `0x10d73178`〜`0x113b3df0`。OTT の画像窓 `0x30000000`〜 とも、FA の画像窓 `0x02000000`〜`0x04319000` とも重ならない |
| 静的データ | `GLOBAL_BASE` = `0x10000000`。FA の `.rdata`〜`.reloc` は FA の画像窓の内側、OTT は `ott_data.c` を別 TU で持つ。両者の署名一致で、共有 static の汚染が無いことを見る |

- 測定 commit: `4ac8fab85` (`tools/perf/p20/build_fold.sh`・`fold_sig.mjs` を追加した commit。測定コードはこの commit で確定)。`git diff 4ac8fab85 HEAD -- tools/perf/p20` は本 PR の時点で空。
- 環境: node v22.23.3、emcc は `/opt/emsdk` (`toolchain-emsdk`)。素材 `plugins-freshair` (Fresh Air.Win.zip)・`work-m6-ott` (`tools/ott/work/lift`)。CPU は runner の 4 vCPU、測定時の load average 0.10。
- 入力の入手: `$RUNNER_TEMP/fa` に `plugins-freshair` を展開し `FA_DL` で指定 (`tools/targets/freshair/fetch.sh`)。前提 `tools/perf/p20/build_fa_renamed.sh` (#4732) の出力 `work/fa2` を使う。

## 3. 再現

```sh
FA_DL=$RUNNER_TEMP/fa bash tools/targets/freshair/fetch.sh
EMSDK=/opt/emsdk bash tools/perf/p20/build_fa_renamed.sh      # #4732 の改名版 (work/fa2)
EMSDK=/opt/emsdk bash tools/perf/p20/build_fold.sh            # 1 link・1 wasm
node tools/perf/p20/fold_sig.mjs tools/perf/p20/work/fold/fold.cjs 400 64030
NEG=1 node tools/perf/p20/fold_sig.mjs tools/perf/p20/work/fold/fold.cjs 400 64030
NEG_OTT=1 node tools/perf/p20/fold_sig.mjs tools/perf/p20/work/fold/fold.cjs 400 64030
```

## 4. 未解決

| 受入の未達 | なし (受入 3 件は §2 の実測で満たす) | - |
| 畳み込み後の出力と native の突合 (差分 harness) は未実施。判定は署名一致のみ | 署名が一致しても、畳み込み後の全出力が native と一致するかは未確認 | 本 issue の受入外 |
| AudioWorklet 上の畳み込み後の駆動は未測定 | ブラウザ上の成否は未確認 | 本 issue の受入外 |
