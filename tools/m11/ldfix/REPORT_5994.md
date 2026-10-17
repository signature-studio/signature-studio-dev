# #5994 (LD-295): first-deref-not-entry 修復 関数群 B (10 関数) の survey 到達理由の記録 — 部分達成

**判定: 部分達成**。10 関数それぞれについて、survey で到達しない状況と直接呼び出し元を記録した (§2)。呼び出し元の到達は測っていない。survey の計装で呼び出し元を見る測定は、この run では完了できなかった (§4)。

先行: #3194 (`REPORT_930.md`・`REPORT_1325.md`)・#3195 (`REPORT_3195.md`)。群 A は #5993。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 10 関数 (db6480・dc27c0・ddd4d0・41b8d0・41b970・449550・44fb40・784ed0・c40420・f552a0) について、survey で到達しない理由 (呼び出し元・計装の届かない経路) を関数ごとに REPORT に記録 | **一部**。呼び出し元 (IR の直接呼び出し元と、間接呼び出しの trampoline 経路) は §2 に関数ごとに記録した。呼び出し元が survey で到達するかは測っていない。そのため「なぜ到達しないか」の機構は未確定 (§3) |

## 2. 関数ごとの記録

測定の入力: `work/boot_final3.ll` (sha256 先頭 16 桁 `010451add5147d37`・529468 行。`work-m11.tar.zst` 同梱)。survey の既存結果: `results/reach_930.json` (942 unit)・`results/reach_1325_head.json` (942 unit)。

「kind=ok で入口に hit」は、その関数の入口計装が kind=ok の unit で 1 回以上 hit したもの。

| 関数 | survey kind=ok hit | 他 kind の hit | IR の直接呼び出し元 (2 段目) | 間接 call 経路 (trampoline) |
|---|---|---|---|---|
| db6480 | 0 | — | dc25f0 (→ dc27c0) | 有 (`m11_tr_function_db6480`) |
| dc27c0 | 0 | — | dbde10 (→ 10348b0) | 有 |
| ddd4d0 | 0 | — | ddeca0 (→ de10c0) | 有 |
| 41b8d0 | 0 | — | 41bd20 (→ 41bff0)・41be80 (→ 41c040) | 有 |
| 41b970 | 0 | — | 41bd20・41be80 (同上) | 有 |
| 449550 | 0 | — | 449600 (→ 50a8c0・50aa70・50abe0・50ad30・528150)・47a250 (→ 42 関数) | 有 |
| 44fb40 | 0 | — | 44fab0 (→ 44fce0) | 有 |
| 784ed0 | 0 | — | 785220 (→ 7878c0・78bab0・78c110)・786180 (→ 785a90) | 有 |
| c40420 | 0 | — | d341b0 (→ d34290) | 有 |
| f552a0 | 0 | — | f3c7b0 (→ f40840) | 有 |

- 関数ごとの hit 件数は、committed 2 本の survey で確認した。41b8d0・41b970・449550・44fb40・784ed0・c40420・f552a0・db6480・dc27c0・ddd4d0 は、どちらの JSON でも kind=ok の hit が 0。
- 40fe90 は reach_1325_head で oob (unit 745) と halt0 (unit 895) の hit だけ。この run の対象外。
- 間接 call 経路は、関数の 2 段目呼び出し元として `m11_tr_function_*` が出る (`m11_build.sh` の間接 call トランポリン)。どの unit がこの経路を通るかは未計測。
- 呼び出し元の 2 段目が多い 449550 (← 47a250 の 42 呼び出し元) と 784ed0 (← 785220・786180) は、呼び出し元のうち survey で到達するものの有無を個別に見る必要がある (未実施)。

計算は `tools/m11/ldfix/callers_5994.py` (静的・計装なし)。出力:

```
python3 tools/m11/ldfix/callers_5994.py work/boot_final3.ll 101d180 db6480 dc27c0 ddd4d0 41b8d0 41b970 449550 44fb40 784ed0 c40420 f552a0
```

## 3. 未確定と理由

- 「survey で到達しない」の機構 (呼び出し元が kind=ok の unit で通らないのか、通っても入口計装に届かないのか) は、この REPORT では確定していない。
- 理由: 呼び出し元の計装付き survey を取り直すには、committed の `work-m11` と同じ build が必要。`work-m11` 同梱の `obj/*.o` は HEAD の C ソース (`m11_ov.c`・`m11_rt.c`・`m11_win.c`) より古く、`m11_build.sh` も `work/ir_conditions.json` を要求する (同梱されていない)。
- 試行: 同梱 obj を HEAD の C から再コンパイルして `reach_509.sh` を実行した。23 関数の計装で結果は kind 分布 ok 136・miss 797・oob 8・halt0 1。committed (ok 870・miss 47) と一致しないため、この結果は呼び出し元の到達の根拠に使わない。
- したがって §2 の呼び出し元は静的な事実 (IR の direct call) だけで、到達の事実ではない。

## 4. 未実施と残件

| 残件 | 影響 | 起票先 |
|---|---|---|
| 呼び出し元 (§2 の 2 段目) の kind=ok 到達を、committed と同じ build で計装して測る | 10 関数の「到達しない理由」の機構が未確定 | #5994 (本 issue)・#3194 |
| 同梱 obj の C 再コンパイルと `ir_conditions.json` の再現 (build 経路の確認) | 上の測定の前提 | #3194 |

- 子 issue は起票しない (測定の残件は親 #3194 の受入 4 に既にあり、本 issue の PR 本文の未解決表に書く)。
