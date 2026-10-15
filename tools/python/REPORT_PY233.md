# tools/python REPORT: PY-233 general.getRecPPB の切替先の実行時値 (#3690, 親 #3003)

> 前段: `tools/python/REPORT_PY121.md` (PE 静的解析で切替式 `0xd68d90` を確定)・`tools/flelift/boot/REPORT.md` §9-§11 (boot 停止点 unit 209)・`tools/python/REPORT_APPENDIX_PY123.md` §2 (fill `f_6a7b70` の 0 化)。
> 既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D25 と照合。lift の翻訳欠陥 (D1a〜D23・D25) の症状とは一致を確認できなかった。D20・D21 (load・引数の値の化け) も候補として見たが、buf=0 の呼出しという本件の観測とは一致を示せない。fill が buf=0 で呼ばれる上流の判定は #3112 に任せる。類型 ID は付けない)。

## 結論

- **受入 1 (入口の値): 未取得。** 切替関数 `0xd68d90` の入口観測点は、shim 経路の boot (units 209 → exit) で 0 件。2026-10-15 の再測定 (§5・main `321f1620e`) でも、root 有り・root 無し (対照) のどちらでも 0 件。呼出元は `f_d69310` (getRecPPB 本体 = Python 側の API ハンドラ) と `f_13751d0` の icall 分岐 case の 2 箇所で、boot はどちらにも入らなかった。
- **受入 2 (取得できない場合): 記録した。** 到達範囲と必要な変更は §3。
- **停止点の値 (参考)**: unit 209 の後の `0x412a0d` (exit 直前) で `[0x15e4558]=0`・`[0x15e35c8]=0`・`[0x16ba7f0]=0`・`[0x16ba808]=0`。切替の両経路とも X=0 (null)。この値は実行時の正しい値ではない (次の項目)。
- **原因 (推定)**: 実測したのは、unit 209 の fill `f_6a7b70` の呼出し 6 回目 (dst=`0x1400000`・4 MiB) の範囲内で、P (`0x15e4558`)・Q (`0x15e35c8`) への 16 バイト書込みが各 1 件起き、0 になったことまで (書込み監視で 2 件)。fill の入口 (6 回目) ではまだ PE 初期値 (`0x16ba7f0`・`0x16ba808`) だった。書込み元 VA は出ないため、fill が書込み元であることは推定。
- **切替条件**: 確定できず。PE 静的の式 (`P≠0` なら `X=[P]`、`P=0` なら `X=[Q]`・REPORT_PY121 §「getRecPPB の切替」) はそのまま。実行時の入力を得るには fill の呼出元の修復 (#3112) が前提。
- mock・C provider は変えない (実装数・未実装数の変化 0)。

## 1. 観測結果 (測定 commit `d5d8336c3`)

| 観測点 | 位置 (lift C) | 結果 |
|---|---|---|
| getRecPPB 切替の入口 `0xd68d90` | `fle_lifted_s7.c:309282` (`f_d68d90`) | **0 件** (boot は units 209・exit まで未到達) |
| 停止点 `0x412a0d` (`call 0x406fc0`・戻り先 `0x412a12`。unit 209 の MessageBoxA の後) | `fle_lifted_s2.c:33349` (`f_4128b0`) | 1 件: P=0・Q=0・`[0x16ba7f0]`=0・`[0x16ba808]`=0・c1=c2=0・X=0。`[X+0xb20]` は読まず (無効) |
| fill `f_6a7b70` の入口 | `fle_lifted_s1.c:112101` | 6 回: dst = `0x0`・`0x400000`・`0x800000`・`0xc00000`・`0x1000000`・`0x1400000`。val=0・cnt=`0x100000` (DWORD = 4 MiB)。**6 回目の入口で P=`0x16ba7f0`・Q=`0x16ba808` (初期値のまま)** |
| 書込み監視 (`FLE_WWATCH`・監視 4 セル) | `fle_cpu.h:79` (STX 16 バイト。書込み元 VA は出ない) | 2 件: `0x15e35c8` (a=`0x15e35c0`・n=16) 0x16ba808→0 / `0x15e4558` (a=`0x15e4550`・n=16) 0x16ba7f0→0 |

- PE 初期値 (pefile で `.data` の raw を読む): `0x15e4558`→`0x16ba7f0`、`0x15e35c8`→`0x16ba808`。`.bss` の `0x16ba7f0`・`0x16ba808` は raw 無し (0)。
- 敷設: `fle_boot_enter` の初回で `fle_data_install` が `.data` (`0x13a5000`〜`0x15e5008`) を敷設する。6 回目の fill 入口で値が PE 初期値と一致したことから、敷設は効いている。
- 0 化の源: fill の 6 回目 (dst `0x1400000`・4 MiB → `0x1400000`〜`0x1800000`) が P・Q を含む。fill の 6 回は 0x0〜0x1800000 を覆う (`REPORT_APPENDIX_PY123.md` §2 の静的記録と一致。本 REPORT は入口の引数を実測した)。
- **fill → 0 化の対照は未実施**: 診断 `FLE_DIAG_NULLFILL=1` (buf = `[this+0x50]` = 0 の fill を戻す) は、fill が root 無し (unlifted) のときだけ効く (`fle_boot.c:268`)。本 probe は既定の root 有り lift (`FLE_EXTRA_ROOTS=0x6a7b70`) で、`FLE_DIAG_NULLFILL=0` を指定しているため、診断は no-op。よって上の 0 化は対照の結果ではない。既存の記録 (`tools/flelift/boot/REPORT.md` §11) では root 無し lift で診断を付けると GetMem・undo slot の 0 化が消えており、P・Q について同じ対照を取る作業は §未解決に置く。

## 2. 手段 (再現)

```sh
bash tools/flelift/boot/fle6_measure.sh   # 前提: FL_WIN64_DIR (fl-win64 展開先)・SS_EMSDK_ENV ([EMSDK])。shim 経路のみは FLE_BOOT_RUNS=shim FLE_BOOT_TAG=py233
bash tools/flelift/boot/py233_getrecppb_probe.sh   # 観測点 3 つ + FLE_WWATCH (4 セル) の variant を作って boot
```

- 観測 C 文は `tools/flelift/boot/dbg_lift.py --c` で lift 出力のコピー (`work/boot/lift_dbg/`・gitignore) に挿入する。ポインタは `< 0x30000000` のときだけ読む。
- 書込み監視の slot は `-DFLE_WWATCH_SLOTS=` で上書きする (既定値は従来の 2 slot)。
- boot の実行の第 1 引数は**絶対パス**にする (`fle_boot.mjs` が `import()` するため、相対パスは bare specifier として失敗する)。

## 3. 到達範囲と必要な変更

- **boot 連鎖の到達範囲**: shim 経路 (root `0x6a7b70` あり) は units 209 → `MessageBoxA` → `ExitProcess(0)` (`0x412a0d`)。GetMem 2,314・FreeMem 1,199・IPP 判定 NG (既知) は `tools/flelift/boot/REPORT.md` §9-§10 と一致。
- **切替関数の呼出元**: `f_d69310` (getRecPPB 本体。Python 側の API 経由で、boot の 209 unit までには入らない) と `f_13751d0` の icall 分岐 case (`0xd68d90` の間接分岐)。後者が boot で通るかは未確認。
- **必要な変更**:
  1. fill `f_6a7b70` の呼出元 (`tools/flelift/boot/REPORT.md` §11 の記録では `0x6c7923` ← `f_815050`、幅 2^20) の判定と修復 → 既存 **#3112 [FLE-13]**。修復後、`.data` が 0 化されないことを確かめてから、停止点を越えて `0xd68d90` の入口を再測定する (本 script がそのまま使える)。
  2. 修復後に boot が止まる次の地点: 既存の `unlifted 0x6bbc20` → **#3491 [FLE-14]**。
  3. getRecPPB を boot で通すには Python 側の呼出し経路が要るかもしれない。**未確認**。

## 4. 検証

- 測定 commit: `d5d8336c3` (観測スクリプトの最後のコード変更)。`git diff d5d8336c3 HEAD -- tools/flelift tools/python ':!*.md'` は、本 REPORT の commit 後も空 (差分 0)。
- 再現 (HEAD `d5d8336c3`): `py233_getrecppb_probe.sh` 1 回 (1m33s・4 コア・load は今回の run で未取得)。結果は §1 と同一。lift 出力は `3e88853d7` で作った (`git diff 3e88853d7 HEAD -- tools/flelift/x64c.py tools/flelift/boot/gen_boot.py tools/flelift/boot/fle6_measure.sh tools/flelift/boot/build.sh tools/flelift/fle_data_gen.py tools/flelift/rt/fle_cpu.h` は空)。
- baseline (`fle6_measure.sh` shim 経路・`3e88853d7` で測定。以後は lift の入力が不変なので再測定していない): lift 49〜61s・peak RSS 610MB、clang 8 shard 63〜73s、boot 19〜20s。units 209・stopped 209・exit・getmem 2314・freemem 1199・IPP 判定 NG (rc=3・既知)。変化 0。
- ネガティブコントロール: 観測の前後対照として、fill 入口 (6 回目・値は初期値) と停止点 (値は 0) を取った。書込み監視の検出自体の対照 (変化しない slot で 0 件になること) は未実施。
- e2e: `fle_cpu.c` の変更は `FLE_WWATCH` 定義時だけ効く (既定のマクロ値は従来の 2 slot)。既定の boot の結果は §4 の baseline と一致。`tools/flelift/fle_e2e.sh` は未実行。
- KPI (起動): 前後とも units 209・最初のウィンドウ未達 (`MessageBoxA` → `exit(0)`)。本 PR は既定経路の boot 結果を変えない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| fill `f_6a7b70` の呼出元 (buf=0 から 4 MiB ずつ 6 回の 0 化) の判定と修復。`.data` の P・Q を 0 にする | 切替の実測ができない。boot 連鎖の silent miscompile の疑い | #3112 [FLE-13] (既存・OPEN) |
| 修復後の次の blocker `unlifted 0x6bbc20` | 最初のウィンドウ未達 | #3491 [FLE-14] (既存) |
| getRecPPB (`0xd68d90`) の呼出元が boot に入るか (Python API 経由のみか、icall 分岐 `f_13751d0` か) | 到達しなければ boot では値を取れない | #3003 (親・PY-127) に本 REPORT の結論を返す |
| 書込み監視 (STX) の書込み元 VA が出ない (`fle_cpu.h:79`)。書込み元は fill の呼出し順と入口の値からの推定 | P・Q の書込み元 (fill か) が未確定。0 化の機構が決まらない | #3112 [FLE-13] (既存・OPEN) へコメント済み: 書込み元 VA の特定 (書込み元 PC の記録) を修復範囲に含める |
| fill → P・Q の 0 化の対照 (root 無し lift + `FLE_DIAG_NULLFILL=1` で P・Q が残るか。§1) | 対照が無く、fill の 0 化を実測と言えない | #3112 [FLE-13] (既存・OPEN) へコメント済み: root 無し lift で同じ観測を取る |

## 5. 再測定と対照 (2026-10-15・main `321f1620e`・測定 commit `d677564bc`)

§1〜§4 (commit `d5d8336c3`) の後に main が進んだため、同じ観測を取り直した。#3112 が依頼した対照 (root 無し lift + `FLE_DIAG_NULLFILL=1`) も測った。

### 5.1 結論

- **受入 1 (入口の値): 未取得 (再確認)。** `0xd68d90` (切替)・`0xd69310` (`general.getRecPPB` 本体)・`0x13751d0` (icall 分岐の関数) の入口は、root 有り・root 無し (対照) のどちらでも 0 件。boot は unit 209 の先で止まり、`general.getRecPPB` の呼出し側に届かない。
- **対照 (#3112 の依頼): 実施。** root 無し lift + `FLE_DIAG_NULLFILL=1` で fill (`0x6a7b70`) を戻すと、P・Q への書込みは 0 件 (`fle_wwatch` 0 件)。root 有り route で見た P・Q の 0 化は、fill の buf=0 呼出しに由来すると推定する (5.3)。
- **切替条件: 未確定。** 入口に届かないため、実行時の P・Q・X の値は取れない。

### 5.2 測定 (`fle6_measure.sh` と `py233_getrecppb_probe.sh`・4 コア)

| 項目 | root 有り (shim・既定) | root 無し + NULLFILL=1 (対照) |
|---|---|---|
| units_run / 停止 | 209 / `exit` (`0x412a0d`) | 209 / `unlifted 0x6bbc20` |
| GetMem / FreeMem | 2,314 / 1,199 | 2,314 / 1,200 |
| IPP 判定 | NG (ptr `0x0`・rc=3・既知) | OK (ptr `0x7f10001c`) |
| fill `0x6a7b70` | 6 回 (dst `0x0`〜`0x1400000`・4 MiB 刻み) | 戻し (buf=0 の skip 計数 1,048,576) |
| P・Q への書込み (`FLE_WWATCH`) | 2 件 (`0x15e35c8`: `0x16ba808`→0・`0x15e4558`: `0x16ba7f0`→0) | 0 件 |
| `0xd68d90` / `0xd69310` / `0x13751d0` | 0 / 0 / 0 | 0 / 0 / 0 |
| 停止点 `0x412a0d` の P・Q・X | 0・0・0・0・X=0 | 未到達 |
| `0x6bbc20` (画素ストア) | 0 件 | 1 件 (site `0x6c9380`・矩形 (0,0,2^20,2^20)) |

工程 (実測・fle6 の段階時間): root 有り: gen-A 7 s・lift 83 s・clang 117 s・boot 25 s (計 3 分 52 秒)。probe: 2 分 13 秒。対照: lift 81 s・clang 97 s・boot 22 s (計 3 分 27 秒)。対照の probe: 2 分 08 秒。load は 0.5〜2.3。

### 5.3 解釈 (推定を含む)

- **P・Q の 0 化の経路 (推定)**: fill の buf=0 呼出しは dst を 0 から 4 MiB 刻みで進めて書くため、`.data` (`0x13a5000`〜`0x15e5008`) を含む範囲へ書き込む。native では dst=0 付近は未マップで AV すると推定される (#3112 と同じ見立て。未検証)。したがって root 有り route の停止点の 0 は、native の実行時の値ではない。
- **対照の残り**: fill を戻すと P・Q は残る (書込みが無い)。ただし同じ route は `0x6bbc20` (未 lift) で止まり、切替の入口に届かない。
- **未解明**: fill の呼出し回数が root 有り 6 回・対照 1,048,576 回 (skip 計数) と大きく違う。root 有りで fill の後に boot の流れが変わる理由は未確認 (#3112)。

### 5.4 到達範囲と必要な変更 (受入 2 の更新)

- 切替の入口へ至るには、boot の unit 209 の先で (a) buf=0 の fill の上流の修復 (#3112)、(b) `0x6bbc20` の先の進行 (#3770・#3771 で範囲を確認済み)、(c) `general.getRecPPB` (Python API のハンドラ・`REPORT_PY121`) を boot の後段から呼ぶ route が要る。(c) は未実装で、本 PR の範囲外。
- (c) は子 issue **#3987** [PY-289] に移した (親 #3690 の受入 1・3 も同じ子に移す)。

### 5.5 KPI (起動)

- 前後 (root 有り・main): units 209 → 209 (不変)。最初のウィンドウ: 無し (`MessageBoxA` → `exit(0)` at `0x412a0d`)。
- 本 PR は既定経路の build・boot 結果を変えない (観測 script の変更のみ)。対照 route は `FLE_DIAG_NULLFILL=1` の診断で、既定経路ではない。

### 5.6 検証

- 測定 commit: `d677564bc` (probe の変更。以後のコード差分は REPORT のみ)。
- 再現: `FL_WIN64_DIR`・`SS_EMSDK_ENV` を設定して、`FLE_BOOT_RUNS=shim FLE_BOOT_TAG=py233 bash tools/flelift/boot/fle6_measure.sh` → `bash tools/flelift/boot/py233_getrecppb_probe.sh`。対照は `FLE_EXTRA_ROOTS= FLE_BOOT_WORK=<work>/boot_rootless FLE_BOOT_RUNS=diag_shim FLE_BOOT_TAG=py233rl bash tools/flelift/boot/fle6_measure.sh` → `FLE_BOOT_WORK=<work>/boot_rootless FLE_DIAG_NULLFILL=1 bash tools/flelift/boot/py233_getrecppb_probe.sh`。
- 結果 JSON: `tools/flelift/boot/results/boot_summary_py233.json`・`boot_summary_py233rl_diag_shim.json` (絶対パスを含まない)。
- `fle_e2e.sh` は未実行 (既定経路の build・boot を変えないため)。

### 5.7 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 切替入口 `0xd68d90` の実行時の値 (受入 1・3) | 切替条件が決まらない | 子 issue #3987 [PY-289] (本 PR で起票) |
| buf=0 の fill の上流 (P・Q の 0 化) | 停止点の 0 は実行時の値ではない | #3112 [FLE-13] (open) |
| fill の呼出し回数の差 (6 回 / 1,048,576 回) | 対照の解釈 | #3112 |
| STX の書込み元 PC の記録 (fill か) | 0 化の機構が推定のまま | #3112 |
