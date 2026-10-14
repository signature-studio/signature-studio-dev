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
| 文字列窓の除外 (判定基準の決定・除外件数の記録) | 1 | #1987 (MX-29。PM 判断待ち。基準が決まるまで実装しない) |
| `pdata` 案と code/data 判定案のどちらを採用するか・`pdata` 案で落ちる code の検算 | 2 | #1987 (MX-29。PM 判断待ち) |
| flow モードの正しさ検証 (REPORT_MX13 §3 の範囲外) | 2 | #1987 (MX-29。PM 判断待ち) |
