# p0c 付録 N (#6046: 手書き本体のうち x87 の 5 本を x87 一般 pass に置換)

REPORT.md 索引の §27。親 #3952 (残件 A)・#2182 (P0c-17) の BODIES 14 本のうち、x87 スタック参照のずれで手書きしていた本体の一部を既存の `x87fix.py` の対象に入れた。

## 27. #6046: 手書き本体 14 → 9 (x87 の 5 本を一般 pass に置換)

- 測定 commit: `ecadfb82d` (コードを変えた最後の commit。`tools/plugins/p0c/p0c4_abi_e2e.py` と `k80_hand_bodies.py`)。
- 基準: origin/main `de14f0d49` (worktree `ws-6046`、branch `6046-x87-hand-bodies`)。

### 27.1 根本原因 (受入 3)

- 手書きの本体が必要だったのは、`x87fix.py` の `--funcs` 一覧 (`p0c4_abi_e2e.py` の `funcs`) にその関数が入っていなかったため。
- `x87fix.py` の `skip` 判定に入れない関数は、`__frontend_reg_load.fpr` / `__frontend_reg_store.fpr` が IR に残る (`work/exp/pe.ll` の 0x5dee20 は 9 行)。そこで差分が出ていた。
- 一覧に入れると、5 本は `fixed` (`work/exp/x87.json`)。残る 5 本は `skip:*` (下表)。

| VA | x87fix の判定 (一覧に入れた場合) | 置換 |
|---|---|---|
| 0x5dea40 | fixed (patterns 19, sites 16) | 置換 (本 PR) |
| 0x5dec40 | fixed (patterns 24, sites 27) | 置換 (本 PR) |
| 0x5dedb0 | fixed (patterns 10, sites 5) | 置換 (本 PR) |
| 0x5dee20 | fixed (patterns 7, sites 5, init_top_store) | 置換 (本 PR) |
| 0x5dee50 | fixed (patterns 10, sites 13, init_top_store) | 置換 (本 PR) |
| 0x5de620 | skip:no-top-var | 残 (未解決) |
| 0x5dfae0 | skip:dup delta (2, -1) | 残 (未解決) |
| 0x5dffc0 | skip:store val no def | 残 (未解決) |
| 0x5e0300 | skip:ambiguous-balance | 残 (未解決) |
| 0x5e0350 | skip:ambiguous-balance | 残 (未解決) |

### 27.2 変更

- `p0c4_abi_e2e.py`: x87fix の `--funcs` に上の 5 本を追加。`HB_N` 14 → 9。
- `k80_hand_bodies.py`: BODIES から 5 本を削除 (0x5dee20・0x5dee50・0x5dedb0・0x5dea40・0x5dec40)。docstring の 0x5dee20 行を削除。
- 新規の pass は作っていない。既存の `x87fix.py` の対象関数を広げただけ。

### 27.3 実測 (全て 4 vCPU・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`RETDEC_ROOT=$RUNNER_TEMP/retdec/retdec`・`PATH=/usr/lib/llvm-18/bin:$PATH`)

| 測定 | commit | rc | 所要 (wall) | load 1 分 (開始 → 終了) | 結果 |
|---|---|---:|---:|---|---|
| `p0c_e2e.sh` (基準・lift 含む) | `de14f0d49` | 0 | 8 分 28 秒 | 1.02 (起動直後) | `== e2e OK ==` |
| `p0c4_abi_e2e.py 2000` (基準) | `de14f0d49` | 0 | 29.3 秒 | 6.67 → 4.43 | `run=68 ok=68 sig11=0`・`p0c4 ABI e2e OK` |
| `p0c4_abi_e2e.py 2000` (修正後・作業ツリー) | (未コミット) | 0 | 28.4 秒 | 0.76 → 0.86 | `run=68 ok=68 sig11=0`・`p0c4 ABI e2e OK` |
| `p0c4_abi_e2e.py 2000` (修正後) | `ecadfb82d` | 0 | 28.5 秒 | 0.52 → 0.71 | `run=68 ok=68 sig11=0`・`p0c4 ABI e2e OK` |
| `p0c_e2e.sh` (修正後・lift 生成済みを再利用) | `ecadfb82d` | 0 | 8.8 秒 | 0.48 → 0.56 | `== e2e OK ==` |
| `k80_diff.py --cases 10000` (置換 5 本) | `ecadfb82d` | 0 | 10.5 秒 | — | 5 本とも `ret_diff=0 buf_diff=0` (下表) |

- `p0c_e2e.sh` の基準 8 分 28 秒は、`work/` が無かったため lift を含めて生成した時間。修正後は生成済みを再利用したので 8.8 秒。同じ条件での比較ではない。
- 修正後の `p0c4 2000` の CSV は全 68 kernel buf_diff=0 (`p0c4_head.log`)。

10000 case (`k80.hb.ll` = `ecadfb82d`):

| VA | ret_diff | buf_diff |
|---|---:|---:|
| 0x5dea40 | 0 | 0 |
| 0x5dec40 | 0 | 0 |
| 0x5dedb0 | 0 | 0 |
| 0x5dee20 | 0 | 0 |
| 0x5dee50 | 0 | 0 |

### 27.4 負論対照 (受入 4)

置換の効果を見るため、手書き本体も x87fix の対象もない IR (`work/diff3/k80.pe.ll` = 基準の中間 IR・2000 case) で差分を取った。

| VA | ret_diff | buf_diff |
|---|---:|---:|
| 0x5dea40 | 2000 | 5166346 |
| 0x5dec40 | 2000 | 5088752 |
| 0x5dedb0 | 2000 | 2583215 |
| 0x5dee20 | 2000 | 5168510 |
| 0x5dee50 | 2000 | 5168510 |

手書き本体と x87fix 対象の両方を外すと 5 本とも FAIL する。修正後は 0。

### 27.5 残り (受入 1・未解決)

- 置換した本数: 5 本 (14 → 9)。
- 残りの手書き本体 9 本 (`k80_hand_bodies.py` の BODIES): 0x5e0300・0x5e0350・0x5de620・0x5dfae0・0x5dffc0 (対象 10 本の残り 5 本。`x87fix` が `skip` する)・0x5dfff0・0x5e12c0・0x5e1490・0x5df340 (対象外)。
- 残り 5 本の対象は、x87fix の `skip` 理由が 4 種 (no-top-var・dup delta・store val no def・ambiguous-balance)。いずれも一般 pass の判定条件を広げる作業が必要で、本 run の範囲では完結しない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x5e0300・0x5e0350・0x5de620・0x5dfae0・0x5dffc0 の手書き本体 5 本 (x87fix の skip 4 種) | BODIES 9 本が残る | #3952 (親。本文に残件のチェックリストを追記) |
| 0x5dfff0・0x5e12c0・0x5e1490・0x5df340 の手書き本体 4 本 | 対象外。本 issue の対象ではない | #3952 (親) |

### 27.6 差分 (WORKFLOW §6)

- 測定 commit: `ecadfb82d`。REPORT 追加後の HEAD までの `tools/plugins/p0c` のコード差分 (REPORT を除く) は下記の出力のとおり空。

```
git diff ecadfb82d HEAD -- tools/plugins/p0c ':!*REPORT*'
```

### 27.7 再現

```
export FL_WIN64_DIR=<fl-win64 展開先> RETDEC_ROOT=<retdec 展開先> PATH=/usr/lib/llvm-18/bin:$PATH
bash tools/plugins/p0c/p0c_e2e.sh
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000
python3 tools/plugins/p0c/k80_diff.py --ir tools/plugins/p0c/work/diff3/k80.hb.ll --cases 10000 --only 0x5dea40,0x5dec40,0x5dedb0,0x5dee20,0x5dee50
```
