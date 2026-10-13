# REPORT — HB-H15 Fruity Wrapper の lift 方式判定 (分割 a: 計測の土台)

- 親: #94 (HB-H4) / 本 issue: #783 / 担当 dir: `tools/hostbridge/wrapper_lift/`
- 検証起点: `origin/main` @ 7c5f7a8f (作業ブランチ `783-wrapper-lift-method`)
- 素材: `fl-win64` (`flstudio_win64_26.1.7.5653.exe` 由来の `extracted/block19091_PE.bin` / `block23676_PE.bin`)
- 既知類型との関係: 該当なし (decode 計測のみ。lift 出力はまだ無い)
- 子 issue: #828 (方式比較) / #829 (CreatePlugInstance 到達) / 兄弟 #784 #787 #788 (#94 分割)
- 再現: `FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/measure_decode.py` (decode 所要は §1 の表。NC は `--nc`)
  - 依存: `pip install capstone pefile` (実行環境: capstone 5.0.7 / pefile 2024.8.26)
  - 出力: `tools/hostbridge/wrapper_lift/work/decode_block*.json` (gitignore。commit しない)

## 1. 実測 (受入条件 1 の比較表のうち、本 run で測れた項目)

| 項目 | block19091 | block23676 |
|---|---|---|
| ImageBase / SizeOfImage | 0x400000 / 6,094,848 B | 同左 |
| .pdata エントリ数 | 19,816 | 19,826 |
| 関数数 (chain 併合後) | 19,816 | 19,826 |
| decode 成功 (bad=0) の関数数 | 19,812 (99.98%) | 19,822 (99.98%) |
| decode 命令数 (線形, 関数範囲内) | 686,756 | 686,889 |
| decode 不能バイト位置 | 5,199 | 5,199 |
| `CreatePlugInstance` VA | 0x86ab10 | 0x86a970 |
| decode 所要 (n=3, min–max) | 2.46–2.49 s | 2.46–2.50 s |

- 計測環境: capstone 5.0.7 / pefile 2024.8.26 (venv)、load average (1 分値) は計測前後 0.22–0.39 の範囲。decode 所要は 3 回の min–max。
- 素材: `fl-win64` (`extracted/block19091_PE.bin` / `block23676_PE.bin`)。検証 HEAD は PR 本文に記載。

**chain 併合の実効性**: `.pdata` エントリのうち `func_at(merge=True)` の範囲が元の (begin,end) と異なるもの (chain エントリ) は両 block とも 0 件。
よって chain 併合は実質無効で、併合後の関数数は pdata エントリ数と一致する。

**数え方の定義**
- 関数数: `pefile` の `.pdata` (RUNTIME_FUNCTION) を `liftlib/pe.py` の `Image.func_at(merge=True)` で chain 併合し、
  併合後の範囲の重複を除いた数 (chain エントリ 0 件のため併合は実質無効)。`.pdata` 外の leaf 関数は数えていない。
- decode 成功率: 併合範囲内を先頭から capstone (64bit) で線形 decode し、1 バイトでも decode 不能な位置があれば
  その関数を不成功とする。ratio = 成功関数 / 関数数。
- 線形 decode は命令境界の誤りを含みうる (データの混入を検出しない)。「実 lift の成功率」ではなく「decode 可能性の上限」として読む。

**decode 不能の内訳** (両 block 共通。bad は関数ごとの不能バイト数)
- 0x40ce20-0x40cf2b (bad 9)
- 0x425720-0x42b7b2 (bad 5,124)
- 0x56f5c0-0x570b30 (bad 39)
- 0x572b00-0x575134 (bad 27)
- 合計 5,199 = 9 + 5,124 + 39 + 27 (4 関数の和)。decode 失敗関数は 19,816 件中 4 件。

**ネガティブコントロール** (`measure_decode.py --nc`、block19091): clean 関数 0x407310-0x40734a の先頭 1 バイトを 0x06 (64bit で不正) に置換。
- 注入前: 成功 19,812 / bad 5,199
- 注入後: 成功 19,811 (−1) / bad 5,200 (+1)
- 判定検査 (成功率) が注入 1 箇所で反応することを確認済み。
- `CreatePlugInstance` VA: export テーブルを `parse_data_directories(EXPORT)` で解析した値。
  block19091 の値 0x86ab10 は `HOSTBRIDGE.md` §1 の `fw:0x86ab10` と一致 (照合済み)。

## 2. RetDec の単発試行 (不成功)

- コマンド: `retdec-decompiler -o cpi_sel.ll --select-ranges 0x86ab10-0x86ac40 block19091_PE.bin` (ツールは `docs/REFERENCES.md` の `[RETDEC]`、バージョン未確認)
- 結果: exit 1、6 秒。ログ末尾 `[capstone2llvmir]: Missing type for register number: 243`。
  先頭の `No matching plugins found for 'FishPE 1.1x'` は format 判定の警告。
- 解釈: **この 1 関数範囲でも RetDec は IR を出力できなかった**。全体 (19,816 関数) の成否・件数は未測定。
  `--select-ranges` の指定方法自体の誤りの可能性を否定していない (未切り分け)。
- 未解決: RetDec の全体 lift 成否と、失敗型の分類 → #828 (§4)。

## 3. 未実測 (本 run の範囲外)

| 項目 | 状態 |
|---|---|
| liftlib (RetDec → 修復 → emcc) の Wrapper 適用 | 未着手 (RetDec 出力が無い) |
| x64c (`tools/icall/x64c_census.py` 系) の Wrapper 適用 | 未着手 |
| 採用方式の wasm build 可否・所要秒 | 未着手 |
| CreatePlugInstance への到達 | 未着手 |

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec の Wrapper 全体 lift の成否・失敗型分類 (本 REPORT §2 の単発失敗の切り分け含む) | lift 方式の比較表の 1 列が埋まらない | #828 |
| liftlib / x64c の Wrapper 適用と比較表の完成 | 受入条件 1 未達 | #828 |
| CreatePlugInstance 到達 (受入条件 2) | 受入条件 2 未達 | #829 |
