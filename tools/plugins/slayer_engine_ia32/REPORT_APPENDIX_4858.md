# REPORT_APPENDIX_4858 — x87 独立入口 0x1000bf1e の非自明性 (eax) と TARGETS 入り (#4858 PLG-G2-66)

親: #4080 (前提 #4844 は merge 済み)。 入口 `0x1000bf1e` は cdecl・a0 = double (引数形は REPORT_APPENDIX_4080.md §1)。
起動・GUI に関わらない (製品 KPI は対象外)。 静的解析と x87 命令の突合のみ。
測定 commit: `417548895` (コードを変えた最後の commit)。

## 1. 非自明性の判定方法

`0x1000bf1e` は OBJ 窓 (0x10F80000 の 0x540 B) もスタックも書かない。 既存の effect 判定 (OBJ 窓が変わった行) は 0 件になるため、
この関数には使えない。 代わりに **戻り値 eax が入力に依存して 2 種類以上になること** を判定に使う (`x87_fn_diff.py` の
`nontrivial: 'eax'`。 PUSH64 測定の判定と同じ規則)。

逆アセンブル (`0xbf1e`〜`0xbf59`): `mov 0xe(%ebp),%ax` → `and $0x7ff0,%ax` の指数部を取り、`fldt` (80bit) か `fldl` (double) へ分岐する。
eax は指数部のみで決まる。 4000 行 (seed 2989) で `eax == (hi16 & 0x7ff0)` が **4000 / 4000** 一致し、distinct eax は **13 種**。
(`hi16` は a1 = 引数の上位 dword の上 16bit。 最初に試した「上位 dword そのもの」との一致は 165 / 4000 で、判定規則には使わない。)

## 2. 突合の結果 (commit `417548895`)

既定ゲート (`python3 x87_fn_diff.py`、`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`):

| 関数 | 行 | bit 一致 | 構造 (eax・x87 深さ) | 非自明性 |
|---|---:|---:|---|---|
| `0x1000bf1e` | 4000 | 4000 | eax 不一致 0・深さ不一致 0 | eax 13 種 (OBJ 窓変化 0 は想定内) |

- 全 TARGETS (8 本): PASS、rc 0。 `[build] native 0.05 s, wasm emcc 9.26 s; [run] native 0.574 s, wasm(node) 0.942 s; load1 0.72`。
- 同 commit の `x87_fn_diff.py` 全体の wall 時間: 19.98 s (`real`)。
- ネガコン `--nega`: bit 一致 26619 → 26618 (行 0 の ST(0) の最下位 bit を反転)、検出 OK。 判定器が通るだけでないことを確認。
- 前提 (lift): `lift_text.py` を同 commit で再生成して実行。 rc 0。

## 3. 判定の作り方の変更点

- TARGETS の各要素に任意の `nontrivial` キーを足した (既定は未指定 = 従来の OBJ 窓の判定)。 `'eax'` を指定した関数だけ eax の種類数を判定に使う。
- 既存の 7 本の判定は変えない (未指定の行は従来の `effect > 0` のまま)。
- PROBE から `0x1000bf1e` を外した (TARGETS に移動)。

## 4. 未解決

- `0x1000bf1e` の ST(0) の float64 は 4000 語中 4000 bit 一致 (1 ulp 差 0)。 float32 も一致。 差分なし。
- 断片 6 本の親入口 `0x1000c077` の確定は本付録の範囲外 (REPORT_APPENDIX_4080.md §3 のとおり。 子 #4837 に残る)。
