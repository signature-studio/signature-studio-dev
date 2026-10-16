# MX-25 (#1913) flow 閉包: 新入口の .pdata 限定オプションと文字列窓の扱い

- 親: #1625 (MX-13) / 起票: #1913 (MX-25)。本ファイルは #1913 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX5 §5 と一致)。
- 実装: `dsp/scripts/mx_closure.py` の第 5 引数 `ENTRY` (`any` = 既定・従来どおり / `pdata` = 新入口を .pdata begin に限る)。
  `ENTRY` 未指定時の挙動は変更前と同一 (下記 §2 の `any` 再測定で確認)。

## 1. 受入の達成状況

- 受入 1 (文字列窓を flow の code から除外・除外件数を記録): **未達**。
  - 判定基準は issue 本文のとおり PM が決める。実装 agent は基準を決めていない。
  - 本 PR では除外を実装していない。文字列窓の件数も未計測。
- 受入 2 (入口を .pdata begin に限るか code/data 判定を入れるかを決め、閉包サイズと round 推移を記録): **部分達成**。
  - 「.pdata begin に限る」案 (`ENTRY=pdata`) の閉包サイズと round 推移を §2.2 に記録した。
  - どちらを採用するかの決定は PM に委ねる (§4)。code/data 判定案は未実装・未測定。
- 受入 3 (e2e PASS・negctl 3 件 FAIL<期待>): **達成** (§3。コミット済み HEAD の実測)。

## 2. 閉包サイズと round 推移 (実測)

測定 commit: `3225b096` (`mx_closure.py` の最後のコード変更)。RTTI 抽出は `mx_rtti.py` (同 PE・rc 0)。

### 2.1 `ENTRY=any` (既定) の再測定

`python3 dsp/scripts/mx_closure.py "work/extracted/VST3/Massive X.vst3" work/mx25/rtti.json work/mx25/flow_any flow any`

- rc 0 / elapsed 212.36s / load 0.32 0.42 0.22 → 1.00 0.74 0.39
- 閉包 入口 507,258 (`pdata_funcs` 13,246 / `pct_pdata` 7.08)・round 34 で収束。
- REPORT_MX13 §2 の値 (507,258・round 34・.pdata 13,246) と一致。既定経路は変更前と同一。

### 2.2 `ENTRY=pdata`

`python3 dsp/scripts/mx_closure.py "work/extracted/VST3/Massive X.vst3" work/mx25/rtti.json work/mx25/flow_pdata flow pdata`

- rc 0 / elapsed 0.83s / load 0.45 0.45 0.22 → 0.45 0.45 0.22

| round | 入口数 | 増分 | flow 到達バイト | 到達命令 | 間接 jmp 未解決 (当該 round) |
|--:|--:|--:|--:|--:|--:|
| seeds | 567 | — | — | — | — |
| 1 | 606 | +39 | 208,409 | 48,046 | 21 |
| 2 | 614 | +8 | 11,743 | 2,814 | 2 |
| 3 | 614 | +0 | 201 | 51 | 0 |

- 収束: round 3 で新規入口 0。最終入口 614 (うち .pdata begin 613)。
- 閉包 `pct_pdata` 0.33%。`closure_total.bytes_pdata` 243,884。
- round 1 の到達バイト 208,409・到達命令 48,046 は REPORT_MX13 §2 の round 1 と一致 (seeds 経由の初期到達は共通)。

### 2.3 比較

| 案 | 最終入口 | .pdata begin 以外の入口 | round | elapsed |
|---|--:|--:|--:|--:|
| `any` (既定) | 507,258 | 494,012 (97.4%) | 34 | 212.36s |
| `pdata` | 614 | 1 | 3 | 0.83s |

- `pdata` 案は .pdata 外の番地を新入口にしないため、入口が 99.9% 減る。
- ただし **正しさは未検証**。`pdata` 案は .pdata 外の関数途中・データ領域に到達する code を閉包から落とす可能性がある。どれだけ落ちるかは本測定では分からない。
- 検算 (`mx_flow_recheck.py`) は `ENTRY` を読まないため、`pdata` 案の検算は未実施。

## 3. 検証 (測定 commit `3225b096`)

- **e2e (`bash dsp/e2e.sh`・n=1)**: rc 0 / `OK elapsed=30s` / load 0.71 0.69 0.38 → 0.83 0.72 0.40。
- **negctl (`bash dsp/negctl.sh`・n=1)**:
  - NC1 `insns=3118 (base 258087) unsup=67 (base 48612)` → FAIL<期待>
  - NC2 `insns=4575 (base 258087) unsup=746 (base 48612)` → FAIL<期待>
  - NC3 `insns=31 unsup=0` → FAIL<期待>
- e2e / negctl は linear 経路の検証。`mx_closure.py` は両者から呼ばれない (`grep` で確認)。
- **HEAD 差分** (測定 commit → HEAD・コード範囲): `git diff 3225b096 HEAD -- tools/targets/massivex/dsp/scripts/mx_closure.py` は本 PR の commit 時点で 0 行 (差分 0)。

## 4. 未解決 (追跡先)

| 残件 | 受入 | 起票先 |
|---|---|---|
| 文字列窓の除外 (判定基準の決定・除外件数の記録) | 1 | 実装済み (§5.1)。除外件数を記録 |
| 入口判定 `pdata_call` の検算: capstone と objdump の先頭ブロック判定の不一致 117 件 (mismatch 0 は未達・再測定 `a505be525`) | 2 | #4068 [MX-44] (§5.5) |
| `pdata_call` を既定にするか・`pdata` 案で落ちる code の正しさ検証 (REPORT_MX13 §3 の範囲外) | 2 | PM 判断 (#1987 本文 5。既定は `any` のまま) |

## 5. MX-29 (#1987): 文字列窓の除外と入口判定 `ENTRY=pdata_call`

- 判定基準: #1987 本文の PM 判断 (2026-10-15) のとおり。既定 `ENTRY=any` は変えない。
- 測定 commit (検算 `mx_flow_recheck.py` の再測定): `a505be525` (`LOCKABLE` に `xor` を加えた commit。`mx_closure.py` の最後のコード変更は `039adc3f6`)。素材 `plugins-massivex` → `Massive X.vst3` md5 `622993e76565f49c094063a2b717d6ca` (95,356,824 B)。素材の展開は `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key` (展開 125 件の md5-ok 0/125 は §8.1 の既知事象。VST3 本体は md5 一致)。
- 測定 commit 以降のコード差分 (`git diff a505be525 HEAD -- tools/targets/massivex/dsp/scripts`): 本 REPORT 更新の commit ではスクリプトを変えないため 0 行 (出力は PR 本文に添付)。
- 再測定の手順: `mx_rtti.py` → `mx_closure.py flow pdata` (4 s)・`flow pdata_call` (3 m 23 s、22 round で収束・169,974 入口) → `mx_flow_recheck.py` (`pdata` 4.9 s PASS / `pdata_call` 3 m 9 s・RESULT=FAIL)。
- 測定時の load: `pdata_call` の開始時 0.37 0.47 0.36 (06:41)。
- 039adc3f6 の変更: (1) `mx_closure.py`: 先頭ブロックで未文書化の FSTP1 別名 `fstpnce` (D9 D8+i) を不正扱い (SDM の命令表に無い)。閉包 169,981 → 169,974 (−7)。(2) `mx_flow_recheck.py`: objdump 出力に SDM 規則の後処理 (字句 `(bad)`・`%?`、REX2 (`d5`)、REX 直後の VEX、LOCK の非ロック命令・非メモリ宛先)。宛先は AT&T の最後のオペランドを括弧内のカンマを無視して取る。mismatch 行は `work/mx29/flow_pdata_call_mismatch.tsv` に出す。

### 5.1 文字列窓 (受入 1)

- 基準: `.text` 内で印字可能 ASCII (`\t\r\n` と 0x20〜0x7e) が 8 バイト以上続き直後が NUL、または UTF-16LE の同文字 8 字以上 + U+0000。`.pdata` 関数と重なるものは窓にしない。
- 検出: 生マッチ 57 → 併合 53 → `.pdata` と重なる 29 を除外 → **残り 24 窓 (計 1,484 B)**。
- 長さ上位 20 件 (VA・長さ B): 0x1970ce0・92 / 0x1957c00・88 / 0x1902c00・77 / 0x19a3f50・76 / 0x19c7f20・75 / 0x19b96b0・73 / 0x1958da3・72 / 0x19ca780・72 / 0x19bb630・70 / 0x18f9920・69 / 0x18fe9e0・69 / 0x19dd1c8・69 / 0x19b14a0・68 / 0x18f8230・67 / 0x199b280・64 / 0x19accd0・64 / 0x19abb50・56 / 0x19d1180・55 / 0x19aee00・52 / 0x10d9300・50。
- `pdata_call` の flow が窓に当たった件数: 4 窓 (窓内の番地は code から除外し、入口にしない)。直接 call 目標が窓内に入った件数: 0。

### 5.2 閉包サイズと round 推移 (受入 2)

| ENTRY | 最終入口 | うち `.pdata` begin | `pct_pdata` | round | elapsed | leaf 候補 (objdump 後処理) ok / bad |
|---|--:|--:|--:|--:|--:|--:|
| `any` (既定) | 507,258 | 13,246 | 7.08 | 34 | 276 s (§2.1 の再測定) | — |
| `pdata` | 614 | 613 | 0.33 | 3 | — | — |
| `pdata_call` | 169,974 | 9,521 | 5.09 | 22 | 200 s (3 m 20 s) | 160,344 / 21,188 |

- `any` の値は REPORT_MX13 §2 と一致 (既定経路は不変)。`pdata` の値は §2.2 と一致 (`pdata` は `pdata_call` の変更の影響を受けない)。
- `pdata_call` の round 推移 (新規入口の累計・round 1〜22): 1,949 / 3,694 / 7,987 / 18,455 / 39,070 / 71,052 / 106,081 / 134,086 / 151,736 / 160,881 / 165,445 / 167,689 / 168,888 / 169,461 / 169,724 / 169,848 / 169,910 / 169,947 / 169,964 / 169,968 / 169,974 / 169,974。round 22 で増分 0 となり収束。
- BFS 検算 (`mx_flow_recheck.py`): `pdata` / `pdata_call` とも BFS 閉包 == round ループの入口 (True)、round 別 added 合計 == 閉包 − seeds (一致)。

### 5.3 検算 (受入 2・`mx_flow_recheck.py` の ENTRY 対応・測定 commit `039adc3f6`)

`LOCKABLE` に `xor` を加えた版 (測定 commit `a505be525`・2026-10-15 再測定) の数字。`039adc3f6` の旧数値 (118 件・113 件) は `lock xor` のメモリ形を誤って不正扱いしていたため無効で、使わない。

直接 call 目標 (`.text` 内・thunk 外・`.pdata` begin を除く) を (i) 文字列窓 (ii) 先頭ブロック不正 (iii) 先頭ブロック正常 に分類。(ii)/(iii) の判定は objdump 2.42 (`-b binary -m i386:x86-64`) に SDM 後処理を入れた側で行い、capstone (入口の採否に使った判定) と食い違いを数えた。

| ENTRY | 対象 | (i) 窓 | (ii) 不正 | (iii) 正常 | (iii) で入口に入らない (取りこぼし) | 入口で (iii) でない (過剰) | mismatch |
|---|--:|--:|--:|--:|--:|--:|--:|
| `pdata` | 1,712 | 0 | 299 | 1,413 | 1,413 (pdata 案で落ちる leaf 候補) | 0 | **0 (PASS)** |
| `pdata_call` | 181,532 | 0 | 21,187 | 160,345 | 5 | 112 | **117 (未達)** |

- `pdata` は mismatch 0 (再測定でも変化なし)。
- `pdata_call` の mismatch 117 の内訳 (`mx_flow_recheck.py` が出す `_mismatch.tsv` の理由別・§5.5 に分類):
  - 109 件: objdump (SDM 規則) が LOCK 違反とし、capstone が受理する。内訳は、LOCK 可能な命令で宛先がレジスタ 80 件 (`adc` 50・`add` 19・`or` 5・`xor` 3・`and` 2・`sub` 1)、LOCK 不可の命令 29 件 (`repnz movsb`・`movsd`・`bnd`・`cvt*`・`nopl`・`movq` など)。SDM 上はいずれも #UD。capstone 5.0.7 は LOCK の宛先・命令・REP との併用を見ないため受理する。判定は capstone 側の修正が要る (子 issue #4068)。
  - 5 件: capstone が不正・objdump が受理する。4 件は単独デコードで確認 (`62 02 …` EVEX 形 2 件と `4e 4e …` 1 件は capstone が拒否、`0f ff` は capstone が `ud0` と復号するが、スクリプトの判定では不正扱い)。残り 1 件 (0x81a740) は先頭命令は capstone が受理するため、先頭ブロック内の後続命令の不正を疑うが、個別の命令は未特定。
  - 3 件: 原因未確定。TSV の objdump 行 (`(bad)`・`rex2`) と、対象番地を単独でデコードした結果が一致しない (例: 0x12e3768 は先頭 `00 00` が単独デコードで `add %al,(%rax)` と受理され、`(bad)` にならない)。objdump 側の番地の取り方 (連続逆アセンブル時の境界ずれ) の疑い。切り分けは #4068。
- 取りこぼし 5 件 (objdump 側では leaf 候補、capstone 側では不採用) は上の「capstone が不正・objdump が受理」の 5 件と重なる。過剰 112 件は、objdump が不採用で capstone が採用した行 (`cap_ok_obj_bad`: LOCK 109 + `(bad)/%?/rex2` 2 + `rex2` 1 = 112) と一致する。
- 検算は `pdata_call` の入口を正しいと認めない: mismatch 117 のため、「入口が (iii) を全て取る (取りこぼし 0)」は未達。
- `xor` 修正 (B1) の効果: 旧 110 → 新 109 (LOCK 行) の 1 件減。残る `lock xor` 3 件 (`lock xor 0x…(%rax),%esi`・`lock xor 0x0(%rax),%dl` ×2) は宛先がレジスタで、SDM 上 #UD のため不正のまま。メモリ宛先の `lock xor` が受理されたかは、旧 TSV を残さなかったので直接は確認していない (1 件減は推定)。

### 5.4 検証 (受入 3・測定 commit `039adc3f6`・n=1)

- e2e (`MX_PE=… bash dsp/e2e.sh`): rc 0 / `OK elapsed=27s` / load 1.46 3.00 2.38 → 1.30 2.84 2.34。
- negctl (`MX_PE=… bash dsp/negctl.sh`): NC1 `insns=3118 (base 258087) unsup=5 (base 24258)` → FAIL<期待> / NC2 `insns=4575 unsup=302 (base 24258)` → FAIL<期待> / NC3 `insns=31 unsup=0 (base 24258)` → FAIL<期待>。
- e2e / negctl は linear 経路の検証。`mx_closure.py` は両者から呼ばれない。

### 5.5 未解決 (追跡先)

| 残件 | 受入 | 起票先 |
|---|---|---|
| `pdata_call` の mismatch 117 → mismatch 0 と取りこぼし 0 の確認 (MX-58 #5399 の分類は `REPORT_APPENDIX_5399.md`: 最新 head の mismatch 24 件を理由別に分類・REX 直後 F0 17 件は SDM 未確認)。内訳: capstone の LOCK 規則 109 件 (宛先レジスタ 80・LOCK 不可命令 29)・objdump 受理 capstone 不正 5 件 (単独デコードで 4 件確認・1 件未特定)・原因未確定 3 件 | 2 | #4068 [MX-44] (子 issue。本 issue から移管) |
| `pdata_call` を既定にするか (数値は §5.2・§5.3。既定は `any` のまま) | 2 | PM 判断 (#1987 本文 5) |

### 5.6 #4979 の追記 (測定 commit `00c7332c1`・素材の無い run の記録)

- 変更: `mx_closure.py` の先頭ブロック判定を `block_ok` (`insn_sdm_ok` を通す) に置換。`ENTRY=any` の経路は変えない (`leaf_ok` は `pdata_call` でだけ呼ばれる)。`00c7332c1` から PR head までのコード差分は 0。
- 単体テスト: `python3 dsp/scripts/test_mx_closure_lock.py` → 8 件 OK。
- 出所の注意: 以下の e2e・negctl・closure の値は PR #5022 作成 run の実測で、REPORT への転記。素材 `plugins-massivex` (`Massive X.vst3` md5 `622993e76565f49c094063a2b717d6ca`) は fix run の runner に無く、再実行していない。

**e2e・negctl (測定 commit `00c7332c1`・n=1・PR 作成 run)**

- e2e (`MX_PE=… bash dsp/e2e.sh`): rc 0 / `OK elapsed=28s` / load `0.07 0.30 0.17 → 0.44 0.37 0.20`。
- negctl (`MX_PE=… bash dsp/negctl.sh`): NC1 `insns=3118 (base 258087) unsup=5 (base 22745)` → FAIL<期待> / NC2 `insns=4575 (base 258087) unsup=285 (base 22745)` → FAIL<期待> / NC3 `insns=31 (base 258087) unsup=0 (base 22745)` → FAIL<期待>。
- base unsup: 本節の `22,745` と §5.4 の `24,258` が食い違う。測定条件の差か、どちらかが古いかは未確定 (main の再測定が必要・未実施)。

**pdata_call の closure (測定 commit `00c7332c1`・PR 作成 run)**

- 入口 169,974 (§5.2 の旧規則) → 169,752 (本 PR)。旧規則にあって本 PR で落ちた入口 259 件・本 PR で新たに入った入口 37 件。
- 落ちた入口の先頭命令 (上位): `lock adc` 50・`lock add` 29・`repne movsb` 10・`lock or` 6・`lock inc` 4 など。

**mismatch の未確定事項**

- 本節の取りこぼし 23・過剰 3 (合計 26) は、§5.7 (`4040ca5ff`) の再実行でも同じ値。mismatch の確定値と内訳は §5.7 を参照する。
- LOCK 規則の効果 (closure 259 件減) と、capstone の LOCK 判定 (mismatch の 109 件) の関係は、再実行まで断定しない。
- 取りこぼし 5 → 23 (新規に落ちた入口 18 件) は未解決。`pdata_call` は既定ではないため merge は可逆。

**規則の根拠 (未確定)**

- `45 f0 …` (REX 直後の F0) を #UD とする SDM 節は未確認。REX 直後の F3 を「REX が無視される」とする扱いとの整合も未説明。
- 規則が正しいかは #4981 (MX-51) で判定する。

## 5.7 #4981 (MX-51): 検算の capstone 判定を closure と揃えた実測

- 測定 commit: `4040ca5ff` (`mx_flow_recheck.py` の capstone 側を `mx_closure.insn_sdm_ok` と REX2 (d5) 除外に揃えた commit)。閉包の再計算は `bed64571a` (`mx_closure.py` は未変更) の出力を使用。
- 素材: `plugins-massivex` → `Massive X.vst3` md5 `622993e76565f49c094063a2b717d6ca` (一致)。展開 125 件の md5-ok 0/125 は §8.1 の既知事象。
- 手順: `mx_rtti.py` (3.9 s) → `mx_closure.py flow pdata_call` (3 m 01 s、22 round、169,752 入口) → `mx_flow_recheck.py` (2 m 56 s)。
- 結果 (`RESULT=FAIL`): BFS == loop True / 入口 169,752 / (i) 0・(ii) 21,170・(iii) 160,257。取りこぼし 23・過剰 3・**mismatch 26** (前回 117)。
- 変化: 前回の mismatch 117 のうち LOCK 109 件は検算側の判定の古さによるもので、closure の規則と揃えて解消。残り 26 件は下表。REX2 (d5) は recheck だけの除外規則で、§5.3 の内訳には REX2 の件数が無いため、解消数には数えない。件数の対応は下の表。

件数の対応 (§5.3 の 117 → §5.7 の 26)。件数は各 REPORT の記載どおり。番地ごとの照合はしていない。

| 区分 | 件数 | 根拠 |
|---|--:|---|
| §5.3 の mismatch | 117 | §5.3 の内訳 (LOCK 109 + capstone 不正 5 + 原因未確定 3) |
| 解消 (§5.7 が「LOCK 規則」と記した分) | −109 | §5.7 の変化 |
| 残り (§5.3 の LOCK 以外) | 8 | 117 − 109 |
| §5.7 の mismatch | 26 | 内訳は §5.7 の表 (17 + 2 + 2 + 1 + 1 + 2 + 1) |

- 8 件から 26 件への増加 (差 18 件) は、件数だけでは「規則変更で新規に出た件」と「残存」に分けられない。§5.7 の表 (REX 直後 F0 17 件など) は種類で分類したもので、§5.3 の区分とは対応づけていない。
- **18 件 (26 − 8) の内訳は未確定。`_mismatch.tsv` が要る。** 残り 8 / 26 は内訳未確定として読むこと。
- §5.7 の「REX2 1 件を解消」は §5.3 の内訳に REX2 の件数が無いため、この表では扱わない。§5.7 の表には rex2 1 件 (0x2693a0c) が残っている。
- 番地ごとの対応 (どの 117 件が解消し、どの 26 件が新規か) は `_mismatch.tsv` が必要で、本 run では再生成できなかった。素材 `plugins-massivex` を取得して `mx_flow_recheck.py` を head で再実行してから作る。
- 測定時の load: 閉包開始 1.09 0.47 0.18 / 検算開始 1.62 2.11 1.06。e2e (`MX_PE=… bash dsp/e2e.sh`) は `OK elapsed=27s`・load 2.47 3.00 1.69 → 1.97 2.84 1.67・rc 0。単体テスト `test_mx_closure_lock.py` は 8 件 OK。
- 測定 commit 以降のコード差分 (`git diff 4040ca5ff HEAD -- tools/targets/massivex/dsp/scripts`): 本 REPORT 更新のみのため 0 行。

残り mismatch 26 の内訳 (`_mismatch.tsv` の objdump 行で分類):

| 件数 | 種類 | 扱い |
|--:|---|---|
| 17 | REX 直後に F0 (例 `4e f0 …`・`45 f0 …`)。closure は #UD とし、objdump は受理 | 規則の正否が未確定 (§5.6)。SDM の REX 節で確認するまで規則は変えない |
| 2 | EVEX 形 (`62 02 …`)。capstone 不正・objdump 受理 | 未分類 |
| 2 | `0f ff` / `57 ff` の形。capstone 不正・objdump 受理 | 未分類 |
| 1 | `4e 4e …` 連続 REX。capstone 不正・objdump 受理 | 未分類 |
| 1 | `41 f2 f0 …` (REP と LOCK の併用)。capstone 不正・objdump 受理 | 未分類 |
| 2 | `(bad)` (0x12e3768・0x2470627)。capstone 受理・objdump 不正 | 番地ずれの疑い (前回から継続) |
| 1 | `rex2` (0x2693a0c)。capstone は APX の lea 形として受理 | 番地ずれの疑い |

- 受入 2 (mismatch 0・取りこぼし 0) は未達。閉包 169,752 は規則の判断待ち (`pdata_call` は既定ではない・既定 `any` は不変)。

## 5.8 MX-59 (#5400): 番地ずれ疑い 3 件の判定 (head `9645894e3` を実測。`0b91334ed` の値は main 取り込み前の参考値)

- **head 実測 (`9645894e3`・`git diff --numstat 0b91334ed 9645894e3 -- tools/targets/massivex/dsp/scripts` = `7 1`)**: 素材 `plugins-massivex` → `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key` → `Massive X.vst3` md5 `622993e76565f49c094063a2b717d6ca` (95,356,824 B・一致)。`mx_rtti.py` → `mx_closure.py flow pdata_call` (22 round・入口 169,752・2 m 0 s) → `mx_flow_recheck.py` (2 m 11 s・終了時 load `4.47 2.04 0.82`・RESULT=FAIL・rc 1)。展開 125 件の md5-ok 0/125 は §8.1 の既知事象。
- head の結果 (`0b91334ed` の値と並べる):

| 項目 | `0b91334ed` (参考) | head `9645894e3` |
|---|--:|--:|
| 入口 | 169,752 | 169,752 |
| (ii) 先頭ブロック不正 | 21,168 | 21,168 |
| (iii) 先頭ブロック正常 | 160,259 | 160,259 |
| 取りこぼし | 23 | 23 |
| 過剰 | 1 | 1 |
| mismatch | 115 | **24** |
| `mismatch_cap_bad_obj_ok` | (未記載) | 23 |
| `mismatch_cap_ok_obj_bad_(bad)/%?/rex2` | (未記載) | 1 |

- head の 3 件の判定: `0x12e3768` (`(bad)`) と `0x2693a0c` (rex2) は head の mismatch に**無い** (`0b91334ed` の値でも無い。`ljmp` を TERM に加えた効果が head でも維持される)。`0x2470627` (`(bad)`・先頭は表データ `02 f9 fb 46 …`) は head でも**残る** (capstone 受理・objdump `(bad)`)。よって head では「2 件は mismatch に無い・1 件 (`0x2470627`) は未解決」。
- `0b91334ed` → head の番地ごとの差 (`mismatch_0b91334ed.tsv` と `mismatch_head.tsv` の比較。ともに `work/mx29/`・gitignore): 旧 115 = 共通 6 + LOCK 規則で消えた 109 (旧 `lock` 109 件の全て) ; 新 24 = 共通 6 + 新規 18 (capstone 不正・objdump 受理 18 件)。共通 6 件に `0x2470627` を含む。`insn_sdm_ok` (SDM の LOCK 規則) が capstone 側の LOCK 109 件を一致扱いにし、代わりに capstone 不正・objdump 受理の 18 件が新たに mismatch に出た。取りこぼし・過剰は両方で 23・1 (同一)。
- head の mismatch 24 の内訳 (`mismatch_cap_bad_obj_ok` 23・`mismatch_cap_ok_obj_bad_(bad)/%?/rex2` 1 = `0x2470627`)。23 件は全て capstone 不正・objdump 受理 (`capstone=False objdump=True`)。
- `0b91334ed` → head の番地ごとの差 (`work/mx29/mismatch_0b91334ed.tsv` と `mismatch_head.tsv`・gitignore。同じ `flow_pdata_call_sets.pkl` に旧版・新版の script を当てて再生成): 旧 115 = 共通 6 + 旧だけの 109 (旧 `lock` 109 件の全て・capstone 側の LOCK 判定が一致扱いに変わって消えた)。新 24 = 共通 6 + 新だけの 18 (capstone 不正・objdump 受理)。共通 6 件は `0x2470627` を含む 6 件。取りこぼし 23・過剰 1 は両方で同一。
- 以下の旧記述は `0b91334ed` の値 (取り込み前の参考値)。
- 入力: `mx_rtti.py` → `mx_closure.py flow pdata_call` (22 round・169,752 入口)。`mx_flow_recheck.py` は `0b91334ed` で実行。
- 変更 (`0b91334ed`): 先頭ブロックの終端 `TERM` に `ljmp` (`ff /5`・遠方ジャンプ) を加えた。`ljmp` は制御を移すため、その後ろは先頭ブロックではない。
- 結果 (`0b91334ed`・`RESULT=FAIL`):

| 項目 | 値 |
|---|--:|
| (ii) 先頭ブロック不正 | 21,168 |
| (iii) 先頭ブロック正常 | 160,259 |
| 取りこぼし | 23 |
| 過剰 | 1 |
| mismatch | 115 |
| `(bad)/%?/rex2` | 1 |
| `lock` (LOCK 規則) | 109 |
| capstone 不正・objdump 受理 | 5 |

- 変更前との比較はしない。変更前 (`0b91334ed` の親) の同一 run の値は本 run では再測定できていない。§5.3 の値 (対象 181,532・入口 169,974) とは入口集合が違い (対象総数の差 105)、同じ入口集合ではないため「117 → 115」は比較として成立しない。この比較は撤回する。
- 3 件の判定 (`0b91334ed` の script での値。`ljmp` の効果だけを見ている。`insn_sdm_ok` 取り込み前):
  - `0x12e3768` (`(bad)`): 先頭ブロックの `ljmp *(%rax,%rax,1)` (`12e37b9`) の後ろ (`12e37be`) の `(bad)` を読んでいた。番地ずれではない。終端に `ljmp` を加えると `0b91334ed` の run では解消。head の判定は上の head 実測節を参照。
  - `0x2693a0c` (`rex2`): 先頭 `e1 8b` は `loope` で正常。`rex2` と判定されたのは後続の `ljmp *(%rbx)` (`2693a17`) より後ろ。終端に `ljmp` を加えると `0b91334ed` の run では解消。head の判定は上の head 実測節を参照。
  - `0x2470627` (`(bad)`): 未解決。先頭が命令列ではなく表 (`02 f9 fb 46 02 18 …` の 8 バイト周期)。`.text` 内のデータ領域を入口として読んでいる疑い。`ljmp` 終端では判定できない。
- 残る mismatch 115 件: LOCK 規則 109 件 (capstone 側の判定。#4068)・capstone 不正 / objdump 受理 5 件・`0x2470627` 1 件。
- 受入 1 (mismatch 0・取りこぼし 0・過剰 0) は未達。取りこぼし 23 と過剰 1 は残る。取りこぼし 23・過剰 1 と #4068 の関係は推定で、未切り分け。
- 実行時間: `mx_flow_recheck.py` 1 m 56 s (wall)・終了後 load `5.21 4.04 2.46` (`0b91334ed` の run)。
- main 取り込み後の script: `mx_flow_recheck.py` は main の `insn_sdm_ok` を取り込んで `0b91334ed` から変わった (`git diff --numstat 0b91334ed 9645894e3 -- tools/targets/massivex/dsp/scripts` = `7 1`)。上の表は取り込み前の値。`7abf69f9d` の `mx_flow_recheck.py` は `9645894e3` と同一 (`git diff 9645894e3 7abf69f9d -- tools/targets/massivex/dsp/scripts` = 空) のため、この節の head 実測が HEAD の値。
- 既定の `any` 経路・`pdata` 経路は変えていない (`TERM` は `pdata_call` の `flow` 検算でのみ使う)。
