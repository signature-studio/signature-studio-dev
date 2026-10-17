# KH-172 (#5653): `build.py ladder` の既定 `--path a` で final.ll の `%arg3` が未定義になる箇所

- 親: #4689 [KH-111] (修正の本体) / 本 issue: #5653 [KH-172] (原因特定。#4689 から分割)。
- 測定 commit: `f195a93a9` (origin/main)。測定は同 commit の worktree (`ws-5653`) で実施。
- 素材: `plugins-kilohearts` の `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/*` → `HeartCore.core_64` (76,642,304 B・sha256 先頭 16 hex `d55ce8b4c0ad7ebe`。REPORT_APPENDIX_780 §3c と同一)。
- ツール: [EMSDK] (emcc 6.0.12) と [RETDEC] (`retdec-decompiler`)。`docs/REFERENCES.md` のエントリ ID で参照。

## 0. 結論

- 既定 `--path a` の `final.ll` で `%arg3` が未定義になる直接の原因は、**`snapins/lift/kh_passes.py` の `pass_f2`** (xmm 入口 live-in の引数化、§2)。
  RetDec の定義 `i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4` を、`pass_f2` が `i64 %arg1, i64 %arg2, double %kxmm2, double %kxmm3` に書き換える。Win64 では GPR と XMM が引数の位置 (slot) を共有するため、`xmm2`/`xmm3` を使う関数では `%arg3`・`%arg4` (GPR の 3・4 番目) が**シグネチャから消える**。本体には `%arg3` の使用が残る。
- emcc の最初の報告は `function_180bac490` の `%arg3` (`final.ll:4918`) だが、同じ欠陥で **6 関数**が影響を受ける (§3)。
- 別欠陥 (本 issue の範囲外・§4): `pass_branches` が生成する BB が 2 つの terminator を持つ。シグネチャを直しても `final.ll` は LLVM IR として不正で、emcc は通らない。

## 1. 再現

- `cd snapins/lift && python3 build.py ladder --no-compare` (既定 `--path a`)。`rc=1`。
  `final.ll:4918:36: error: use of undefined value '%arg3'` → `call i128 @__asm_movsd(i64 %arg3)`。emcc 段の失敗。
- 所要・load は本付録では未計測 (失敗の再現だけを目的とした run)。

## 2. 原因の機械的な確認

| 段 | `function_180bac490` の定義 |
|---|---|
| RetDec 生 IR (`work/ladder/retdec/ladder.dc5cfb6299.drc.ll` 5518 行) | `(i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4)` |
| `passes.json` の live-in | `180bac490:xmm2 = double`・`180bac490:xmm3 = double` |
| `fix.ll` (`pass_f2` 後) 5549 行 | `(i64 %arg1, i64 %arg2, double %kxmm2, double %kxmm3)` |
| `final.ll` (4876 行) | 同上。本体は 4918 行で `%arg3`・4895 行で `%arg4` を読む |

- `pass_f2` (`kh_passes.py` 395〜410 行) の組み立て: 位置 `pos` が `newp` (xmm の live-in) にあれば `%kxmmN` を出し、そのとき `pos+1` の既存 GPR 引数は**捨てる**。末尾の追加ループは `pos-1 > maxpos` の GPR しか戻さない。そのため、`xmm2`/`xmm3` の位置 (pos 2, 3) に当たる `%arg3`・`%arg4` (`pos+1` = 3, 4) が落ちる。
- 同じ欠陥の別の表れとして、`pos` が**全部 xmm** の関数では GPR が全部消える (`function_18132a4e4`・`function_18132a978` は RetDec で 4 個の `i64` だったものが、`(float, float, double, float)` だけになる)。

## 3. 影響範囲 (`final.ll` を走査した結果)

RetDec 定義の引数を超えて、本体が `%argN` を読むのに定義が無い関数を数えた (`final.ll` の全 define を走査。走査スクリプトは repo に無く、本 PR では保存していない。再現には `final.ll` の define ごとに `%argN` の使用と定義を照合する一時スクリプトが要る):

| 関数 | 定義行 | 未定義の `%argN` |
|---|--:|---|
| `function_180bac490` | 4876 | arg3・arg4 (emcc が報告した関数) |
| `function_180bacef0` | 4977 | arg1・arg2・arg3 |
| `function_180fcce40` | 6685 | arg1 |
| `function_180fd8988` | 10292 | arg4 |
| `function_18132a4e4` | 12612 | arg1・arg2・arg3・arg4 |
| `function_18132a978` | 12906 | arg1・arg2・arg3・arg4 |

- `pass_f2` で署名が変わった関数は全部で 30 件。そのうち上の 6 件だけが「本体が未定義の `%argN` を読む」。残りの 24 件は本体が読まないため、emcc は通る。
- 呼び出し側 (`function_1804d98b0` 等の call) は RetDec の 4 引数のまま。署名を直す場合は call 側の引数数も揃える必要がある。

## 4. 別欠陥 (修正済み: 測定 commit `f8f37b452`・PR #6128。検証状態は §7)

`pass_branches` (`kh_passes.py` 209 行〜) の出力で、`khbd17` (`final.ll` の 5210 行付近) は terminator を 2 つ持ち、直後の `khsk18` は命令も terminator も持たない空のブロック (修正前の状態):

```
khbd17:
  ...
  br label %dec_label_pc_180bad220
  br label %khsk18
khsk18:
```

- 後続の `br label %khsk18` は、領域の末尾が既に terminator (`br`) で終わるブロックに `fn.after[i1]` を足すために生じる。
- `final.ll` は `%arg3` の箇所 (4918 行) で emcc が止まるため、この欠陥は今の run では見えない。`%arg3` を直した後の `clang -x ir` で `expected instruction opcode` (5228 行) として初めて出る。
- 実測: `final.ll` の 4876 行の定義だけを `(... , i64 %arg3, i64 %arg4)` に置き換えた試験コピーは、`llvm-as` (LLVM 18) で `5228:1: error: expected instruction opcode` で止まった (`%arg3` の報告は消えた)。`clang -x ir` は同じ形を検出しないので使わない (§7.4)。

## 5. 修正の方向 (未実施・#4689 の受入)

- `pass_f2` の署名組み立てを、GPR 引数は位置に関係なく必ず残し、xmm の live-in は**追加**の引数として足す形にする (GPR と XMM の位置の衝突を解く)。call 側の引数数も同時に揃える。
- `pass_branches` は、領域の末尾が terminator で終わるときに `fn.after` へ `br` を足さない。
- 修正後は `build.py ladder --no-compare` (既定 `--path a`) が exit 0 になるかを確認する (#4689 受入 1)。`--path s0` の wasm 574,270 B は変わらないこと (#4689 受入 2)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `pass_f2` の署名組み立ての修正 (§5) | 既定 `--path a` の emcc 失敗 | #4689 (KH-111) |
| `pass_branches` の二重 terminator (§4) | 署名修正後に emcc が止まる | #4689 (KH-111) の範囲に追記 |
| 6 関数の本体の動作一致 (`--no-compare` を外した比較) | 未測定 | #4689 (KH-111) |

## 7. 二重 terminator 修正 (`f8f37b452`) の検証 (実測)

- 修正の commit: `f8f37b452` (`snapins/lift/kh_passes.py` の `pass_branches`。13 行追加・1 行削除)。
- 測定 commit = `672af0466` の `lift/` 差分は `f8f37b452` と同一 (`git diff f8f37b452 672af0466 -- tools/targets/kilohearts/snapins/lift/` は 0 行)。
- 測定環境: 4 vCPU・素材は `plugins-kilohearts` (HeartCore.core_64 76,642,304 B・sha256 先頭 16 hex `d55ce8b4c0ad7ebe`)・`toolchain-emsdk` (emcc 6.0.12)・`toolchain-retdec` (RetDec v5.0)。いずれも `$ARTIFACTS_DIR` から展開。測定時の load average は 0.4〜1.3 (`uptime`、実行前後に取得)。

### 7.1 `build.py ladder` の実測 (HEAD `672af0466`)

| 実行 | rc | 結果 | 所要 (wall) | peak RSS |
|---|--:|---|--:|--:|
| `python3 build.py ladder --no-compare` (既定 `--path a`) | 1 | `final.ll:4918:36: error: use of undefined value '%arg3'` → emcc 失敗 | 45.3 s | 636 MB |
| `python3 build.py ladder --no-compare --skip f2` | 1 | emcc 段で `wasm-ld: undefined symbol: rax` / `r8` / `rcx` (stubs.o)。IR 構文エラーは出ない | 3.9 s | 137 MB |
| `python3 build.py ladder --path s0 --no-compare --tag s0` | 0 | `wasm_bytes` **574,264**・`undefined_imports []`・`emcc_peak_rss_mb` 156 | 15.9 s | 635 MB |

- 再現: `cd tools/targets/kilohearts/snapins/lift` → 上の 3 コマンドを順に実行 (`TMPDIR=$RUNNER_TEMP`・`/usr/bin/time -v` 付き)。`--tag s0` は実際に通ることを確認済み (minor 指摘への回答)。
- 並列 1 プロセス (`build.py` は直列)。load average は実行前後で 1.1〜1.3。
- 既定 `--path a` と `--skip f2` は `work/ladder/main/` を上書きする (`--tag` を付けていない run のため)。`--path s0 --tag s0` は `work/ladder/s0/` に出る。

### 7.2 修正前 `fe48dca85` の同コマンド (対照)

修正前は `f8f37b452~1` の worktree (`fe48dca85`) で同じ手順を実行。

| 実行 | rc | 結果 | 所要 (wall) | peak RSS |
|---|--:|---|--:|--:|
| `python3 build.py ladder --no-compare` (既定 `--path a`) | 1 | `final.ll:4918:36: error: use of undefined value '%arg3'` (修正後と同一) | 43.9 s | 635 MB |
| `python3 build.py ladder --path s0 --no-compare --tag s0` | 0 | `wasm_bytes` **574,264**・`undefined_imports []` | 15.5 s | 635 MB |

- `--path s0` の `wasm_bytes` は修正前後で同じ 574,264 (修正の影響なし)。

### 7.3 二重 terminator の解消 (修正前後の IR を比べた結果)

数え方: `final.ll` を基本ブロック (ラベル行・`<label>:N` 行で区切る) ごとに、terminator (`br`・`ret`・`switch`・`unreachable`・`invoke` 等) の行数を数え、2 以上のブロックの数を出す。スクリプトは `work/` 外の一時ファイルで、repo には入れていない。

| 対象 | 二重 terminator ブロック数 | 例 (修正前) |
|---|--:|---|
| 修正前 `fe48dca85` の `final.ll` (`--path a`) | **5** | `khbd17:5218` (2 terminator)・`khbd20:5332`・`khbd23:5431`・`khbd30:7021`・`khbd40:13161` |
| 修正後 `672af0466` の `final.ll` (`--path a`) | **0** | — |
| ネガティブコントロール (`fe48dca85` の `final.ll` を数えたもの) | 5 (上の行と同じ) | — |

- `final.ll` は `%arg3` のエラーで emcc が止まるため、`clang`・`llvm-as` で見られるのは修正前後の IR 全体の先頭エラーだけ。
- 修正前の `khbd17` 付近 (5218〜5228 行): `br label %dec_label_pc_...` の直後に `br label %khsk18` があり、`khsk18:` は命令を持たない。
- 修正後の `final.ll` には `khbd17` という名前は無い (ラベル番号は生成ごとに変わるため、番号では比べない。本表は「ブロック数」で比べる)。

### 7.4 検査の方法

- `clang -x ir -fsyntax-only` と `clang -x ir -c` は、二重 terminator を含む最小例 (`bad_term.ll`) を rc=0 で通すため、この検査には使えない (本節では採用しない)。
- `/usr/lib/llvm-18/bin/llvm-as` は verifier 付きで、修正前の `khbd17` と同形の最小例 (空の `khsk` を伴う 2 つの `br`) を `expected instruction opcode` で拒否し、正しい形は通す。
- 修正前後の `final.ll` は `%arg3` で先に止まるため、`llvm-as` の出力は両方とも `4918:36: use of undefined value '%arg3'` (同一)。
- `%arg3` を `function_180bac490` の定義でだけ直した試験コピー (`/tmp` のみ):
  - 修正前: `5228:1: error: expected instruction opcode` (REPORT §4 の記述と一致)。
  - 修正後: `5025:42: use of undefined value '%arg1'` (`function_180bacef0` の別の未定義。§3 の表の対象で本 issue の範囲外)。空ブロック由来の構文エラーは出ない。

### 7.5 状態

- 受入 1 (既定 `--path a` が exit 0): **未達**。`%arg3` (`pass_f2` の署名) は #4689 の次 run。
- 受入 2 (`--path s0` の `wasm_bytes` 不変): 修正前後で 574,264 (一致)。issue・`REPORT_APPENDIX_780.md` の 574,270 B とは 6 B 差。差は本 PR の修正ではない (修正前から 574,264)。`f9da4f150` 以降の `lift/` の差分 (`941777d89` の `GetLastError` shim 削除・`11a17671d` の `snapins.json` の carveproc 追加) が候補だが、`f9da4f150` で同素材を測り直していないので原因は未確定。
- 二重 terminator の解消: **実測で確認** (修正前 5 → 修正後 0)。
