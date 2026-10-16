# MX-54 (#5019) 付録: U3e の件数 47 と 42 の切り分け

本体の結論と件数の表は [REPORT_MX33.md](REPORT_MX33.md) §7.1。ここは 47 件 (appendix・probe) と 42 件 (`mx54_u3e.py`) の差の実測。

## 1. 測定条件

- 素材: `plugins-massivex` → `Massive X.vst3` 95,356,824 B・md5 `622993e76565f49c094063a2b717d6ca` (一致)。展開は `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`。
- 入力: `mx6_e2e.sh` が生成する `vectorcall.json` と `surface_seeds_x64c.json` (exit 0・60 s・load 0.45 0.47 0.23 → 0.88 0.58 0.29)。
- probe: `mx4989_probe.py` を commit `2fc5debe2` から `git archive` で取り出して実行 (repo に追加していない)。実行時間 151 s。
- `mx54_u3e.py`: 同じ PE・同じ入力で実行 (exit 0)。

## 2. 結果

| 測定 | pdata 始点 F | 全 F | 備考 |
|---|--:|--:|---|
| probe `u3e` (`mx4989_probe.py`) | **47** | 193 | appendix の 47 / 193 を同一 PE で再現 |
| `mx54_u3e.py` | **42** | 42 | seeds の pdata 始点 566 件が母集団 |

- 重なり: mx54 の 42 件は probe の 47 件の真部分集合 (mx54 のみ 0 件)。
- probe のみの 5 件: `0x1191850`・`0x15d4c00`・`0x6be100`・`0x6beae0` (seeds と one_round の両方)、`0x1a11e00` (one_round のみ)。

## 3. 差 5 件の該当 site (CFG 直前の命令)

| F | 転送 site | 命令 | F 内の前段 call | 切り分け |
|---|---|---|---|---|
| `0x6be100` | `0x6be1f7` | call | あり | mx54 の「前段 call 除外」の規則で落ちたと読める (未確認) |
| `0x6beae0` | `0x6bf027` | call | あり | 同上 (未確認) |
| `0x1191850` | `0x11918a5` | call | あり | 同上 (未確認) |
| `0x15d4c00` | `0x15d4c58` | jmp | なし | **未切り分け** |
| `0x1a11e00` | `0x1a11e39` | call | なし | **未切り分け** |

- 前段 call 除外の規則は probe に無い (probe は call を見ない)。
- 前段 call なしの 2 件は、mx54 の may-def 判定で xmm4/5 の定義ありとされた可能性があるが、実測していない。

## 4. docstring のフィルタ (F の入口 livein xmm4/5 = 0) の影響

- mx54 の 42 候補 F は、`vectorcall.json` の `livein45` がすべて空 (= xmm4/5 の入口 livein 0)。42/42。
- よって入口 livein のフィルタを掛けても、mx54 の 42 件は変わらない。フィルタ付きの件数は「42 件」と一致する。

## 5. 判定

- 47 (probe・appendix の値) は同一 PE で再現した。
- 42 (mx54) は、前段 call 除外の規則の結果。差 5 件のうち 2 件は未切り分けのまま。
- 件数の扱い (47 と 42 のどちらを本 issue の正とするか) は PM 判断。両方の値と由来を REPORT に残す。
