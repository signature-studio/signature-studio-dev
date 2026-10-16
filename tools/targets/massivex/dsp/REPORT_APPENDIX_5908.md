# Massive X MX-63 (#5908): U3e pdata 始点 47 件と 42 件の差の切り分け

- 解析日: 2026-10-16 / 親 #5019 (MX-54) / 前段 #4989 (MX-52) の U3e 残件
- 素材: `plugins-massivex` → `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`。`Massive X.vst3` = 95,356,824 B・md5 `622993e7…` (REPORT_MX33 §0 と一致)。PE は repo 外 (`$RUNNER_TEMP`)。

## 0. 結論 (先出し)

1. **件数の由来**: 47 は `mx4989_probe.py` (must-def 判定・最初に当たった site で F を数える)。42 は `mx54_u3e.py` (seeds のみ・may-def 0 かつ前段 call なしの site)。両方を正として残す (#5908 の R7 既定案)。
2. **pdata 始点 47 件の内訳**: E 43 件 (源側の証拠あり) と除外 4 件。`mx54` の 42 件は E 43 件のうち seeds 由来の 42 件で、差は `0x1a11e00` (one_round のみ) の 1 件。
3. **issue 本文の site 分類を訂正**: `0x15d4c00` は「前段 call なし」ではなく **F 内で xmm4 が定義済みの経路がある (D)**。残り 3 件 (`0x1191850`・`0x6be100`・`0x6beae0`) は前段 call あり (C) で、一致する。`0x1a11e00` は E。
4. **G 側の入口読みは成立しない (未解決)**: E 43 件の転送先 G は、いずれも pdata 始点ではなく、pdata 関数の**途中**にある (43/43)。命令境界は 7 件のみで、35 件は線形復号の命令境界ではなく、1 件は pdata 範囲外。よって「G の入口 livein が立つ」は関数入口の読みになっておらず、G が実際に転送値を要求するかは判定できない。

## 1. 手順と測定 (測定 commit = `dba7c5908`・scripts は HEAD まで差分 0・本 run では再実行していない。出力は測定時の記録)

- `scripts/mx63_u3e_split.py`: 母集団 = seeds ∪ one_round の pdata 始点 604 件 (入口 livein xmm4/5 = 0)。各 F の direct call/jmp site を次で分類する。
  - D: F 内で xmm4/5 が (いずれかの経路で) 定義済み (may-def ≠ 0)
  - C: 前段に call がある (call は xmm0〜5 を clobber しうる)
  - E: 定義なし・前段 call なし (源側は入口値と同一)。G の入口 livein xmm4/5 ≠ 0
  - G0: G の入口 livein xmm4/5 = 0 / G: G が解析不能・text 外
- 実行: 3.8 s。site 数 D 825・C 1549・G0 351・G 26・E 43。
- `scripts/mx63_g_containment.py`: E 43 件の G の所在を調べる。実行: 4 s。
- 検算 (E8/E9 rel32 の再計算): 本 PR では未実施。再計算を行う script は本 PR に含めていない。よって「命令は正しく復号されている」は本 PR の根拠に含めない (§4 の判定は依らない)。
- 出力の出所: 以下の件数は、著者が測定 commit `dba7c5908` で実行したと記した値 (PR 本文の記載)。`plugins-massivex` 素材が無い run では再実行していない。
  - `python3 scripts/mx63_u3e_split.py <PE> <vectorcall.json> <out.json>`: population 604・E 43・site_cat D 825・C 1549・G0 351・G 26。
  - `python3 scripts/mx63_g_containment.py <PE> <split.json> <out.json>`: counts = pdata 始点 0・途中・命令境界 7・途中・命令境界でない 35・範囲外 1。

## 2. 47 件と 42 件の突合

| 集合 | 件数 | 内容 |
|---|---|---|
| probe 47 (`mx4989_probe` u3e・pdata 始点) | 47 | E 43 + 除外 4 |
| mx54 42 (`mx54_u3e`・seeds のみ) | 42 | E 43 のうち seeds 由来 42 (`0x1a11e00` が無い) |
| E (本 PR・seeds ∪ one_round) | 43 | seeds 42 + one_round のみ 1 (`0x1a11e00`) |

| site F | probe 47 | 分類 | 理由 |
|---|---|---|---|
| `0x15d4c00` | 含む | D | `0x15d4cfc` の jmp で may-def ≠ 0 (一部の経路で ymm4 が定義済み)。probe は must-def (全経路で未定義とは限らない形も数える) で判定するため含まれる。定義の判定規則の違い |
| `0x1191850` | 含む | C | 1 site (`0x1191898`) は G0 (G が xmm4/5 を要求しない)。次の site `0x11918a5` の前に call あり。probe は call を除外しないため数える |
| `0x6be100` | 含む | C | 全 7 候補 site の前段に call。probe は call を除外しないため数える |
| `0x6beae0` | 含む | C (E なし) | 候補 site 21 件のうち D 7 件・C 14 件。E は 0。probe は D/C を区別せず must-def で数えるため含まれる |
| `0x1a11e00` | 含む | E | `0x1a11e39` → G `0x2463a8e` (livein xmm4)。one_round のみ |

## 3. E 43 件の G の所在

`scripts/mx63_g_containment.py` の出力 (`counts`):

| G の所在 | 件数 |
|---|---|
| pdata 始点 | 0 |
| pdata 関数の途中・命令境界 | 7 |
| pdata 関数の途中・命令境界でない | 35 |
| pdata 範囲外 | 1 |

- 例: `0x6da2ae` → G `0x8020e3` (pdata 関数 `0x8016f0` の途中)。`0x8020e3` の復号は `or eax, 0xf6854504` で始まり、関数入口ではない。
- G は入口として線形解析された値で、途中のアドレスからの livein である。関数入口の livein ではない。

## 3b. 本 run の再測定 (未実行)

- 本 run (HEAD `e2a47bf3a` の fix) では、素材 `plugins-massivex` が `$ARTIFACTS_DIR` に無く (`fl-win64.tar.zst` のみ)、`fl-win64` 内にも Massive X の PE は無い。**`mx6_e2e.sh`・`mx63_u3e_split.py`・`mx63_g_containment.py` は本 run では実行していない。**
- 以前に記した実行結果 (46 s・load・全判定 PASS・PE md5 一致・件数の一致) は、本 run の測定ではないため削除した。§1 の値は測定 commit `dba7c5908` の記録である。
- `mx63_g_entry_check.py` は新規追加だが、本 run では **実行していない** (構文確認のみ)。その出力に基づく記述は無い。
- G の関数先頭の同定 (詰め物による判定を含む) は未実施。G 側の判定は未確定のまま (§4・§5)。

## 4. 判定

- **源側 (F の入口値が G へ届くこと)**: E 43 件は、F 内で xmm4/5 が定義されず前段 call もない site で、転送値は F の入口値と同一。
- **G 側 (G が転送値を入口で読むこと)**: 未確定。E 43 件の G は関数入口ではなく、入口 livein の読みは根拠にならない。
- よって、受入条件 (源側と G 側の両方の証拠) は満たせない。件数は 47 と 42 を両方記録し、正は決めない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| E 43 件の G が関数入口でない。G の入口 livein の読みが成立しない。転送先の関数化 (G の実入口の同定) が必要 | U3e の判定 (MX-6 の入口 livein 0 の陰性が過小検出か) を確定できない | #5908 (本 issue に残件として残す) |
| 件数の正 (47 / 42) の決定 | 件数を REPORT に両方記録。正は決めない | #5908 (R7 既定案) |
| `0x15d4c00` の表記 (issue 本文は「前段 call なし」) | 本 PR の表 §2 で D と訂正 | 本 PR で記録 (追加起票なし) |
