# REPORT_APPENDIX_2577 — #2577: RetDec drc.ll の uselistorder 並びの差 (#2456 の残り)

## 21. #2577: 差が入る段とアドレス依存の機構 (部分達成)

- 既知類型との関係: 該当なし (DEFECTS.md の silent miscompile 類型ではない。A7 後の `.ll` の指示行以外は全 run で一致)。既知事象は #668 (LIFTLIB-9) と REPORT_APPENDIX_960 §20 の m11 側の再現。
- 測定 commit: `43ca7475f` (`tools/m11/uselist_stage_2577.sh` の G4 追加版。測定はこの commit の HEAD で実施)。`git diff 43ca7475f HEAD -- tools/m11 ':!tools/m11/REPORT*'` は **0 行** (本節の追記 commit の差。REPORT 以外に変更なし)。
- 条件: PE `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)・RetDec v5.0 (`toolchain-retdec`・sha256 `9d49ffcf…`)・`work-m11` の `boot_ranges.txt` 先頭 150 range (`--select-decode-only`・`--timeout 100`)。素材展開は `$RUNNER_TEMP/fl-win64`・`$RUNNER_TEMP/retdec-root`。
- 再現: `M11_PE=<fl-win64>/extracted/block00031_PE.bin RETDEC=<toolchain-retdec>/bin/retdec-decompiler bash tools/m11/uselist_stage_2577.sh` (計 41 run。実測 5 分 39 秒・user 5 分 25 秒・load 0.62〜1.10・4 コア)。出力は `tools/m11/work/uselist_2577/` (gitignore)。

### 結果 (測定 commit `43ca7475f` の 1 回目の実行)

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

- G3 の on1 と off1 の差は指示行 1 行だけ (`559c559`: `uselistorder i64 %182, { 1, 0, 2, 3 }` と `{ 1, 0, 3, 2 }`。`function_409c80` 内の値)。`.c` は群内で全 run 一致 (G1 `d8437af5`・G2-A `d32d94e5`・G3 `c9f5e103`)。
- 同じスクリプトを 3 回実行した (`8b2c5df2a`・`b4eae735c`・`43ca7475f`)。揺れの有無は実行ごとに変わった (例: G1 は 3 種・1 種・2 種、G2-A は 3 種・1 種・2 種)。**発生率は実行 (セッション) ごとに変わる**ため、1 回の実行の件数で「揺れが無い」とは言えない。どの実行でも、指示行を除いた `.ll` は群ごとに 1 種だった。

### G4: 出力名の長さだけを変える (決定的な切替・`43ca7475f`)

| 条件 | 出力名 (相対) の長さ | `.ll` の md5 (2 回ずつ) | stderr 全体の md5 |
|---|---|---|---|
| 既定 (ASLR 無効・env -i) | 9 字 (`qqqqqqq.c`) | `dcdbd15e`×2 | `9dbacd66` |
| 同 | 17 字 | `a73b4ed0`×2 | `9dbacd66` |
| `--backend-no-opts` | 9 字 / 17 字 | `dcdbd15e`×2 / `a73b4ed0`×2 | `9dbacd66` (同) |
| `--print-after-all` | 9 字 / 17 字 | `a73b4ed0` / `a73b4ed0` | `1f722193` (両方同一) |

- 出力名の長さだけで、同じ入力・同じ環境・ASLR 無効の結果が 2 値の間で決定的に切り替わる (各 2 回)。ASLR も tcache も変えていない。
- 相対名の長さを 3〜37 字で変えると、9・13 字だけ `dcdbd15e` で、他 (3・17〜37 字) は `a73b4ed0` (非単調)。絶対名 41〜139 字は全て `a73b4ed0`。環境変数 (`env -i` と大きい環境) と TMPDIR の長さは結果を変えない (確認済み)。
- `--print-after-all` を付けると切替が消え、stderr の全体 (各 LLVM pass の IR 全文) は 2 条件で同一 (`1f722193`)。**テキストの IR は同一なのに `.ll` の指示行だけが変わる**。

### 切り分けの結論

1. **バックエンド段ではない**: `--backend-no-opts` (バックエンド最適化を止める) でも指示行の揺れは残る (G1・G4)。`.c` は群内で揺れない。
2. **書き出し前の段に限られる (推定)**: ログの phase は `Input binary to LLVM IR decoding` → LLVM/RetDec の最適化群 → `Generate the current LLVM IR` (`.ll` の書き出しに対応すると推定) → `Generate the current bitcode` → `LLVM IR -> HLL` の順。揺れは `Generate the current LLVM IR` より前にある (推定。phase ごとの切り分けは未実施)。
3. **pass 単位 (`--passes` 相当) の段は未特定**: RetDec v5.0 のオプションは `--print-after-all`・`--print-before-all` だけで、use-list を含む per-pass dump が無い (テキスト dump は指示行を載せず、切替も消す)。`--select-functions` は `std::bad_alloc` で失敗した (run 2 件は rc 135・1 件は 93 秒後にハングし PID 指定で停止)。関数単位の切り分けも、このバイナリでは使えない。
4. **アドレス依存 (実証は『出力名の長さに対して決定的に切り替わる』まで)**: 出力名の長さだけで結果が切り替わり、`--print-after-all` の追加の確保で切替が消えた。ヒープ配置への依存は推定 (ヒープ上の値は未計測)。ASLR 有効では同じ長さの出力名でも `dcdbd15e` が 3 回の実行で 12 回中 2 回出た (G3-on)。これは ASLR によるヒープ基点の揺れと整合する (推定)。**どの container (pointer を key にした map/set 等) の反復順かは未特定**。RetDec のソースは toolchain に含まれない (`retdec.tar` の `.cpp`/`.c` 0 件・REPORT_APPENDIX_960 §20 項 4)。

### 検証範囲 / 範囲外

- 範囲内: 150 range (`boot_ranges.txt` 先頭)・単独 range `0x409c80-0x409ed8`・ASLR 有効/無効・tcache 0・出力名長・`--backend-no-opts`・`--print-after-all`。3 回の実行で再現した傾向 (指示行だけが変わる・出力名長で切替) を見た。
- 範囲外: 他の range の関数 (150 range 外の 7,210 range)・RetDec の他バージョン・ソースに基づく container 特定。`--timeout 100` で、単独 range の実測所要は 7.5〜7.9 秒。全 run の rc は 0。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| pass 単位 (`--passes` 相当) の段の特定 (use-list 付き per-pass dump が v5.0 に無い) | 上流 (RetDec) の修正箇所が決まらない。段は『書き出し前の phase 群』まで | #2577 (本 issue に残す) |
| ヒープ配置に依存する container (pointer を key にした反復) の特定 | 機構は推定止まり。RetDec 側の決定化の要否 | #2577 (同上) |
| ASLR 有効での揺れの発生率が実行ごとに変わる原因 | G1〜G3 の件数が実行で変わる (指示行のみ・A7 後の lift には出ない) | 親 #2456・#960 へ提案 (観測のみ) |

- 再現の注意: `-o` の出力名を変えると結果が変わるため、比較する二つの実行は出力名の長さを揃えること (G4 は意図的に変えた例)。
- 本節は `REPORT_APPENDIX_960.md` §20 の『子 issue #2577』の範囲 (pass 単位・機構) への一次結果。RetDec 側の決定化は採らない (§19 の A7 方針を維持)。
