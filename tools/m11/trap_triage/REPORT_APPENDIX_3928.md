# REPORT_APPENDIX_3928 — #3928 (M11-28): unit 144 の trap と UniqueString (4136a0) の deref 脱落

既知類型との関係: D4 (DEFECTS.md) の再発 (UniqueString 系 `function_4136a0` の `*s` 1 段 deref 脱落)。該当 ID は D4 のみ。

> 親 #3643 (M11-26)・#3592 (M11-24)・#2521 の経路の続き。正本は本付録 (REPORT_APPENDIX_2521 §9.4〜§9.5 の続き)。

**結論 (部分達成)**: lift 版 `function_4136a0` (UniqueString 系) は、`mov rax,[s]` (= `*s`) の 1 段 deref を落としている (D4 (DEFECTS.md) 同型・`417b70`・`412d60` と同じ類型)。これを C 転記 (`M11_FIX_4136A0=1`) すると unit 144 (`0x25c540`) は trap → ok になる。一方、unit 158 (`0x26d1a0`) が ok → oom (halt0) に回帰する。既定 OFF のまま残す。受入 1・2 (0x6c の出所・[0x64] の書込み元) は未特定。e2e は未実測。

## 測定条件

- 測定 commit: `2267e738e` (コード変更の最後の commit。`git diff 2267e738e HEAD -- tools/m11 ':!tools/m11/trap_triage'` の出力は 0 行)。基点 `549edb5ea` (origin/main)。
- 素材: `work-m11` (展開先 `tools/m11/work`)・`fl-win64` の `extracted/block00031_PE.bin` (`$RUNNER_TEMP/win64`)・emsdk (`[EMSDK]`)。
- IR: `bash m11_gen_ir2.sh` (41 s)。`ir_sha256` 生成直後 `597757f4…` (#3643 と同じ)。build 後 `362e47a9…`。
- survey は直列 1 本、各条件 n=1。`node m11_survey.mjs` は約 12 s。build は `rm -f work/obj/ov.o` の後に実行 (約 22 s)。uptime load 0.8〜1.2 (1 分値)。

## 実測

| 条件 (HEAD `2267e738e`) | ok / trap / miss / noproc | unit 144 (`0x25c540`) | OFF との unit 差 |
|---|---|---|---|
| OFF (既定 `M11_FIX_4136A0=0`) | 873 / 21 / 47 / 1 | trap (memory access out of bounds) | — |
| `M11_FIX_4136A0=1` | 873 / 21 / 47 / 1 | **ok** | 2 件: 144 trap→ok、**158 ok→oom (halt0->longjmp)** |

参考 (同じ検証の途中で取った値。`M11_FIX_50A830` の行は基点 commit `549edb5ea` (検証は `git worktree add --detach <dir>/work/wt_base 549edb5ea` で同 commit を展開して実行。測定時の作業ツリーの未コミット変更の有無は記録が無く未確認)、組合せ 2 行は測定 commit `2267e738e` と同じコード。`git diff 549edb5ea 2267e738e -- tools/m11` は `m11_build.sh` の CF・stamp と `m11_ov.c` の `4136a0` 転記だけ):

| 条件 | ok / trap / miss / noproc | OFF との unit 差 |
|---|---|---|
| `M11_FIX_50A830=1` (既存の list Add 転記) | 873 / 21 / 47 / 1 | 0 件 (144 は trap のまま) |
| `M11_FIX_4136A0=1 M11_OV_414AD0=1` | 873 / 21 / 47 / 1 | 2 件 (144・158 は上と同じ) |
| `M11_FIX_4136A0=1 M11_FIX_652500=1` | 873 / 21 / 47 / 1 | 3 件 (144 ok・158 oom・895 halt0→memory access out of bounds) |

- 既定 OFF の survey は #3643 (873/21/47/1・unit 144 trap) と一致。
- 158 の回帰は `414ad0` と `652500` の deref 補正では消えない。

## 転記の内容 (`m11_ov.c` `function_4136a0`、`M11_FIX_4136A0` で有効)

```c
u64 p = Q(s);                       /* lift 版は *s を落とし s を文字列ポインタとして読んでいた */
if (p == 0) return 0;
if (D(p - 8) == 1) return p;        /* refcnt (データ -8) */
u64 np = function_412c20((u64)D(p - 4));   /* 長さ (データ -4) */
function_409c80(p, np, (u64)(long long)(int)(D(p - 4) * 2u));
function_412d60(s, 0);              /* *s := 0 と旧 p の解放 */
Q(s) = np;
return np;
```

- lift 版との比較: IR 4136a0 は `arg1` を文字列ポインタとして refcnt (`arg1-8`)・長さ (`arg1-4`)・copy 元 (`409c80(arg1, …)`) に使い、`store … [arg1]` (= `*s := 新ポインタ`) だけは PPointer として扱う。RetDec の deref 脱落の典型 (`417b70`・`412d60` の C 注記と同型)。
- 呼出し元 `413760` (`call 4136a0; ret`) と `414bb0`・`414c70`・`43c4c0` は、dest を PPointer (変数のアドレス) として渡す。`43c4c0` の dest は `653660` の stack 変数 (`stack_var_-64`) で、`414c70` 経由で `4136a0` に届く。

## unit 144 と unit 158 (FIX=1)

- 144: FIX 版では `4136a0` の入口で `s < 0x10000` の呼出しが無かった (一時 trace・削除済み)。OFF の lift 版で `412d60` に渡る `0x6c` は、FIX 版では経路に現れない。`0x6c` は nil の object の +0x6c フィールドの番地と読めるが (推定)、その nil の出所は未特定 (受入 1 は未達)。`[0x64]` の書込み元も未特定 (受入 2 は未達)。
- 158: FIX 版で `4136a0` の入口 `s = 0x10aa1428` (スタック上の変数。`653660` 経由の `43c4c0` の dest) の内容が `0x64002e00650068` (UTF-16LE の `"he.d"`)。PPointer としての値ではなく文字列の中身が入っている。その直後に `412c20(len)` へ進み、`len = [p-4]` が巨大で `409730` (エラー経路) → Halt → oom。
- 上の 158 の値から、スタック変数の内容を文字列の中身で上書きした書込みが、`4136a0` より前の `43c4c0`・`414bb0`・`414c70`・`409c80` のどこかにあると推定 (未確定)。書込み元の特定は store watch (`WATCH_ADDR=0x10aa1428`、unit 158) が要る。

## 受入条件 (#3928) の達成状況

| 受入 | 状態 |
|---|---|
| 1. ON で `412d60` に渡る `0x6c` の出所 (nil の object の何か) | **未達** (FIX で 144 の経路が変わり、出所の採取は未実施) |
| 2. `[0x64]` を 1 にする書込み元 | **未達** |
| 3. ON で 144 が ok、survey ok ≥ OFF − 1 | 144 は ok・ok 873 (≥ 872) で数値は満たす。**ただし 158 が oom に回帰**するため、既定 ON 化の根拠にはしない。部分達成 |
| 4. e2e (`m11_e2e.sh`) の rc | **未実測** (lift 全再生成が約 22 分かかる。本 run で時間が足りない) |
| 5. 既定 ON 化の判断 | **PM 判断** (3・4 が満たされた後)。本 PR では既定 OFF のまま |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 158 の回帰 (FIX=1 で oom)。スタック変数への文字列の書込み元 | `M11_FIX_4136A0=1` を既定にできない | #3972 ([M11-29]) |
| 144 の 0x6c (nil 由来) と `[0x64]` の書込み元 (受入 1・2) | unit 144 の trap の原因が未特定 | #3974 ([M11-30]) |
| e2e (`m11_e2e.sh`) の rc と既定 ON 化 (受入 4・5) | 既定 ON 不可 (上 2 件が前提) | #3972 ([M11-29] の受入に移送) |
| unit 895 の変化 (`M11_FIX_4136A0=1 M11_FIX_652500=1` で trap 種別が halt0->longjmp → memory access out of bounds。ラベルは trap のまま) | FIX 併用時の trap 種別の変化。原因は未特定 | #3972 ([M11-29]) へのコメント追記 |
| 補足節の派生 store watch (`work/sw3928.sh`) は未コミットで、再現 script が無い (再実行していない) | 補足節の数値を第三者が再検証できない | #3972 ([M11-29]) の受入に派生 script の commit を追加 |

## 再現手順

- **unit 差の定義**: unit は index `i` (0〜941、計 942)。`M11_SURVEY_UNITS` のラベル (ok/trap/oom/noproc/miss/clobber) と `M11_SURVEY_DETAIL` の trap 種別 (unit `i` の要素の `trap`。ok の unit の要素には無い) の組が、OFF (既定) と条件で異なる `i` の件数。va は unit の仮想アドレス (`0x…`。unit 144 = `0x25c540`、unit 158 = `0x26d1a0`)。
- **手順** (`tools/m11/` で実行。素材 `work-m11`・[EMSDK]・IR が必要):
  1. `bash m11_gen_ir2.sh` (IR 生成・41 s。生成直後の `ir_sha256` (`work/ir_conditions.json`) を控える)
  2. 条件ごとに: `rm -f work/obj/ov.o && env <条件> bash m11_build.sh && M11_SURVEY_UNITS=work/su_<tag>.json M11_SURVEY_DETAIL=work/sd_<tag>.json node m11_survey.mjs` (条件は下の表)
  3. OFF との突合 (`<tag>` は `off` と各条件の tag):

     ```
     python3 - off <tag> <<'EOF'
     import json, sys
     def load(t):
         u = json.load(open(f'work/su_{t}.json'))
         d = {x['i']: x.get('trap') for x in json.load(open(f'work/sd_{t}.json'))}
         return [(u[i], d.get(i)) for i in range(len(u))]
     a, b = load(sys.argv[1]), load(sys.argv[2])
     diff = [i for i in range(len(a)) if a[i] != b[i]]
     print(len(diff), diff)
     EOF
     ```

- **条件表** (tag → 環境変数 → 本文の表の行):

| tag | 環境変数 | 対応する行 |
|---|---|---|
| `off` | (なし。既定) | OFF |
| `f50a830` | `M11_FIX_50A830=1` | 参考行 (基点 `549edb5ea` の detached worktree で `off` と突合する) |
| `f4136` | `M11_FIX_4136A0=1` | `M11_FIX_4136A0=1` の行 |
| `f4136_414ad0` | `M11_FIX_4136A0=1 M11_OV_414AD0=1` | 組合せ 1 (2 件) |
| `f4136_652500` | `M11_FIX_4136A0=1 M11_FIX_652500=1` | 組合せ 2 (3 件) |

- 本文の実測表の「ok / trap / miss / noproc」は各 tag の `M11_SURVEY` JSON (`m11_survey.mjs` の console 出力) の `ok`・`trap`・`miss`・`noproc` から、「OFF との unit 差」の件数は手順 3 の出力の先頭の数から読む。
- 本 run では素材が無く未実行 (`tools/m11/work` が無い)。本節の手順は未検証。

## 補足: unit 158 の store watch (未特定。子 #3972 へ)

- 監視: `trap_triage/store_watch_2408.sh` の派生 (`work/sw3928.sh`、コミットしない。run 部を unit 0〜157 の計装なしにし、unit 158 だけ `_m11_watch_on(1)`)。`WATCH_ADDR=0x10aa1428`、`M11_FIX_4136A0=1`。監視関数は `653660`・`43c4c0`・`414c70`・`414bb0`・`414ad0`・`413760`・`4136a0`・`414850`・`44f5d0`・`43c8f0`・`652500`・`43c5e0`・`6535a0`・`413480`・`44f040`・`43c870`・`43ba70`・`409c80`・`412c20`・`6539e0`・`653f40`・`65c540` (IR)。派生 script は未コミットのため再現コマンドは無い。本節の数値は作成時の実測の転記で、再現は未確認 (#3972 の受入に移す)。
- 結果: unit 158 の `[aw]` は 3 件。いずれも `653660` の入口の 0 初期化 (`0x10aa1428`・`…1430`・`…1438`)。文字列の中身を書いた store は記録されなかった。unit 158 は `halt0` (survey の oom と同じ)。
- 記録されなかった理由 (推定): `409c80` (IR 版の copy) は `__asm_movups` (16 バイト `store i128`) で書くため、store watch の計装 (`store i64`・`store i8` 系) に映らない。copy 先が `0x10aa1428` になる呼出しが、text を書いた候補。`413760` の戻り値 (FIX 版の `4136a0` は `p` を返す) が `s` に一致する経路は未確認。
- 次の一手 (#3972): `409c80` の入口で `dst` が `[WA, WA+32)` と重なる呼出しを記録し、呼出し元 (`43c4c0`・`414bb0`・`414c70` のどれか) と `dst`・`src`・`n` を採る。
