# REPORT — HB-H15 Fruity Wrapper の lift 方式判定 (分割 a: 計測の土台)

- 親: #94 (HB-H4) / 本 issue: #783 / 担当 dir: `tools/hostbridge/wrapper_lift/`
- 検証起点: `origin/main` @ 7c5f7a8f (作業ブランチ `783-wrapper-lift-method`)
- 素材: `fl-win64` (`flstudio_win64_26.1.7.5653.exe` 由来の `extracted/block19091_PE.bin` / `block23676_PE.bin`)
- 既知類型との関係: 該当なし (decode 計測のみ。lift 出力はまだ無い)
- 子 issue: #828 (方式比較) / #829 (CreatePlugInstance 到達) / 兄弟 #784 #787 #788 (#94 分割)
- 再現: `FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/measure_decode.py` (約 7 秒)
  - 依存: `pip install capstone pefile` (実行環境: capstone 5.0.7 / pefile 2024.8.26)
  - 出力: `tools/hostbridge/wrapper_lift/work/decode_block*.json` (gitignore。commit しない)

## 1. 実測 (受入条件 1 の比較表のうち、本 run で測れた項目)

| 項目 | block19091 | block23676 |
|---|---|---|
| ImageBase / SizeOfImage | 0x400000 / 6,094,848 B | 同左 |
| .pdata エントリ数 | 19,816 | 19,826 |
| 関数数 (chain 併合後) | 19,816 | 19,826 |
| decode 成功 (bad=0) の関数数 | 19,812 (99.98%) | 19,822 (99.98%) |
| decode 命令数 (線形, 関数範囲内) | 686,767 | 686,900 |
| decode 不能バイト位置 | 5,186 | 5,186 |
| `CreatePlugInstance` VA | 0x86ab10 | 0x86a970 |
| decode 所要 | 3.33 s | 3.34 s |

**数え方の定義**
- 関数数: `pefile` の `.pdata` (RUNTIME_FUNCTION) を `liftlib/pe.py` の `Image.func_at(merge=True)` で chain 併合し、
  併合後の範囲の重複を除いた数。`.pdata` 外の leaf 関数は数えていない。
- decode 成功率: 併合範囲内を先頭から capstone (64bit) で線形 decode し、1 バイトでも decode 不能な位置があれば
  その関数を不成功とする。ratio = 成功関数 / 関数数。
- 線形 decode は命令境界の誤りを含みうる (データの混入を検出しない)。「実 lift の成功率」ではなく「decode 可能性の上限」として読む。
- `CreatePlugInstance` VA: export テーブルを `parse_data_directories(EXPORT)` で解析した値。
  block19091 の値 0x86ab10 は `HOSTBRIDGE.md` §1 の `fw:0x86ab10` と一致 (照合済み)。

## 2. RetDec の単発試行 (不成功)

- コマンド: `retdec-decompiler -o cpi_sel.ll --select-ranges 0x86ab10-0x86ac40 block19091_PE.bin` (`/opt/retdec/bin`、バージョン未確認)
- 結果: exit 1、6 秒。ログ末尾 `[capstone2llvmir]: Missing type for register number: 243`。
  先頭の `No matching plugins found for 'FishPE 1.1x'` は format 判定の警告。
- 解釈: **この 1 関数範囲でも RetDec は IR を出力できなかった**。全体 (19,816 関数) の成否・件数は未測定。
  `--select-ranges` の指定方法自体の誤りの可能性を否定していない (未切り分け)。
- 未解決: RetDec の全体 lift 成否と、失敗型の分類 → 子 issue A (下記 §4)。

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
| RetDec の Wrapper 全体 lift の成否・失敗型分類 (本 REPORT §2 の単発失敗の切り分け含む) | lift 方式の比較表の 1 列が埋まらない | 子 issue (下記) |
| liftlib / x64c の Wrapper 適用と比較表の完成 | 受入条件 1 未達 | 子 issue (下記) |
| CreatePlugInstance 到達 (受入条件 2) | 受入条件 2 未達 | #94 の後続 / 子 issue (下記) |
