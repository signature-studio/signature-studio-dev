# Massive X MX-63 (#5908): U3e pdata 始点 47 件と 42 件の差の切り分け

- 解析日: 2026-10-16 / 親 #5019 (MX-54) / 前段 #4989 (MX-52) の U3e 残件
- 素材: `plugins-massivex` → `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`。`Massive X.vst3` = 95,356,824 B・md5 `622993e7…` (REPORT_MX33 §0 と一致)。PE は repo 外 (`$RUNNER_TEMP`)。

## 0. 結論 (先出し)

1. **件数の由来**: 47 は `mx4989_probe.py` (must-def 判定・最初に当たった site で F を数える)。42 は `mx54_u3e.py` (seeds のみ・may-def 0 かつ前段 call なしの site)。両方を正として残す (#5908 の R7 既定案)。
2. **pdata 始点 47 件の内訳**: E 43 件 (源側の証拠あり) と除外 4 件。`mx54` の 42 件は E 43 件のうち seeds 由来の 42 件で、差は `0x1a11e00` (one_round のみ) の 1 件。
3. **issue 本文の site 分類を訂正**: `0x15d4c00` は「前段 call なし」ではなく **F 内で xmm4 が定義済みの経路がある (D)**。残り 3 件 (`0x1191850`・`0x6be100`・`0x6beae0`) は前段 call あり (C) で、一致する。`0x1a11e00` は E。
4. **G 側の入口読みは成立しない (未解決)**: E 43 件の転送先 G は、いずれも pdata 始点ではなく、pdata 関数の**途中**にある (43/43)。capstone の線形復号では命令境界は 7 件のみで、35 件は非境界だった。binutils objdump による検算 (§6) は PE 上で再測定した (測定 commit `b5bf50fb0`)。途中の 42 件 (境界 7 + 非境界 35) について、capstone は境界 7 件、objdump は G が線形境界の件数 4 件と判定した (両者の食い違い 3 件の原因は未確定)。objdump で非境界の 31 件は再同期までの命令数が 40 以内。旧 objdump 数値の撤回は ELF 形式に限定した (§6)。G は pdata 関数の入口ではないため、入口 livein の読みは根拠にならない。G が実際に転送値を要求するかは判定できない。

## 1. 手順と測定

**本 run の測定 (PE 実測・測定 commit = `b5bf50fb0`・素材 `plugins-massivex`)**: `Massive X.vst3` = 95,356,824 B・md5 `622993e76565f49c094063a2b717d6ca` (`parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`・extract の checksum 不一致 0/125 は既知事象)。

| 実行 | 結果 | 経過 | load (start → end) |
|---|---|---|---|
| `mx6_e2e.sh` (`MX_PE` = 上記 PE) | rc 0・全判定 PASS | 45 s | 1.25 0.62 0.25 → 1.12 0.68 0.29 |
| `mx63_u3e_split.py` | population 604・E 43・D 825・C 1549・G0 351・G 26 | 4.9 s | — |
| `mx63_g_containment.py` | 途中・命令境界 7 / 途中・非境界 35 / 範囲外 1 | 0.2 s | — |
| `mx63_g_objdump_check.py` (`b5bf50fb0`) | n 35・転送 site の call/jmp が G と一致 35・G が線形境界 4・直接到達 4・間接 jmp を含む関数 1・非境界の再同期 31 | 1.0 s | — |
| 旧 `mx63_g_objdump_check.py` (`ea8745a84`・`c87be6bc1`) | 同上 (35 / 35 / 4 / 4 / 1 / 31) | 1.0 s | — |

- 測定 commit から HEAD までのコード差分: `git diff b5bf50fb0 HEAD -- tools/targets/massivex/dsp` は、本 REPORT の commit 以外は 0 行 (HEAD 時点で確認する)。
- 測定 commit 以前の変更 (`ea8745a84` → `b5bf50fb0`) は `mx63_g_objdump_check.py` の解析修正のみ。

**以下は測定 commit `dba7c5908` の記録 (本 run では未再測定)**

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

## 3b. 再測定の範囲

- 本 run の PE 実測は §1 の表 (測定 commit `b5bf50fb0`) のとおり。`mx63_g_entry_check.py` は新規追加だが、本 run では **実行していない** (構文確認のみ)。その出力に基づく記述は無い。
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
| 非境界 G 31 件の真偽 (途中の入口か、復号の誤りか) | G の入口 livein の判定は未確定。転送先の関数先頭は確定していない | #5908 (残件) |

## 6. run 4: binutils objdump による独立検算 (U3e 残件 1) — 数値は撤回

- **撤回 (ELF 形式に限る)**: 前の commit `ea8745a84`・`c87be6bc1` の objdump 検算の数値 (転送 site 35/35・G 境界 4/35・直接到達 4/35・間接 jmp を含む関数 1) は、**ELF 形式の入力に対しては採らない**。理由: 飛び先抽出が `0x` 付きの形だけを読んでおり、ELF の `-M intel` 出力 (`call   1129 <f>`、`0x` なし) を読めなかった。その結果 `site_target` が常に `None`、すべての `jmp` を間接として数えていた。
- **PE に対しては撤回しない**: PE の `objdump -d -M intel` は `call   0x180d789c4` のように `0x` 付きで出る。旧スクリプトも PE 上で 35 / 35 / 4 / 4 / 1 / 31 を出し、新スクリプトと一致した (§1 の表)。PE 上の旧数値は、読み取り不具合の影響を受けていない。
- **修正 (本 commit)**: 飛び先抽出を `jump_target()` に 1 か所にまとめ、`0x` の有無の両方を読むようにした (`JUMP_RE = (call|jmp|j\w+)\s+(?:0x)?([0-9a-f]+)`)。`flow()` は module 関数にし、ELF で単体検証できるようにした。
- **ELF による検証 (`gcc -O0 -no-pie` の小さな例、本 run で実施)**:
  - 直接 `call` 2 件・`jle`/`jg`・直接 `jmp` の飛び先は、いずれも `0x` なしの objdump 行から抽出できた (旧 regex は全件取りこぼし)。
  - 関数 `f` (25 命令) は `ret` 直前までの 24 命令に到達し、未到達は `ret` 後の詰め物 1 件のみ。
  - computed goto (`jmp rax`) を含む関数で、間接 jmp を 1 件と数えた (期待値 1)。
- **PE 上の再測定**: 実施済み (§1 の表・測定 commit `b5bf50fb0`・`plugins-massivex` 由来の `Massive X.vst3`)。
- capstone と objdump の境界判定の食い違い: capstone は境界 7、objdump は境界 4 (G が線形境界)。原因は未確定。旧 §6 の説明 (capstone の線形復号が途中の復号不能命令で止まる) は原因の確認をしていないため、残す場合は仮説と明記する。
- 結論: G 側の判定 (受入 1) は、上記の食い違いが解消するまで**未確定**。件数の正 (47 / 42) は決めない (R7 (a))。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| capstone (境界 7) と objdump (境界 4) の境界判定の食い違い (原因未確定) | G 側の判定 (受入 1) が確定しない | #5908 (残件) |
| 非境界 G 31 件の真偽 (復号誤りか、途中の入口か) | U3e の判定 (MX-6 入口 livein 0 の陰性が過小検出か) を確定できない | #5908 (残件) |
| 件数の正 (47 / 42) | 両方記録。正は PM 判断 | #5908 |

## 7. run 5: 非境界 G の線形復号の食い違いの原因 (U3e 残件 2)

- 測定 commit: `32c1f5d9c` (origin/main)。PE = `plugins-massivex` 由来の `Massive X.vst3` (md5 `622993e7…` 一致)。素材は `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key` で展開 (extract の checksum 不一致 0/125 は §1 と同じ既知事象)。
- `mx6_e2e.sh`: rc 0・59 s・load 0.59 0.30 0.12 → 0.89 0.45 0.18・全判定 PASS。
- `mx63_u3e_split.py`: population 604・E 43・D 825・C 1549・G0 351・G 26 (§1 と一致)。
- `mx63_g_containment.py`: 途中・命令境界 7 / 途中・非境界 35 / 範囲外 1 (§1 と一致)。
- `mx63_g_objdump_check.py`: n 35・転送 site 一致 35・G 線形境界 4・直接到達 4・間接 jmp 関数 1・再同期 31 (§1 と一致)。
- `mx63_g_bad_bytes.py` (本 run で新規): 非境界 35 件の G について、G の関数内の objdump 線形復号に (bad) があるかを数えた。

| 判定 (`mx63_g_bad_bytes.py`) | 件数 |
|---|---|
| G より手前に (bad) がある (線形復号が G の手前で信用できない) | 23 |
| 関数全体に (bad) が無い (線形復号は関数全体で成立し、G は命令境界でない) | 12 |
| G が objdump の線形境界 | 4 |

### 食い違いの原因 (確認済み)

- capstone は G より手前の (bad) バイトで線形復号を止める (23 件で `cs_stop` < G)。objdump は (bad) を 1 バイト飛ばして再同期するため、同じ区間を続けて読める。
- したがって capstone の境界 7 と objdump の境界 4 の差は、主に「(bad) の後の再同期の扱い」の違いで説明できる。G 側の線形境界の数値は、どちらの復号も信用できない区間 (23 件) では判定に使えない。
- 実際に (bad) の位置の例: `0xd789c4` (G) は手前の `0xd770c9` で `(bad)` (バイト `d6 00 ff 84 c0 …`)。`0xd0c546` は `0xd09dd8` で `(bad)` (`c5 55 cf 00 ff …`)。

### 判定 (受入 1 の G 側)

- **信用できる区間で判定できたのは 12 件**: 関数全体に (bad) が無く、線形復号は成立しているが、G は命令境界でない。この 12 件は「G は関数途中の非境界」であり、G の入口 livein を入口値の証拠に使えない。
- **残り 23 件は未確認**: (bad) の後の復号が正しいかを、この検算では確定できない。G が途中の入口か、(bad) を含む埋め込みデータ・復号誤りかは区別できない。
- 境界 4 件 (`0x850d80`・`0x86d66c`・`0xa2e5d0`・`0xd0c546`) は、objdump の線形境界かつ直接制御フローで到達するため、途中の入口として成立し得る (§6 と同じ)。ただし capstone では境界でないため、確定ではない。

### 件数 (変化なし)

- 47 (`mx4989_probe.py`) と 42 (`mx54_u3e.py`) は両方記録し、正は決めない (R7 (a))。本 run で件数は変えない。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (bad) を含む関数の後半 23 件の G が途中の入口か、復号誤りか | G 側の判定 (受入 1) が確定しない。MX-6 入口 livein 0 の陰性が過小検出か未確定 | #5908 (残件) |
| 件数の正 (47 / 42) | 両方記録。正は PM 判断 | #5908 |
