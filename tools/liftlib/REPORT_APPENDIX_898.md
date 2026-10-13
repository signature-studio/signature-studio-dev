# LIFTLIB #898 (HB-H22) — iargs 未対応 3 site の bind (付録)

親: [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §17 (#898 の節)。
REPORT_APPENDIX.md が 250 行上限を超えているため、#898 の節はこのファイルに分けて置く (`REPORT_APPENDIX_883.md` と同じ運用)。

## 状態

`site_unbound` は 3 → 0 (main 取り込み後の HEAD で実測)。
- `1801a3117` (rdx = `movzx edx, dl`): 本 PR の movzx 合成で bind。
- `1801c162b` / `1801c1752` (r8 = 5 番目の引数, 入口 rsp+0x28): main の [HB-H25] #1158 で bind 済み。

高バイト (`movzx edx, dh` 等) は合成せず unbound にする (本 PR の review 指摘で追加。`_HIGH8`・T16b)。

### 3 site の bind

| site | 原因 | 対応 |
|---|---|---|
| `1801a3117` | rdx = `movzx edx, dl` (呼出元の入口 dl の 0 拡張) | **解決**。`_resolve` の movzx 分岐 (`sw` = 元レジスタ幅で切る → 呼出側の型へ `zext`)。元レジスタが `ah`/`bh`/`ch`/`dh` の場合は合成せず `None` (unbound)。 |
| `1801c162b` / `1801c1752` | r8 = `mov r8d,[rbp+0x5f]`。入口 rsp+0x28 (5 番目の引数 = スタック渡し) | **main で解決** ([HB-H25] #1158)。本 PR では変更なし。 |

### 実測 (HEAD `5efcb24b`・素材: fl-win64 / work-m6-ott / analysis-ott-binaries / work-liftlib)

- `tests/test_unit.py` T16 (単独実行, `python3 -c` で `t16()`): PASS。`define_fixed=15 sites_fixed=24 site_unbound=0`、再走査 0/0/0、冪等。所要 254.6 秒 (`real 4m14.7s`, rc=0)。
- T16b (高バイト被覆, 新規): PASS。`movzx edx, dh` → None / `movzx edx, dl` → i32 の zext 合成。修正を外すと FAIL することを確認。
- T23: PASS (単独実行 0.0 秒)。
- `leafspec targets/ott_iargs.json --n 200`: 下節を参照 (現 HEAD `704eaab9` で実測)。

### leafspec の実測

- 現 HEAD `704eaab9` の実測 (review run [38456399467](https://github.com/signature-studio/signature-studio-dev/actions/runs/38456399467), conclusion=success): `leafspec targets/ott_iargs.json --n 200` → `scenarios=200 steps=200 match=200 mismatch=0 native_crash=0 wasm_trap=0`、rate=1.000、rc=0、所要 45.3 秒。
- 旧測定 (HEAD 220c4703・main 取り込み前, 履歴): match=200 mismatch=0 wasm_trap=0 (rate 1.000)。所要 22.8 秒 (rc=0)。実行 ID・出力全文は保存していない。

### 再実行に必要な素材

`fl-win64 work-m6-ott analysis-ott-binaries work-liftlib toolchain-emsdk` (`docs/WORKFLOW.md` §11)。
