# REPORT_APPENDIX_2577 — #2577: RetDec drc.ll の uselistorder 並びの差 (#2456 の残り)

## 21. #2577: 差が入る段とアドレス依存の機構 (部分達成)

- 既知類型との関係: 該当なし (DEFECTS.md の silent miscompile 類型ではない。A7 後の `.ll` の指示行以外は全 run で一致)。既知事象は #668 (LIFTLIB-9) と REPORT_APPENDIX_960 §20 の m11 側の再現。
- 測定 commit: 2 回目 `c0b68d971` (表 2・G4 表 2 はこの commit で実施)。1 回目は `43ca7475f` (表 1・G4 表 1)。`git diff 43ca7475f c0b68d971 -- tools/m11 ':!tools/m11/REPORT*'` の出力は次の通り。RetDec の呼び出しは変えていない (コメント・G4 の `.ll` の保存名・G4 diff の出力のみ)。

```diff
diff --git a/tools/m11/uselist_stage_2577.sh b/tools/m11/uselist_stage_2577.sh
index 7ef671d16..bea524e81 100644
--- a/tools/m11/uselist_stage_2577.sh
+++ b/tools/m11/uselist_stage_2577.sh
@@ -2,7 +2,7 @@
 # #2577: RetDec drc.ll の uselistorder 並びの差が入る段を二分する (REPORT_APPENDIX_2577 §21)。
 #   G1: バックエンド最適化を止める (--backend-no-opts)・全 150 range・3 回 (バックエンド段を除いても差が残るか)
 #   G2: 150 range を半分に分ける: A=1-75, B=76-150, B1=76-112, B2=113-150 (各 4 回)
-#   G3: 差の出た単独 range 0x409c80-0x409ed8 (B の 111 番目。function_409c80) を
+#   G3: 差の出た単独 range 0x409c80-0x409ed8 (boot_ranges.txt 全 7,360 range の 111 番目・B の 36 番目。function_409c80) を
 #       on=ASLR 有効 / off=ASLR 無効 (setarch -R) / tc=ASLR 無効 + glibc.malloc.tcache_count=0 で各 4 回
 # 使い方: M11_PE=<fl-win64>/extracted/block00031_PE.bin RETDEC=<toolchain-retdec>/bin/retdec-decompiler bash tools/m11/uselist_stage_2577.sh
 # 前提: work/boot_ranges.txt (work-m11)。出力は work/uselist_2577/ (gitignore)。
@@ -71,7 +71,8 @@ g4run() { # g4run <len> <tag> [extra arg]
   rm -f "$G4/$base.ll"
   ( cd "$G4" && env -i PATH=/usr/bin:/bin TMPDIR="$OUT/tmp" setarch x86_64 -R timeout 250 "$RETDEC_BIN" "$PE" \
       -o "$name" --select-ranges "$SINGLE" --select-decode-only --timeout 100 $extra > "$G4/$base.$tag.log" 2> "$G4/$base.$tag.err" ) || true
-  printf 'G4\t%s\tlen=%s\tll=%s\terr_md5=%s\n' "$tag" "$n" "$(md5sum < "$G4/$base.ll" 2>/dev/null | cut -c1-8)" \
+  mv -f "$G4/$base.ll" "$G4/$base.$tag.ll" 2>/dev/null || true
+  printf 'G4\t%s\tlen=%s\tll=%s\terr_md5=%s\n' "$tag" "$n" "$(md5sum < "$G4/$base.$tag.ll" 2>/dev/null | cut -c1-8)" \
     "$(md5sum < "$G4/$base.$tag.err" | cut -c1-8)" >> "$G4/g4.tsv"
 }
 : > "$G4/g4.tsv"
@@ -80,6 +81,8 @@ for i in 1 2; do for n in 9 17; do g4run "$n" "noopts$i" "--backend-no-opts"; do
 for n in 9 17; do g4run "$n" "printall" "--print-after-all"; done
 echo "== G4 (出力名の長さ・ASLR 無効・env -i。ll=.ll の md5、err_md5=stderr 全体の md5)"
 cat "$G4/g4.tsv"
+echo "== G4 diff (plain1: 9 字 → 17 字の .ll 差。1 行なら指示行だけ)"
+diff "$G4/qqqqqqq.plain1.ll" "$G4/$(printf 'q%.0s' $(seq 1 15)).plain1.ll" || true
 
 echo "== summary (group / label / rc / sec / load1 / ll md5 / 指示行を除いた md5 / 指示行数)"
 cat "$SUM"
```

- 条件: PE `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)・RetDec v5.0 (`toolchain-retdec`・sha256 `9d49ffcf…`)・`work-m11` の `boot_ranges.txt` 先頭 150 range (`--select-decode-only`)。`--timeout` は G1〜G3 が 250、G4 が 100。ASLR は G1・G2・G3-on が有効 (`setarch` なし)、G3-off・G3-tc と G4 が無効 (`setarch x86_64 -R`)。
- 再現: `M11_PE=<fl-win64>/extracted/block00031_PE.bin RETDEC=<toolchain-retdec>/bin/retdec-decompiler bash tools/m11/uselist_stage_2577.sh` (計 41 run・rc 0)。出力は `tools/m11/work/uselist_2577/` (gitignore)。所要は 1 回目 5 分 39 秒 (`43ca7475f`)、2 回目 5 分 41 秒 (`c0b68d971`)。4 コア・2 回目の load1 は 0.34〜1.00。

### 表 1: 1 回目 (測定 commit `43ca7475f`)

| 群 | 条件 | 実行数 | `.ll` の md5 | 指示行を除いた `.ll` の md5 | 指示行数 |
|---|---|---|---|---|---|
| G1 | `--backend-no-opts`・150 range | 3 | `0b4af6ff`×2・`cbee7ce0`×1 | `dcded415`×3 | 817 |
| G2-A | range 1〜75 (ASLR 有効) | 4 | `cad9618a`×1・`cf593eef`×3 | `fed5afff`×4 | 254〜255 |
| G2-B | range 76〜150 | 4 | `69871cbd`×4 | `70afbcb3`×4 | 590 |
| G2-B1 | range 76〜112 | 4 | `452021b7`×4 | `6c6e34b4`×4 | 367 |
| G2-B2 | range 113〜150 | 4 | `6ef96c38`×4 | `daa792d6`×4 | 235 |
| G3-on | 単独 `0x409c80-0x409ed8` (`function_409c80`)・ASLR 有効 | 4 | `dcdbd15e`×1・`a73b4ed0`×3 | `7c556e51`×4 | 55 |
| G3-off | 同・ASLR 無効 (`setarch -R`) | 4 | `a73b4ed0`×4 | `7c556e51`×4 | 55 |
| G3-tc | 同・ASLR 無効 + `glibc.malloc.tcache_count=0` | 4 | `a73b4ed0`×4 | `7c556e51`×4 | 55 |

- G3 の on1 と off1 は 1 回目の 1 run で指示行 1 行だけ違った (`559c559`: `uselistorder i64 %182, { 1, 0, 2, 3 }` と `{ 1, 0, 3, 2 }`。`function_409c80` 内の値)。2 回目では両者は同一。1 run 限りの観測として扱う。`on` (`G3-on1.c` 6 字) と `off` (`G3-off1.c` 7 字) はパスも 1 字違うため、この差を ASLR だけの効果とは言えない。
- `.c` の群内一致 (1 回目の手作業の確認: G1 `d8437af5`・G2-A `d32d94e5`・G3 `c9f5e103`) は、スクリプトが `.c` の md5 を出さないため、再現の記録としては弱い。

### 表 2: 2 回目 (測定 commit `c0b68d971`)

| 群 | 条件 | 実行数 | `.ll` の md5 (件数) | 指示行を除いた `.ll` の md5 (件数) | 指示行数 |
|---|---|---|---|---|---|
| G1 | `--backend-no-opts`・150 range (ASLR 有効) | 3 | `b1719531`×1・`bebbeda0`×1・`ae3a6356`×1 | `dcded415`×3 | 818・818・817 |
| G2-A | range 1〜75 (ASLR 有効) | 4 | `9c5027c5`×4 | `fed5afff`×4 | 255 |
| G2-B | range 76〜150 (ASLR 有効) | 4 | `69871cbd`×3・`ee9f00bd`×1 | `70afbcb3`×4 | 590 |
| G2-B1 | range 76〜112 (ASLR 有効) | 4 | `452021b7`×4 | `6c6e34b4`×4 | 367 |
| G2-B2 | range 113〜150 (ASLR 有効) | 4 | `6ef96c38`×4 | `daa792d6`×4 | 235 |
| G3-on | 単独 `0x409c80-0x409ed8`・ASLR 有効 | 4 | `a73b4ed0`×4 | `7c556e51`×4 | 55 |
| G3-off | 同・ASLR 無効 | 4 | `a73b4ed0`×4 | `7c556e51`×4 | 55 |
| G3-tc | 同・ASLR 無効 + tcache 0 | 4 | `a73b4ed0`×4 | `7c556e51`×4 | 55 |

- 件数の定義: 「実行数」は同じ群の run 数 (同一 commit・同一 PE・同一 RetDec)。「`.ll` の md5 (件数)」は群内の run の `.ll` 全体の md5 の異なり数と、各 md5 の run 数。指示行を除いた md5 も同じ定義で、`grep -v uselistorder` した `.ll` の md5。
- 1 回目 (表 1) と 2 回目 (表 2) で群の種数が変わった: G1 2 種→3 種、G2-A 2 種→1 種、G2-B 1 種→2 種、G3-on 2 種→1 種。発生率は実行ごとに変わる。レビュー側の独立再実行 (`4e5500ba6`・PR review の記載) では G1 3 種・G2-B 3 種・G3-on 1 種。
- 指示行を除いた `.ll` は、1 回目も 2 回目も全群で 1 種だった。

### G4: 出力名の長さだけを変えた比較 (ASLR 無効・env -i)

相対名 9 字 (`qqqqqqq.c`) と 17 字。plain・`--backend-no-opts` は各 2 回、`--print-after-all` は各 1 回。

表 G4-1 (1 回目・測定 commit `43ca7475f`。`.ll` は保存していなかった):

| 条件 | 出力名 (相対) の長さ | `.ll` の md5 (2 回ずつ) | stderr 全体の md5 |
|---|---|---|---|
| plain | 9 字 | `dcdbd15e`×2 | `9dbacd66` |
| 同 | 17 字 | `a73b4ed0`×2 | `9dbacd66` |
| `--backend-no-opts` | 9 字 / 17 字 | `dcdbd15e`×2 / `a73b4ed0`×2 | `9dbacd66` (同) |
| `--print-after-all` | 9 字 / 17 字 | `a73b4ed0` / `a73b4ed0` | `1f722193` (両方同一) |

表 G4-2 (2 回目・測定 commit `c0b68d971`。`.ll` は run ごとに保存):

| 条件 | 出力名 (相対) の長さ | `.ll` の md5 (2 回ずつ) | stderr 全体の md5 |
|---|---|---|---|
| plain | 9 字 / 17 字 | `a73b4ed0`×2 / `a73b4ed0`×2 | `9dbacd66` (同) |
| `--backend-no-opts` | 9 字 / 17 字 | `a73b4ed0`×2 / `a73b4ed0`×2 | `9dbacd66` (同) |
| `--print-after-all` | 9 字 / 17 字 | `a73b4ed0` / `dcdbd15e` | `1f722193` (両方同一) |

- 1 回目: 9 字で `dcdbd15e`・17 字で `a73b4ed0` の切替が出た。9 字と 17 字の `.ll` の差は指示行 1 行 (`559c559`: `{ 1, 0, 2, 3 }` ↔ `{ 1, 0, 3, 2 }`)。この差はレビュー側の独立再実行 (`4e5500ba6`) でも 1 行だった。
- 2 回目: 9 字と 17 字はともに `a73b4ed0` で、plain1 の 9 字と 17 字の `.ll` の差は 0 行 (`== G4 diff` の出力は空)。`--print-after-all` は 1 回目と逆 (17 字だけ `dcdbd15e`)。
- 結論: 出力名の長さによる切替は 1 回目にだけ現れ、2 回目では再現しなかった。『出力名の長さで決定的に切り替わる』とは言えない。
- stderr 全体の md5 は 1 回目と 2 回目で一致 (plain・noopts `9dbacd66`、`--print-after-all` `1f722193`)。`--print-after-all` の IR テキストは両回で同じで、`.ll` の指示行だけが変わる。

### 切り分けと結論 (2 回の測定の合算)

1. **バックエンド段ではない (暫定)**: `--backend-no-opts` でも指示行の揺れは残る (G1 は 1 回目 2 種・2 回目 3 種)。指示行を除いた `.ll` は両回とも全群で 1 種 (表 1・表 2)。
2. **書き出し前の段に限られる (推定)**: ログの phase は `Input binary to LLVM IR decoding` → LLVM/RetDec の最適化群 → `Generate the current LLVM IR` (`.ll` の書き出しに対応すると推定) → `Generate the current bitcode` → `LLVM IR -> HLL` の順。揺れは `Generate the current LLVM IR` より前にある (推定。phase ごとの切り分けは未実施)。
3. **pass 単位 (`--passes` 相当) の段は未特定**: RetDec v5.0 のオプションは `--print-after-all`・`--print-before-all` だけで、use-list を含む per-pass dump が無い (テキスト dump は指示行を載せない)。`--select-functions` は探索時に試したが、失敗・ハングの記録は残っていない (記録なし・結論に使わない)。関数単位の切り分けは未実施。
4. **アドレス依存の機構 (未確定)**: 出力名長に対する切替は 1 回目にだけ観測された。2 回目では再現せず、切替は run ごとに変わる。よって『出力名の長さが原因』とも『ヒープ配置が原因』とも言えない。ヒープ配置依存は推定止まりで、ヒープ上の値は未計測。ASLR 有効の G1・G2・G3-on の `.ll` の種数は run ごとに変わった (表 1・2)。RetDec のソースは toolchain に含まれず、container (pointer を key にした map/set 等) は未特定 (REPORT_APPENDIX_960 §20 項 4)。

### 検証範囲 / 範囲外

- 範囲内 (2 回・計 82 run、rc は全 0): 150 range 先頭・単独 range `0x409c80-0x409ed8`・ASLR 有効/無効・tcache 0・出力名長 9/17 字・`--backend-no-opts`・`--print-after-all`。
- 記録なし (結論に使わない): 同じスクリプトを 3 回実行した群別の種数 (探索時の値。元データは `uselist_stage_2577.sh` の `rm -rf` で消えた)・出力名長 3〜37 字の走査・絶対名 41〜139 字・環境変数と TMPDIR の影響・`--select-functions` の失敗とハング。
- 範囲外: 150 range 外の 7,210 range・他の RetDec 版・ソースに基づく container 特定。単独 range の実測所要は `--timeout 250` の G3 で 1 回目 7.5〜7.9 秒・2 回目 7.6〜8.0 秒。
- 再現の注意: G4 の 9/17 字の対比は 2 回目で再現しなかったため、出力名長を変えた比較の結果を根拠にしない。G3 の on/off は名長が 1 字違う。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| pass 単位 (`--passes` 相当) の段の特定 (use-list 付き per-pass dump が v5.0 に無い) | 上流 (RetDec) の修正箇所が決まらない。段は『書き出し前の phase 群』まで | #2577 (本 issue に残す) |
| 指示行の並びが run ごとに変わる条件 (G4 の切替は 2 回目で再現せず、原因未確定) | 機構は未特定。RetDec 側の決定化の要否も未定 | #2577 (同上) |
| ヒープ配置に依存する container の特定 | 機構は推定止まり | #2577 (同上) |
| ASLR 有効での揺れの発生率が実行ごとに変わる原因 | 件数が実行で変わる (指示行のみ・A7 後の lift には出ない) | 親 #2456・#960 へ提案 (観測のみ) |

- 本節は `REPORT_APPENDIX_960.md` §20 の『子 issue #2577』の範囲 (pass 単位・機構) への一次結果。RetDec 側の決定化は採らない (§19 の A7 方針を維持)。
