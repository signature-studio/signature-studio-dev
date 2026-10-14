# #2780: unit 492 OOB の `4473f0` 配列長計算 (`0x92492493` 乗算) の戻り値の実測

親: #1046 (経緯は `REPORT_1046.md` §10〜§19)。測定 commit: `9b8f133f` (コードを変えた最後の commit。gated probe の追加)。
本節の REPORT は、測定 commit から HEAD までの差分を §8 に示す。

## 0. 結論

- **受入 (`4473f0` の `0x92492493` 乗算の戻り値が OOB の原因か) は実測で「原因ではない」と確定した。**
  unit 17 (正常) は乗算の剰余 `esi` (= `(i+5) % 7`) が i=1..7 で `6,0,1,2,3,4,5` と期待どおり。unit 492 (OOB) は trap までの i=1,2 で `6,0` と同じ値 (§3)。乗算の戻り値は正しい。
- OOB の入力は、`4473f0` の 2 回目の `function_4133f0` 呼出し (i=2、`dest = 0x10aa1160`) の旧値 `*dest = 0x1_00000003`。
  `4133f0` (C 版 `UStrAsg`) が `old - 0x10` を読んで wasm32 の範囲外になる。`4473f0` のループは同じ番地に書いていない。
- `0x10aa1160` の値は、読取りのみの計装 (通常 build) で unit 432・477・484 の書込みの積み重ねと分かった (§5)。上位 dword は unit 432 の 8B 書込み由来、下位 dword は unit 477・484 の 4B 書込み由来。書込みの主体は未特定 (子 issue へ)。

## 1. 素材と再現 (HEAD `9b8f133f`)

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin` 確認)。`toolchain-*` は `/opt`、`work-m11`・`work-liftdiff` は worktree の `tools/m11/work`・`tools/liftdiff/work` に展開。
- 既定 build: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_gen_ir2.sh` rc 0 (30.5 s、490,735 行、ldfix applied) → `bash tools/m11/m11_build.sh` rc 0 → `node tools/m11/trap_triage/survey_units.mjs <out>.json`。
- 計装 build: `M11_PROBE_2780=1 bash tools/m11/m11_build.sh` (IR 側 `trap_triage/probe2780_ir.py`・C 側 `m11_rt.c` の `m11_p2780_put`)。読出し: `node tools/m11/trap_triage/probe_2780_units.mjs <out>.json`。
- 読取りのみ: `SV_WATCH=0x10aa1160 node tools/m11/trap_triage/probe_2780_watch.mjs 0 941` (既定 build で走らせる)。

## 2. 基準 survey (既定 build)

- HEAD `9b8f133f`: `ok 872 / miss 47 / other 1 / halt0 7 / oob 14 / noproc 1`。per-unit JSON は `cmp` で `a68bf026` の 3 回 (`base1`・`base2`・`base3`) と完全一致。
- REPORT_1046 §14 の基準 (`ok 870 / oob 16`) との差は、main の取り込み (`a68bf026`) で unit 304・555 が oob から外れたため。halt0 の 7 件 (114/245/279/314/509/647/895) は一致。unit 492 は oob のままで、frames (`4133f0 ← 4473f0 ← 446400 ← 446ad0 ← ad5700`) も一致。

## 3. `4473f0` の乗算の戻り値 (実測)

`4473f0` の IR (`boot_final.ll`) は `ecx = i+5` を符号付き 64bit 積 `× -1840700269` (= 0x92492493) の上位 32bit で `/7` する (`sar 2` と符号補正)。剰余 `esi = ecx - 7*(ecx/7)` が `r8d = esi+0x31` (`446370` の ID → `423560` の検索) に入る。

| i | ecx (= i+5) | esi (実測, unit 17) | esi (実測, unit 492) | 期待 `(i+5)%7` |
|--:|--:|--:|--:|--:|
| 1 | 6 | 6 | 6 | 6 |
| 2 | 7 | 0 | 0 | 0 |
| 3 | 8 | 1 | — | 1 |
| 4 | 9 | 2 | — | 2 |
| 5 | 10 | 3 | — | 3 |
| 6 | 11 | 4 | — | 4 |
| 7 | 12 | 5 | — | 5 |

- unit 492 は i=2 の途中 (2 回目の `4133f0` 呼出し) で trap するため i=3 以降の記録は無い。i=1,2 の値は unit 17 と一致。
- `esi` の流れ: `4473f0` → `447df0` (r8 を素通し) → `446370` の `r8d` → `423560` の ID 引数 (検索)。検索が当たると slot に値が入るが、本 unit では slot1・slot2 とも 0 (実測 tag 3・4) で、この経路には入らなかった。`447df0` の表参照の添字は `r9d = i-1` で乗算と独立。OOB の入力 (dest2 の旧値) は、乗算の結果とは無関係に §5 の書込みで決まる。

## 4. OOB の入力 (probe build 実測)

probe build (`M11_PROBE_2780=1`) の unit 別 kind は既定 build の `base1.json` と完全一致 (計装が挙動を変えていない)。`4473f0` の 1 反復の記録 (tag: 0=i, 1=ecx, 2=esi, 3=slot1 (447df0 後), 4=slot2, 5=arg2, 6=arg1, 7=dest1 (`rdi`), 8=*dest1 (旧値), 9=dest2 (`rdi+0x38`), 10=*dest2 (旧値)):

- unit 17 (`arg2 = 0x10aa1000`): i=1..7 の全 `*dest` 旧値は 0。dest2 は `0x10aa1138, …, 0x10aa1168`。i=6 の dest2 `0x10aa1160` の旧値は 0。
- unit 492 (`arg2 = 0x10aa1020`):
  - i=1: dest1 `0x10aa1120` 旧値 `0x10be5770` (有効な値・trap せず)、dest2 `0x10aa1158` 旧値 0。
  - i=2: dest1 `0x10aa1128` 旧値 0、slot1=0、slot2=0、**dest2 `0x10aa1160` 旧値 `0x1_00000003`** → `4133f0` (C 版) の `old - 0x10` が範囲外で trap。

`dest2 = arg2 + 0x100 + 8*(i-1) + 0x38` で、unit 17 と unit 492 の差は `arg2` の差 (`0x20`) だけ。`arg2` は `446400` の `rcx` (= `446ad0` 由来のオブジェクト)。

## 5. `0x10aa1160` の値遷移 (読取りのみ・既定 build)

`probe_2780_watch.mjs` で各 unit の前後の値を読んだ (既定 build、IR・C 不変)。抜粋:

```
unit 415 ok 0x8b480000_16158d -> 0xf960
unit 424 ok 0xf960 -> 0x1_1029fe1c
unit 426 ok 0x1_1029fe1c -> 0x10e1ac
unit 427 ok 0x10e1ac -> 0x2636a8
unit 429 ok 0x2636a8 -> 0xf960
unit 432 ok 0xf960 -> 0x1_1029fe28      ← 8B 書込み (上位 dword = 1)
unit 477 exc 0x1_1029fe28 -> 0x1_2      ← 下位 dword のみ 2 に変化 (4B 書込み)
unit 484 exc 0x1_2 -> 0x1_3             ← 下位 dword のみ 3 に変化 (4B 書込み)
unit 492 exc 0x1_3 -> 0x0               ← 旧値 0x1_00000003 を読んだ後、UStrAsg が dest = s (0) を書く
```

- 上位 dword の `1` は unit 432 の 8B 書込み由来、下位 dword は unit 477 と 484 の 4B 書込み由来。`0x1_00000003` は、どの単一の書込みにもない混在値。
- unit 477・484 の遷移は REPORT_1046 §14 の `0x10a9f910` の遷移 (`0x1_2 → 0x1_3`) と同じ形。REPORT_2672 は `0x10a9f910` の unit 477 の下位 4B 書込みの主体を C 版 `function_4133f0` の shadow stack 局所 (`u32 len`, `m11_ov.c:345`) と特定している。`0x10aa1160` の書込み主体は未確認。

## 6. 解釈 (仮説を含む)

- `4473f0` は `dest1`・`dest2` (`arg2+0x100..+0x170`) を、自分では初期化せず `UStrAsg` の旧値として読む (`old = Q(dest)` を読んでから `Q(dest) = s` を書く)。この領域の初期化 (呼出し元の系列) が native で行われ、lift で欠けるかは **未確認**。
- 欠落の型: D17 (`DEFECTS.md`: 64bit 局所の 0 初期化が 4B store に縮み、上位 4B が残る) に似るが、本件は下位 dword も残骸 (unit 477・484 の 4B 書込み) で、D17 そのものとは断定できない。類型は **未確定**。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x10aa1160` の下位 4B 書込み (unit 477・484) と 8B 書込み (unit 432) の主体 (IR site・C 関数) | OOB 入力の出自が未確定 | 子 issue (本 PR の後に起票。番号は PR 本文・issue コメントに記載) |
| `arg2` の 8 要素配列 (`+0x100..+0x170`) を native で誰が初期化するか、lift で欠けるか | 修復 (初期化の復元) の方針が未確定 | 同上 |
| 類型 (D17 / 別類型) の判定 | DEFECTS の登録が未確定 | 同上 |

## 8. 差分 0 の証跡

- 測定 commit: `9b8f133f`。以後の差分は本 REPORT と `docs/DOC_MAP.md` のみ (下記コマンドで確認)。
- `git diff --stat 9b8f133f HEAD -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_rt.c tools/m11/m11_ov.c tools/m11/trap_triage/survey_units.mjs tools/m11/trap_triage/probe2780_ir.py tools/m11/trap_triage/probe_2780_units.mjs tools/m11/trap_triage/probe_2780_watch.mjs`: 空 (コード差分 0)。
