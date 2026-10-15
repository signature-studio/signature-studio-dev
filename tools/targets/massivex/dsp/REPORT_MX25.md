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
| 入口判定 `pdata_call` の検算: capstone と objdump の先頭ブロック判定の不一致 1,527 件の理由別全数分類 (mismatch 0 は未達) | 2 | #1987 (MX-29。残件として本 issue に残す・§5.3) |
| `pdata_call` を既定にするか・`pdata` 案で落ちる code の正しさ検証 (REPORT_MX13 §3 の範囲外) | 2 | PM 判断 (#1987 本文 5。既定は `any` のまま) |

## 5. MX-29 (#1987): 文字列窓の除外と入口判定 `ENTRY=pdata_call`

- 判定基準: #1987 本文の PM 判断 (2026-10-15) のとおり。既定 `ENTRY=any` は変えない。
- 測定 commit: `d5d83b5c` (`mx_closure.py` / `mx_flow_recheck.py` の最後のコード変更)。素材 `plugins-massivex` → `Massive X.vst3` md5 `622993e76565f49c094063a2b717d6ca` (95,356,824 B)。
- 測定 commit 以降のコード差分: 本 REPORT の commit だけで、`git diff d5d83b5c HEAD -- tools/targets/massivex/dsp/scripts` は 0 行。

### 5.1 文字列窓 (受入 1)

- 基準: `.text` 内で印字可能 ASCII (`\t\r\n` と 0x20〜0x7e) が 8 バイト以上続き直後が NUL、または UTF-16LE の同文字 8 字以上 + U+0000。`.pdata` 関数と重なるものは窓にしない。
- 検出: 生マッチ 57 → 併合 53 → `.pdata` と重なる 29 を除外 → **残り 24 窓 (計 1,484 B)**。
- 長さ上位 20 件 (VA・長さ B): 0x1970ce0・92 / 0x1957c00・88 / 0x1902c00・77 / 0x19a3f50・76 / 0x19c7f20・75 / 0x19b96b0・73 / 0x1958da3・72 / 0x19ca780・72 / 0x19bb630・70 / 0x18f9920・69 / 0x18fe9e0・69 / 0x19dd1c8・69 / 0x19b14a0・68 / 0x18f8230・67 / 0x199b280・64 / 0x19accd0・64 / 0x19abb50・56 / 0x19d1180・55 / 0x19aee00・52 / 0x10d9300・50。
- `pdata_call` の flow が窓に当たった件数: 4 窓 (窓内の番地は code から除外し、入口にしない)。直接 call 目標が窓内に入った件数: 0。

### 5.2 閉包サイズと round 推移 (受入 2)

| ENTRY | 最終入口 | うち `.pdata` begin | `pct_pdata` | round | elapsed | leaf 判定 (capstone) ok / bad |
|---|--:|--:|--:|--:|--:|--:|
| `any` (既定) | 507,258 | 13,246 | 7.08 | 34 | 276 s | — |
| `pdata` | 614 | 613 | 0.33 | 3 | 3 s | — |
| `pdata_call` | 169,981 | 9,521 | 5.09 | 22 | 137 s | 160,459 / 21,073 |

- `any` の値 (507,258・round 34・.pdata 13,246) は REPORT_MX13 §2 と一致 (既定経路は不変。elapsed は負荷差で 212 s → 276 s)。`pdata` の値は §2.2 と一致。
- `pdata_call` の round 推移 (新規入口): 1,950 / 3,695 / 7,989 / 18,457 / 39,073 / 71,055 / 106,085 / 134,092 / 151,743 / 160,888 / 165,452 / 167,696 / 168,895 / 169,468 / 169,731 / 169,855 / 169,917 / 169,954 / 169,971 / 169,975 / 169,981 / 169,981 (round 1〜22)。round 22 で収束。
- BFS 検算 (`mx_flow_recheck.py`): `pdata` / `pdata_call` とも BFS 閉包 == round ループの入口 (True)、round 別 added 合計 == 閉包 − seeds (一致)。

### 5.3 検算 (受入 2・`mx_flow_recheck.py` の ENTRY 対応)

直接 call 目標 (`.text` 内・thunk 外・`.pdata` begin を除く) を (i) 文字列窓 (ii) 先頭ブロック不正 (iii) 先頭ブロック正常に分類。先頭ブロックは capstone (closure と同じ判定) と objdump 2.42 (`-b binary -m i386:x86-64`) の 2 通りで判定し、食い違いを数えた。

| ENTRY | 対象 | (i) 窓 | (ii) 不正 | (iii) 正常 | (iii) で入口に入らない (取りこぼし) | 入口で (iii) でない (過剰) | mismatch 内訳 (LOCK / REX / 他 / 逆向き) |
|---|--:|--:|--:|--:|--:|--:|---|
| `pdata` | 1,712 | 0 | 278 | 1,434 | 1,434 (pdata 案で落ちる leaf 候補) | 0 | 15 / 4 / 2 / 1 (計 22) |
| `pdata_call` | 181,532 | 0 | 19,572 | 161,960 | 1,514 | 13 | 970 / 92 / 452 / 13 (計 1,527) |

- 不一致の多くは objdump が受理し capstone が不正とする命令 (例: `f0 41 83 fb 08` = LOCK 接頭辞を付けたレジスタ宛 `cmp`、`4d f0 e8` = REX の後に LOCK 接頭辞、`40 c5 …` = REX の後の VEX)。これらは SDM 上 #UD のため、判定には capstone を採った。逆向きの 13 件 (capstone が受理し objdump が不正) は理由未調査。
- **mismatch 0 は未達**。「他 452」の理由は未分類で、1,514 件の取りこぼしは decoder の方針差に依存する上限値 (0〜1,514)。残件は §4 の表 (#1987)。

### 5.4 検証 (受入 3・測定 commit `d5d83b5c`・n=1)

- e2e (`MX_PE=… bash dsp/e2e.sh`): rc 0 / `OK elapsed=22s` / load 3.95 2.60 1.58 → 2.94 2.47 1.56。
- negctl (`MX_PE=… bash dsp/negctl.sh`): NC1 `insns=3118 (base 258087) unsup=5 (base 24258)` → FAIL<期待> / NC2 `insns=4575 unsup=302 (base 24258)` → FAIL<期待> / NC3 `insns=31 unsup=0 (base 24258)` → FAIL<期待>。
- base の unsup 24,258 は §3 の 48,612 と異なる。原因は測定 commit `3225b096` 以降の `tools/flelift/x64c.py` の更新 (`b2b898522` 以降)。e2e・negctl は `mx_closure.py` を呼ばない (linear 経路の検証)。

### 5.5 未解決 (追跡先)

| 残件 | 受入 | 起票先 |
|---|---|---|
| capstone と objdump の先頭ブロック判定の不一致 1,527 件の理由別全数分類 (特に「他 452」と逆向き 13)・mismatch 0 | 2 | #1987 (本 issue に残す) |
| `pdata_call` を既定にするか (数値は §5.2・§5.3。既定は `any` のまま) | 2 | PM 判断 (#1987 本文 5) |
