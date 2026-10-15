# PY-307 (#4181 / 親 #3282): `0x1050f90` の n→n1→n2 係数の PE 確定

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #3282 (PY-181)。前段: `tools/python/REPORT_APPENDIX_4109.md` (n→n1→n2 の入口)。

## 結論

- 確定 `0x40c660` = `cvtsd2si rax, xmm0`。丸めは既定の round-to-nearest-even (RNE)。
- 確定 `0xf824b0(ptr, n)` (n1 の変換):
  - `ptr == null` のとき `n1 = n` (そのまま返す。0xf8250b)。
  - `ptr != null` のとき `x = float(n · 2^-30)` (double の 2^-30 を掛けて float 化)。`x' = 0xf823f0(ptr, x)`。`y = clamp(x', 0, 1)` (下限 0・上限 1。定数 0xf82518 の dword は 0.0、0xf82520 は 1.0)。`n1 = RNE(y · 2^30)` (定数 0xf82524 = 2^30)。
- 確定 `0xf823f0(ptr, x)` の分岐:
  - `ptr == null` または `byte [ptr+0x4c] == 0` のとき `x' = x` (恒等写像)。
  - それ以外は `x' = float(0xbaffb0(ptr))` (0xbadd00 のノード走査で得る double)。**数値式ではなく、オブジェクトごとの表引き。** 係数としては確定しない (下の未確定)。
- 確定 `0x10469f0(n1, lo, hi)` (目標値の補間): `n2 = lo + RNE( (double)n1 · 2^-30 · (double)(hi − lo) )`。係数 2^-30 は slot 0x1046a20 (qword、`pe_rip_consts.py` で確認)。
  - `n1 ∈ [0, 2^30]` のとき `n2 ∈ [lo, hi]` (積の項が `[0, hi−lo]` に入り、RNE は整数の端点を越えない)。
  - `lo`・`hi` は `0x1050f90` の出力 (REPORT_APPENDIX_4109 の確定事項)。flags & 2 のとき `lo = 0`・`hi = 0x100000`。
- 確定 `0x1051c90(obj, n1)` (2 段目の写像):
  - `obj[0x60]` が `≤ 0x0fffffff` (符号なし)、かつ `obj[0x60] & 0xffff == 4`、かつ `obj[0x70] & 0x20 ≠ 0`、かつ `idx = obj[0x60] >> 16` が `[0, count)` のとき `n2 = trunc((n1 − 2^29) · M / 48) + 2^29`。ここで `M = int32 [entry+0x2f4]` (`entry = fe8bb0(table, idx)`)。divisor 48 は `r8d = 0x30` (0x1051d04)。
  - それ以外は `n2 = n1`。
  - 範囲: `|M| ≤ 48` なら `n2 ∈ [0, 2^30]` (n1 と同じ範囲)。`|M| > 48` なら範囲は `M` で広がる (M は表の値で、本 issue では未読)。
- 確定 `0x10517c0` 周辺 (呼び出し元の 1 例): `0x10469f0` の引数 `n1` は `0xf824b0(ptr=[obj+0x90], n=[obj+0x68])` の結果。`lo` = `[rbp+0xb4]`、`hi` = `[rbp+0xb0]` (0x1051806 の直前)。他の呼び出し元 (0x1047714・0x1047964・0x1047d93・0x1049b2c・0x104a48f・0x104b300・0x104b83e) は未読。

## 値域 (係数から導出できる範囲)

| 量 | 式 | 値域 |
|---|---|---|
| n1 (ptr=null) | `n1 = n` | n そのまま (int32) |
| n1 (ptr≠null、恒等の 0xf823f0) | `RNE(clamp(n·2^-30, 0, 1) · 2^30)` | `[0, 2^30]` |
| n2 (0x10469f0) | `lo + RNE(n1·(hi−lo)/2^30)` | `[lo, hi]` (flags&2 のとき `[0, 0x100000]`) |
| n2 (0x1051c90、M 既知) | `trunc((n1−2^29)·M/48) + 2^29` | `|M| ≤ 48` で `[0, 2^30]` |

## 測定

- 測定 commit: `1f12b1b6d` (origin/main。分析スクリプトは変えていない)。
- 素材: `fl-win64.tar.zst` の `block00031_PE.bin` (22,227,016 byte) を `$RUNNER_TEMP/fl/extracted` に展開 (`tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl extracted/block00031_PE.bin`、実測 2.9 秒)。
- 逆アセ (`analysis/flapi/pe_disasm.py`、`FL_WIN64_DIR=$RUNNER_TEMP/fl`、要求命令数で打ち切り): `0xf823f0` (120)・`0x40c660`・`0x661450`・`0x10469f0` (ret まで 0x1046a1d)・`0xf824b0` (60)・`0x1051c90` (60)・`0xbaffb0`・`0xbadd00` (60)・`0xfe8bb0`。全て終了 0。
- 定数 (`pe_rip_consts.py`): `0xf82518`=2^-30 (qword の f64 表示 9.3132e-10)・`0xf82520`=1.0 (f32)・`0xf82524`=2^30 (f32)・`0x1046a20`=2^-30 (f64)。`0x1051cc9` の参照先 slot `0x15e2218` は値の型を未確認 (ポインタ経由で読まれる)。
- 呼び出し元 (E8 相対の走査): `0x10469f0` は 8 箇所、`0x1051c90` は 3 箇所。

## 未確定 (子 issue へ)

- `0xf823f0` の非恒等分岐 (`0xbaffb0(ptr)` = `0xbadd00(ptr, ptr[0x2c])`)。ノードの二重連結走査と既定値 `[0xa33f96]` の実値が未確定のため、数値式にできない。値の出所 (table) を確定しないと `n1` の式が閉じない。
- `0x1051c90` の表エントリ `+0x2f4` (M) の由来と、`obj[0x60]`・`obj[0x70]` を埋める経路。
- `0x1046a30(key, 0, 0x20)` と `0x1046a30(key, 0x40000000, 0x20)` (flags&2 == 0 のときの lo・hi)。効果関数で PY-175 の範囲。
