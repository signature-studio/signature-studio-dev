# REPORT — HB-H15 Fruity Wrapper の lift 方式判定 (分割 a: 計測の土台)

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md`。§9 (#1521) の全文は付録 `tools/hostbridge/wrapper_lift/REPORT_APPENDIX_1521.md`。

- 親: #94 (HB-H4) / 本 issue: #783 / 担当 dir: `tools/hostbridge/wrapper_lift/`
- 検証起点: `origin/main` @ 7c5f7a8f (作業ブランチ `783-wrapper-lift-method`)
- 素材: `fl-win64` (`flstudio_win64_26.1.7.5653.exe` 由来の `extracted/block19091_PE.bin` / `block23676_PE.bin`)
- 既知類型との関係: 該当なし (decode 計測のみ。silent miscompile の類型には当たらない。lift 出力の類型は §6 末尾)
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
| x64c の block23676 への Wrapper 適用 | 未着手 (block19091 は §6) |
| 採用方式の wasm build 可否・所要秒 | 未着手 |
| CreatePlugInstance への到達 | 未着手 |

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec 既定モードの reg 243 失敗の原因 (分割 lift は §5 で測定済み) | 既定モードは使えない | #828 |
| liftlib / x64c の Wrapper 適用と比較表の完成 | 受入条件 1 未達 | #828 |
| CreatePlugInstance 到達 (受入条件 2) | 受入条件 2 未達 | #829 |
| liftlib (RetDec → 修復 → emcc) の Wrapper 適用・wasm build 可否と採用方式の決定 | 比較表の build 列と採用方式が埋まらない | #917 (子) |
| RetDec 既定モード (`--select-decode-only` なし) が reg 243 で落ちる原因 | 既定モードで Wrapper を lift できない理由が未特定 | #828 |
| RetDec の Wrapper 全体 lift の成否・失敗型分類 (分割 lift の 93 件 / block19091・block23676 は §5 で分類済み。残る未解決は liftlib 経路での失敗型) | liftlib 経路の失敗型が未確定 | #828 (liftlib 経路は #917) |

## 5. 方式比較の実測 (#828、検証 HEAD: 本 PR)

計測: `RETDEC=<retdec>/bin/retdec-decompiler FL_WIN64_DIR=<fl-win64>/extracted python3 tools/hostbridge/wrapper_lift/retdec_batch.py block19091_PE.bin block23676_PE.bin` (RetDec v5.0、batch 500、直列)。x64c は `tools/icall/x64c_census.py` (関数集合は §1 と同じ chain 併合)。本 PR の数値の正本はこの節。§6 は本節を参照する。

| 項目 | RetDec (分割 lift) | x64c (静的カバレッジ) | liftlib (RetDec→修復→emcc) |
|---|---|---|---|
| block19091: 関数数 | 19,816 | 19,816 | 未測定 |
| block19091: lift 成功 (関数単位) | 19,723 (99.53%) | — | 未測定 |
| block19091: emcc `-c` 通過 (修復なし, 関数単位) | 未計測 (旧値 17,243 / 19,816 は測定スクリプト版が不明で fail-open 経路の可能性があるため撤回。本 HEAD の runner に emcc 無し) | — | 未測定 |
| block23676: 関数数 / lift 成功 | 19,826 / 19,733 (99.53%) | — | 未測定 |
| 未対応命令数 (block19091 / block23676) | — | 3,697 / 3,697 (0.56% / 0.56%) | 未測定 |
| build 可否 (wasm) | 未実施 | 未実施 | 未実施 |
| 所要 (RetDec, 全呼び出し秒 `retdec_seconds_all`, block19091 / block23676) | 267.37 / 265.41 (前回 run) | 11.22 s (block19091, 19,816 関数, 単一プロセス) | 未測定 |

- 計測環境: RetDec v5.0 (`[RETDEC]`、公式 Linux release を RUNNER_TEMP に展開)、capstone 5.0.7 / pefile 2024.8.26。直列 1 プロセス。load average (1 分値) は計測中 0.23–0.33。
- 所要の注意: 本 HEAD の runner には `[RETDEC]` の実体が無く、RetDec の所要は本 HEAD で再計測していない。表の 267.37 / 265.41 s は本節の定義による旧計測値。同じ項目の別値 (305.01 s / 305.04 s) が以前の記載にあり、どちらが正かは RetDec を入れた環境での再計測で確定させる (未解決、#828)。
- 所要の定義: `retdec_seconds_all` = 分割前の親 batch・分割後の子 batch・単独失敗を含む、全 `retdec-decompiler` 呼び出しの wall 時間の和 (呼び出し 40 回、全て exit 0)。`retdec_seconds_ok_calls` (rc == 0 の呼び出しだけの和) は同値 (267.37 / 265.41) で、今回は失敗呼び出しが無いため差は出ない。
- 定義: RetDec 成功 = 出力 C に `function_<開始 VA>` の定義本体が現れる関数。`exit 0` だが定義が無い関数は失敗 (reason `no_definition`)。RetDec の出力 C はコンパイル可否を保証しない (emcc 通過は別欄)。
- 失敗 93 件の内訳 (block19091 / block23676 とも同じ): (a) RetDec が非 0 終了 = 0 件 (全 40 呼び出しが exit 0 で、分割による単独 range の非 0 終了は起きなかった)。(b) exit 0 だが定義なし = 93 件。(a) に該当する代表的なエラー行は無い。(b) の 93 件は線形 decode の不能範囲 (§1: 0x40ce20 / 0x425720 / 0x56f5c0 / 0x572b00 の各範囲) と重ならず (0 件)、原因は未特定。失敗 93 件の全アドレスは `retdec_block*.json` の `failed_funcs` (gitignore)。
- ネガティブコントロール (`retdec_batch.py --nc`、block19091 の先頭 20 関数を 1 batch で lift): 出力 C から `function_407310` の定義ヘッダ (`int64_t function_407310(void) {`) を 1 行削除すると、defined が 20 → 19 になり、対象関数の判定が `ok` → `no_definition` に変わる。判定が定義行の有無に依存することを確認。
- 命令数の定義の差: x64c の 659,894 (block19091) は `tools/icall/x64c_census.py` が recursive descent (関数の入口から到達できる命令のみ) で数えた値。§1 の 686,756 は `.pdata` 範囲の線形 decode の総数。同じ 19,816 関数を対象とするが、数え方が異なる (線形 decode は関数内のデータ・到達不能コードも数える)。よって両者は直接比較できない。
- x64c の未対応: census 経路の未対応 mnemonic は 66 種 (上位は `movsq` 1,587 / `stosq` 435 / x87 / `rep movsq` 68 / `lock xadd`・`lock cmpxchg`)。Delphi RTL の文字列コピー (rep/movs) と x87 演算が主因。これは静的カバレッジで、x64c の実 lift 成否ではない。
- wrapper 経路 (`x64c_wrapper.py`、全 pdata 関数を root にした生成) の unsup は 3,629 件 / 81 種 (`lift_meta.json` の `unsup` 合計。`x64c.py` ba13c9dc 版で実測)。census 経路の値と集計対象が異なるため直接比較しない。
- §1 の decode 所要: 本 HEAD の `measure_decode.py` 単発実行では block19091 4.15 s (`decode_seconds`)。表の 2.46–2.49 s は前回 n=3 の値で、環境の load により変動する。

**RetDec の既定モードの失敗 (§2 の追試)**: 1 関数範囲だけでなく block19091・block23676 の全体でも、既定モードは decode 段で
`[capstone2llvmir]: Missing type for register number: 243` により exit 1 で落ちる (約 8 s)。対照の小さい PE (block00004 / block00006) は exit 0。
`--select-decode-only` を付けると範囲指定の lift が通る。reg 243 の由来は未特定 (capstone 5.0.7 では `X86_REG_BND1` に当たるが、
両 block の `.text` を線形 decode しても BND レジスタは現れない。RetDec 同梱の capstone の番号体系の差の可能性が残る)。

**未解決 (受入条件の残り)**
- liftlib (RetDec 出力 → 修復 → emcc) を Wrapper に適用した成否と、wasm build 可否。RetDec の batch 出力 C を結合して emcc する経路は未着手。
- 採用方式の判定。RetDec は分割 lift で 99.53% が通るが、修復なしの emcc 通過は未計測 (旧値 87.02% は撤回) で、出力の build と実行 (bit 一致) が未確認のため、単独で採用とは言えない。x64c は命令カバレッジ 99.44% だが実 lift 未実施。
- 上記は子 issue #917 ([HB-H23]) として起票する (§4 の 2 行)。

## 6. 比較表 (#917 受入条件 1〜3。検証 HEAD: 本 PR、2026-10-13 run)

数値の正本は §1・§5。ここは到達状況のみ。計測環境: `[EMSDK]`・`[RETDEC]` の実体は本 HEAD の runner に無く、emcc 相当の検査は clang `-fsyntax-only` で代用した (下記)。

| 項目 | RetDec 分割 lift | x64c (`x64c_wrapper.py`) | liftlib (RetDec→修復→emcc) |
|---|---|---|---|
| block19091: 関数数 | §5 | §5 (全 pdata 関数を生成) | 未測定 |
| block19091: lift | §5 (成功率) | 例外なく C を生成。未対応 mnemonic の関数は実行時に `ott_unsup` で fail-fast | 未完 (下記) |
| block19091: C の構文検査 | §5 (修復なしの通過率) | `ULLULL` 18 行を補正すると clang 構文検査を通過 (下記) | 未測定 (修復は未実施) |
| block23676 | §5 | 未実施 | 未測定 |
| wasm link (emcc, 全体) | 未実施 | 未完 (旧計測で 400 秒の timeout。完了時間は未測定) | 未実施 |

**x64c 生成物の `ULLULL` (本 HEAD で実測)**
- 生成 C (`x64c_wrapper.py`、block19091、19,816 関数、`tools/ott/lift/x64c.py` は ba13c9dc 版で実行) の `ULLULL` は **18 行**。全 18 行が `cmpxchg qword ptr` の 64bit 分岐の else 節 (`R[RAX] = (R[RAX] & ~0xffffffffffffffffULLULL) | ...`)。
- 原因行: `tools/ott/lift/x64c.py` の `i_cmpxchg`。ba13c9dc では 1447 行 `amask = '0xffffffffffffffffULL' if sz == 8 else hex(MASK[sz])` と、1449 行の `'... ~%sULL ...' % (..., amask)`。`sz == 8` の amask は既に `ULL` を含むため、`~%sULL` の `ULL` と二重になる。main では同じ箇所が 1491 / 1493 行 (main の x64c.py は 1605 行、ba13c9dc は 1560 行)。
- main 取込み後の `x64c.py` (HEAD `4900b0f5`) で同じ生成を再実行しても `ULLULL` 18 行・clang エラー 18 件で、原因は残っている (main 版の該当行は 1491 / 1493 行)。
- 前回 REPORT が挙げた `x64c.py:260` (`hex(MASK[s])`) は原因ではない。`hex(MASK[s])` は `0xff` 形式で `ULL` を含まず、260 行の `~%sULL` は `ULL` が 1 つだけ付く。
- 補正の効果: 補正なし `clang -fsyntax-only` は 18 件のエラー (`invalid suffix 'ULLULL' on integer constant`)。`sed 's/ULLULL/ULL/g'` 後は 0 件で通過 (28.7 s)。前回の「2 箇所補正」は誤りで、補正箇所は 18 箇所。
- emcc は本 HEAD の runner に無く、emcc `-c` の再測定はしていない。clang の結果は C 構文の検査であり、emcc 通過の証拠ではない。
- 元の `tools/ott` は変更していない。`x64c.py` 本体の修正は #1128 の範囲 (別 PR)。
- `docs/DEFECTS.md` の該当 ID: なし。構文エラーとして検出されるため、silent miscompile の類型ではない。

**未解決 (受入条件の残り → 子 issue #1128 `[HB-H26]`)**
- liftlib (RetDec C → 修復 → emcc) の Wrapper 適用: RetDec 出力は `.ll` ではなく C であり、liftlib の `lift` 入口 (`targets/*.json`・`.ll` 前提) に直接載らない。修復 (`int64_t*` と整数の混在、`__asm_movsd` 等の未宣言 helper) が未実施。
- block23676 の x64c 実 lift と、両 block の wasm link 完了 (受入条件 1・2 の残り)。
- 採用方式の判定 (受入条件 4): build 可否が揃うまで決められない。**採用方式は未決定**。

## 7. #1128 の実測 (検証 HEAD: 7ceb66ce)

環境: `[EMSDK]` (`toolchain-emsdk`) の emcc、`[RETDEC]` (`toolchain-retdec`) v5.0、load average (1 分値) 0.6–2.4。

| 項目 | block19091 | block23676 |
|---|---|---|
| RetDec 分割 lift 成功 (§5 の再現) | 19,723 / 19,816 (99.53%)・188 s | 19,733 / 19,826 (99.53%)・194 s |
| RetDec 出力 C の emcc `-c` 通過 (修復なし, 関数単位) | 未計測 (旧 fail-open 版の値は無効・撤回。下記 #1340 参照) | 未計測 (同左) |
| 同 (`-Wno-implicit-function-declaration -Wno-int-conversion -Wno-incompatible-pointer-types`) | 未計測 (旧 fail-open 版の 19,650 / 19,816 は無効・撤回。ファイル単位の exit 0 件数も撤回) | 未測定 |
| x64c 生成 (`ULLULL` 吸収後) | 19,816 関数・`ULLULL` 0 行・60 s | 19,826 関数・`ULLULL` 0 行・60 s |
| x64c `emcc -c` (`-I tools/ott/rt`) | exit 0・34.5 s・error 0 | exit 0・34.4 s・error 0 |
| x64c wasm link (`-Wl,--export-all -Wl,--allow-undefined`) | exit 0・0.66 s・43,828,879 B | exit 0・0.47 s・43,833,146 B |

- **#1340 による訂正 (旧 emcc_per_function.py は fail-open)**: 旧版は timeout で `rc=None`・`out=""` となり、`ERR_RE` が `error:` 行のみを拾うため、
  帰属 0 件のファイルの全関数を通過扱いにしていた。`fatal error:` と `emcc: error:` (行番号なし) も帰属 0 件となり、同じく全通過になっていた。
  旧版で測った修復なし通過 (17,155 / 19,816、17,161 / 19,826)、`-Wno-*` 付きの 19,650 / 19,816、ファイル単位の exit 0 件数 (16 / 40) は、
  いずれも fail-open 経路を通りうるため**撤回** (無効)。修復なし run の emcc exit 内訳 (exit 0 / 非 0 / timeout のファイル数) と未帰属 error 行数も**未測定**。
  修正後の値は実 emcc での再計測まで出せない (下記)。
- **修復なし通過の受入状態**: 未計測 (fail-open 版は無効)。修正後のスクリプトによる数値は本 PR に含めない。emcc 系の行は測定値を持たないため、測定 commit と freshness (`git diff <測定 commit> HEAD -- tools/hostbridge/wrapper_lift`) の対象も無い。
- **#1340 修正後のスクリプト** (`emcc_per_function.py`): `rc != 0` (timeout 含む) で、ファイル内の関数帰属が無い、または帰属できない error 行がある場合は、
  そのファイルの全 defined 関数を失敗にする (fail-closed、`failclosed_files` で件数を出す)。`fatal error:` を `ERR_RE` に含める。
  帰属できなかった error 行は `unattributed_error_lines` に別計上する。`--cc` でコンパイラを差し替え可能にした。
- **#1340 ネガティブコントロール** (検証 HEAD: 本 PR の修正 commit、同梱 clang 18.1.3 を `--cc clang` で使用、`--targets` は block19091)。
  入力 `work/nc/nc_mixed.c` (`function_407310` 正常・`function_407460` は未宣言 `__asm_missing()` を呼ぶ・`function_4074b0` 正常):

  | 条件 | 新版 `functions_pass` / `functions_with_error` | 旧版 (d3a9ad56) |
  |---|---|---|
  | mixed (clang, error 1 行 → `function_407460` 帰属) | 2 / 1 | 2 / 1 |
  | 全正常 `nc_ok.c` (clang, exit 0) | 2 / 0 | (未測定) |
  | 全正常 `nc_ok.c` に `--force-fail-file` (timeout 模擬) | 0 / 2 | (未測定) |
  | mixed に `--timeout 0` (実 timeout 経路) | 0 / 3 | **3 / 0 (fail-open 再現)** |
  | mixed・error 行番号なし `emcc: error:` (shim) | 0 / 3 (`unattributed_error_lines` 1, `failclosed_files` 1) | (未測定) |
  | mixed・`fatal error:` (shim, file:line) | 2 / 1 (`function_407460` のみ失敗) | (未測定) |

  旧版の mixed (clang) は、`function_407460` のみ失敗・残 2 関数通過で、新旧とも一致する (未宣言 error の帰属は旧版でも正しい)。
  fail-open は timeout 経路でのみ発生する。
- **#1340 の残り (未達)**: block19091 / block23676 の RetDec 出力 C の再生成と、修正後スクリプトでの emcc 再計測 (§7 表) は、この run に `toolchain-emsdk` / `toolchain-retdec` が無いため未実施。
  再起動時は `oc_artifacts: fl-win64 toolchain-emsdk toolchain-retdec` が必要。
- 再計算コマンド: `python3 tools/hostbridge/wrapper_lift/emcc_per_function.py <retdec_batch_dir> --targets <block.bin> --out <json>` (関数単位、pdata 集合で数える)。
  x64c: `FL_WIN64_DIR=<fl-win64>/extracted python3 tools/hostbridge/wrapper_lift/x64c_wrapper.py <block.bin> <out>` の後に `emcc -c -I tools/ott/rt`。
- `ULLULL` の吸収: `x64c_wrapper.py` が生成後に `ULLULL` → `ULL` を置換する (`tools/ott/lift/x64c.py` は変更していない。本体の修正は別 PR)。
- 修復なし RetDec 出力の誤り内訳 (block19091、全 40 ファイル、error 行 11,432。上位 12 種の集計): undeclared function 8,062 (`__asm_*`・`__readgsqword` 等)、incompatible pointer types 1,245、int 変換系 (incompatible pointer to integer conversion) は上位 6 種の計 1,968、goto/label 関連 94 (`statement not in loop or switch` 78 + `undeclared label` 16)。
- **注意 1**: `-Wl,--export-all` なしの link は wasm が 2.9 KB で、未 export 関数が DCE されたと推定 (未確認)。build の証拠にならないため、表の値は export-all 版のみ。
- **注意 2**: `--allow-undefined` のため、link が通っても未解決シンボルの有無は未検証。
- **注意 3**: 93 件の `no_definition` (§5) の原因は未特定のまま。

**採用方式 (暫定、受入条件 4)**: **x64c (Wrapper 経由) を採用候補とする**。両 block が生成・`emcc -c`・wasm link を通る。RetDec 分割 lift は、修復なしの `emcc -c` 通過が未計測 (旧値は撤回) で、修復 (undeclared helper・goto/label) が必要なため build 可否が出ない。
ただし x64c の実行結果 (bit 一致) と CreatePlugInstance 到達 (#829) は未検証。よって「採用」は build 経路の判定であり、実行検証は残る。

## 8. #1339: RetDec 分割 lift 出力 C の修復 (測定 commit: a10c1f60、2026-10-13 run)

- 結論: 分割 lift の出力 C は helper 宣言の補修と判定修正で emcc `-c` 通過数が増えたが、wasm link・方式比較は本節では未達。測定表・内訳・未修復の分類は付録 `REPORT_APPENDIX_1339.md` を参照 (全文は分割移動)。

## 9. #1521: int/pointer・frontend helper の修復と emcc 通過数 (測定 commit: bb076c69)

- 結論: int/pointer 混在 (`-Wint-conversion`) は修復済み (block19091_0.c で 46 → 0、全 40 ファイルで修復後 0)。emcc exit 0 は 40 ファイル中 1 件のみで受入条件 3 は未達 (残りは goto/break 94 件と引数型不一致 1,245 件)。未達は子 issue #1679 (HB-H35)・#1680 (HB-H36) に分割。
- 測定表・残り error の内訳 (合計 1,377)・受入条件の判定・再測定手順・未検証項目は付録 `tools/hostbridge/wrapper_lift/REPORT_APPENDIX_1521.md` (§9 全文の分割移動) を参照。

## 11. #1680: 引数型不一致 (`incompatible pointer types passing`) の修復 (測定 commit: f6913004)

- 結論: 宣言側 `int16_t *` は正しい (Win32 LPCWSTR・PE 内 UTF-16LE と一致)。呼出側の `L"..."` (wasm32 で 4B) を `(int16_t *)u"..."` に直す (`retdec_repair.py --wide`)。両 block で `incompatible pointer types passing` は 1,245 / 1,251 → 0、error 行は 1,377 / 1,383 → 132、emcc exit 0 は 1 → 11 (40 件中)。
- 判定の根拠・代表例 3 種・全件の UTF-16LE 裏取り・測定表・再現手順は付録 `tools/hostbridge/wrapper_lift/REPORT_APPENDIX_1680.md` を参照。
- 未達: 残り 132 件 (goto/break・label・代入型不一致) → #1679 (HB-H35)。修復後の実行 (bit 一致) と wasm link は未検証。

## 10. #1522: `no_definition` 残り 4 件の原因 (測定 commit: 05db246f)

- 結論: 4 件のうち 3 件は判定の取りこぼしで修正済み。残る 1 件 (0x570b30) は原因未特定 (#1819)。→ #1819 で原因特定・修正済み (§11・全文は `REPORT_APPENDIX_1819.md`)。
- 判定の取りこぼし (3 件): 旧 `DEF_RE` は `function_<VA>` 名だけを定義とみなした。RetDec は関数名を別名で出すことがあり、`0x41c480` は `__dbk_fcall_wrapper`、`0x86ab10` / `0x86a970` は `CreatePlugInstance`、`0x87cdf0` / `0x87cfc0` は `entry_point`。単独 range の RetDec 出力 (exit 0) で定義を確認。判定に `// Address range: 0x<VA> - ...` 直後の関数定義を追加して修正。
- batch 固有の脱落 (1 件): `0x570b30` は batch (500 関数) 内の出力に定義もヘッダも無い。単独 range・2 件ペアでは `function_570b30` として出る。batch の RetDec 出力が範囲を落とす現象で、原因は未特定。
- 再計測 (retdec_batch.py、判定修正後): block19091 は 19,816 中 19,815 ok・1 件 `no_definition` (0x570b30)、block23676 は 19,826 中 19,825 ok・1 件 (0x570b30)。RetDec 呼び出し 40 回、全 exit 0。所要 273.95 s / 274.23 s。load average 0.01–0.28。
- 修正前の値 (旧判定): 付録 `REPORT_APPENDIX_1339.md` の表 (a10c1f60 時点) を参照。
- ネガティブコントロール (範囲ヘッダ経由の定義を 1 行削除して `ok` → `no_definition` に変わることの実測): 本 run は未実施。RetDec (`toolchain-retdec`) が素材に無く、`retdec_batch.py --nc` を実行できなかった。合成入力での確認のみ: `// Address range: 0x1000 - 0x1010` + `int64_t __dbk_fcall_wrapper(...) {` の 2 関数を入力すると `defined_before`=2・対象 0x1000 の削除後 `target_status_after`=`no_definition`。`negative_control()` は範囲ヘッダ経由の VA を選ぶよう修正 (`nc_remove`)。実 RetDec 出力での数値は再実行で埋める。
- 未達 (受入条件 2・3): emcc exit 0 の wasm link と方式比較表は本 run で未実施。REPORT §9 の通り emcc exit 0 は 40 ファイル中 1 件 (#1679・#1680 が未完)。

## 11. #1819: batch で `0x570b30` が脱落する原因と修正 (測定 commit: 4568c3f3)

- 結論: 脱落は RetDec の隣接範囲の取り扱いが原因。`retdec_batch.py` で定義が出なかった範囲だけを再試行して修正。切り分けと測定は `REPORT_APPENDIX_1819.md`。

## 12. #1679: loop 外 break・undeclared label の制御構造復元 (測定 commit: 98c5f8ca)

- 結論: loop 外の `break -> 0x<VA>` は、飛び先の注釈 `// 0x<VA>` が同じ関数内にあるものだけ `goto lab_0x<VA>` に直す (`retdec_gotofix.py`)。機械的な `break` 書換えは採らない。
- 測定値・方式・未検証は付録 `REPORT_APPENDIX_1679.md` が正本。27 件の原因は付録 `REPORT_APPENDIX_4393.md` (#4393)。既定段の特定は `REPORT_APPENDIX_5743.md` (#5743): 注釈が戻るのは計 5 組 (`EmptyStmtOptimizer`・`WhileTrueToWhileCondOptimizer` のどちらか単独 disable で 2 組、両方 disable で 3 組)。付録 §4b: ヘッダ名 32 種の全 disable で 12 組が戻り、1-minimal は VarDefStmtOptimizer 単独で 11 組・VarDef + WhileTrueToWhileCond で 1 組 (母集団 32 種の中での結果。残り 16 種は未測定)。VarDef 単独 disable では `not in loop` の件数は減らない。0x683120 (付録 §4c): 注釈は VarDef 単独で戻るが、`not in loop` を消すのは WhileTrueToWhileCond 単独 (段が一致しない)。引数・代入・初期化の `L"..."` 型不一致は #2071 で修復 (測定は付録 `REPORT_APPENDIX_2071.md`)。残る 8 件のうち struct 代入・member 参照の 5 件は #2853 (HB-H47) で `retdec_repair.py --struct` により修復 (測定は付録 `REPORT_APPENDIX_2853.md`)。未宣言 identifier 2 件と整数リテラル 1 件は直さない (同付録 §2)。

## 13. #1822: exit 0 ファイルの wasm link と採用方式 (測定 commit: 7d15ceab)

- 結論: **採用方式は x64c (`x64c_wrapper.py`)**。RetDec 経路は batch 間でグローバル名 `g*` が衝突し wasm link できない。測定値・手順・未検証項目の正本は付録 `REPORT_APPENDIX_1822.md`。
- 未検証: wasm の実行 (bit 一致)・CreatePlugInstance 到達 (#829)。

## 14. #829: x64c wasm build と CreatePlugInstance 入場 (測定 commit: a55fd489)

- 結論: **x64c の wasm build は両 block で exit 0** (未解決 import `ott_*` 3 件を許容したリンク成功。rt は非リンク)。**CreatePlugInstance (VA 0x86ab10) への入場を実測で確認** (`[cpi] enter 0x86ab10`)。入場後は host 引数が無く最初の間接 call で停止するため、完走は未検証。詳細は付録 `REPORT_APPENDIX_829.md`。
- 既知類型との関係: 該当なし (停止は host 未構成による実行時 trap)。検証起点: `origin/main` @ `9b352bd7`。測定 commit: `a55fd489`。`a55fd489` から検証 HEAD までの差分は `cpi_reach.mjs` のヘッダコメント 1 行のみ (判定ロジック不変。出力は付録 §6)。

| 段 (block19091 / block23676) | exit | 秒 | load (1 分値・開始→終了) | 並列 |
|---|---|---|---|---|
| x64c 生成 | 0 / 0 | 67 / 67 | 1.13→1.08 / 0.21→0.76 | 1 |
| `emcc -c` | 0 / 0 | 45 / 45 | 0.99→1.04 / 0.76→0.93 | 1 |
| wasm link (43,828,879 B / 43,833,146 B) | 0 / 0 | 11 / 1 | 1.03→1.49 / 0.93→0.93 | 1 |

- 秒は各段 n=1 (単一測定)。変動の min–max は未評価 (付録 §1)。数値の内訳 (C・`.o` のサイズ、unsup 内訳、入場の実測) は付録が正本。
- 到達 (block19091): harness が VA を直接呼ぶ入場 (`_ott_run`)。Wrapper の LoadLibrary → GetProcAddress 経路は通していない。NULL host・ゼロ埋め host の両方で `entered=true`。最初に失敗する関数は `f_77fbb0` の `0x77fbf3` `call qword ptr [rax]` (host 由来の値が無いことが原因と推定。未検証)。NC (別 VA) は `entered=false` (弱い NC)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| CreatePlugInstance の完走・起動経路 (LoadLibrary → GetProcAddress) からの到達・bit 判定 | 完走は未検証。host 再構成と停止点 (`f_409b70`) は #2653 で実測 (`REPORT_APPENDIX_2653.md`) | #3597 (HB-H51) |
| block23676 の入場 (VA 0x86a970) | #2653 で入場を実測 (`entered=true`・測定 commit `22625fe8c`) | 解決 (#2653) |
