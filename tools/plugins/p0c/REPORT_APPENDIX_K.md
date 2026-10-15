# p0c 付録 K (#3281: GLOBAL_INITS の PE 値化)

REPORT.md 索引の §24。H の 250 行上限のため新設した (H には節を足さない)。

## 24. #3281 [P0c-20]: GLOBAL_INITS を PE の .data から読む pass に置換

- 測定 commit: `74ae2bbf2` (コードを変えた最後の commit)。その前の `701c4af7a` は置換対象を 0x6fffb0 のみとした中間版。
- 変更: `k80_pe_globals.py` を新設 (`@global_var_<VA> = global iN 0` のうち VA が PE の raw data を持つ
  セクションに入るものを、PE の実バイト (little-endian) の値に置換。PE 値 0 は 0 のまま)。
  `k80_hand_bodies.py` の `GLOBAL_INITS` を削除 (BODIES 14 本は不変)。`p0c4_abi_e2e.py` の chain に
  `ext → k80_pe_globals → k80_hand_bodies` を入れ、`HB_N = 14`・`PE_N = 2` で件数を検査する。
- 置換対象 (PE 実測。image base 0x400000・`.data` RVA 0x2d3000): `0x6fffb0` (f64 x2 = (0.5, 0.5)) と
  `0x6fc26c` (f32 x4 の表。IR は i128 0)。両方とも `.data` の初期値を持つ 0 初期化 i128 である。
  親 issue の想定は 1 件 (0x6fffb0) だったが、一般規則 (PE .data の 0 初期化整数 global の置換) を
  当てると 2 件になる。0x6fc26c は置換で 68 kernel の 2000 case・0x5df340 の 10000 case の buf_diff を変えなかった
  (下表)。`EXPECT` 以外の置換対象が出た場合は SystemExit (fail-closed)。

### 24.1 実測

| 項目 | 結果 |
|---|---|
| `bash p0c_e2e.sh` | rc=0・所要 8 分 20 秒 (05:00:10〜05:08:30 UTC)・work/ を再生成 |
| `p0c4_abi_e2e.py 2000` (測定 commit) | rc=1・所要 28 秒 (05:14:52〜05:15:20 UTC)。失敗は [7] の 1 件のみ (下記) |
| 通過した検査 | k80abi / argfix・x87fix の冪等 / llvm-as (x87fix・hb) / `k80_pe_globals` の冪等 (2 回適用 byte 一致) と件数 2 / `k80_hand_bodies` の冪等と件数 14 / [5b] 戻り値 2001/2001 一致 |
| status センサス | run=68 ok=68 sig11=0 (親の想定 67 より 1 件多い。0x5e1280 が CSV に出る) |
| buf_diff≠0 の kernel | 1 件: 0x5e1280 buf_diff=3996 (2000 case)。他 67 kernel は 0 |
| 0x5e03f0 (10000 case) | buf_diff=0 (置換あり) |
| 負論対照: 0x5e03f0 (2000 case, 置換なし IR) | buf_diff=5,168,510 (置換で 0 になることの対照) |
| 0x5df340 (10000 case, 置換あり) | buf_diff=0 |
| 0x5e1280 (2000 / 10000 case) | buf_diff=3996 / 19986。置換なし IR (ext→hb) でも 2000 case で 3996 |

- 0x5e1280 は本変更の前から buf_diff≠0 である (置換なしの chain でも同値)。`[7]` の回帰判定に
  引っかかるため p0c4 の rc は 1 になる。本 issue では kernel の修復をしていない。子 issue で扱う。
- `ret_diff` は rax と比べた値のため、xmm0 を返す kernel では意味を持たない (p0c4_abi_e2e.py の数え方の定義どおり)。
  合否は buf_diff で判定する。

### 24.2 残った手書き本体 (BODIES 14 本)

本変更は GLOBAL_INITS のみ。BODIES 14 本は残っている。`k80_hand_bodies.py` の冒頭に書かれた根拠 (REPORT_APPENDIX_H §19) は次のとおり。
残り 10 本の原因は本測定では確認していない (子 issue で切り分ける)。

- `function_5dfff0`: 引数 a(xmm2)/b(xmm3) の参照が入れ替わる + (1±a)*b を 80-bit で丸める。
- `function_5dee20`: out[2k+j] += in[k] (f32 加算)。RetDec の fstp 参照先がずれる。
- `function_5e0300`, `function_5e0350`: 80-bit 中間値の丸め。
- `function_5dffc0`: 10000 case で残差が残る kernel (x87 fsincos 縮約。付録 J §23)。
- 残り 9 本 (`function_5dee50`・`5de620`・`5dedb0`・`5dea40`・`5dec40`・`5e12c0`・`5e1490`・`5df340`・`5dfae0`): 根拠の記述なし。原因未確認。

## 24.3 再現

```
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 RETDEC_ROOT=$RUNNER_TEMP/retdec/retdec PATH=/usr/lib/llvm-18/bin:$PATH \
  bash tools/plugins/p0c/p0c_e2e.sh
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000
python3 tools/plugins/p0c/k80_diff.py --ir tools/plugins/p0c/work/diff3/k80.hb.ll --cases 10000 --only 0x5e03f0
```

### 24.4 測定 commit からの差分

`git diff --stat 74ae2bbf2 HEAD -- tools/plugins/p0c ':!*REPORT*'` の出力は空 (測定後にコードは変えていない)。
