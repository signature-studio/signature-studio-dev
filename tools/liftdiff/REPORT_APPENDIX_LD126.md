# liftdiff REPORT 付録: LD-126 (#2723) wasm 側の持ち越し状態の候補別切り分け

親 #2681 (LD-121)。前提は `REPORT_APPENDIX_LD121.md` (wasm 側の持ち越しが揺れの原因) と `REPORT_APPENDIX_LD122.md` (0x959a40 の出所)。
測定 commit: **`2bad8864`** (コードを変えた最後の commit。`rt/ld_wasm.c`・`rt/ld_runner.mjs`・`ldlib/build_wasm.py`・`ld126_wasm_state.py`・`ld126_summarize.py`)。

既知類型との関係: 該当なし。`docs/DEFECTS.md` の類型とは別で、wasm ランナの case 間で残る状態 (ランナ内部の持ち越し) を候補ごとに戻して見ている。

## 結論

- 持ち越しを運ぶ候補を**単独で戻すだけで揺れが消えるものは、この測定の範囲では無い**。chunk 1 の 18 関数で、単独の最大は C 静的変数 (`sta`) の 4/18 match。
- **スタック (と SP) は単独では効かない** (`stk` = 18/18 mismatch・outcome が none と完全に一致)。
- **`sta` の 4 件 (`0x4bf600`・`0x7850d0`・`0xb77200`・`0x50ab90`) は、LD121 で heap 高水位外の残存を持つと見た 3 件を含む** (相関であり因果は未検証)。ただし `sta` は heap 高水位の管理変数 (`ld_heap_hw`・`ld_heap_used`) を含むため、「C 静的変数」と「heap 高水位」は分かれていない (未解決 → #3384)。
- **`sta_img` (スタック無し) で `all` の効果が消えない**のに、`all` (スタックを足す) で 18/18 mismatch に戻る。単一関数 `0x50ab90` の診断でも同じ。スタック復元が静的変数と image の効果を打ち消す機構は未特定 (#3384)。
- `0x5d19e0` (chunk 0) は今回の対象外 (#3385)。受入条件の (b)・(c) は未達。

## 1. 測定条件

- 素材: `fl-win64` (`extracted/block00031_PE.bin`・22227016 B)・`work-liftdiff` (`tools/liftdiff/work/m11`・`simd.c` sha256 `d82e2759…` 一致)・`work-m11` (`tools/m11/work`)。`toolchain-emsdk` は runner 既存の `[EMSDK]` (`docs/REFERENCES.md` §4)。
- wasm: `build_wasm.build(m11, False)` (link 3.3 s・`wasm_size` 4459215)。native: `gcc -O1` で `work/ld_native`。
- 機: 4 vCPU・RAM 15 GiB。5 条件を同時に流した (`xargs -P 5`)。全 5 条件 wall 298〜301 s、`sta_img` 単独 wall 199 s。実行前の load は 0.18 (00:29 UTC)。load は各回で未記録 (n=1)。
- 線形メモリの配置 (`Session._layout` と `ld_w_layout`・測定時): image `[0x0, 0x18c0000)`・C 静的 `[0x10000000, …)`・`g_heap` `0x10070000` (96 MiB)・`g_inbuf` (192 MiB)・`g_arena` `0x22071000` (1 MiB)・stack `[0x224bbd00, 0x22cbbd00)` (8 MiB)。

## 2. 方法

- `ld_wasm.c` の `ld_w_snapshot` (SNAPSHOT 時) で、3 候補の pristine 複製を作る。
  - `stk`: スタック `[stack_end, stack_base)` と SP (JS 側の `sp_restore`)。
  - `sta`: C 静的変数。`[__global_base, stack_end)` から `g_heap`・`g_inbuf`・`g_arena` を除いた残りの区間 (複数区間)。
  - `img`: image 全体 `[0, imglen)` (WR 範囲を含む。WR は case ごとに既に戻している)。
- `RESET <mask>` を、chunk 1 の対象 18 関数 (shard 1 の 19 関数 `read_19` のうち chunk 1 に含まれる件。ld121 と同じ) の直前に送る (ld121 の wasm 作り直しと同じ位置)。mask: `stk`=1・`sta`=2・`img`=4・`all`=7 (1+2+4)・`sta_img`=6・`none`=0 (対照)。
- 判定は `liftdiff.make_record` の verdict。case の outcome 分布も併記する。

## 3. 結果 (chunk 1 の 18 対象関数・n=1)

| 条件 (RESET) | match | mismatch | outcome (native_fault / diff / equal / both_fault / hang / wasm_trap) |
|---|---|---|---|
| `none` (対照・新ビルド) | 0 | 18 | 61 / 70 / 7 / 22 / 26 / 12 |
| `stk` (スタック + SP) | 0 | 18 | 61 / 70 / 7 / 22 / 26 / 12 |
| `sta` (C 静的変数) | 4 | 14 | 63 / 70 / 14 / 21 / 25 / 5 |
| `img` (image 全体) | 1 | 17 | 51 / 67 / 8 / 30 / 28 / 14 |
| `all` (stk + sta + img) | 0 | 18 | 61 / 70 / 7 / 22 / 26 / 12 |
| `sta_img` (sta + img) | 4 | 14 | 64 / 70 / 14 / 20 / 25 / 5 |

- 対照 `none` の outcome 分布は `REPORT_APPENDIX_LD121.md` §3 の `none` (n=1) と完全に一致 (ビルド変更による差は無い)。
- `sta` の match は `0x4bf600`・`0x50ab90`・`0x7850d0`・`0xb77200`。`img` の match は `0x50ab90` のみ。`sta_img` の match は `sta` と同じ 4 件。
- 全件の判定は `results/ld126_wasm_state.tsv` (`ld126_summarize.py` で生成。列: 各条件・`wasm_restart_ld121` = ld121 の wasm 列の参照値)。
- outcome 列の出所: `work/ld126/<条件>.jsonl` の `cases` を数えた値。`work/` は gitignore で repo に無い。repo に残すのは verdict だけ (TSV)。outcome の再現は §7 の手順で `work/ld126/` を作り直す。

### 3.1 診断: スタック復元の打ち消し (chunk 先頭 306 件・対象 1 件 `0x50ab90`)

| 条件 | mask | 0x50ab90 |
|---|---|---|
| `sp` (SP のみ) | 8 | mismatch |
| `sta_sp` (SP + sta) | 10 | match |
| `sta_img` (sta + img・SP とスタック無し) | 6 | match |
| `stk` (スタック + SP) | 1 | mismatch |
| `all` (全部) | 7 | mismatch |

- スタック復元 (`1`) を足したときだけ match が消える。SP の復元 (`8`) は効かない。
- 全 chunk (18 件) では同じ差が、`sta_img` の match 4 件と `all` の match 0 件として出る (§3)。

## 4. 読み取り

- `stk`・`all` の outcome 分布は、6 種すべてで `none` と完全に一致する。`RESET` が実際にメモリを戻したことは本測定では確かめていない (戻したバイト数と snapshot との差分の証跡は未取得)。したがって **all = none の一致は未確認**。証跡の取得は #3384 の最初の作業。
- 持ち越しは**単独の候補では説明できない**。`sta` は 4/18 を戻すが、残り 14 件は戻らない。`all` が `sta_img` の効果を打ち消すのは、候補の単純な和では説明できない (相互作用)。
- `sta` の対象のうち 3 件 (`0x4bf600`・`0x7850d0`・`0xb77200`) は LD121 で「wasm 先頭 case に高水位外の残存がある 3 関数」と同じ集合。残存と C 静的変数 (heap 高水位の管理変数) の関係は、本測定では未確認 (#3384)。
- image 単独の効果は 1 件 (`0x50ab90`) で、sta より弱い。`0x50ab90` は sta・img・sta_img・sta_sp の 4 条件で match になるため、この関数の揺れは静的変数と image の両方に関わる可能性がある (未確認)。

## 5. 失敗した初版 (破棄・記録のため)

- 初版の snapshot は、複製を 1 件ずつ malloc しながら C 静的変数を複製していた。複製の途中の `ld_rst` 表 (静的変数) と dlmalloc の管理情報が `sta` 復元で書き戻され、`sta`・`all` の結果が無効だった (`all` = `none` の不自然な一致は、この初版で見えた)。
- 修正: 全 malloc → 表の完成 → まとめて複製 (`ld_rst_take`)。修正後に 5 条件を取り直した。初版の出力は `work/ld126/v1_bug/` (gitignore。repo には入れない)。
- 修正後も `all` = `none` は残った (本付録の結論はこの版による)。

## 6. 差分と測定の鮮度

- 測定 commit `2bad8864` 以降、`tools/liftdiff/rt`・`tools/liftdiff/ldlib` は変えていない。`git diff 2bad8864 HEAD -- tools/liftdiff/rt tools/liftdiff/ldlib | wc -l` = 0。
- `ld126_wasm_state.py`・`ld126_summarize.py` は docstring の件数 (19 → 18) だけを変えた。実行経路は変わらないので、再測定は不要。差分の全文 (`git diff 2bad8864 HEAD -- tools/liftdiff/ld126_wasm_state.py tools/liftdiff/ld126_summarize.py`):

```diff
diff --git a/tools/liftdiff/ld126_summarize.py b/tools/liftdiff/ld126_summarize.py
index eb37d8bd5..4c1b21f88 100644
--- a/tools/liftdiff/ld126_summarize.py
+++ b/tools/liftdiff/ld126_summarize.py
@@ -3,7 +3,7 @@
 
   python3 ld126_summarize.py > results/ld126_wasm_state.tsv
 
-行 = sample:800 の chunk 1 の 19 関数 (ld121 と同じ)。列 = 候補ごとの verdict。
+行 = sample:800 の chunk 1 の 18 関数 (shard 1 の 19 関数のうち chunk 1 に含まれる件。ld121 と同じ)。列 = 候補ごとの verdict。
 wasm_restart_ld121 は results/ld121_restart_probe.tsv の wasm 列 (関数ごとに wasm を作り直した参照値)。
 """
 import collections, json, os, sys
diff --git a/tools/liftdiff/ld126_wasm_state.py b/tools/liftdiff/ld126_wasm_state.py
index 8c7cde681..828c2d241 100644
--- a/tools/liftdiff/ld126_wasm_state.py
+++ b/tools/liftdiff/ld126_wasm_state.py
@@ -1,11 +1,11 @@
 #!/usr/bin/env python3
-"""LD-126 (#2723): sample:800 (shard 1) の 19 関数の揺れを、wasm 側の持ち越し候補ごとに戻して切り分ける。
+"""LD-126 (#2723): sample:800 (shard 1) の 19 関数のうち chunk 1 に含まれる 18 件の揺れを、wasm 側の持ち越し候補ごとに戻して切り分ける。
 
   python3 ld126_wasm_state.py --reset none --out work/ld126/none.jsonl
   python3 ld126_wasm_state.py --reset stk  --out work/ld126/stk.jsonl
 
 cmd_batch の chunk 1 (sample:800 の 400 件目以降) を 1 組の runner で流す (ld121_restart_probe.py と同じ開始状態)。
---reset は、chunk 1 に含まれる 19 関数の直前に、wasm 側の次の候補だけを SNAPSHOT 時点の内容へ戻す (RESET 行)。
+--reset は、shard 1 の 19 関数のうち chunk 1 に含まれる 18 件の直前に、wasm 側の次の候補だけを SNAPSHOT 時点の内容へ戻す (RESET 行)。
   stk: wasm スタック (と SP)   sta: C 静的変数 (g_heap・g_inbuf・g_arena を除く data/bss)   img: image 全体 (WR 範囲外を含む)
   all: 上の 3 つすべて。none は戻さない (ld121 の none と同じ経路で、ビルドの変更の対照に使う)。
 """
```

- 本付録 (REPORT・TSV) の追加は、上の範囲外。

## 7. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"     # extracted/block00031_PE.bin を含む展開先
cd "$(git rev-parse --show-toplevel)/tools/liftdiff"
tar --zstd -xf "$ARTIFACTS_DIR/work-liftdiff.tar.zst" -C ../..
tar --zstd -xf "$ARTIFACTS_DIR/work-m11.tar.zst" -C ../..
mkdir -p "$FL_WIN64_DIR" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$FL_WIN64_DIR" extracted/block00031_PE.bin
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
python3 -c "from ldlib import build_wasm as b; b.build(b.load_target('targets/m11.json'), False)"
printf '%s\n' none stk sta img all | xargs -P 5 -I{} sh -c 'python3 ld126_wasm_state.py --reset {} --out work/ld126/{}.jsonl > work/ld126/{}.log 2>&1'
python3 ld126_wasm_state.py --reset sta_img --out work/ld126/sta_img.jsonl        # 追加 (sta_img)
python3 ld126_summarize.py > results/ld126_wasm_state.tsv
```

- 診断: `python3 ld126_wasm_state.py --reset <mask> --limit 306 --out work/ld126/diag_<mask>.jsonl` (mask: `sp`=8・`sta_sp`=10・`sta_img`=6・`stk`=1・`all`=7)。
- 生データは `work/ld126/` (gitignore)。集計は `results/ld126_wasm_state.tsv` (コミット済み)。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `sta` の内訳 (heap 高水位の管理変数と他の C 静的変数を分けて単独で戻す。n=2 以上) | 持ち越しの機構 (受入 (a) の絞り込み) | #3384 (LD-155) |
| スタック復元が `sta_img` の効果を打ち消す機構 (スタックのどの範囲・どの読みが効くか) | 候補の相互作用の説明 | #3384 (LD-155) |
| 候補の n=2 反復 (本付録は n=1) | 結論の再現性 | #3384 (LD-155) |
| `0x5d19e0` (chunk 0) の両側持ち越しの中身 (native 側を含む) | 受入 (c) | #3385 (LD-156) |
| `0x959a40` (chunk 1 の 18 件に含む。shard 1 の 19 件に入るが、shard 12 の r2〜r4 では mismatch の run 依存・`REPORT_APPENDIX_LD122.md` §3) | 対象 18 件の扱い | PM agent の判断待ち: 0x959a40 を shard 1 の対象 18 件に含めたまま扱うか・既定案: 含めたまま記録し、run 依存の扱いは #2682 の残件とする |
| malloc 領域 (`ld_blks` 等・RESET 対象外) と g_inbuf (入力バッファ) の持ち越し | 候補に含めていない | #3384 (LD-155) に追記 (未測定) |
| RESET の効きの証跡 (戻したバイト数・snapshot との差分)。`all` = `none` の一致の切り分け (§4) | all = none の一致が未確認 | #3384 (LD-155) の最初の作業 |
