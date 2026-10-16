# M11 LB 依存 unit 差 8 件の切り分け (#3325・親 #3296・祖父 #3229)

測定主体: 本 PR の作業 runner (2026-10-15 UTC)。素材は `fl-win64` (`extracted/block00031_PE.bin` 22,227,016 B のみ展開)・`tools/m11/work/` (work-m11 展開済み・lift 成果物あり)・`[EMSDK]` (toolchain-emsdk 既存・`docs/REFERENCES.md`)。
測定 commit: `d6b7b27c` (コードを変えた最後の commit。計測 env の既定は 0)。`git diff d6b7b27c HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` の出力は空。
既知類型との関係: 該当なし (類型の新規候補は §5)。

## 1. 結論

- **#3296 の源修正の前提が build に効いていない (HEAD `d6b7b27c` の計測 build での観測)。** `function_412770` の実行体は IR 本体ではなく、`tools/m11/m11_ov.c` の手書き C 版 (`function_412770(void* ctx)`・longjmp 相当で `m11_throw_dllmain_done` を投げる) である。IR 本体 (`ptr null` の rep movsq を含む) は両 LB とも観測 probe が 0 回で、実行された証拠は無い (§2・§2-1)。
- したがって `REPORT_N403.md` §7 (#3229 節) と `#3296` 本文の推定「arg1 先が 0 のため address 0 を読む」は、この実行経路では成立しない (棄却)。#3296 の源修正の効果が出ないことは、この構造で説明できる見込み (推定。当時の build との食い違いは §2-1 の注記)。
- kind 差 8 件は HEAD (`d6b7b27c`・既定フラグ) でも再現した (§3)。原因の分岐は未特定。`function_4128b0` の Halt 分岐の入口まで絞れた (§4)。
- 未達の受入条件 (分岐値の呼出し時点の実測・kind 差 0・新類型の行案) は子 issue `[M11-N182]` へ移した (§6)。

## 2. function_412770 の arg1 観測 (受入 1)

計測: `M11_INSTR_412770=1 M11_TOLERANT_ERR=1` で build し、寛容起動 (942 unit) を LB=0 / LB=0x10000 で各 1 回。`m11_post.py` が IR 本体を `function_412770__lifted` に改名し、観測 wrapper `function_412770` (weak) を置く。

| LB | 観測行 `[m11][412770]` | unit 40 の結果 (C 版を通る経路か) |
|---|---|---|
| 0 | 0 件 | ok (trap なし) |
| 0x10000 | 0 件 | halt0 (C 版の `m11_throw_dllmain_done` まで到達) |

- 観測 wrapper が 0 回。IR 本体の arg1 (`ptr %arg1`) と `[arg1+0]` は実行時に存在しない。
- LB=0x10000 の unit 40 の trap スタック (wasm 関数名は同一 build で付与): `m11_throw_dllmain_done` ← `function_412770` (C 版・`m11_ov.c` の `EM_JS` 呼出し元) ← `function_4128b0__lifted`。IR の本体は `m11_throw` を直接呼ばないので、この frame は C 版である。
- 推定の棄却: 「寛容起動の arg1 先が 0 のため、`[arg1+0]` が address 0」(`REPORT_N403.md` §7 の候補 (b) の読み替え。`#3296` 本文の推定) は、この経路 (C 版が arg1 を読まない) では起きない。

### 2-1 観測 0 回の根拠と未実施の対照

- 観測 probe は `m11_post.py` の `weaken` が作る weak wrapper に入る (`M11_INSTR_412770=1` のときだけ)。同名の強定義 `function_412770(void* ctx)` が `tools/m11/m11_ov.c` 443 行に、ゲート無しで置かれている。リンクでは強定義が選ばれ、weak 側 (probe を含む wrapper と IR 本体) は使われない。よって観測 0 回は、この build 配線から導かれる。
- 同じ計測 build 内の照合: unit 40 (LB=0x10000) は `function_412770` に到達する (§4 の trap スタックは C 版の `m11_throw_dllmain_done` まで出る) のに、観測行は 0 件。probe の wrapper が使われていれば 1 件出るはずで、これは probe が使われていない直接の証拠。
- **未実施 (ネガコン)**: 強定義を外す (または IR 側を選ばせる) build で probe が発火することの確認は行っていない。本 runner に `tools/m11/work/` (lift 成果物) が無く、build の再生成が本 fix の時間内に収まらないため。→ §6 未解決。
- **当時の build との食い違い (未解決)**: `trap_triage/REPORT_1080.md` (c4e93550) は、IR 本体を差し替えた patch A/B で unit 304・555 の kind と trap 番地が変わったと報告している。`m11_ov.c` の強定義と `m11_post.py` の weak 化は c4e93550 にも既にあるため、弱定義が破棄される構造とは両立しない。当時の build で IR 本体が使われたか、別要因かは未確定。したがって「観測 0 回・IR 本体は使われない」は HEAD の build に限る。

## 3. kind 差 8 件 (受入 3 の現状)

d6b7b27c・既定フラグ (計測 OFF) で `m11_lb_unit_diff.py` の kind 差 = **8**。unit 一覧 (index・VA・LB=0 / LB=0x10000 の結果) は `tools/m11/REPORT_N403.md` §6-2 と同一のため、本書には再掲しない (正本は REPORT_N403 §6-2)。

## 4. trap 位置 (受入 2)

wasm 関数 index は **build ごとに変わる** (例: index 3149 は LB=0x10000 build では `function_535240`、LB=0 build では `function_535c11`)。各 build の `work/m11_boot.cjs.wasm` で `python3 tools/m11/m11_wasmnames.py <wasm> <idx>` して名前を付けた。

LB=0 側 (`M11_TOLERANT_STACK=...` の trap スタック):

| unit | 直接の trap 関数 (offset) | 呼出し元 |
|---|---|---|
| 291・296・304・555 | `function_535c11` (0x194cbb 系) | `function_4fad10` ← `function_4fb910` ← unit 関数 |
| 745 | `function_407e20__lifted` (FastMM_FreeMem 本体・0x13d5d6) | `function_407e20` (probe wrapper) ← `function_409440__lifted` ← `function_409440` (FreeMem wrapper) |

LB=0x10000 側:

| unit | 直接の trap 関数 | 呼出し元 |
|---|---|---|
| 153 | `function_412e40` (0x6b739) | `function_664fd0` ← `function_665b90` |
| 158 | `function_412c20` (0x14cc66) | `function_4136a0` ← `function_413760` ← `function_414bb0` ← `function_653660` |
| 40 | (halt0) `function_412770` C 版 | `function_4128b0__lifted` |

- unit 153・158 の呼出し鎖は `tools/m11/REPORT_N403.md` §5 (表の 153・158 行) と同値。正本は REPORT_N403 §5 で、本書の表は受入 2 のため残す。

**未特定:** address 0 を読む命令 (受入 2 の後半)。trap の wasm offset から IR 命令への対応は未実施。

### 4-1 function_4128b0 の Halt 分岐 (IR・LB=0 build の定数)

`function_4128b0__lifted` (IR) で `function_412770` (C 版) へ進む条件:

1. `load i64 [0xFA5008]` (= 16404488) が 0 でないこと (LB=0x10000 では +0x10000)。**誤り。§9 参照** (この条件は 412770 の呼出しを守らない。守るのは 2 と 3)。
2. `load i64 [18787760]` が 0 でないこと。
3. `GetCurrentThreadId() == load i32 [18787804]` であること。
4. 通ると `store i64 0 → [18787760]` の後に `function_412770(18787752)` を呼ぶ。

unit 40 の前後 (u32 の下位 4B) を LB 別に読んだ値 (`M11_TOLERANT_PEEK`・`M11_TOLERANT_PEEK_UNITS=40`):

| LB | before | after | kind |
|---|---|---|---|
| 0 | `[18787752]=0 [18787760]=0 [18787804]=0` | 同じ | ok |
| 0x10000 | `[18853288]=0 [18853296]=0 [18853340]=0` | 同じ | halt0 |

- 4 は関数内で `[18787760]` を 0 に戻すため、unit 前後の読みでは条件を判定できない。**呼出し時点** (`function_4128b0` の入口と分岐直前) の値が要る → 子 issue。
- LB 差の候補: 1 の `[0xFA5008]` と 3 の `GetCurrentThreadId` 比較。どちらが LB で変わるかは未確定。
- IR 上の行番号: **未取得** (本 runner に `tools/m11/work/` が無い)。3 条件の IR 上の位置は、work-m11 のある run で次の式を実行して確定する (**未実行**): `grep -n "function_4128b0__lifted\|i64 16404488\|i64 18787760\|i64 18787804" tools/m11/work/boot_final3.ll` (16404488 = 0xFA5008・10 進の番地は未検証)。番号が出るまで、本節は §4 の peek の値だけに基づく。

## 5. 新類型の候補 (docs/DEFECTS.md 用・未確定)

候補 X: 「手書き C 上書き (`m11_ov.c`) が IR 本体より優先され、IR 側の修正が build の実行経路に入らない」。#3296 の源修正がこれに当たる見込み。類型 ID は未付与 (採番と `docs/DEFECTS.md` への登録は PM 判断。本体は編集しない)。行案は `docs/DEFECTS.md` の表の列順に合わせる。

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|---|---|
| (未付与) | ours (build 配線) | 新規 (M11 #3325) | IR 側 (`function_412770` の `ptr null` 読み) を直しても build の実行結果が変わらない。効果が 0 のまま見過ごされる | `m11_post.py` が IR の `define function_*` を weak 化し、`m11_ov.c` の同名の強定義がリンクで選ばれる。IR 本体は使われない | HEAD `d6b7b27c` の計測 build で probe 0 回 (§2・§2-1)。unit 40 の trap は C 版の経路のみ (§4)。kind 差 8 件は残る (§3) | 未確定 (案: 同名の強定義と weak 定義の両方が `nm` に現れる関数を build ごとに列挙し、修正対象の関数が強定義なら FAIL にする。未検証) | 未確定 (案: 修正対象を強定義側に入れるか、強定義を gate で外してから IR 修正を入れる。未検証) |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_4128b0` の 412770 呼出し分岐の値 (呼出し時点・LB 別) | LB=0x10000 の unit 40 の halt0 の原因が未特定 | `[M11-N182]` (子 issue) |
| unit 153・158 の OOB 命令 (wasm offset → IR 命令) と LB=0 側 291・296・304・555・745 の OOB 命令 | kind 差 7 件の原因が未特定 | `[M11-N182]` |
| kind 差 0 (受入 3)。新類型 (§5 の行案) の登録 | #3296・#3325 の受入が未達。登録は PM 判断 | `[M11-N182]`・PM 判断 |
| ネガコン (probe の発火対照) が未実施 (§2-1) | 観測 0 回の根拠が build 配線の構造のみ | `[M11-N182]` |
| REPORT_1080 (c4e93550) の IR 差替えによる unit 304・555 の変化と、弱定義が破棄される構造との食い違い (§2-1) | HEAD 以外の build で IR 本体が使われたかが未確定 | `[M11-N182]` |
| IR 上の 3 条件の行番号・grep 式の実行 (§4-1) | 条件の IR 上の位置が未確定 | `[M11-N182]` |
| #3296 / PR #3327 の源修正が build の実行経路に無い (§1・§2) | #3296 の受入「kind 差 0」は源修正では達成できない見込み | PM 判断 (親 #3296 へのコメント) |
| 寛容起動 pin と snapshot 値の差 (数値は REPORT_N403 §6-5 が正本) | REPORT_N403 §6-5 の既存未解決。本件では未確認 | REPORT_N403 §6-6 に残す |

## 7. 再現

- 計測 build: `M11_INSTR_412770=1 M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=40,153,158,291,296,304,555,745 bash tools/m11/m11_lb_tolerant_repro.sh <LB> work/<dir>`
- peek: `M11_TOLERANT_PEEK=<addr,..> M11_TOLERANT_PEEK_UNITS=40 node tools/m11/m11_tolerant.mjs` (build 済みの `work/m11_boot.cjs` を使う。アドレスは LB 分ずらす)
- 既定 (計測 OFF): `bash tools/m11/m11_lb_tolerant_repro.sh 0 work/head_lb0` と `... 0x10000 work/head_lb10000` → `m11_lb_unit_diff.py` で kind_diff 8 (§3)

## 8. function_4128b0 入口の分岐値の観測 (#4457・受入 1 達成・受入 3 達成・受入 2 未達)

測定 commit: `e60c17037` (番地修正 `6136fda91` を含む head。`M11_INSTR_4128B0` 配線は `bcdf045f7`・計測 env の既定は 0)。素材は `fl-win64`・`work-m11`・`toolchain-emsdk` (`[EMSDK]` 6.0.12)。

- **測定 commit 以降の測定対象コード差分** (`git diff bcdf045f7 424a6373b -- tools/m11/m11_ov.c tools/m11/m11_post.py tools/m11/m11_build.sh`。`m11_build.sh` は差分 0):
  ```diff
  -    unsigned long long a1 = R(0xfa5008), a2 = R(0x11dadb0), a3 = R(0x11daddc);
  +    unsigned long long a1 = R(0xfa5008), a2 = R(0x11eadb0), a3 = R(0x11eaddc);
  +            // #4184 (LD-200): POINT は 8 バイト値渡し (x64 rcx = x | y<<32)。下位 32bit が x、上位が y
  ```
  (`m11_ov.c` の番地 2 行と `m11_post.py` の注釈 1 行。`m11_ov.c` の番地修正は既定 OFF の経路を変えない。ON 観測の読み先だけ変わる)
- 本 PR の `tools/m11` 全体の差分 (23 ファイル・+6379/-27) は main 取り込みを含むため、測定対象の差分ではない。
- **再測定 (修正後・本 run)**: 測定 commit は `e60c17037` (番地修正 `6136fda91` を含む head)。素材 `work-m11`・`toolchain-emsdk` を展開して build・寛容起動 (942 unit) を実行した (§8-1・§8-2)。
- **IR の番地確認**: LB=0 の build の IR (`work/m11_fix_on_lb0/boot_final.ll`・post 前) で `inttoptr (i64 16404488)` 5 箇所・`18787760` 2 箇所・`18787804` 1 箇所。LB=0x10000 の IR は +0x10000 (16470024 / 18853296 / 18853340)。番地は正しい。
- **測定対象のコード差分**: `git diff e60c17037 HEAD -- tools/m11/m11_ov.c tools/m11/m11_post.py tools/m11/m11_build.sh` は本節の commit 以降も空 (測定 commit = HEAD のため定義上 0)。`bcdf045f7` からの差分は上記の番地修正と注釈 1 行のみ。

- 観測点: `function_4128b0` の入口 (`m11_post.py` の wrapper + `m11_ov.c` の `m11_4128b0_obs`)。`M11_INSTR_4128B0=1` のときだけ入る。`function_412770` の強定義 (`m11_ov.c`) は観測点にしない (§2)。
- 番地 (LB=0 の番地): `[0xFA5008]` (16404488 = 0xFA5008)・`[0x11EADB0]` (18787760)・`[0x11EADDC]` (18787804, GetCurrentThreadId 比較の相手)。LB=0x10000 は +0x10000 (16470024 / 18853296 / 18853340)。
- **修正 (指摘 1)**: 旧版の C 側は `0x11DADB0` / `0x11DADDC` を読んでいた (10 進 `18787760` と 0x10000 ずれ)。§8-1 の旧値はこの誤った番地の読みで、根拠にならない。番地は `m11_ov.c` 1230・1239 行で `0x11EADB0` / `0x11EADDC` に直した。IR での実在は上の「IR の番地確認」で確認済み。

### 8-1 入口の実測 (計測 ON・修正後の番地・head `e60c17037`)

`M11_TOLERANT_ERR=1` で観測行を取得 (未指定だと `[m11][4128b0]` 行は出ない)。

| LB | 観測 unit (入口の 3 値 `[0xFA5008]` `[0x11EADB0]` `[0x11EADDC]`) |
|---|---|
| 0 | 8 件: 114・245・279・314 (`0xFA5008`=0x1)・509・647・895 (`0x10251780`)・941。全件 `[0x11EADB0]=0`・`[0x11EADDC]=0` |
| 0x10000 | 9 件: 40・114・245・279・314 (`0xFB5008`=0x1)・509・647・895 (`0x10251780`)・941。全件 `[0x11FADB0]=0`・`[0x11FADDC]=0` |

- どの観測 unit でも、分岐 2・3 の値は 0。`0x11EADB0` が非 0 になる経路は、この入口では観測されなかった。
- unit 40 (LB=0x10000) は入口で `[0xFB5008]=0`・分岐 2・3 も 0 だが、trap スタックは `function_4128b0__lifted` → `function_412770` → `m11_throw_dllmain_done` を通る (`M11_TOLERANT_STACK=40`)。IR では `function_412770` の呼出しが 2 箇所 (IR 117917 行: 分岐 2・3 の経路 / 118017 行: `[18852992]` 経路) あり、unit 40 は入口の観測を経ない後者の可能性がある。**未特定** (§8-3)。
- `GetCurrentThreadId` は shim で 1 を返す (`tid=0x1`)。

### 8-2 観測の副作用・kind 差 (修正後の番地・head `e60c17037`)

| 比較 | kind 差 | 差の unit |
|---|---|---|
| 既定 OFF の LB=0 2 回 (run1 vs run2) | 0 | — |
| 既定 OFF の LB=0 vs LB=0x10000 | 8 | 40・153・158・291・296・304・745・895 (§3 と同一) |
| 計測 ON の LB=0 vs LB=0x10000 | 4 | 40・153・158・745 |
| 同 LB 内で OFF vs ON (LB=0) | 3 | 101・304・895 |
| 同 LB 内で OFF vs ON (LB=0x10000) | 3 | 101・291・296 |

- 既定 OFF の LB=0 2 回は kind 差 0 (再現性あり)。既定 OFF の LB 差 8 件は §3 と同一の unit 集合。
- 同 LB 内の OFF vs ON の kind 差 3 件は、観測 (ON) が結果を変えていることを示す。原因 (線形メモリ読み・`fprintf`・link の形) は未切り分け。
- 候補 (未検証): 観測 ON の `fprintf` による shadow stack の汚染。`M11_TRACE_ISOLATE=1` (隔離版) での切り分けは未実施。

### 8-3 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 40 (LB=0x10000) の 412770 への進入経路 (IR 117917 行か 118017 行か。入口の観測に出ない理由) | LB 差の原因が未特定 | 親 #3389 (PM 判断) |
| 同 LB 内の OFF vs ON の kind 差 3 件 (観測の副作用の切り分け: 読みの位置・fprintf・link・`M11_TRACE_ISOLATE=1`) | 入口値を LB 差の根拠に使えない | 親 #3389 (PM 判断) |
| 既定 OFF の LB 差 kind 差 8 件の原因 | 受入 3 は既定 OFF で不変 (達成) だが、8 件の原因は未特定 | 親 #3389 (PM 判断) |

## 9. function_4128b0 の 412770 呼出し分岐の 3 値 (#5666・受入未達・計測は呼出しに届かず)

測定 commit: `775d2cace` (計測 env `M11_INSTR_412BR` の既定は 0。既定 build は変わらない)。素材は `fl-win64`・`work-m11`・`toolchain-emsdk` (`[EMSDK]`)。LB=0 / LB=0x10000 とも寛容起動 942 unit。

- **番地の基点**: 本節の番地は、`m11_ov.c` の `R(rva)` が実行時に `M11_LB_BASE` を加算した後の実アドレス。LB=0x10000 の値は `R(18787504)`=0x11FACB0・`R(18787464)`=0x11FAC88・`R(16404480)`=0xFB5000 (LB=0 の `R` は 0x11EACB0・0x11EAC88・0xFA5000)。
- **`=2`・`=3` の結果は現 commit の code では再現しない (取り消し・再測定待ち)**: `775d2cace` の `m11_post.py` では `=2`・`=3` の分岐が `=1` の `if` の内側 (4 スペース下げ) にあり、`=1` でないと置換が入らない。そのため `=2` では `m11_412770_br2_obs` が一度も呼ばれず、`=3` では gate probe が入らない。下の `=2` の発火行と `=3` の timeout は、この code からは説明できないため根拠にしない。修正は次 commit の `m11_post.py` (分岐を depth 0 へ出した) で行い、`=1`・`=2`・`=3` で挿入される呼出しは合成 IR で確認済み。**実 IR (`boot_final3.ll`) での再測定は未実施** (`work/` 無し・`work-m11`/`toolchain-emsdk` 未展開)。
- `=1` の結果 (発火 0 件) は、ネストの影響を受けない分岐で入っているため 775d2cace の code の結果として有効。head `d16dbb88c` でも reviewer が再測定し 0 件 (rc=0・15.9 s)。本 commit では `=1` は取り直していない。
- **head での再測定 (本 commit の code・LB=0x10000)**:
  - `=2`: `m11_lb_tolerant_repro.sh 0x10000` が 600 s で timeout (rc=124)。`tolerant.out` は 0 行で、`[m11][412br2]` の行は 0 件。`775d2cace` の「unit 40・114・245・279 で発火」は head で再現せず、取り消す (発火の根拠として使わない)。post 段では `m11_412770_br2_obs` が 1 件挿入されることを確認済み (`M11_INSTR_412BR=2 python3 m11_post.py` で `br2=1`)。
  - `=3`: 修正前の `m11_post.py` は `gate` の文字列が IR 全体で 75 件あり、assert で build 失敗 (fail-closed)。本 commit で gate の置換を `function_4128b0` の範囲に限定し、`boot_final3.ll` に `m11_412770_gate_obs` が 1 件入ることを確認。その上で寛容起動を 420 s で打ち切り、timeout・`tolerant.out` は 0 バイト (観測 0 件)。300 s の旧結果は使わない。
  - LB=0 の対照 (head `f30c0478e`・同じ build 条件・1 回ずつ): 下の表。

- **LB 対照の表 (head `f30c0478e`・`m11_lb_tolerant_repro.sh`・各 1 回)**:

  | モード | LB | rc | wall | units_total / ok | `[m11]` 観測行 | 備考 |
  |---|---|---|---|---|---|---|
  | `=1` | 0 | 0 | 15.6 s | 942 / 873 | 0 件 | `boot_final3.ll` の `m11_412770_br_obs` 2 件 (宣言 + 呼出し) |
  | `=1` | 0x10000 | 0 | 15.6 s | 942 / 873 | 0 件 | 同上 |
  | `=2` | 0 | 0 | 15.8 s | 942 / 873 | 0 件 | `m11_412770_br2_obs` 2 件 (宣言 + 呼出し)。`[m11][412br2]` 0 件 |
  | `=2` | 0x10000 | 124 | 600 s で timeout | - | 0 件 | round 3 の再測定 (`d16dbb88c`) と同じ |
  | `=3` | 0 | 0 | 102.8 s | 942 / 873 | 0 件 | `m11_412770_gate_obs` 2 件 (宣言 + 呼出し) |
  | `=3` | 0x10000 | - | 420 s 打ち切り | - | 0 件 | timeout。`tolerant.out` は 0 バイト |

  - 読み方: `=1` は LB によらず完走し観測 0 件。`=2`・`=3` は LB=0 では完走 (観測 0 件) し、LB=0x10000 では 600 s・420 s で完走しない。観測行の件数は全条件で 0 のため、LB 差は「観測行の有無」ではなく「寛容起動が完走するか」にだけ出ている。完走の差は各 1 回の測定で、再現性は未確認。
  - `=2`・`=3` の LB=0 の完走は、probe が入った build で寛容起動の unit が全て進んだことを意味する。`[0x11FACB0]` 系の値は観測されていないため、この表から分岐の値は言えない。
  - `tolerant.out` の観測行: 0 件 (引用できる `[m11][412br*]` 行なし)。引用は `M11_TOLERANT` 要約行の `units_total`・`ok` のみ。
- **IR の訂正 (§4-1 の誤り)**: `[0xFA5008]` (分岐 1) は `function_4128b0` 入口の判定 (IR `%3`) で、`function_4125e0`・`function_4127d0` を通るかだけを決める。412770 の呼出しを守るのは `[18787760]` (分岐 2) と `GetCurrentThreadId() == [18787804]` (分岐 3) の 2 条件 (IR `%7`・`%10`)。§4-1 の「1. `[0xFA5008]` が 0 でないこと」は誤り。
- **呼出し直前の 3 値 (`M11_INSTR_412BR=1`)**: IR の 1 本目の呼出し (`dec_label_pc_4128ed` の `%13 = call function_412770(18787752)`) の直前に probe を置いた。LB=0x10000 の 942 unit で発火 0 件。LB=0 でも発火 0 件。つまり、この呼出しは寛容起動の全 unit で到達しない。
- **2 本目の呼出し (`M11_INSTR_412BR=2`)**: IR `%52` (`[18787456]` 経路) に probe を置いた。**(取り消し: head で再現せず・下の head 再測定を正とする)** 旧 `775d2cace` の測定では LB=0x10000 で unit 40 を含む 4 unit (40・114・245・279) で発火し、いずれも `[0x11FACB0]=0x2`・`[0x11FAC88]=0x0`・`[0xFB5000]=0xd8` (または 0xe4)。この経路は分岐 2・3 を通らない。LB=0 では同じ probe の run が unit 888 で止まり、観測行は 0 件 (`tools/m11/work/repro5666_lb0_p2/tolerant.out`)。
- **未達**: 受入「分岐の値を LB 別に呼出し時点で実測する」は、1 本目の呼出しが全 unit で届かないため達成していない。`M11_INSTR_412BR=3` (分岐 2 の判定直前の gate probe) は、旧 `775d2cace` の 300 s timeout 結果を取り消す。head での再測定は 420 s で打ち切り、観測 0 件で結果は出ていない。
- **run の停止**: `M11_INSTR_412BR=1` と `=2` の寛容起動は、run ごとに unit 283・888 付近で止まる場合があった (1 回目の LB=0x10000 `=1` は 8 s で完了。同じ build の再実行で挙動が変わる)。原因は未特定。probe の副作用の疑いを残す (§8-2 の観測副作用と同種)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1 本目の 412770 呼出し (分岐 2・3 の後) が寛容起動で届かない理由 (gate の値・分岐 2 の判定の直前) | LB 差の原因が未特定。受入未達 | 親 #3389 / #5666 (PM 判断) |
| `M11_INSTR_412BR=2` で LB=0x10000 の 2 本目の経路 (分岐 2・3 を通らない) がどの LB 差で通るか (LB=0 の対照が未完) | unit 40 の halt0 の経路の特定が未完 | 親 #3389 |
| probe 有効時の寛容起動の停止 (unit 283・888) | 計測の再現性 | 親 #3389 |
