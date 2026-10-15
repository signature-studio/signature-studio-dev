# tools/iltools — T-SH-12 (#154): ILTools_x64.dll の export 閉包 lift gate

## 0. 結論

- **判定: PASS (export 閉包 gate)**。PM 判断 (2026-10-15) の完了条件 1 を満たす。測定 commit `c2df31c1` (コード変更の最後の commit)。
  - roots = PE export のうち `.text` 内の 6 本 → 直接 call 閉包 **824 関数**: unsup 0 / unlifted callees 0 / imports 111。
  - 閉包外の x87 関数 **45 本**は lift せず、呼ばれたら必ず abort する trap stub にする (`x64c --trap`)。
  - 陰性対照: (a) 閉包 root に x87 関数 45 本を混ぜると unsup 1,236 で gate が FAIL / (b) trap stub 45 本を native で呼ぶと 45/45 が abort (stderr に `trap stub`)。
- 全 .pdata (11,747 関数) の lift は未完のまま (旧測定は §3)。gate の対象を export 閉包に変えた。
- 完了条件 2 (FruityPlug SGv2) は PM 判断で本 issue から外れた。完了条件 3 (QFC boot / FreeType) は子 issue へ移す (§4)。
- よって PR は `Closes #154` (完了条件 1 の達成 + 完了条件 3 の子 issue 化)。

## 1. 実測 (測定 commit `c2df31c1`・コミット済み HEAD で再現)

`FL_WIN64_DIR=<fl-win64 展開先> QFC_PY=<capstone+pefile の python> bash tools/iltools/lift_measure.sh` (exit 0)

| 項目 | 値 |
|---|---|
| roots | PE export のうち `.text` 内の 6 本 (`CreateCursorFromFont` / `CreatePathManagerInstance` / `CreatePluginPathManagerInstance` / `DestroyPathManager` / `ShowEngineChoice` / `__dbk_fcall_wrapper`)。`dbkFCallWrapperAddr` は `.text` 外 (data) のため除外 |
| 閉包 (`--closure 50`) | functions **824** / insns 37,869 / **unsup 0** / **unlifted callees 0** / imports 111 |
| trap stub | **45** (`x87_traps.py`: `.pdata` のうち f* 命令を含む関数。閉包とは交わらない)。うち 42 本は算術 x87 を含み、3 本 (`0x407cb0` / `0x59b280` / `0x59bf80`) は fldcw・fnstcw 系の制御命令のみ (x64c は対応済み。閉包外なので保守的に trap にした) |
| 所要 | gate 全体 19.6 s (陰性対照 2 本を含む)。load 0.76 0.54 0.26, nproc 4 |
| 判定 | `closure_gate.py`: PASS (exit 0) |

## 2. 陰性対照

| 対照 | 操作 | 期待 | 結果 |
|---|---|---|---|
| (a) 閉包に x87 を混ぜる | 閉包 root に x87 関数 45 本を追加 (trap 無し) | gate FAIL (unsup) | functions 870 / **unsup 1,236** / trap 0 → FAIL (exit 1)。unsup の内訳 (fld 311 / fmul 202 / fadd 151 / fxch 118 / fstp 117 ほか) は §3 の全 .pdata lift と一致 |
| (b) trap が発火する | 45 trap stub を native harness (`trap_harness.c` + `fle_lifted.c` + `fle_cpu.c`) で各 1 回呼ぶ | 全て abort + stderr に `trap stub` | **45 / 45 発火** (`[fle] UNSUPPORTED instruction at 0x...: trap stub (x64c --trap): ...`) |

`ott_unsup` は hook の有無に関係なく必ず abort する (`fle_cpu.c`)。`ott_unlifted` は `fle_ff_hook` 設定時に戻るため、trap には使わない。

## 3. 旧測定 (全 .pdata を roots にした lift・FAIL が正しい結果だった時点)

測定 commit `e341f64e` 系 (`--closure 0`・`.pdata` 11,747 roots): functions 11,747 / insns 399,453 / unlifted callees 0 / imports 548 / **unsup 1,236 (全て x87)**。
閉包 gate (§1) はこの値を置き換える。x87 は export 閉包には 0 本 (§4)。

## 4. 未解決 (起票先付き)

| 未解決 | 理由 | 起票先 |
|---|---|---|
| QFC の boot (InitDll → FontCache_*) と FreeType 結合 | 完了条件 3。FreeType 採用 (#145 T-SH-01) に従属 | 子 issue (親 #145)。番号は PR 本文と issue コメントに記載 |
| 閉包外の x87 関数 45 本が実行時に届くか | 間接 call 368 site は静的に決まらない (§5 [C])。届けば trap が abort する (§2 (b) で発火は確認済み)。ILTools の boot 実行は未着手 | PM 判断 (ILTools boot を別 issue にするか) |
| SGv2 (FruityPlug) の win 対応 | 完了条件 2。PM 判断で本 issue から外れた (#2630 の実測: PE 133 本で一意にならない) | PM 判断 (mac `SGv2_x64.dylib` との突合は PLG の lift が必要とした時点) |
| 閉包 824 と `x87_reach.py` の閉包 835 の差 11 | 未確認 (x64c 側の callee 解決条件の差)。gate は x64c の閉包で判定しているため影響なし | 記録のみ (本 PR で追跡しない) |

## 5. x87 の到達範囲 (PM 判断の材料・`tools/iltools/x87_reach.py`)

測定 commit `2735a7ba` (測定後のコード差分 0。本節は docs のみ)。`python3 tools/iltools/x87_reach.py <block24347_PE.bin>` (集計のみ・gate なし)。

| 項目 | 値 |
|---|---|
| [A] .pdata 関数 / f* 命令 / x87 を含む関数 | 11,747 / 1,256 / **45** (f* 1,256 = 非制御 1,236 (lifter の unsup と一致) + 制御 20 (fldcw・fnstcw 系。x64c は対応済み)) |
| [B] export 6 本 (.text 内) → 直接 call 閉包 | 835 関数 / x87 関数 **0** / x87 命令 **0** |
| [B2] entry point 0x2b35f0 → 直接 call 閉包 | 31 関数 / x87 関数 0 |
| [C] 閉包内の間接 call/jmp | 368 site (248 関数)。静的には追えない |
| [D] DIR64 reloc が関数先頭を指す (関数ポインタ・VMT 候補) | 5,785 関数 / うち x87 関数 **0** |
| [E] code 内の rip 相対 `lea` が x87 関数先頭を指す | x87 関数 **41 本** (参照は全て lea)。参照元は **3 関数** で、export 閉包にも entry 閉包にも入らない |

読み: x87 命令は export と entry から直接 call では届かない。間接到達は静的には決まらないため、閉包外 45 本は trap stub で守る (PM 判断 (b): 2026-10-15)。(a) の 80bit 再現 (softfloat) は採らない。

## 6. 回帰と差分

- x64c の既定経路は不変: `--trap` 無しの export 閉包 lift (`--closure 50`) で、変更前後の `fle_lifted.c` が `cmp` でバイト一致 (824 関数)。`lift_meta.json` に `traps` キーが増え、表示行の末尾に `traps N` が付く。
- 測定 commit `c2df31c1` からコード差分 (`git diff c2df31c1 HEAD -- tools/flelift/x64c.py tools/iltools/*.py tools/iltools/*.sh tools/iltools/*.c`) は PR 作成時点で 0 行。
