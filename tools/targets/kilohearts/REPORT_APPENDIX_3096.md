# REPORT 付録 (#3096 KH-44): Delay の emcc 残件 — `code` 関数ポインタ化

`REPORT_APPENDIX.md` の 250 行上限のため分割した (前節の正本は `REPORT_APPENDIX.md` §10-7q ④・§10-7p-3 の census)。

#### 10-7t. #3096 (KH-44) run: `code` を関数ポインタにして間接呼出し 21 件を解消 (部分・emcc 577 → 556)
- 結論: `code` 型の間接呼出し 21 件 (`called object type 'code'`) を 0 件にした (測定 commit `26b003692`)。Delay の emcc 残件は 577 → **556** 件。残りは引数過不足 108・型不一致 187・未定義 identifier 17・未関数化 callee 5・その他 2 で、子 issue に分けた (下表)。
- 原因: `ghidra_shim.h` の `typedef void code;` のため、`(code *)swi(3)` の戻り値を `(*pcVar)()` で呼ぶ箇所が「void は関数でない」で落ちていた (21 件・`pcVar` は `swi(3)` (未宣言の疑似関数) の直後に来る。`swi` 側は #3095 [KH-43] の範囲)。
- 変更 (1 行): `typedef void code;` → `typedef longlong (*code)();`。
  - 戻り値を `longlong` にしたのは、`lVar4 = (*pcVar2)();` の代入を「void を代入」の型エラーにしないため。
  - 引数なし `()` (非プロトタイプ) にしたのは、`(*pcVar)(x)` の引数付き間接呼出し 4 件が `(void)` 形では `too many arguments` になるため (試行で確認: `(void)` は 21 件が引数数不一致に移るだけだった)。

**① 環境 (repo 外で作業。`work/` は使わない)**
- 素材 `plugins-kilohearts` (`tar --zstd --occurrence=1 -xf` で `Kilohearts Offline Installer.zip` 3,833,108,300 B のみ取り出し → `payload.dat` → `windows.zip/1ccb1df8…` → `HeartCore.core_64` 76,642,304 B)。
- [GHIDRA] 12.1.4 (zip 569,649,598 B・sha256 `ddac49f9…d2db` 一致・repo 外に展開)、[JDK21] `temurin-21-jdk-amd64`、[EMSDK] emcc 6.0.12。
- `fl-win64` は本 run で未使用 (Delay の emcc 経路に不要)。
- decompile: lift 141 件 → **141/141 OK** (analyzeHeadless wall 34.3 s, n=1)。C 化: `delay.c` 7,248 行。

**② Delay の census (`emcc -c -ferror-limit=0`・`emcc_census.py`・測定 commit `26b003692`)**

| 分類 (census 行) | 前 (変更前の shim・同じ converter = origin/main `26222d139`) | 後 (`26b003692`) | 起票先 |
|---|---|---|---|
| 未関数化 callee | 5 | 5 | #3802 [KH-66] |
| レーン型 (`undefined1[N]`・メンバ参照) | 191 | 191 | #3094 [KH-42] |
| 引数数不一致 | 108 | 108 | #3800 [KH-64] |
| SIMD・AVX・swi 疑似関数 | 46 | 46 | #3095 [KH-43] |
| code 型の間接呼出し | 21 | **0** | 本 PR で解消 |
| 未定義 identifier (`DAT_`・`uRam`・`LAB_`・`PTR__`) | 17 | 17 | #3802 [KH-66] |
| 演算・代入・ポインタの型不一致 | 187 | 187 | #3801 [KH-65] |
| その他 (`FUN_18004cf20` の conflicting types) | 2 | 2 | #3802 [KH-66] |
| **合計** | **577** | **556** | |

- 差分の確認: 前後の emcc log の差は `called object type 'code'` 21 行の消滅のみ (`diff` で確認。他の行の増減 0)。

**③ 回帰 (gain / haas / gate)**
- decompile 10/10 OK (run_all.sh の 10 関数 = gain・haas・gate の lift)。生成 C に `code` の出現 0 (`grep -w code`)。
- `emcc -c` (build_cmp.sh と同じ `-w -O1 -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=incompatible-pointer-types-discards-qualifiers`) の `.o` を **旧 shim (`typedef void code;`) と新 shim で作り比べ、3 本とも byte 一致** (`cmp`)。エラーログも 3 本とも一致 (gain 0・haas 0・gate 0)。
- したがって §10-7q ⑤ の Gain/Haas/Gate 1000/1000 bit-exact の結果は、本変更で変わらない (生成物が同一)。1000 trial 突合は本 run で再実行していない。

**④ 残件の内訳と子 issue (本 PR のあと、`親: #3096`)**
- 子は 1 PR 3 件の上限に合わせ、残件を 3 つに分けた (#3800・#3801・#3802。親は #3096)。件数はすべて上の census (`26b003692`) の値。
- ① #3800 [KH-64]: 引数過不足 108 件 (`too few arguments` 84・`too many` 24): 呼出元の機械語から引数・戻り値を確定して `patches.py` の ABI 表へ。
- ② #3801 [KH-65]: 型不一致・ポインタ型 187 件 (`invalid operands` 52+16+11 ほか・`assigning to 'V128'` 24・`int-conversion` 13+9 ほか)。issue 本文の 248 は旧値 (#3094・#3095 の分を含む旧分類)。
- ③ #3802 [KH-66]: 未定義 identifier 17 件 (`DAT_` 10・`uRam` 5・`LAB_` 1・`PTR__` 1)・未関数化 callee 5 件・その他 2 件 (`conflicting types`)。

**未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 引数過不足 108 件 | Delay の emcc が通らない | #3800 [KH-64] (`親: #3096`) |
| 型不一致・ポインタ型 187 件 | 同上 | #3801 [KH-65] (`親: #3096`) |
| 未定義 identifier 17・未関数化 callee 5・その他 2 | 同上 | #3802 [KH-66] (`親: #3096`) |
| レーン型 191 件 | 同上 | #3094 [KH-42] (既存) |
| SIMD・AVX・swi 疑似関数 46 件 | 同上 | #3095 [KH-43] (既存) |
| Delay の 1000 trial 突合・ネガコン | emcc 未通過のため未実施 | #3073 [KH-41] (既存) |
