# REPORT_APPENDIX_2814 — Slayer_Engine.dll (block22434) の未被覆 .text の区間判定と ia32 の std・shld (#2814 / 親 #1098)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §11 (結論 1 行)。 本付録が測定値の正本。
- 測定 commit: `e0e81a667` (コードを変えた最後の commit。 `tools/ott/lift/x64c.py`・`tools/ott/rt/ott_cpu.{c,h}`・`lift_text.py`・`gap_classify.py`)。 `git diff e0e81a667 HEAD -- tools/ott tools/plugins/slayer_engine_ia32/*.py` の出力は空 (後続は docs のみ)。
- 入力: `block22434_PE.bin` (179,512 B, sha256 `84b64c43…de724a9`、素材 `fl-win64` を `extracted/block22434_PE.bin` だけ展開)。 emcc は素材 `toolchain-emsdk` の emcc 6.0.12。
- 起動・GUI に関わらない (製品 KPI は対象外)。
- 既知類型との関係 (`docs/DEFECTS.md`): 新類型は無し。 DF 未モデル化は、従来 `std` が `ott_unsup` (fail-fast) で止まっていたため silent の類型に当たらなかった。 本付録の変更で `std` を lift するため、DF の正しさは §5 の試験で確認する。

## 1. 結論

1. 未被覆 11,348 B (239 区間) を (a) 17 区間 2,677 B / (b) 5 区間 2,388 B / (c) 217 区間 6,283 B に分類した。 (c) のうち nop・int3・00 だけの padding が 184 区間 1,364 B、中身のある区間が 33 区間 4,919 B。 全 239 区間の根拠は [GAP_CLASSES_2814.md](GAP_CLASSES_2814.md) (自動生成)。
2. (b) の 5 区間を roots に加えて 2 回目の lift をした。 被覆は 61,654 B (84.46%) → 62,320 B (85.37%)、+666 B。 functions 465 → 472、insns 20,632 → 21,354、jump table 22 → 23。
3. ia32 の `std` と `shld` を x64c に入れた (IA32 限定)。 `[unsup] 非 x87` は 2 件 → 0 件。 x64 の出力は 17 本で不変。
4. 未解決: (c) 中身あり 33 区間 (4,919 B) と (a) 判定保留 2 区間 (0x10010bbf・0x1000ea92、§4)。 子 #3546 (PLG-G2-28) で判定する。

## 2. 分類の規則 (`gap_classify.py`)

区間 = `.text` の被覆 0 の連続域 (lift 1 回目の結果)。 規則は上から順に適用する。

| 分類 | 規則 | 件数 |
|---|---|---:|
| (c) padding | 区間が 90 / cc / 00 のみ | 184 区間 (1,364 B) |
| (a) data-in-code | jt 表 (`lift_meta.jt_ranges`) と半分以上重なる | 11 区間 |
| (a) data-in-code | `.text` 内の reloc 値 (jt の外) を 2 本以上指される | 6 区間 |
| (b) 関数 | 直接 call/jmp/jcc の先頭になる (先頭が 90/cc/00 でないこと) | 2 区間 |
| (b) 関数 | prologue (`55 8b ec`・`8b ff 55 8b ec`・`83 ec`・`81 ec`) で始まる | 3 区間 |
| (c) 参照なし | 上記のどれでもない | 33 区間 (4,919 B) |

- 直接分岐は線形掃引 (CS_MODE_32) の rel 先で、掃引の境界ずれを含む上限。 reloc 参照は `.text` 内の HIGHLOW (type 3) のうち jt 表の外にあるもの。

## 3. (b) と判定した 5 区間の根拠 (受入 1・2)

| VA | B | 根拠 | 参照元 (call/jmp) | 先頭 8 B |
|---|---:|---|---|---|
| 0x1000bd6b | 79 | 直接 call/jmp の先 | 0x10009ee5 | `55 8b ec 81 c4 30 fd ff` |
| 0x1000beeb | 117 | 直接 call/jmp の先 | 0x10009f85 | `55 8b ec 81 c4 30 fd ff` |
| 0x1000c077 | 13 | prologue `83 ec 2c` (jmp [table] を含む断片) | なし | `83 ec 2c 83 e0 3f ff 24` |
| 0x1000c516 | 571 | prologue `83 ec 2c` (x87 を含む) | なし | `83 ec 2c db 3c 24 db 7c` |
| 0x1000ed9d | 1,608 | prologue `55 8b ec 83 ec 48` (最大区間) | なし | `55 8b ec 83 ec 48 53 56` |

- 0x1000ed9d (1,608 B) は未被覆の最大区間。 関数として lift すると、区間の中の jt 表は含まれない (jt 0 B)。 (b) の判定で jt 重なりは 0 を条件にした。
- 0x1000c516 は x87 命令を含む。 x87 の unsup 件数は §6 のとおり増えたが、増えた箇所は (b) 区間の外で closure により新たに到達したコードを含むかもしれず、位置は未特定。 いずれも実行時は fail-fast で止まり、silent にはならない。

## 4. reloc 値の区間ごとの判定 (受入 2)

- `.text` 内の reloc 値 (jt の外) のうち、未被覆域を指すものは 97 本 (17 区間)。 本付録の定義は jt 表の内部を指す値も数える。 `REPORT_APPENDIX_1098.md` §3 の 76 本・86 本 (未被覆内 73 値) とは数え方が違う。
- 17 区間は**すべて (a)** に分類した (jt 表と重なる 11 区間、`.text` 内の reloc 値 2 本以上の 6 区間)。 よって、reloc 値を理由に roots へ加えた区間は 0。 reloc から指された区間を roots に入れると data を命令として読むため、これは 1098 の判断と同じ。
- 判定保留 2 区間:
  - `0x10010bbf` (822 B・reloc 46 本): 先頭 `cc 55 8b ec 57 56` は関数の prologue に見えるが、reloc 46 本は区間の中にあり、位置の間隔が 4 バイトの並びになっていない。 命令の途中の即値の可能性がある。 (a) とした。
  - `0x1000ea92` (466 B・reloc 8 本): 先頭 `cc cc 55 8b ec 53` で、reloc 8 本のうち区間の中にあるのは 3 本。 (a) とした。
- 2 区間は子 #3546 で、命令境界を確かめて決める。

## 5. x64c の変更 (受入 3・IA32 のみ)

- `std` → `fDF = 1`、`cld` → `fDF = 0` (x64 は従来どおり何も出さない)。
- `rep movs`・`rep stos`・非 rep の `movs`/`stos`・`repne scasb` の方向を `fDF` で切り替えた。 `DF=0` の `rep movs` は従来の `memmove` のまま。 `DF=1` は 1 要素ずつ後ろから。
- `shld` (32bit のみ) を追加。 `count & 31` が 0 のときはフラグを変えない。 CF = dst の最後に出た bit、OF = MSB 変化、SF/ZF/PF は結果。
- runtime: `tools/ott/rt/ott_cpu.h`・`ott_cpu.c` に `fDF` を追加 (x64 の生成物は参照しない)。
- DF の試験: `gcc` で `ott_cpu.c` と試験 (4 ケース: `rep movsd` の DF=0/1、`rep stosb` DF=1、`movsb` DF=1) を実行し、参照の結果と一致 (4/4)。 **試験は生成式を手で写したもので、lift 出力そのものは実行していない**。 実行の正しさは #1223 の差分試験で扱う。

## 6. 実測 (測定 commit `e0e81a667`、HEAD で再現)

| 項目 | 1 回目 (分類のみ) | 2 回目 (b を追加) | 比較の基準 (origin/main `3cf0f759f`) |
|---|---:|---:|---|
| functions / insns | 465 / 20,632 | 472 / 21,354 | 465 / 20,632 |
| 被覆 (B / %) | 61,654 / 84.46% | 62,320 / 85.37% | 61,654 / 84.46% |
| 未被覆 (区間数・B) | 239・11,348 | 237・10,682 | 239・11,348 |
| jump table | 22 | 23 | 22 |
| unsup 非 x87 (件) | 2 (`std`・`shld`) | 0 | 2 |
| unsup x87 (件) | 87 | 89 | 87 |
| `emcc -c` (実 emcc 6.0.12) | rc 0・859,955 B | rc 0・928,669 B | rc 0・859,955 B (再現) |
| lift 所要 (`lift_text.py` 全体・2 パス) | | 13.6 s (HEAD 1 回) | 6.7 s (1 パス) |

- 「unsup x87」は `lift_meta.json` の値の和。 新規の (b) 区間 (0x1000c516 など) に x87 が 2 件増えた。 いずれも fail-fast で、silent ではない。
- 検証 (HEAD `e0e81a667`、clean worktree、素材 `$ARTIFACTS_DIR` の展開先 `$RUNNER_TEMP`):
  - `jt_check.py`: `[jt] OK`・switch 表 23 本 (case 値 245)・生データ一致 23/23。
  - `iat_check.py`: `[iat] OK`・IAT 参照 80/80 (1098 付録の 75 件から増えた。 増えた分は新しく lift した関数内の参照)。
  - `verify_ia32_jt.py`: `[jt] OK` (dispatcher 0x100014a4、case 21/PE 25)。
  - `measure.py` (gate): C1 PASS (0x14c)・C2 PASS (73,002 B)・C3 PASS (0.0055%)・C4 PASS (priv 15)・`[measure] OK (4/4)`。
  - `measure.py --nega`: `nega: 0/3 miss`。
  - x64 回帰: 素材の x64 PE 258 本のうち、サイズ順に 16 本おき 17 本 (`*_PE.bin`) を、EntryPoint と export を roots、closure 2 で `origin/main` の x64c と新 x64c で lift → `ott_lifted.c`・`lift_meta.json` を `cmp`。 **17/17 一致**。

## 7. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64      # tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst extracted/block22434_PE.bin
export EMSDK=$RUNNER_TEMP/tc/emsdk              # tar --zstd -xf $ARTIFACTS_DIR/toolchain-emsdk.tar.zst
export PATH=$EMSDK/upstream/emscripten:$(ls -d $EMSDK/node/*/bin | head -1):$PATH
python3 tools/plugins/slayer_engine_ia32/lift_text.py              # 1 回目 → 分類 → 2 回目 (work/lift_text/)
python3 tools/plugins/slayer_engine_ia32/gap_classify.py --json tools/plugins/slayer_engine_ia32/work/lift_text/gap_classes.json --md   # 区間表
O=tools/plugins/slayer_engine_ia32/work/lift_text; P=$FL_WIN64_DIR/extracted/block22434_PE.bin
python3 tools/plugins/slayer_engine_ia32/jt_check.py $O/ott_lifted.c $O/lift_meta.json $P
python3 tools/plugins/slayer_engine_ia32/iat_check.py $O/ott_lifted.c $P
FL_PE=$P python3 tools/ott/lift/verify_ia32_jt.py $O/ott_lifted.c
python3 tools/plugins/slayer_engine_ia32/measure.py && python3 tools/plugins/slayer_engine_ia32/measure.py --nega
```

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (c) 中身あり 33 区間 (4,919 B)・参照なし。 間接 call 先か断片かの判定 | 被覆の上限 (残り未被覆 10,682 B のうち) | #3546 (PLG-G2-28) |
| 判定保留 2 区間 (0x10010bbf 822 B・0x1000ea92 466 B) | 同上 | #3546 |
| 2 回目で増えた x87 unsup 2 件 (位置は未特定) | 実行時 fail-fast。 silent ではない | #1099 (PLG-G2-9) |
| 生成物の実行の正しさ (native vs wasm)・DF の実行試験 | 未検証 (試験は生成式の写しのみ) | #1223 (PLG-G2-11) |
| `sahf` の AF 未反映・`fs:` の TEB 0 埋め | 1098 から継続 | #1223 |
