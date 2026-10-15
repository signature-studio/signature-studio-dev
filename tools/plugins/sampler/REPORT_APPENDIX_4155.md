# sampler REPORT 付録 (#4155 [PLG-F3-40]: VEX comis の機械語の消費命令と IR の 1:1 対応 / 欠落の切り分け)

> 親 #3241 の分割 1。正本の結論は `REPORT_APPENDIX_1774.md` §7c.1・§7c.3 (子 [PLG-F3-33] が消費条件の再導出を受ける)。
> 本書は照合の実測と欠落の段階の切り分け。 照合の道具は `tools/plugins/sampler/vex_comis_match.py`。

## 0. 要点

- 機械語の VEX comis と IR の VEX 呼び出しは、19252 で **14 件中 11 件**、19048 で **12 件中 8 件** が 1:1 で対応する (IR のみの VEX 呼び出しは 0 件)。
- **欠落は 19252 で 3 件、19048 で 4 件** (前回 run の「3 件 × 2 engine」の記述は 19048 について訂正)。 全件が、直前の `vcomisd` の `je`/`jb`/`jbe` の **fall-through 側の先頭基本ブロック** にある。
- 欠落の段階: `e.drc.c` (RetDec の C 出力) の時点で、当該 VA の注記 `// 0x...` が無い。 つまり **RetDec の CFG 構造化の段で fall-through の基本ブロックが落ちている**。 `lift_ranges.sh` の pass 段より前。 pass は欠落を再現できない (IR に無い呼び出しには触れない)。
- RetDec の CFG 警告 (`NonRecursiveCFGBuilder`) は、欠落 VA の範囲 (`0x180017xxx`・`0x18001dxxx`・`0x180040xxx`) に 0 件。 落とした経路は警告に出ていない (未特定)。

## 1. 測定

- 測定 commit: 本 PR の HEAD (`engine_lift.sh` の経路は main `1ff7c6880` と同一。 本 PR はコード変更が `tools/plugins/sampler/` の新規ファイルのみ)。
- 素材: fl-win64 (`block19252_PE.bin`・`block19048_PE.bin`)。 RetDec (`/opt/retdec`)・emsdk (`/opt/emsdk`) は runner の既存。
- `engine_lift.sh` (前景・timeout 900 s)、summary.csv:

| engine | summary.csv | unimpl (列 6) | emcc -c rc (素 / fixcmp / f80) | lift_s |
|---|---|---|---|---|
| 19252 | `19252,522,0,551,1,7,1,0,1,16,2,165,0,29,549,0` | 7 | 1 / 1 / 0 | 16 |
| 19048 | `19048,1658,0,1712,0,9,0,0,0,62,2,97,0,54,1710,0` | 9 | 0 / 0 / 0 | 62 |

- 注: unimpl の値 (19252 = 7・19048 = 9) は前回 run (4155 のコメント: 19252 = 7・19048 = 9) と一致。 `REPORT_APPENDIX_1774.md` §7c の表 (4 / 4) とは、main 側の変更で異なる (1774 の測定 commit 以降の差)。 本付録は現 main の値を使う。

## 2. 照合の出力 (`vex_comis_match.py`)

19252 (機械語 VEX 14 / IR の VEX 呼び出し 11。 出力の `IR:` 行は VEX のみ):

```
180017961 vcomisd -> je | IR:vcomisd
180017973 vcomisd -> jbe | IR MISSING (fn 0x180017640, VA in e.drc.c: no)
18001798d vcomisd -> je | IR MISSING (fn 0x180017640, VA in e.drc.c: no)
1800179c1 vcomisd -> jb | IR MISSING (fn 0x180017640, VA in e.drc.c: no)
18001a934 vcomisd -> je | IR:vcomisd
18001aab2 vcomisd -> ja | IR:vcomisd
18001aac0 vcomisd -> jb | IR:vcomisd
18001abd0 vcomisd -> jae | IR:vcomisd
18001abf6 vcomisd -> cmovae | IR:vcomisd
18001bb0d vucomisd -> ja | IR:vucomisd
18001bb1b vucomisd -> jbe | IR:vucomisd
18001bc03 vucomiss -> jne | IR:vucomiss
18001bd18 vucomiss -> cmovne | IR:vucomiss
18001be0a vucomiss -> cmovne | IR:vucomiss
missing in IR: 3
```

19048 (機械語 12):

```
18001c4cd vucomisd -> ja | IR:vucomisd
18001c4db vucomisd -> jbe | IR:vucomisd
18001c5c3 vucomiss -> jne | IR:vucomiss
18001c6d8 vucomiss -> cmovne | IR:vucomiss
18001c7ca vucomiss -> cmovne | IR:vucomiss
18001db8e vcomisd -> jbe | IR:vcomisd
18001dbc0 vcomisd -> jae | IR:vcomisd
18001dc45 vcomisd -> je | IR MISSING (fn 0x18001d7f0, VA in e.drc.c: no)
180040f11 vcomisd -> je | IR:vcomisd
180040f23 vcomisd -> jbe | IR MISSING (fn 0x180040bf0, VA in e.drc.c: no)
180040f3d vcomisd -> je | IR MISSING (fn 0x180040bf0, VA in e.drc.c: no)
180040f71 vcomisd -> jb | IR MISSING (fn 0x180040bf0, VA in e.drc.c: no)
missing in IR: 4
```

## 3. 欠落の原因の切り分け

- **機械語の形** (19252 `0x180017940` 付近、19048 `0x180040f00` 付近。 両者同形): `vcomisd xmm5, [..]` → `je 0x...` → (fall-through) `vpxor xmm5` → `vcomisd xmm0, xmm5` → `jbe` → ... 。 欠落の VA は fall-through 側の先頭 (`0x180017973`・`0x180040f23`) と、そこからさらに続く `vcomisd` (`0x18001798d`・`0x1800179c1`・`0x180040f3d`・`0x180040f71`)。
- **IR (`e.drc.ll`)**: `je` は `icmp eq` の値比較 (`%33 = icmp eq i64 %26, %32`) になり、`br` の偽側は `dec_label_pc_180017bb9` (`0x180017bb0` 側) に向く。 偽側 (`0x18001796f` 以降) の基本ブロックは、`e.drc.ll` にも `e.drc.c` にもラベルが無い。
- **C 出力 (`e.drc.c`)**: `function_180017640` の `if (result == v5)` の偽側が、`0x180017be0` (then 側) の後ろの `return` まで飛ぶ構造のみ。 fall-through の本体は存在しない。 19048 の `function_180040bf0` も同形。
- **結論**: 欠落は RetDec の CFG 構造化 (`e.drc.c` 生成) の段で起きている。 本 pass (`vex_comis_flags.py`) や `lift_ranges.sh` の後段の変更では直らない。 RetDec 側の起因 (どの変換が fall-through を捨てるか) は未特定。
- 補足: `function_18001d7f0` (19048 の欠落 1 件) は `0x18001dc45` の `je` (`0x18001dc49`) の fall-through が `0x18001dc4b` から続くが、同じく C 出力に注記が無い。 同類とみなすが、個別の関数の構造は未確認。

## 4. 起票先・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec が `vcomisd`→`je` の fall-through 基本ブロックを CFG 構造化で落とす原因 (どの変換か) が未特定 | 欠落 7 件 (19252: 3・19048: 4)。 その関数の VEX comis は flag が IR に出ない | 子 [PLG-F3-33] (#3241 側) の受入に含める (欠落の切り分けは本付録で完了、直し方は未) |
| 消費条件の再導出 (`je`・`jb`・`jbe` 等から IR の `icmp` 条件へ) | 残りの unimpl `vcomisd`・`vucomisd`・`vucomiss` | 子 [PLG-F3-33] |
| 他 plugin への影響の再測定 | 同上 | 子 [PLG-F3-33] |

本付録で完了したのは「機械語と IR の 1:1 対応表」「欠落 7 件の所属と段階の切り分け」。 **受入の unimpl 消去・他 plugin の再測定は未達** (本 PR の範囲外)。
