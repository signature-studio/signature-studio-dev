# REPORT_APPENDIX_3928 — #3928 (M11-28): unit 144 の trap と UniqueString (4136a0) の deref 脱落

既知類型との関係: D4 (DEFECTS.md) の再発 (UniqueString 系 `function_4136a0` の `*s` 1 段 deref 脱落)。該当 ID は D4 のみ。

> 親 #3643 (M11-26)・#3592 (M11-24)・#2521 の経路の続き。正本は本付録 (REPORT_APPENDIX_2521 §9.4〜§9.5 の続き)。

**結論 (部分達成)**: lift 版 `function_4136a0` (UniqueString 系) は、`mov rax,[s]` (= `*s`) の 1 段 deref を落としている (D4 (DEFECTS.md) 同型・`417b70`・`412d60` と同じ類型)。これを C 転記 (`M11_FIX_4136A0=1`) すると unit 144 (`0x25c540`) は trap → ok になる。一方、unit 158 (`0x26d1a0`) が ok → oom (halt0) に回帰する。既定 OFF のまま残す。受入 1・2 (0x6c の出所・[0x64] の書込み元) は未特定。e2e は未実測。

## 測定条件

- 測定 commit: `2267e738e` (コード変更の最後の commit。`git diff 2267e738e HEAD -- tools/m11 ':!tools/m11/trap_triage'` の出力は 0 行)。基点 `549edb5ea` (origin/main)。
- 素材: `work-m11` (展開先 `tools/m11/work`)・`fl-win64` の `extracted/block00031_PE.bin` (`$RUNNER_TEMP/win64`)・emsdk (`[EMSDK]`)。
- IR: `bash m11_gen_ir2.sh` (41 s)。`ir_sha256` 生成直後 `597757f4…` (#3643 と同じ)。build 後 `362e47a9…`。
- n=1 の限界: 144 (trap→ok)・158 (ok→oom) の反転は各条件 n=1 に基づく。survey の ok 数は環境で 872〜874 に動く (`tools/m11/REPORT_3520.md`)。
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

- 既定 OFF の survey は #3643 (873/21/47/1・unit 144 trap) と集計値で一致。**unit 単位の突合 (再現手順 3) は未実施** (本 run で `work-m11` が無く survey を再生成できない)。unit 差 0 は未確認。
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

## 補足: unit 158 の store watch (#3972 で再測定)

- 結論: 書込み元は未特定。store 命令の計装 (全 store) と copy (`409c80`) の入口計装の両方で、文字列の書込みが記録されない。書込みは別経路 (`__asm_rep_movsq_memcpy` 等) の疑い。
- 再現: `M11_FIX_4136A0=1` の build は `bash tools/m11/trap_triage/store_watch_3972.sh <tag>` (既定は `WATCH_ADDR=0x10aa1428`・`WATCH_UNIT=158`。`WATCH_ALL=1` で全関数の store を計装)。前提: `work-m11`・`fl-win64`・`[EMSDK]`・`bash m11_gen_ir2.sh` 済み。出力は `work/probe3972/<tag>.err`。
- 測定 (HEAD 時点の commit・1 回ずつ・n=1):

| 条件 | `[aw]` の内訳 | 結果 |
|---|---|---|
| 候補関数のみ計装 (既定) | `653660` の入口 0 初期化 3 件 (`0x10aa1428`・`…1430`・`…1438`) | unit 158 `halt0` |
| `WATCH_ALL=1` (全関数の store) | `653660` の入口 0 初期化 4 件のみ | unit 158 `halt0` |
| `409c80` 入口の計装 (`M11_CP_ALL=1` で全呼出し) | 呼出し 0 件 | unit 158 `halt0` |

- 文字列の書込み (`"he.d"` の 8 バイト) は、上の計装のどれにも映らなかった。`store` 命令・`409c80` の copy のいずれも経由しないことになる。候補は IR の `__asm_rep_movsq_memcpy` (28 箇所)・`__asm_rep_movsb_memcpy` (1 箇所)・`__asm_rep_stosq_memset` (6 箇所) の経路。次の一手として、これらの入口で `dst` が `[WA, WA+32)` と重なる呼出しを記録する (未実施)。
- 旧 (#3928 補足節) の `[aw]` 件数 3 件は、候補計装で再現した。派生 script は本 PR で commit した (`store_watch_3972.sh`・`copy_watch_3972.py`・`watch_copy_3972.c`)。

### #3972 run 2 の実測 (commit `c39ea4679`・n=1)

- IR: `bash m11_gen_ir2.sh` rc 0 (47 s)。素材 `work-m11`・`work-liftdiff`・`toolchain-emsdk`・`toolchain-retdec`・`fl-win64` (`block00031_PE.bin` のみ `$FL_WIN64_DIR/extracted/` = [WIN64]) を展開。
- 再現: `bash trap_triage/store_watch_3972.sh rep1` (`M11_FIX_4136A0=1`・unit 158) で `[aw]` 4 件 (`653660` 入口の 0 初期化 `0x10aa1428`・`…1430`・`…1438`・`…1440`)。前回の 3 件から 1 件増えた (監視対象 `0x10aa1440` を含むため。前回は範囲外)。
- `REP=1` (rep 系 helper 35 箇所の入口計装): unit 158 の `[rp]` は 0 件、`[aw]` は同じ 4 件。結果は halt0。
- 計装の検証: `REP=1` で `WATCH_ADDR=0x10aa1000` (unit 158) と `WATCH_ADDR=0x10000000` (unit 0) の `[rp]` は 0 件。**既知の書込みで `[rp]` が出ることは未確認** (計装が効くかは未検証)。
- 未特定: 文字列 `"he.d"` の書込み元。`store` 命令 (54,041 件・ptr 取りこぼし 0) と `409c80` の copy と rep 系 helper の入口のいずれでも、unit 158 の書込みを捕まえていない。残る候補は SSE 系 helper (`__asm_movdqa`・`__asm_movups` 系 等の関数呼出し) の経路。
- 次の一手: (1) 既知の書込みで `[rp]` が出ることを確かめる計装の検証、(2) SSE 系 helper の入口計装、(3) 書込みが unit 158 の実行中か直前かを切り分ける (`m11_watch_on` の範囲を unit 157 の後から)。

### #3972 run 3: 計装なしの unit 境界サンプリング

- 目的: 計装 (store・copy・rep) に依らず、`0x10aa1428` の 8 バイトが unit の境界でどう変わるかを読むだけで測る。計装 0 の clean build (`M11_FIX_4136A0=1`)。
- 再現: `cd tools/m11 && bash trap_triage/first_write_3972.sh <tag> 0x10aa1428 158` (前提: `work-m11`・`fl-win64`・`[EMSDK]`・`bash m11_gen_ir2.sh` 済み。出力 `work/probe3972/fw_<tag>.txt`)。
- 結果 (n=1): unit 0〜157 の境界で値が変わるのは 0 から別の値への一時変化が多数 (unit 43・45・51 ほか)。unit 156 の出口で `3014aa10 3014aa10` に変わり、unit 157 では変化なし、unit 158 の出口 (`halt0` 後) で `0000000000000000`。`"he.d"` (`0x64002e00650068`) は unit 158 の境界では観測されなかった。
- 解釈: `"he.d"` の書込みは unit 158 の実行中にだけ現れる一時的な値と読める。ただし unit 158 は `halt0` で終わるため、出口の `0` が unit 158 の処理によるか halt 後の後始末かは区別できていない。store 計装も rep 計装も書込みを捕まえていないため、書込み経路は計装の対象外 (未特定)。

### #3972 run 4: call 単位の値変化の検出 (`callchk_3972.sh`)

- 手段: IR の直接 call (`%x = call ... @name(` の形。`llvm.*`・`m11_*` を除く) の直後に `m11_callchk(site)` を入れ、unit 158 の実行だけ、監視番地 `0x10aa1428` の 8 バイトが前回の call から変わったら site を出す (読み取りだけ)。store・copy・rep の計装が映らなかった書込みを、call 境界で拾うための派生。
- 観測の範囲: 正規表現は `tail call` と間接 call (`call ... %fp(`) に一致しない。手元の 3 行の IR で確認し、直接 call だけが入ることを見た。よって `tail call`・間接 call の直後で起きた書込みは観測外 (call 境界で拾えない書込み)。
- 限界: 基準値は unit 158 で最初の計装 call が走った時点の値。それより前の書込みは見えない。
- 再現: `cd tools/m11 && bash trap_triage/callchk_3972.sh <tag>` (前提: `work-m11`・`fl-win64`・`[EMSDK]`・`bash m11_gen_ir2.sh` 済み。出力 `work/probe3972/cc_<tag>.err`・`cc_sites.json`)。
- 測定 (HEAD `callchk` 追加 commit・同じ `callchk_3972.sh` で計装したビルドを 2 回。各 1 回ずつ = 計 2 行):

| ビルド | 変化の件数 | `"he.d"` (`68 00 65 00 2e 00 64 00`) の出現 |
|---|---|---|
| c2 | 7 | 無し |
| c3 | 5 | 有り (`680065002e006400`・site 10499 `function_414c70` の `call function_4133f0` の直後) |

- 読み: 文字列の 8 バイトは `function_414c70` 内の `call function_4133f0` の直後に現れた (c3)。ただし c2 では現れず、同じ script でも site 番号と観測順が変わる。原因は未確定 (run 間の揺れ、または IR 生成の非決定性)。1 回の観測を書込みの確定とはみなさない。同じ入力から同じ IR が出るかは未確認。
- 未確定: `4133f0` 自体の内部のどの store / helper が書いたか。`414c70` の入口でも `"he.d"` の出現を再確認していない。
- 次の一手 (#3972): (1) `4133f0` の入口・出口で同じ監視を入れ、c2/c3 の差 (run 間の揺れ・IR 生成の非決定性) を切り分ける。(2) 書込みの先頭 (`4133f0` の中の helper) を特定する。

### #3972 run 5: 入口計装で `4133f0`・`414c70` を観測 (`entry_3972.sh`)

- 手段: `entry_3972.py` が `function_4133f0` (id=1)・`function_414c70` (id=2) の入口に `m11_wprobe` を入れ、unit 158 の実行だけ引数と監視番地 `0x10aa1428` の 8 バイトを出す (読み取りだけ)。派生 script・計装の C・Python は commit `7f0a63ec3` (`tools/m11/trap_triage/entry_3972.{sh,py,c}`)。
- 再現: `cd tools/m11 && bash trap_triage/entry_3972.sh <tag>` (前提: `work-m11`・`fl-win64`・`[EMSDK]`・`bash m11_gen_ir2.sh` 済み。出力 `work/probe3972/en_<tag>.err`)。
- 測定 (commit `6739a2745`・`M11_FIX_4136A0=1`・unit 158・n=2): IR `m11_gen_ir2.sh` rc 0 (54 s)。`ir_conditions.json` は `ldfix=applied` `450560=applied`・`ir_sha256=e48c31d2…` (生成直後。レビュー run の `af3e9e05…` とは一致しない。再生成ごとの sha 差は未切り分け)。2 回とも同じ結果: `[wp] id=2 n=1 a1=10aa1488 a2=64002e00650068 a3=2539c8 watch=680065002e006400`。`id=1` (`4133f0` の入口) は 0 件。unit 158 は `halt0`。
- callchk (commit `6739a2745`・n=1): `[cc] site=10499 hit=5 old=0000000000000000 new=680065002e006400 -> function_414c70 IR line 121120 call function_4133f0`。
- 読み: `414c70` の入口で既に監視番地は `"he.d"` (UTF-16LE)。書込みは `414c70` の入口より前 (監視 ON 以前の unit 0〜157 を含む) に書かれていた。`m11_watch_on(1)` の直前の値は記録していないため、書込みが unit 158 の中で起きたとは言えない。`4133f0` の入口には届いていない。
- 前回 (run 4) の callchk は c3 で site 10499 (`414c70` 内の `call 4133f0`) を指したが、今回の callchk の再実行 (r4a) でも同じ site 10499 が `"he.d"` を出した。ただし entry 計装では `4133f0` の入口が 0 件なので、site 10499 の値変化は `4133f0` の呼出し以前に起きたものを検出した可能性もある (callchk は call 直後に比べるため)。書込み元は `414c70` の入口より前 (監視 ON 以前を含む) と読む。
- 未確定: `414c70` の呼出し元 (`414c70` を呼ぶ関数) と、入口より前の書込み経路。次の一手: unit 158 の `414c70` 呼出しの直前 (呼出し元の入口) に同じ計装を入れる。

### #3972 run 6: 呼出し元の入口・出口の監視 (`edge_3972.sh`)

- 手段: `edge_3972.py` が `function_43c4c0`・`function_414bb0`・`function_414c70` の入口 (alloca 群の直後) と各 `ret` 直前に `m11_eprobe` を入れ、監視番地の値が変わった点だけを出す (読み取りだけ)。派生は `tools/m11/trap_triage/edge_3972.{sh,py,c}`。
- 再現: `cd tools/m11 && bash trap_triage/edge_3972.sh <tag>` (前提: `work-m11`・`fl-win64`・`[EMSDK]`・`bash m11_gen_ir2.sh` 済み。出力 `work/probe3972/ed_<tag>.err`・`ed_sites.json`)。
- 測定 (n=1・`M11_FIX_4136A0=1`・unit 158): 同じ worktree で `callchk_3972.sh` (r6a) と `edge_3972.sh` (r6e) を続けて実行。
  - r6a (callchk): `[cc] site=10499 hit=5 old=0000000000000000 new=680065002e006400 -> function_414c70 IR line 121120 call function_4133f0`。直前の変化は site 10396 (`413760` の `call 4136a0`)。
  - r6e (edge): 変化点 3 件 (`414bb0` 入口 `0x43c964`・`414bb0` ret `0x2539b0`・`43c4c0` 入口 `0x265c90`)。**`"he.d"` は出ない**。unit 158 は `halt0`。
- 読み: 計装 (入口・出口の読み取り) で観測が変わり、r6a で見えた `"he.d"` が r6e では出なかった。書込みの位置は確定していない。`414c70` の入口 (r6e の計装では `414c70` の入口の値変化は無し) とも食い違うため、計装ごとに IR の配置が変わって観測が動くと推定する (未確認)。
- 結論: 書込み元は未特定。`callchk` の `"he.d"` 検出は計装ごとに再現しない (n=1 の揺れ)。次の一手として、揺れを生む IR の差 (計装の挿入で変わる値・alloca の位置) を切り分けるか、wasm を計装なしで動かせる別の観測 (メモリ dump) に移す必要がある。

## #5093 (M11-32): [0x64] の書込み元の探索 (部分・未達)

- 測定 commit: `59e21b78f` (probe `probe_5093.mjs` と本節を含む PR の tree。build 対象のコードは `2e3c6d554` と同一: `git diff 2e3c6d554 59e21b78f -- tools/m11` は `probe_5093.mjs` と本付録の追加 35 行だけ)。OFF (既定) の build。IR `ir_sha256=d66e24aa…` (gen 直後)・build 後 `64a0e5dc…`。#3643 の `597757f4…` とは IR が違う (再生成の差。未切り分け)。
- survey (OFF・n=1): 873 / 21 / 47 / 1 (ok/trap/miss/noproc)・unit 144 は `memory access out of bounds`。#3643 の集計と一致。
- 順序: unit 0〜143 を順に走らせると unit 114 も trap し、unit 144 の trap は 0〜143 の実行後の状態に依る。unit 144 を単独で走らせると trap しない (probe の順序依存)。
- unit 144 の trace (順次実行後): `[m11][icall] 0x25c540` → `[m11][UStrAsg] dest=0x10aa13b8 src=0x6c old=0x0` → trap。trap の wasm 関数は `407e20`←`409440`←`412d60`←`4136a0`←`413760`←`414bb0`←`414c70`←`43c4c0`←`653660` (`m11_wasmnames.py`)。
- `UStrAsg` (C 転記 `function_4133f0`) は `src≠0` かつ `[src-8]≥0` のとき `[src-8]` を +1 する。よって `src=0x6c` なら `[0x64]` 0→1 が期待される。
- **未解決 (矛盾)**: 上の呼出しの後、`[0x64]` は trap 後も 0 のまま読める (`probe_5093.mjs`)。`UStrAsg` の +1 が実行されていないか、trap が +1 より前で起きているかを切り分けていない。よって「`UStrAsg` が `[0x64]` の書込み元」とは確定できない。
- `[0x60,0x80)` の store 計装 (IR store・rep/copy) が 0 件だった既存結果と、C 転記の `UStrAsg` 内の書込みの関係は未検証 (C 側の書込みは IR store 計装の対象外)。
- 次の一手: (1) `function_4133f0` の入口・+1 の直後に `D(0x64)` を読む一時 trace を入れ、+1 が走るかを確かめる (probe 派生はコミットしない)。(2) `src=0x6c` を渡す呼出し元 (`43c4c0`→`414c70`→`414bb0`→`413760`→`4136a0` の経路) の引数を確かめる。

## #5329 (M11-32 受入 1): 入口計装を `43c4c0`・`414bb0` に広げた測定 (未達)

- 測定 commit: `82aca9fcc` (`entry_3972.py` に `function_43c4c0` (id=3)・`function_414bb0` (id=4) の入口計装を追加)。`git diff b912d309f 82aca9fcc -- tools/m11` は `entry_3972.py` の追加のみ。
- 条件: `M11_FIX_4136A0=1`・unit 158・n=1・`entry_3972.sh r3` (70 s・rc 0)。`r2` と同じ結果を再現。
- 監視番地 `0x10aa1428` の値 (入口時点):
  - unit 158 開始 (監視 ON 後): `414bb0` 入口 `1814aa10…`・`9814aa10…` (監視 ON 直後)
  - `43c4c0` 入口: `4420000000000000`
  - `414c70` 入口: `680065002e006400` (`"he.d"`)
  - `414bb0` 入口 (2 回目): `680065002e006400`
- 結論: `"he.d"` は `43c4c0` の入口 (`4420…`) と `414c70` の入口 (`"he.d"`) の間で書かれた。`43c4c0` の IR 本体は `414c70` を直接 1 回呼ぶ (IR の grep で確認)。
- 未確認: (a) 書込みが `43c4c0` の本体の中か、その下の呼出し先の中か。(b) `43c4c0` 本体内の呼出し順 (`414850`・`44f5d0`・`414ec0`・`409c80`・`413760`・`413680`・`4133f0`・`412d60` などのうち、どれが `414c70` より前か)。IR の grep は呼出しの有無だけを見ており、順序は見ていない。(c) 書込み元の関数・命令。
- 次の一手: `43c4c0` 本体の各 call の直前・直後で監視番地を読む計装 (読み取りのみ) を入れ、`4420…` から `"he.d"` に変わった call を二分探索する。
