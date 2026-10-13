# modulation 付録 (#527 PLG-F5-2 engine gate)

本体 `REPORT.md` の §4 (engine 4 本) の到達性 gate。判定は `engine_judge.py` (exit code 化)。

## I. engine 到達性 gate (受入 1 の exit code 化)

- 判定: `engine_judge.py <outdir>` (`engine_lift.sh` の出力 `summary.csv` と `engine_name_gap.py` の名前照合)。
  - 合格: `lift_rc == 0` かつ `erc3 == 0` かつ define 無し range (名前照合後) が 0 件 (0 B)。exit 0。
  - 不合格: 上記のどれかが欠ける。exit 1。
  - 入力不正 (summary.csv の欠落・列数・非整数、名前照合の失敗)。exit 2。
- 出力行には `stub=` (未実装 helper 数) を必ず併記する。stub を含む `emcc -c` 通過は正しさを示さない (bit-exact は #197 で未検証)。
- ネガティブコントロール: `engine_judge.py --selftest` (合成入力 6 ケース、全て期待 exit と理由文字列を確認)。

### I.1 NC (selftest、HEAD の commit で実行)

| ケース | 期待 exit | 実測 exit | 理由の文字列 |
|---|--:|--:|---|
| 無改変 (good) | 0 | 0 | PASS |
| `lift_rc=1` | 1 | 1 | `lift_rc=1` |
| `erc3=1` | 1 | 1 | `emcc_c_rc(erc3)=1` |
| `function_2000` の define を除去 (名前照合で解決不可) | 1 | 1 | `define 無し range 1 件` |
| 列数不足 (16 → 15 列) | 2 | 2 | `列数` |
| 非整数 (`x`) | 2 | 2 | `整数` |
| summary.csv 無し | 2 | 2 | `summary.csv` |

`selftest: OK` (exit 0)。

### I.2 実測 (4 本、`engine_lift.sh <block> 300` の順次実行、`engine_judge.py` で判定)

測定 commit: origin/main 2b99366a の上に `engine_judge.py` を追加した worktree (`ws-527`、`work/` は gitignore)。 lift 本体は未変更。

| block | lift_rc | erc3 | define 無し (名前照合後) | stub | judge |
|--:|--:|--:|--:|--:|---|
| 18977 | 0 | 0 | 0 件 (0 B) | 70 | PASS (exit 0) |
| 19143 | 0 | 0 | 0 件 (0 B) | 64 | PASS (exit 0) |
| 19266 | 0 | 0 | 0 件 (0 B) | 60 | PASS (exit 0) |
| 19268 | 0 | 0 | 0 件 (0 B) | 92 | PASS (exit 0) |

- 名前照合の内訳 (define 無し 2 件の解決先): 18977 `dispatch` + `entry_point` / 19143 `DispatchToEngine` + `entry_point` / 19266 `VSTPluginMain` + `entry_point` / 19268 `entry_point` + `VSTPluginMain` (PR #980 の結論を再現)。
- 注意: この gate は到達性のみ。stub (未実装 helper) を含み、bit-exact は未検証 (#197・#534・#779)。
- 受入 1 の残り: judge 相当の exit code gate は本 PR で追加。bit-exact は #197 依存のため未達。
