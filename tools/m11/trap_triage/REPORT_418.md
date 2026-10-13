# #418: 409470 (ReallocMem) の C 転記が unit 884 でハングする原因

**判定: 部分達成。受入条件 1 (原因特定) は達成、2 (再適用 + 回帰 0) は未達、3 (ネガコン) は達成。**
原因は 409470 の転記ミスではなく、**別関数 `function_410320` (System._ClassCreate) の脱落**。

## 1. 原因 (実測)

| 段階 | 実測 |
|---|---|
| 転記版 409470 を単独適用 | `SV_ONLY=884` で 60 s 超ハング (再現) |
| 409470 の引数 | 1 回目 `pv=c53d80 *pv=c60530 size=c00`。`*pv` が **VMT 領域 (.text)** を指し、`408040` に入ると `[*pv-8]=0xcccccccccccccccc` (padding) を読んで戻らない |
| 呼出元 | `1268010 → 1267c90 → 10601e0 → 410320 → ...`: `10601e0` が `410320(self, alloc)` の戻り値をオブジェクトとして使う |
| 根本 | `410320` の機械語は `test dl,dl; jl skip; mov rcx,rax; call [rax-0x30]` (= VMT vmtNewInstance)。RetDec は間接 call を落とし `ret arg1` にした (IR `ret i64 %arg1`)。**494 call site 全てで「生成されたオブジェクト」が TClass (VMT) 自身**になる |
| 従来 (RetDec 版 409470) はなぜ戻ったか | **未検証の仮説**: deref 脱落した 409470 は `P` 自体 (変数のアドレス) を旧ブロックとして扱うため、不正なヘッダを読まずに別経路へ進んだ。実測していない |

分類: 「転記の誤り」ではなく **「別関数の脱落」** (issue の 3 候補のうち 3 番目)。409470 の C 転記 (逆アセンブル boot0.drc.dsm 409470..4094e6 と突合) 自体は正しい。

## 2. 410320 を転記すると何が起きたか

- vmtNewInstance の既定実体 `0x40f960` (`GetMem([self-0x80])` + `InitInstance 0x40fb40`) は **boot closure 外**で disp 表に無く、`m11_icall` は icall-miss → 0 を返す (`slot=f960`)。オブジェクトが NULL になり、unit 884 は halt0 (ハング解消)。
- `0x40f960` 相当を C で補った版 (`GetMem(D(self-0x80))` + 0 埋め + vptr 設定) では unit 884 単独は OOB (ハングせず)。
- ただし 409470 + 410320 を両方入れた全 942 unit survey は **unit 114 で新たにハング**する。

## 3. 新ハングの最小化 (`ddmin_units.py`)

全 unit 0–114 でのみハングし、50–114 / 0–49+114 では完走 → unit 間の状態依存。delta debugging で
**最小集合 `{1, 17, 45, 95, 114}`** (この 5 unit を順に実行すると 114 で停止しない)。
`--prof` 上位: `function_5c00e0` 77% / `function_439670` 14% (= 5c00e0 内の `[node+0]` リンクリスト走査ループ
`5c0138..5c0181`。リストが循環している疑い)。

切り分け (最小集合で実行):

| 構成 | 完走 |
|---|---|
| 転記なし (HEAD) | はい |
| 409470 のみ (=#414 で revert した構成) | はい (※ unit 884 単独はハング。この集合には 884 を含まない) |
| 410320 のみ | **いいえ (ハング)** |
| 409470 + 410320 | いいえ |

つまり 410320 の補完実装 (NewInstance の InitInstance 相当の欠落: interface vptr 設定・ゼロ初期化範囲など) が
不完全で、5c00e0 のリストを壊している可能性が高い。**未確定** (循環の生成元は未特定)。

## 4. 再現手順

```sh
cd tools/m11   # work/ = work-m11 展開済み。capstone/pefile (pip) が要る
git apply trap_triage/ov_409470_410320_experiment.patch                    # 409470 + 410320 の C 転記 (実験版)
bash m11_build.sh
SV_ONLY=884 timeout 60 node trap_triage/survey_units.mjs /dev/null        # 409470 のみ → ハング (patch の 410320 を外した場合)
SV_ONLY=1,17,45,95,114 timeout 10 node trap_triage/survey_units.mjs /dev/null   # 410320 補完版 → 114 でハング
python3 trap_triage/ddmin_units.py 0,1,...,114                             # unit 集合の最小化
```

ネガコン: `git checkout`/patch を外して `m11_build.sh` → `survey_units.mjs` は
`ok 830 / oob 44 / halt0 20 / miss 46 / abort 1 / noproc 1` (trap 65) の従来結果に戻る (実測)。

注: 本 runner のスナップショットでは HEAD (fa918df) の survey は ok 830 / trap 65 で、#414 本文の ok 829 / trap 66 と
1 unit 異なる (work-m11 の boot_final3.ll は 2026-10-10 生成)。回帰判定は同一 runner の HEAD 比で行った。

## 5. 未解決

- 410320 補完版で 5c00e0 のリストが循環する原因 (`InitInstance 0x40fb40` の実体は closure 外。interface table 初期化 (vptr の追加設定)
  を省いている可能性)。次の手: 0x40fb40 の機械語を逆アセンブルで転記し、unit 114 でハングしない状態で 884 を通す。
- 受入条件 2 (409470 再適用で回帰 0): 410320 が先決。**本 PR は転記を採用しない** (m11_ov.c 無変更)。実験 patch のみ保存。

> **更新 (#474)**: 上記の未解決は解決済み。unit 114 のハング原因は `InitInstance 0x40fb40` ではなく `function_5c0270` の unlink の deref 脱落で、
> 409470 + 410320 を再採用して survey 回帰 0 (ok 839 / trap 56)。詳細は `REPORT_474.md`。
