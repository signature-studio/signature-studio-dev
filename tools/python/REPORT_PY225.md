# PY-225 (#3651): getGridBit の件数 `[grid+0x22fc]-8` の生成経路と値

親: #3596 (PY-218)。前段: PY-112 (`tools/python/REPORT_PY112.md`)。

既知類型との関係: 該当なし (逆アセンブル解釈と mock/C の照合。`docs/DEFECTS.md` の類型には当たらない)。

## 結論

- **件数の書込み経路は PE で特定した** (下の表)。件数 n は `0x12d09e0(P)` の戻り値で、`[grid+0x22fc]` の配列を作る `0x417fc0` の 4 番目の引数 (`*r9`) として渡る。確保時に `[ptr-8] = n` を書く (`0x4180fe`)。
- **n の式: `n = ceil((P+0x50) / X) * C`**。X = 96 (`.data` `0x15d89c8` の int 値 96 = PPQ)、C = 4 (`.data` `0x15d898c` の int 値 4 = 1 拍あたりの step 数)。`P+0x50` はパターン長 (ticks・推定)。
- **件数 64 は静的に確定できない**。n = 64 ⇔ `ceil(L/96) = 16` ⇔ `1440 < L <= 1536` (L = `P+0x50`)。`P` は `*(0x15e2218)` で、指す先 `0x16bafc8` は `.bss` (ファイル上 0)。L は実行時の値で、PE の静的値からは決まらない。
- 受入 2 (NSTEP と境界の修正) は**未実施** (コード変更なし)。件数が L に依存するため、固定の `NSTEP 64` を直す対象が定まらない。L の既定値と書込み元は子 issue に分けた (下の未解決表)。
- 検証済みの前段: `provider/build.sh` → `channels_diff` は HEAD で PASS (calls 214・diffs 0)。mock/C の挙動は変えていない。

## 測定

- 基点: `origin/main` = `c2324dea6`。測定 commit: `8b1f484cc` (解析スクリプト `pe_py225_disp_scan.py` を追加した commit。この後の commit は本 REPORT と DOC_MAP のみ)。差分の証跡: `git diff 8b1f484cc HEAD -- tools/python/analysis tools/python/host tools/python/provider tools/python/tests` は 0 行 (本 REPORT の commit は範囲外)。
- 素材: `fl-win64` を `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` で全展開 (5.444 秒)。`extracted/block00031_PE.bin` (22,227,016 B)。`toolchain-emsdk` は `provider/build.sh` の前提として存在を確認 (`$HOME/artifacts/toolchain-emsdk.tar.zst`)。
- 環境: runner 4 core、node v22.23.3。

| 検査 | コマンド | 結果 | 所要 |
|---|---|---|---|
| 展開 | `tar --zstd -xf ... -C $RUNNER_TEMP/fl-win64` | rc 0 | 5.444 秒 |
| `0x22fc` の全 .text 走査 | `FL_WIN64_DIR=... python3 tools/python/analysis/flapi/pe_py225_disp_scan.py 22fc` | store 0 件・lea 2 件・その他 5 件 | 26.494 秒 |
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0 | 数秒 |
| channels 差分 | `cd tools/python && node tests/channels_diff.mjs` | `{"calls":214,"diffs":0,"PASS":true}` | 1 秒未満 |

- 走査の出力: `0x22fc` を含む命令は `0x118629a`・`0x11862c7`・`0x118639b` (`[rdi/rax+0x22fc]` の読出し)、`0x12d3e3c`・`0x12d3e54` (`[rbx+0x22fc]` の読出し: 件数 `[ptr-8]` の読出し元)、`lea` の `0x1186378` (`&[grid+0x22fc]` を渡す)・`0xe1d2cd` (`lea rdx, [rip+0x22fc]`・用途未確認)。store は 0 件。直接の store が無いのは、件数付き配列を `0x417fc0` の呼出しで作るため。
- ネガティブコントロール (存在しない disp の走査で 0 件になること): 未実行 (時間切れ)。

## 件数の生成経路 (PE 実測)

| VA | 役割 | 読めた処理 |
|---|---|---|
| `0x1186300` | channel 列の走査 | `esi` を `0` から `P+0x10 - 1` まで回し、`obj = 0xfe8bb0(P, esi)`。`P = *(0x15e2218)` |
| `0x1186371` | grid の有無 | `grid = obj+0x7ac` が非 0 なら `byte [grid+0x2304] = 1` |
| `0x1186378` | 配列の確保 | `0x417fc0(&[grid+0x22fc], [rip+0x145f22], 1, n)`。`n = edi` |
| `0x1186308` | n の算出 | `edi = eax` (直前の `call 0x12d09e0` の戻り値) |
| `0x12d09e0` | n の式 | `((P+0x50) + X - 1) / X * C`。X = `*(int*)*(0x15e27f0)` = 96、C = `*(int*)*(0x15e1c70)` = 4。`idiv` の除数と加算が同じ X |
| `0x417fc0` → `0x417b70` | 配列確保 | `*r9` (= n) を件数として受ける。旧配列 `*rcx` を `[rbp+0x78]` に読む |
| `0x4180eb`〜`0x4180fe` | ヘッダ | `call 0x409410(n*stride + 0x10)`。`[rax+4] = 1`、`[rax+8] = rcx` (rcx = 件数)。データ先頭 = `rax+0x10` なので `[データ-8] = 件数` |
| `0x12d3e20` | 読出し | `0x12d3e3c`: ptr = `[grid+0x22fc]`、ptr != 0 なら `n = [ptr-8]`。`p < n` なら `byte [ptr+p]`、`p >= n` なら event 経路 (PY-112) |

判断の根拠:
- `0x12d09e0` の式 `ceil(L/X)*C` は、既存 REPORT_PY42 の `getPatternLength` の既定値 (`0x12d09e0`) と一致する (既定パターン長を step 数で返す関数)。
- `0x4180fe` の件数は `[rsp+0x80]`。新規確保 (旧配列が無い) の経路では `*r9` (= n) のまま。**複製元の件数 `S` を取る経路 (`0x418030`) では `min(n, S - start)` になりうる** (推定。`0x417b70` の分岐の全体は未読)。

## L (= `P+0x50`) の状態

- `P = *(0x15e2218)` の静的値は `0x16bafc8` (`.data`)。指す先は `.bss` (0x16bafc8 は .bss の範囲内)。ファイル上の値は 0 で、起動後に実行時に入る。
- `P+0x50` の書込み元は未調査 (時間切れ)。候補の走査は `pe_xref.py` / `pe_chain_stores.py` で可能だが、`[reg+0x50]` の store は多数あり、P に限定できていない。
- 既定値は実行時の値で、PE の静的解析からは確定できない。件数が 64 かは L の既定値次第。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| L = `P+0x50` の既定値と書込み元 (実行時の値) | n が 64 か未確定。NSTEP 64 の正しさを判定できない | 子 issue (`[PY-230]`・親 #3651) |
| 件数 n の複製経路 (`0x418030`・旧配列がある場合の件数 `min(n, S-start)`) | 旧配列がある場合の件数の式が未確定 | 子 issue (`[PY-230]`) |
| 受入 2: NSTEP と境界 `p >= 64` の修正 | L が決まるまで直す対象が無い | 子 issue (`[PY-230]`) |
| event 経路 (`0x12d16a0`・`0x12df210`) | 件数以上の position の値 (PY-218 の範囲) | 親 #3596 |

## 再現

- 展開: `tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'`。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- 走査: `python3 tools/python/analysis/flapi/pe_py225_disp_scan.py 22fc` (26.5 秒)。
- 逆アセンブル: `pe_disasm.py 12d09e0 50`・`1186300 60`・`417fc0 90`・`417b70 45`・`4180f0 40`・`12d3e20 40`。
- 静的値: `pe_va_read.py 15e27f0,15e1c70,15d89c8,15d898c,15e2218`。
