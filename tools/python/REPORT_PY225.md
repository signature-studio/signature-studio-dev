# PY-225 (#3651): getGridBit の件数 `[grid+0x22fc]-8` の生成経路と式

親: #3596 (PY-218)。前段: PY-112 (`tools/python/REPORT_PY112.md`)。子: #3669 (PY-230)。

既知類型との関係: 該当なし (逆アセンブル解釈と mock/C の照合。`docs/DEFECTS.md` の類型には当たらない)。

## 結論

- **件数の書込み経路は PE で特定した** (下の表)。件数 n は `0x12d09e0(rcx)` の戻り値で、`[grid+0x22fc]` の配列を作る `0x417fc0` の 4 番目の引数として渡る。確保時に `[ptr-8] = n` を書く (`0x4180fe`)。
- **n の式: `n = ceil(L / 96) * 4`**。`L = mem32(mem64(0x15e2aa0) + ebx*0xC0 + 0x50)`。ebx は `0x11862e0` の第 1 引数。X = 96 (`.data` `0x15d89c8` の int 値 96 = PPQ)、C = 4 (`.data` `0x15d898c` の int 値 4 = 1 拍あたりの step 数)。
- **L は実行時の値で、件数 64 は静的に確定できない**。`mem64(0x15e2aa0)` の静的値 `0x193fce0` は `.bss` (ファイル上は 0)。n = 64 ⇔ `ceil(L/96) = 16` ⇔ `1440 < L <= 1536`。
- 受入 2 (NSTEP と境界の修正) は未実施 (コード変更なし)。L の既定値と書込み元、件数の複製経路は子 #3669 に分けた。
- 検証済みの前段: `provider/build.sh` → `channels_diff` は測定 commit `3c86b93de` で PASS (calls 214・diffs 0)。

## 測定

- 基点: `origin/main` = `14024ed2a` (旧基点 `c2324dea6` から main を取り込み。merge commit `e2d3f7917`・衝突なし)。
- **測定 commit: `3c86b93de`** (ネガティブコントロールのスクリプト `pe_py225_negctl.sh` を追加した commit。コードを変えた最後の commit)。本 REPORT の commit は docs のみ。差分の証跡: `git diff 3c86b93de HEAD -- tools/python/analysis tools/python/host tools/python/provider tools/python/tests` (本 REPORT の commit 後に 0 行を確認)。
- 素材: `fl-win64` を `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` で展開 (1.553 秒・`extracted/block00031_PE.bin` 22,227,016 B)。
- `toolchain-emsdk` は本 run の素材 (`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ) に無かった。上流 emsdk を pin と同じ 6.0.12 で取得して代用した: `git clone --depth 1 --branch 6.0.12 https://github.com/emscripten-core/emsdk.git` → `./emsdk install 6.0.12` (17.688 秒) → `./emsdk activate 6.0.12`。`EMSDK_ENV=<emsdk>/emsdk_env.sh` を指定して `provider/build.sh` を実行。R2 素材と上流 6.0.12 が同一かは `[未確認]`。
- 環境: runner 4 core、node v22.23.3。各検査の前後の load average は 0.15〜0.81 (`uptime`)。

| 検査 | コマンド | 結果 | 所要 |
|---|---|---|---|
| 素材展開 | `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` | rc 0 | 1.553 秒 |
| emsdk 取得 | `./emsdk install 6.0.12` | rc 0 | 17.688 秒 |
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0 (`dist/flprov.{js,wasm}` を作成) | 0.650 秒 |
| channels 差分 | `cd tools/python && node tests/channels_diff.mjs` | `{"calls":214,"diffs":0,"PASS":true}` | 0.037 秒 |
| 走査と対照 | `bash tools/python/analysis/flapi/pe_py225_negctl.sh` (下表) | rc 0 | 88.728 秒 (走査 6 回) |

### 走査とネガティブコントロール (測定 commit `3c86b93de`)

| 行 | 操作 | 期待 | 実測 |
|---|---|---|---|
| 原本 `22fc` | `pe_py225_disp_scan.py 22fc` | store 0・lea 2・その他 5 | store 0 件 / lea 2 件 / その他 5 件 |
| 対照 1 (存在しない disp) | `22f9` | 0 件 | store 0 / lea 0 / その他 0 |
| 対照 2 (正の対照。store の分類) | `2304` | store が 1 件以上 | store 3 件 / lea 1 件 / その他 6 件。store に `0x1186371` (`mov byte ptr [rax + 0x2304], 1`) を含む |
| 1 箇所を壊す (複製 PE) | VA `0x1186378` の `lea rcx, [rax+0x22fc]` の disp を `22fc` から `22f8` へ (1 箇所) | `22fc` の lea が 2 から 1 | 複製の `22fc`: lea 1 件 / その他 5 件 (不変) |
| 同上 | 同上 | `22f8` の lea が 1 から 2 | 複製の `22f8`: lea 2 件 (`0x1186378` と、原本から有る rip 相対の `0x11a0b71`) |

- 走査の出力 (原本 `22fc`): `0x22fc` を含む命令は、`0x118629a`・`0x11862c7`・`0x118639b` (`[rdi/rax+0x22fc]` の読出し)、`0x12d3e3c`・`0x12d3e54` (`[rbx+0x22fc]` の読出し: 件数 `[ptr-8]` の読出し元)、`lea` の `0x1186378` (`&[grid+0x22fc]` を渡す)・`0xe1d2cd` (`lea rdx, [rip+0x22fc]`・用途未確認)。store は 0 件。直接の store が無いのは、件数付き配列を `0x417fc0` の呼出しで作るため。
- `22f8` は 0 件の対照に使えない (原本でも `0x11a0b71` の `lea rdx, [rip + 0x22f8]` が 1 件当たる)。0 件の対照は `22f9` を使う。
- channels_diff の対照: `tools/python` の `host`・`tests`・`dist`・`analysis/flapi/flapi_ids.json`・`analysis/ilmcp` を `$RUNNER_TEMP/py225_chdiff_neg` に複製し、`host/fl_mock.mjs` の `"channels.channelCount": () => st.channels.length,` を `+ 1` に変えると、`node tests/channels_diff.mjs` は `AssertionError [ERR_ASSERTION]: channels/playlist 差分 1 件` で rc 1。原本は rc 0 (PASS)。

## 件数の生成経路 (PE 実測)

| VA | 役割 | 読めた処理 |
|---|---|---|
| `0x11862e0` | 関数の入口 | `push r14` から。`mov ebx, ecx` (`0x11862eb`) で第 1 引数 (ebx) を受ける |
| `0x11862ff` | L を持つ構造体の位置 | `rcx = mem64(0x15e2aa0) + ebx*0xC0` (`0x11862ed`〜`0x11862ff`)。`0x1186300` は `0x11862ff` の命令の途中 |
| `0x1186303` | n の算出 | `call 0x12d09e0` (rcx を渡す)。戻り値を `edi` に置く (`0x1186308`) |
| `0x12d09e0` | n の式 | `mov ecx, [rcx+0x50]` で L を読み、`n = ((L + X - 1) / X) * C`。X = `*(int*)*(0x15e27f0)` = 96 (`add ecx, [rax]` と `idiv [r8]` が同じ X)。C = `*(int*)*(0x15e1c70)` = 4 (`imul eax, [rcx]`) |
| `0x118630c`〜`0x1186316` | channel 列の先頭 | `rcx = *(0x15e2218)` = P (`0x16bafc8`・`.bss`)。`B = *(P)`。count = `mem32(B+0x10)` |
| `0x118631e`〜`0x11863b7` | channel 列のループ | esi を 0 から count−1 まで回す。`obj = 0xfe8bb0(B, esi)` (`0x1186330`〜`0x118633c`) |
| `0x1186365`〜`0x1186371` | grid の有無 | `grid = obj+0x7ac` (`0x1186365`)。非 0 なら `byte [grid+0x2304] = 1` (`0x1186371`) |
| `0x1186378`〜`0x118638f` | 配列の確保 | `rcx = &[grid+0x22fc]` (`lea`)、`rdx = [rip+0x145f22]`、`r8d = 1`、`r9 = n` (`movsxd`)。`call 0x417fc0` |
| `0x417fc0` → `0x417b70` | 配列の確保 (本体) | `0x417fc0` は 4 番目の引数 (n の値) を `[rbp+0x58]` に置き、そのアドレスを r9 にして `0x417b70` を呼ぶ (`0x417fe9`)。`0x417b70` は `*r9` (= n) を件数として受け、旧配列 `*rcx` を `[rbp+0x78]` に読む |
| `0x4180eb`〜`0x4180fe` | ヘッダ | `call 0x409410` (rcx = `r14+0x10`)。`[rax+4] = 1`、`[rax+8] = rcx` (件数 = `[rsp+0x80]`)。データ先頭 = `rax+0x10` なので `[データ-8] = 件数` |
| `0x12d3e20`〜`0x12d3e3c` | 読出し | ptr = `[grid+0x22fc]`。ptr != 0 なら `n = [ptr-8]`。`p < n` なら `byte [ptr+p]`、`p >= n` なら event 経路 (PY-112) |

判断の根拠:
- `0x12d09e0` は、既存 REPORT_PY42 の `getPatternLength` で既定値として同定済みの関数 (要素の +0x44 が正でないときの既定値 `0x12d09e0`) と同じ。式 `ceil(L/X)*C` はその `idiv` / `imul` で確認した。
- 複製元の件数 `S` を取る経路 (`0x418030`) では `min(n, S - start)` になりうる (推定。`0x417b70` の分岐の全体と `0x418030` は未読)。

## L (= `table[ebx]+0x50`) の状態

- `L = mem32(mem64(0x15e2aa0) + ebx*0xC0 + 0x50)`。`mem64(0x15e2aa0)` の静的値は `0x193fce0` (`.data` の qword・`pe_va_read.py`)。`0x193fce0` は `.bss` で、ファイル上は 0 (起動後に実行時に入る)。
- ebx は `0x11862e0` の第 1 引数。呼出し元は未調査。
- L の既定値と書込み元は未調査 (時間切れ)。PE の静的解析からは確定できない。
- 旧版の訂正: 旧版は `P+0x50` を件数の入力としていた。`P = *(0x15e2218)` (= `0x16bafc8`・`.bss`) は channel 列の先頭 (`B = *(P)`) を指すもので、件数の入力ではない。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `L = table[ebx]+0x50` の既定値 (起動直後・空の project) と書込み元。ebx の値 (`0x11862e0` の呼出し元) を含む | n が 64 か未確定。NSTEP 64 の正しさを判定できない | 子 #3669 ([PY-230]) |
| 件数 n の複製経路 (`0x418030`・旧配列がある場合の件数 `min(n, S-start)`) | 旧配列がある場合の件数の式が未確定 | 子 #3669 ([PY-230]) |
| 受入 2 相当: NSTEP と境界 `p >= 64` の修正 | L が決まるまで直す対象が無い | 子 #3669 ([PY-230]) |
| event 経路 (`0x12d16a0`・`0x12df210`) | 件数以上の position の値 (PY-218 の範囲) | 親 #3596 ([PY-218]) |

## 再現

- 展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'`。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- 走査と対照: `bash tools/python/analysis/flapi/pe_py225_negctl.sh` (約 89 秒)。単体の走査は `python3 tools/python/analysis/flapi/pe_py225_disp_scan.py 22fc` (約 14 秒)。
- 逆アセンブル: `pe_disasm.py 11862e0 60`・`12d09e0 50`・`417fc0 50`・`417b70 45`・`12d3e20 40`。
- 静的値: `pe_va_read.py 15e2aa0,193fce0,15e2218,15e27f0,15e1c70,15d89c8,15d898c`。
- provider: `EMSDK_ENV=<emsdk>/emsdk_env.sh bash tools/python/provider/build.sh` → `cd tools/python && node tests/channels_diff.mjs`。
- channels の対照: 上の「channels_diff の対照」の手順。
