# tools/flelift/boot — REPORT 付録 (PERF-P14 #970: boot closure の variant 別 build と実行時間)

> 正本: この付録 (測定値)。`REPORT.md` §0 の 1 行から参照する。親 #672 の PERF-P14 (元 #168 PERF-P9 の残件 ④ の boot 連鎖側)。
> 測定 commit: `8842433a` (測定時の code は `62db1035` と同一。§G)。round 2 で全変種を現 head で再測定した。

## A. 結論

- boot closure (FLE-6 shim 経路・lift closure 2・root `0x6a7b70`) を **-O0 / -O2 / -O2 -flto** の 3 変種で build し、wasm bytes・build 所要・node 実行時間 (n=10) を測った。
- **3 変種の boot 出力署名は一致** (`dff527aaafbcb7ac`)。units_run 209・GetMem 2,314 / FreeMem 1,199・va_bytes 15,470,544 も一致。ただし署名は boot の計数と ipp 状態の正規化ハッシュで、**出力メモリは比較していない**。結論は「停止点までの計数と ipp 状態が一致」に限る。
- **判別力**: ネガコン `FLE_IPP=0` (shim 無し) で GetMem 1,891 / FreeMem 776 に変わり、署名は `b53eaa576ddc3592` になる (§C-3・今回の再測定で確認)。
- 実行時間 (n=10): plain p50 17.967 s / o2 p50 3.855 s / o2lto p50 3.838 s。o2 と o2lto は min–max が重なり、差は誤差の範囲。**LTO の結論は §B の範囲に限る** (shim は -O1 固定で全変種共有)。
- 前回 round (`4d60968f`) の値 (plain 13.906 s / o2 2.925 s) とは一致しない。今回は全体に長い側の値になった (§C-0)。変種間の比は同じ実行の中でのみ有効。
- 最初のウィンドウは未達 (unit 209 の後の `MessageBoxA` → `exit(0)`、#3060)。描画の同一性は未確認。

## B. 測定条件・LTO の対象範囲

- 同一 lift 産物を全変種で共有: `fle6_measure.sh` の lift (closure 2・root `0x6a7b70`・shard 8・cap 13800MB) = 29,908 関数 (lift 60 s・ピーク RSS 610 MB)。
- 変種ごとに 8 shard (`FLE_SHARDS=8`) の C を `build.sh` で `emcc -c` → link。最適化は `FLE_CC_OPT`。
- -O0 (plain): `FLE_CC_JOBS=3`・shard cap 5000MB (`fle6_measure.sh` の既定)。-O2 / -O2 -flto: `FLE_CC_JOBS=2`・shard cap 6000MB。-O2 -flto の木全体は `rss_cap.py` で cap 12000MB を監視。
- **LTO の対象範囲**: `build.sh` は shimx (`tools/shimx/src/*.c`) を `-O1` 固定で 1 回だけ `$W/obj/sx_*.o` にビルドし (`.sx_done` で再利用)、全変種で共有する。shimx は `FLE_CC_OPT` の対象外で、bitcode でもない。よって `-flto` が効くのは lifted C・data・cpu・glue・bridge・textwin・boot の C だけで、shim は -O1 のまま。LTO の差はこの範囲の結論である。
- 署名 = boot と ipp を JSON 正規化して sha256 の先頭 16 桁 (`variant_boot.sh`)。壁時計は node 起動・wasm (62〜127MB) のコンパイル・boot を含む (boot 本体だけの時間ではない)。

## C. 実測値

### C-0. 前回 round との関係

前回 round (`4d60968f`) の値は plain p50 13.906 s / o2 2.925 s / o2lto 2.962 s。今回 (`8842433a`・同じ code) は 17.967 / 3.855 / 3.838 s で、全変種が 25〜30% 長い。wasm bytes は前回と数 KB 異なる (原因は未確認)。今回の実行中の load は boot 中で 1.2〜1.6 (前回は未記録)。絶対値は環境と時刻に依存するため、今回の表の変種間の比だけを使う。

### C-1. build (wasm bytes・壁時計・load・並列数・RSS)

**n=1 (変動幅は未測定)**。並列数と cap が変種で異なるため、build 秒の変種間比較は参考値にとどめる。

| 変種 | wasm (B) | build 壁時計 (s) | load 1 分 (開始→終了) | `FLE_CC_JOBS` | shard cap (MB) | shard ピーク RSS 最大 (MB) | 木全体 peak (MB) |
|---|--:|--:|---|--:|--:|--:|--:|
| -O0 (plain) | 127,080,832 | 75 (clang-plain 段・shimx の -O1 obj 作成を含む) | 0.90→2.04 | 3 | 5000 | 2,667 | 未計測 |
| -O2 (o2) | 64,683,360 | 219 | 1.65→2.33 | 2 | 6000 | 1,718 | 未計測 |
| -O2 -flto (o2lto) | 62,605,001 | 590 | 1.97→1.66 | 2 | 6000 | 1,069 | 8,124 (cap 12000 内) |

link の検査: 3 変種とも `mismatch 0 / undefined 0 / duplicate 0`。

### C-2. 実行時間と署名 (node・`--boot-only`・n=10・`variant_summary.py --check` の出力)

| label | wasm (B) | n | p50 (s) | p90 (s) | min–max (s) | units_run | va_bytes | signature | rc | FLEBOOT_IPP_CHECK |
|---|--:|--:|--:|--:|---|--:|--:|---|--:|---|
| plain | 127080832 | 10 | 17.967 | 18.368 | 17.882–18.966 | 209 | 15470544 | dff527aaafbcb7ac | 3 | ok:false (既知) |
| o2 | 64683360 | 10 | 3.855 | 3.928 | 3.838–3.956 | 209 | 15470544 | dff527aaafbcb7ac | 3 | ok:false (既知) |
| o2lto | 62605001 | 10 | 3.838 | 3.867 | 3.756–3.937 | 209 | 15470544 | dff527aaafbcb7ac | 3 | ok:false (既知) |

- 生データ: `tools/flelift/boot/results/variant_970_summary.tsv` (30 行 + header)。`python3 tools/flelift/boot/variant_summary.py tools/flelift/boot/results/variant_970_summary.tsv --check` で上の表を再現し、別実装 (`statistics.quantiles`) と一致 (rc 0)。
- rc 3 は `FLEBOOT_IPP_CHECK` NG (REPORT §10・#3060 の既知状態)。署名は 30 run すべて同一。停止点は 3 変種とも unit 209 の後の `MessageBoxA` → `exit(0)`。

### C-3. ネガコン (署名の判別力・plain)

| 入力 | GetMem / FreeMem | units_run | ipp_mode | signature |
|---|--:|--:|--:|---|
| shim 有 (`FLE_IPP=1`・C-2 の plain) | 2,314 / 1,199 | 209 | 1 | `dff527aaafbcb7ac` |
| shim 無し (`FLE_IPP=0`・1 run・今回の再測定) | 1,891 / 776 | 209 | 0 | `b53eaa576ddc3592` |

署名は変わる (不一致)。この入力変更で boot の計数 (GetMem / FreeMem) も変わる。出力メモリは見ていない。

## D. 起動指標 (前後)

- units_run: 前 209 → 後 209 (3 変種とも)。**変化なし**。
- 最初のウィンドウ: 未達のまま (`MessageBoxA` の text 源は未特定、#3060)。
- GetMem / FreeMem: 2,314 / 1,199 (shim 有・3 変種同一)。va_bytes 15,470,544 は `FLEBOOT_RESULT` の `va_bytes` (`fle_boot.mjs` の `boot.va_bytes`) 由来。

## E. 再現

```sh
export FL_WIN64_DIR=<fl-win64 展開先 (extracted/block00031_PE.bin を含む)> SS_EMSDK_ENV=<emsdk 6.0.12 の emsdk_env.sh> FLE_BOOT_WORK=<repo 外の作業 dir>
FLE_BOOT_RUNS=shim bash tools/flelift/boot/fle6_measure.sh   # gen → lift → -O0 (plain) → boot (exit 3 は既知の IPP 判定 NG)
FLE_CC_OPT="-O2" FLE_LABEL=o2 FLE_SHARDS=8 FLE_CC_JOBS=2 FLE_CC_RSS_CAP_MB=6000 bash tools/flelift/boot/build.sh plain
python3 tools/flelift/boot/rss_cap.py --cap-mb 12000 --log $FLE_BOOT_WORK/rss_lto_total.log -- env FLE_CC_OPT="-O2 -flto" FLE_LABEL=o2lto FLE_SHARDS=8 FLE_CC_JOBS=2 FLE_CC_RSS_CAP_MB=6000 bash tools/flelift/boot/build.sh plain
FLE_BOOT_N=10 bash tools/flelift/boot/variant_boot.sh plain o2 o2lto                 # → $FLE_BOOT_WORK/variant/summary.tsv
python3 tools/flelift/boot/variant_summary.py $FLE_BOOT_WORK/variant/summary.tsv --check   # §C-2
FLE_IPP=0 FLE_BOOT_VARIANT=plain node tools/flelift/boot/fle_boot.mjs $FLE_BOOT_WORK/fleboot_plain.cjs <out.json> --boot-only   # §C-3
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk`。fl-win64 は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <dir> extracted/block00031_PE.bin` で PE だけ展開した (WORKFLOW §11)。emsdk は `[EMSDK]` (6.0.12・`docs/REFERENCES.md` の `toolchain-emsdk` 行) の既存の導入を使い、新たに導入していない。生成物は repo 外の `FLE_BOOT_WORK` に置く (`tools/**/work/` を作業場にしない)。

## F. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 描画 (最初のウィンドウ) の変種間同一性。unit 209 の後 `MessageBoxA` で止まるため未確認 | 署名は boot 計数と ipp 状態までで、描画の一致は未確認 | #3060 [FLE-11] |
| 署名は計数と ipp 状態の正規化ハッシュのみ。出力メモリ全体の hash 比較は未実施 (C-3 のネガコンも出力メモリは未比較) | 「3 変種一致」は計数と ipp 状態の一致に限る | #3060 (FLE-11 の検証で扱う) |
| LTO の対象範囲: shimx は `-O1` 固定で全変種共有・bitcode でない。`-flto` は shim に効かない | 「-O2 -flto」は lifted C と runtime だけに効く。shim を含む LTO の効果は未測定 | #672 へのコメント (既存の親。shim の最適化変種化を親への提案として書く。新規子は起票しない) |
| build 秒は n=1 (変動幅未測定)。並列数・cap・load が変種で異なる | build 秒の変種間比較は参考値 | 本 PR 本文 (再測定の子は起票しない) |
| 前回 round (13.906 / 2.925 s) と今回 (17.967 / 3.855 s) の差の原因が未特定 | 実行時間の絶対値は環境依存。今回 run 内の比のみ有効 | 本 PR 本文 (再測定の子は起票しない) |
| 既定経路 (root 無し) の変種別測定 | 本付録は shim 経路のみ | #672 (親)・#3060 |

## G. 差分確認

- 測定 commit: `8842433a`。`62db1035` (main 取り込み) 以後の docs 3 件 (`d4b0b3e5`・`e8897577`・`8842433a`) は docs のみ。
- 実行経路の code は `62db1035` と `8842433a` で同一 (出力は空):
  `git diff 62db1035 8842433a -- tools/flelift tools/shimx tools/shared ':!*.md' ':!*.tsv' ':!*.json'`
- 前回の測定 commit `4d60968f` からの差は、main 取り込み merge `62db1035` で入った code (`x64c.py`・`fle_data_gen.py`・`rt/fle_cpu.h`・`build.sh` の EXPORTS 行・`fle6_measure.sh`・`fle_boot.c`・`fle_boot.mjs`・`tools/shimx/src/handles.c`・`shimx.h`・`exports.txt`・`data/sigs.json`) であり、それらは今回の再測定に含めた。
- 今回の再測定の結果ファイルは `tools/flelift/boot/results/boot_summary_fle6.json` (現 head の code の出力で `tolerant`・`cfi` キーが増えた) と `results/variant_970_summary.tsv`。
