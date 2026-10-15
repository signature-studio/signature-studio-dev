# REPORT 付録 (#4889 KH-128): Delay の `FUN_180fbc1f4` 呼出し 2 件の引数を機械語で確定し規則化

親 #4836 (KH-119) の分割 C。census の正本は `REPORT_APPENDIX_3800.md` §10-7u。本付録が本件の正本。

#### 10-7w. #4889 (KH-128): `FUN_180fbc1f4` の呼出し 2 件 (C 1082・1088) の引数源を xmm0 (float) と確定し規則化

- **結論**: 呼出し 2 件の引数は xmm0 (float)。符号分岐の係数 (`±0.16609640419483185`) を含む式を規則化した。Delay の emcc 引数数不一致は **79 → 77** (−2。規則 5 件・件数はすべて 1)。
- **前提の訂正**: 旧 issue 本文の「rcx 源」は誤り (#4889 のコメント・PM 訂正どおり)。`FUN_180fbc1f4` の入力は xmm0、戻り値も xmm0。
- **受入 1' (呼出し 2 件の xmm0 源を機械語で確定)**: **一部達成**。引数源が xmm0 (`movaps xmm0,xmm6` の直後に call) であることは下表の機械語で確定。符号分岐の対応は未確定: `ucomiss xmm6,xmm0` の比較対象 xmm0 が 0.0 であることを示す命令 (`xorps xmm0,xmm0` 等) と VA を、本 run では確認できなかった (`plugins-kilohearts` が無く逆アセンブル不可)。受入 1' の符号部分を満たさない範囲は、呼出し 2 件の符号 (±0.166) の選択。未確定の扱いは子 #5402 [KH-161] に移す。
  - 符号分岐の向き (xmm0 = 0.0 を前提とした読み): `ucomiss xmm6,xmm0` の後の `jae 1802eded3` は xmm6 ≥ xmm0 (順序付き) で飛ぶ。これは C の `if (0.0 <= fVar26 * _DAT_1814dd30c * p24)` の真の枝 (C 1082) に対応する。前提の xmm0 = 0.0 は未確認。
  - 行番号: issue 本文の emcc 行 1081・1087 と本付録の C 行 1082・1088 は、同じ 2 件の呼出しを指す。1 行ずれの基準差。本 run では行番号の基準を再確認できていない。
- **受入 2' (`ABI['delay']` に規則 1 件 = 呼出し 1 件・件数 1 を assert)**: **達成** (5 件とも件数 1 で通過。呼出し 2 件・宣言 1 件・本体 2 件を含む)。
- **受入 3 (Gain / Haas / Gate の生成 C と sigs.json が origin/main と cmp 0 差分)**: **達成** (gain・haas・gate の `.c`・`sigs.json`・`globals.json` 計 9 本、差分 0)。
- **受入 4' (残件数を書く。基準は現在値)**: **一部達成**。下表の census は origin/main `3dc77c71a` (本 run の実測 79) を基準にした。issue 指定の基準 82 (`REPORT_APPENDIX_4883.md`) との差 3 件の原因は**未確定** (#4883 以降の main 変更の可能性。確定はしていない)。未確定の扱いは子 #5402 [KH-161] に移す。
- **数値の扱い**: emcc 通過は値の正しさを示さない。Delay の wasm は成立せず (引数数不一致 77 件が残る)、1000 trial は未実施 (#3073 [KH-41] が担当・open)。

**測定 commit** (コードを変えた最後の commit): 本 PR の commit (`ghidra_route/patches.py`・`docs/DOC_MAP.md`・本付録)。`git diff <測定 commit> HEAD -- tools/targets/kilohearts/ghidra_route` の出力は 0 行。
**検証起点** (baseline): origin/main `3dc77c71a`。

**機械語の根拠 (capstone・`HeartCore.core_64`)**

| 項目 | 機械語 (VA) | 結論 |
|---|---|---|
| 呼出元 1082 (X ≥ 0 枝) | `1802ede08` `mulss xmm6,[1814dd30c]` (=48.0) → `mulss xmm6,[rax+0x24]` → `1802ede18` `ucomiss xmm6,xmm0` / `jae 1802eded3` → `mulss xmm6,[181563050]` (= −0.16609640419483185) → `movaps xmm0,xmm6` → `call 180fbc1f4` (1802edede) | 引数 xmm0 = X·48·p24·(−0.166)。C の if (`0.0 <= X`) の真の枝に対応 |
| 呼出元 1088 (X < 0 枝) | `1802ede21` `mulss xmm6,[1813a9e38]` (= +0.16609640419483185) → `movaps xmm0,xmm6` → `call 180fbc1f4` (1802ede2c) | 引数 xmm0 = X·48·p24·(+0.166)。C の else 枝に対応 |
| callee `FUN_180fbc1f4` | `movss [rsp+8],xmm0` で入力を読む (冒頭 180fbc1f4)。戻り値は `xmm6` 経由で xmm0 | 宣言 `float FUN_180fbc1f4(float)`。`param_1` を bits 変換せず `fVar4` に入れ、戻り値は `fVar4` |
| 掛け算の順 | 機械語 `xmm6 = fVar26·48` の後に `p24` を掛け、符号の係数を最後に掛ける | 規則の式 `fVar26 * _DAT_1814dd30c * p24 * K` と左結合で一致 |

**census (emcc の排他的集計・`emcc_census.py`・n=1)**

| 区分 | origin/main `3dc77c71a` (baseline) | 本 PR |
|---|---|---|
| 128bit レーン型 | 166 | 166 |
| **引数数不一致** | **79** | **77** |
| 演算・代入・ポインタの型不一致 | 90 | 90 |
| 合計 (emcc error 行) | 335 | 333 |

**実測**: `gtype_census.sh` の前処理 (`analyzeHeadless` DecompEach 139 関数) 約 50 s・`ghidra_to_c.py delay` 数秒・`emcc -c` (delay) 16.0 s (real)。素材・環境は runner の `$RUNNER_TEMP/kh` (repo 外)。

**Gain / Haas / Gate の不変 (受入 3)**: 同じ Ghidra 出力 (`gtype/out`) から、origin/main の `ghidra_route` (`git archive`) と本 PR の `ghidra_route` で `ghidra_to_c.py` を実行し、生成物 9 本を `cmp`。差分 0。

**未解決 (起票先付き)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 引数数不一致の残り 6 件 (`FUN_180fb5dd0` 2・`FUN_180fd5bf4` 2・`FUN_180fd8988` 2) | Delay の emcc 不通過 (wasm 不成立) | #4917 [KH-135] (既存 open) |
| 引数数不一致の残り 71 件 (#4917 の 6 件を除く) | Delay の emcc 不通過 (wasm 不成立) | #5401 [KH-160] (本 PR で起票) |
| 基準 82 (`REPORT_APPENDIX_4883.md`) と 79 (origin/main `3dc77c71a`) の差 3 件・原因未確定 | census の基準 | #5402 [KH-161] (本 PR で起票) |
| 符号分岐の対応 (1802ede18 `ucomiss xmm6,xmm0` の xmm0 = 0.0 を示す命令と VA) が未確定 | 呼出し 2 件の符号 (±0.166) の根拠 | #5402 [KH-161] (本 PR で起票) |
| 1940 行 (`FUN_1802ed550` 内 `FUN_180fbc1f4(_DAT_1813f9f5c / …)`) は宣言変更で float 引数として型が通る。規則化はしていない (件数は変わらず) | 呼出しの値は機械語 (1802ed584 直前 `divss`) と読めるが、突合は未実施 | #3073 [KH-41] (open・既存。1000 trial で判定) |
| Delay の数値未検証 (1000 trial・ネガコン・第二 oracle) | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] (open・既存) |
