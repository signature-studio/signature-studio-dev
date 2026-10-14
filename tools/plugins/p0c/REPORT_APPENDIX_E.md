# tools/plugins/p0c REPORT 付録 E (§14〜§15)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本ファイルは本体から**無変更で分割移動**した節の全文 (#378, `docs/DOC_MAP.md` §1)。節番号・見出しは移動前のまま。§15.4 (#360) は分割後に main で追記された節で、同様に無変更で置く。

## 14. P0c-6 追記 (#277): native crash 7 kernel と abi-mismatch 7 kernel の原因は ABI 抽出・引数割付・入力ドメインだった

作成: 2026-10-12 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD: `400d546` (main) / 検証 HEAD: `15617b4`
既知類型との関係 (DEFECTS.md): D19 (差分ハーネスの境界 read 不一致) と同系統 (§12.4 の候補)。新類型候補は §14.4。
素材: `fl-win64.tar.zst` の `block18983_PE.bin` のみ。`work/k80.lift.ll` は `lift_ranges.sh` で再生成 (RetDec v5.0)。
数え方・buf_diff の定義は §11.3 / §12.2 と同じ (2000 case/kernel, fork 隔離, 並列 1)。

### 14.1 結論 (先出し)

1. **対象 A の sig11 は 7 → 0** (`p0c4_abi_e2e.py` の `run=61 ok=54 sig11=7` → `run=67 ok=67 sig11=0`)。
   7 kernel は 4 つの別原因で、いずれも lift IR / ext 精度ではなく `k80abi.py` / `k80_diff.py` の欠陥だった。
2. **対象 B は 7 のうち 6 kernel が ok モデルになった** (0x5dee90 / 0x5df040 / 0x5e09f0 / 0x5e0a70 / 0x5e0b10 /
   0x5e1210)。残る 0x5e12b0 は引数接続では救えない (§14.3)。
3. 数値差分が測れるようになった結果、**ok かつ buf_diff=0 の kernel は +10**: 0x5e0630 / 0x5e06e0 /
   0x5e08d0 / 0x5e09f0 / 0x5e0a70 / 0x5e0b10 / 0x5e0c00 / 0x5e1010 / 0x5e1210 / 0x5e1280。起点 (#277 単独の検証 HEAD
   `15617b4`) では 29 → 39 で、起点で bit-exact だった 29 kernel は 1 つも失っていない。§13 (#310) を取り込んだ
   merge 後 HEAD の実測は **45** (`p0c4_abi_e2e.py 2000` の CSV で status ok かつ buf_diff=0 を数えた値。
   45 のうち上記 10 を除く 35 は件数が §13 の「修正後 35」と一致するが、kernel 集合の照合は未実施)。起点の sig11 / abi-mismatch で測れていなかった kernel のうち差分が出たものは
   §14.3 に残差として分けた。
4. 回帰 11 kernel (0x5de820 ほか) は buf_diff=0 維持。

### 14.2 原因と修正 (kernel 別・実測)

| 原因 | 対象 kernel | 修正 | 負論対照 (修正を外すと) |
|---|---|---|---|
| (a) `k80abi.py`: 先に write 済みの reg (`mov r8, rdx` 後の `[r8]`) を引数ポインタ base に数え、実際の引数 r8 (個数) に buffer を割り当てて OOB | 0x5e0630 / 0x5e06e0 / 0x5e08d0 / 0x5e0a70 | write 済み reg の deref は base でなく copy 逆伝播の種にだけ使う | `K80_NO_WRITTEN_BASE=1`: 上記 4 が sig11 |
| (b) `k80_diff.py`: RetDec の `%argN` は win64 gpr 序数だが、機械語が rcx を読まない kernel で使用 slot を詰めて割り当て、IR が 1 つずれた arg に store (NULL 書き込み) | 0x5de3e0 / 0x5e1280 | `%arg1..4` は序数で固定 (後ろの gpr を使うときのみ) | `K80_NO_ARGORD=1`: 2 kernel が sig11 |
| (c) `k80abi.py`: `lea [rcx+r8*4]` の index 専用 reg (r8=個数) が copy 伝播で base 扱い | 0x5e02b0 | ptr_struct を持つ kernel に限り index 専用 reg を base から外す | `K80_NO_IDX_NOT_BASE=1`: sig11 |
| (d) `k80_diff.py`: clip_index kernel で gain が大きいと `cvttsd2si`=0x80000000 → neg でも INT_MIN → clamp 素通り → 負添字 | 0x5e0c00 | gain 指数を 2^-9..2^-1 に制限 (ドメイン制約) | `K80_NO_CLIPRANGE=1`: sig11 (他 2 kernel の buf_diff も変動) |
| (e) `k80abi.py`: `movlps xmm, [m]` の dest を read 扱いし偽の xmm 引数 (xmm0/xmm2) を作った | 0x5dee90 / 0x5df040 | movlps/movlpd/movhps/movhpd の dest は read から除外 | `K80_NO_PARTIAL_LOAD=1`: 2 kernel が abi-mismatch (run 65) |
| (f) `k80abi.py`: stack 引数幅を命令名 (`cvtss2sd` の `sd`) で 64bit と誤判定 | 0x5e09f0 / 0x5e0a70 / 0x5e0b10 / 0x5e1010 | メモリオペランドの大きさを使う | `K80_NO_MEMW=1`: 4 kernel の buf_diff が 0 → 2,580,673 / 2,583,215 / 1,291,834 / 787,450 |
| (g) `k80_argfix.py` [C]: `cvtss2sd xmm0, xmm3` (reg-reg 単項) の source xmm を接続できなかった | 0x5e09f0 / 0x5e0a70 / 0x5e0b10 | dest を含まない形を second pass で突合 | `K80_NO_REGSRC=1`: **差なし** (下記) |
| (h) `k80abi.py`: 自分で書いた stack home slot (`movss [rsp+0x18], xmm2`) の読み戻しを stack 引数扱い | 0x5e1210 | write 済み stack slot は read 候補から除外 | `K80_NO_STACKW=1`: 0x5e1210 が結果から消える (abi-mismatch) |
| (i) `k80_argfix.py` [C]: 同じ placeholder が `movss` と `cvtss2sd` の両方に使われ出現順突合が破綻 | 0x5e1210 | 各 use が取りうる xmm 集合の積が 1 つのときだけ接続 | `K80_NO_INTERSECT=1`: 0x5e1210 が結果から消える |

(g) の負論対照は **差が出なかった** (`K80_NO_REGSRC=1` で run=67 ok=67、CSV も不変)。(g) を入れた時点 (HEAD `fce0e86`) では
argfix の `helper_xmm` が 9 → 12 に増え 0x5e09f0 / 0x5e0a70 / 0x5e0b10 が ok になったが、その後に入れた (i) の
積集合 fallback が同じ placeholder を接続できるため、現状では (g) は冗長 (未検証: (g) と (i) の両方を外した場合)。
冗長なため削除せず、環境変数で外せる形で残している。

### 14.3 実測 (検証 HEAD `15617b4`)

| コマンド | 結果 |
|---|---|
| `p0c4_abi_e2e.py 2000` | rc=0、26.7〜27.1 s (load average 0.5〜0.9)、`run=67 ok=67 sig11=0`、起点は `run=61 ok=54 sig11=7` |
| `p0c4_abi_e2e.py 2000` (origin/main = `35bdf9d` を merge した後のコミット済み HEAD `330ada8`) | rc=0、14.5 s (load average 0.28→0.44)、`run=67 ok=67 sig11=0`、ok かつ buf_diff=0 は 45 |
| `p0c4_e2e.py 2000` | rc=0、111.8 s / 112.5 s (2 回)、判定 bit-exact 7/14 (§12.2 と同じ) |
| `p0c2_e2e.sh 2000` | rc=0、50.5 s |
| `p0c3_e2e.sh 2000` | rc=0 (回帰判定から 0x5de3e0 を除外した後。除外前は FAIL-REGRESS、下記) |
| `ext_core_test` N=300000 | `ext core OK`、1.9 s |

対象 A (起点 sig11 → 修正後):

| kernel | buf_diff | ret_diff | 備考 |
|---|---:|---:|---|
| 0x5e0c00 | 0 | 0 | bit-exact |
| 0x5e0630 | 0 | 0 | bit-exact |
| 0x5e06e0 / 0x5e08d0 | 0 | 2000 | ret は native が rax を放置 (合否は buf_diff のみ) |
| 0x5e1280 | 0 | 0 | bit-exact |
| 0x5e02b0 | 2,578,706 | 0 | **残差** (maxulp 610,852,255)。f32chain、x87 の fild×fmul 模型 (推定・未検証) |
| 0x5de3e0 | 2000 | 0 | **残差**: IR の store が `[rdx]` (上位 32bit) を欠落している (下記) |

対象 B (起点 abi-mismatch → 修正後): 0x5e09f0 / 0x5e0a70 = buf_diff 0 (ret 2000)、0x5e0b10 / 0x5e1210 = 0 (ret 0)、
**0x5dee90 = 2,565,360 / 0x5df040 = 2,565,277** (ok モデルだが差分あり・残差)。0x5e12b0 は abi-mismatch のまま。

**残差・未解決 (推定ラベル付き)**:

- **0x5de3e0 (buf_diff=2000)**: 機械語は `fistp qword` の上位 dword を `[rdx]`、下位を `[r8]` に書くが、
  x87fix 後 IR は `%arg3` への store のみ (上位 dword の store が無い)。RetDec が `[rdx]` 側 store を落としたと**推定**
  (lift 欠落。DEFECTS 類型は未照合)。起点では sig11 で buf_diff が測れず `p0c3_e2e.sh` の回帰判定を素通りしていた。
  今回モデルが直り測れるようになり FAIL-REGRESS になったため、判定リストから外した (欠陥を隠すのではなく
  「測れていなかった」ことを REPORT に残す)。
- **0x5dee90 / 0x5df040 (約 2.57M)**: 未調査 (ok モデルで差分が出るようになった段階)。
- **0x5e12b0**: RetDec の IR が `ucomiss` のフラグ使用と被演算子 (xmm0/xmm1) を落とし、引数ゼロ・戻り値定数 0 の関数
  (`define i64 @function_5e12b0()`) になっている。引数接続の対象外で、lift 側の欠陥 (0x5e0d80 で §13 が修復した
  ucomiss 符号欠落と同系統の**推定**)。
- 0x5e0d80: 検証 HEAD `15617b4` 時点は 951,534 だったが、§13 (#310) の ucomiss 符号修復を取り込んだ merge 後は
  **buf_diff=0** (`p0c4_abi_e2e.py 2000` 実測)。#331 の対象ではない。
- 0x5e1490 (1,046,283 → 1,201,366): 0x5e0c00 の gain 制限に伴い乱数列が変わったため変動
  (`K80_NO_CLIPRANGE=1` で旧値に戻る)。原因は未調査で、悪化ではなく入力列の差。

### 14.4 DEFECTS.md 行案・未解決・起票先

- **D23 (新, 候補) ABI 抽出の read/write 誤分類**: 症状 = native 実行が sig11 または引数が偽に増える。
  根本原因 = (a) write 済み reg の deref、(c) index 専用 reg、(e) 部分 load の dest、(f) 命令名による幅推定、
  (h) 自書き stack slot の読み戻し。検出信号 = `gpr_base` / `xmm_slots` / `stack` が機械語を読むと食い違う。
  修復 = 負論対照付きの個別除外 (§14.2)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~0x5de3e0 の `[rdx]` store 欠落 (lift)~~ | 解決 (#982, §14.7) | — |
| 0x5e12b0 の ucomiss 被演算子・flags 落ち (lift) | abi-mismatch のまま (§14.8 → E2) | #938 [T-SH-22] (同系統の汎用 IR pass) |
| ext 精度が必要な kernel の wasm32 検証・framework 統合 | #269 §12.4 と同じ | #197 (既存提案) |

(0x5dee90 / 0x5df040 / 0x5e02b0 は §14.6 で解消。当初の「x87 模型の問題」の推定は外れ、原因は deref の落ち。)

### 14.6〜14.8 (#983・#982 の修復詳細・#331 残件の現況)

> §14.6 (#983: 残差 3 kernel の原因確定と修復)・§14.7 (#982: 0x5de3e0 の上位 dword store 復元)・§14.8 (#331 残件の現況) は [`REPORT_APPENDIX_E2.md`](REPORT_APPENDIX_E2.md) に分割移動した (250 行上限・無変更)。

## 15. 環境パス置換 (#346, 親 #294・先行 #312): /home/ubuntu 絶対パスを tools/shared へ

既知類型との関係 (DEFECTS.md): 該当なし (パス参照の置換のみで lift/IR には触れない)。

### 15.1 変更

`*.sh *.py *.json *.ts *.mjs` (work/ 除く) の `/home/ubuntu` 参照 9 行を置換。既定値は従来と同一なので、環境変数未設定のローカル挙動は変わらない。

| ファイル | 置換 |
|---|---|
| `p0c_e2e.sh` `p0c2_e2e.sh` | `source tools/shared/env.sh` + `PE="$FL_WIN64_DIR/extracted/block18983_PE.bin"` |
| `f80_assess.py` `k80chop.py` `k80abi.py` | `tools/shared/paths.py` の `FL_WIN64_DIR` から `PE` を組む |
| `kernel_matrix.py` `verify_table.py` | 同 `EXT = FL_WIN64_DIR/extracted` |
| `k80_diff.py` | `PE` は同上。`LIFTP` は `REPO_ROOT/tools/plugins/lift/passes` (旧: `/home/ubuntu/work/webstudio/...` 固定) |

`p0c_e2e.sh` step 1 は `inventory/kernel_table.py` に `$PE` を引数で渡す。同スクリプトの既定値が `/home/ubuntu` 固定 (p0c の外・本 PR の範囲外) のため。

### 15.2 検証 (検証起点 `origin/main` = 2c3e526、素材は `fl-win64` のみ)

- 受入条件 1: `grep -rn '/home/ubuntu' tools/plugins/p0c --include=*.sh --include=*.py --include=*.json --include=*.ts --include=*.mjs --exclude-dir=work | wc -l` → 0。
- 受入条件 2 (before/after): 同一サブセットを置換前 (`origin/main` の detached worktree・`/home/ubuntu/work/analysis/win64` を symlink で用意) と
  置換後 (symlink 削除・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` のみ) で実行し出力を `cmp`。
  サブセット = `kernel_table.py` → `f80_assess.py` → `f80_micro` (2000000 case) → `k80abi.py` → `k80chop.py`。
  所要 before 1.06 s / after 1.06 s、load average 0.45 / 0.38 (1 分値)、各 n=1・直列。

| 出力 | before/after | sha256 先頭 12 桁 |
|---|---|---|
| kernel_table stdout / `kernel_table.json` | 一致 | 55b1810cba94 / ce8c15353720 |
| f80_assess stdout / `f80_classes.json` | 一致 | 7b13c98d9494 / ef4fdcd06cf9 |
| f80_micro stdout | 一致 | d092659b28a9 |
| k80abi `k80abi.json` | 一致 | b30e176cd3eb |
| k80chop stdout | 一致 | e9192d1bbce2 |
| k80abi stdout | 1 行目のみ差 (出力先絶対パスに worktree 名が入る) | — |

- ネガティブコントロール: `FL_WIN64_DIR=/nonexistent python3 k80chop.py` → `FileNotFoundError: /nonexistent/extracted/block18983_PE.bin` で FAIL (`FL_WIN64_DIR` が実際に効いている)。
- 構文: `python3 -m py_compile` 6 本・`bash -n` 2 本 OK。

### 15.3 検証範囲 / 範囲外 / 未解決

範囲外: `kernel_matrix.py` `verify_table.py` `k80_diff.py` `p0c2_e2e.sh` `p0c_e2e.sh` の実行。前 3 本は `nsis_blockmap.json` や `/opt/retdec` の lift 成果物
(`toolchain-retdec`・`work-m6-ott` 等) が要る。置換は `PE` / `EXT` / `LIFTP` の定義行のみで、構文確認と `FL_WIN64_DIR` 解決の確認に留めた。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `inventory/kernel_table.py:15`・`lift/batch_lift.sh:31` に `/home/ubuntu` 既定が残る (p0c 外) | 他 area の置換 issue 待ち | #294 の該当 area 子 issue |
| `kernel_matrix.py` `verify_table.py` `k80_diff.py` と e2e 全体を `oc_artifacts` 付きで未実行 | 置換行以外の挙動は未検証 | #360 (本 PR のレビュー run でも `oc_artifacts:` で再実行可) |
| §13.4 の「絶対パス依存 (#294)」のうち p0c 内の `/home/ubuntu` 参照は解消 (`/opt/retdec` は残る) | — | #294 |

### 15.4 #360: 追加素材での full e2e before/after (検証 HEAD 856be6b / 比較元 8af7eb0)

素材: `fl-win64` `toolchain-retdec` `toolchain-emsdk` `work-m6-ott` `work-liftlib` (`oc_artifacts`)。before = `856be6b^1` (= `8af7eb0`、置換前)、after = `856be6b` (#359 merge)。
before は `/home/ubuntu/work/analysis/win64` と `/home/ubuntu/work/webstudio` を symlink で用意、after は `/home/ubuntu` を削除し `FL_WIN64_DIR` のみ。各 n=1・直列・4 コア runner。

結論: **`p0c_e2e.sh` / `p0c2_e2e.sh` は置換前後とも rc=0、決定的な成果物はすべて一致**。不一致は RetDec が同一入力でも出力を変えることだけで、置換とは無関係 (下記)。

| 項目 | before | after |
|---|---|---|
| `p0c_e2e.sh` | rc=0、12.9 s (kernel_matrix は skip。前段で別実行) | rc=0、8.6 s (同) |
| `p0c_e2e.sh` 初回 ([2] kernel_matrix.py 12 = 181 DLL 走査を含む) | 515.7 s、rc=1 ([4] で上記の理由)、load 12.09 (開始 1 分値) | 512.5 s、rc=0、load 1.97 (同) |
| `p0c2_e2e.sh` | rc=0、47.8 s、load 3.82 | rc=0、44.7 s、load 1.80 |

(表の `p0c_e2e.sh` 行は `work/kernel_matrix.json` が既にあり [2] を skip した再実行。kernel_matrix を実行した初回の `p0c_e2e.sh` 全体が、after は rc=0・512.5 s (その中の [2])、
before は 515.7 s で `p0c/work/kernel_table.json` の置き場所違いにより [4] で rc=1 だったため、同ファイルを `p0c/work/` に置いて再実行した。after の再実行 (8.6 s) の load は記録に失敗。)

一致を `cmp` / sha256 で確認したもの (先頭 12 桁):

| 出力 | 結果 |
|---|---|
| `kernel_matrix.json` / `kernel_used_norm.json` / `table_verify.json` | 一致 (487412af06e6 / 0b123bd6264f / e5709ebd4e62) |
| `verify_table.py` stdout ([3])、`f80_assess` + `f80_micro` stdout ([5][6]) | 一致 (8623cae11386 / 83bf33956334) |
| `k80abi.json`、`diff/k80.lower.ll`、`diff/k80.argfix.ll` | 一致 |
| `p0c2_sweep.csv` (194 行) | 一致 (52d0c45c63f9) |
| `p0c2_e2e.sh` stdout (パス正規化後) | 一致 (idempotent OK / argfix idempotent OK / wasm32 compile OK 100972 bytes) |

**RetDec は非決定的** (置換と無関係): `retdec-decompiler` に同一 PE・同一 ranges を与えて 2 回走らせると `k80.drc.ll` の sha256 が変わる (alloca の並びと `uselistorder`)。(追記 #695/#887: alloca 並びは `base.canon_alloca_order` で正規化済み。k80 の base.ll は ASLR 有無によらず一致。手順は `tools/liftlib/REPORT_APPENDIX_D.md` §23.4。)
このため before/after で再 lift した `k80.lift.ll` は 58 行差になる。lift 以降を比較するため、after では `k80.lift.ll` を before のものに揃えてから `p0c2_e2e.sh` を再実行し、上表の一致を得た。
差が残るのは lift 由来の `k80.*.ll` / `k80_simd.c` / `k80.drc.*`、実行ごとにアドレスが変わるログ (`build.log` `run.err`)、`k80diff` バイナリ、`diff/driver.c` の `map_image(...)` の PE パス 1 行 (これは置換の意図した差)。

`nsis_blockmap.json`: どの素材にも無く (`block_manifest.json` も無い)、`f2/mk_blockmap.py` で `PLUGIN_MATRIX.json` から再構成した (182 行、sha256 9dfb59584586)。
`kernel_matrix.py` が使うのは `kind=PE` で `Fruity\Effects|Generators` 配下の行のみで、181 DLL / 133 delphi / init 発見 130 は before/after で同じ。

ネガティブコントロール (after、すべて rc=1): `FL_WIN64_DIR=/nonexistent` で `p0c_e2e.sh` / `p0c2_e2e.sh` / `verify_table.py` / `k80abi.py` が
`FileNotFoundError: /nonexistent/extracted/block18983_PE.bin`。`FL_WIN64_DIR` 未設定かつ `/home/ubuntu` 無しでは `p0c2_e2e.sh` が旧既定 `/home/ubuntu/...` を見て失敗する (既定値が従来のまま)。
`grep -rn '/home/ubuntu' tools/plugins/p0c ... --exclude-dir=work | wc -l` → 0。

範囲外 / 未解決: `inventory/kernel_table.py:15` と `lift/batch_lift.sh:31` ほか `lift/` 配下の `/home/ubuntu` 既定は別 area の置換 issue (#294 配下) で扱う。
`k80_diff.py` は `p0c2_e2e.sh` [6] 経由で実行済み (`LIFTP` は `REPO_ROOT` 基準で解決)。RetDec の非決定性は §15.4 に実測を残すのみで、RetDec 非決定は #668、`p0c_e2e.sh` [4] の `kernel_table.json` 置き場所と `nsis_blockmap.json` 生成は #669 に起票。


### 15.5 #346 受入条件 2 の実測 (検証 HEAD d529f071 / 比較 before 8af7eb0 + [4] 1 行修正 / after 856be6b)

本節の fresh 実測は検証 HEAD `d529f071` (main `5847ac61` を merge した PR head)。コードは `d529f071` と同一で、後続 commit は本 REPORT のみ変更する。
素材は `fl-win64` のみを `$RUNNER_TEMP/fl-win64` に展開。RetDec・emsdk は runner 既存の `[RETDEC]`・`[EMSDK]` (`docs/REFERENCES.md`)。依存 (pefile・capstone・numpy) は repo 外の venv。`llvm-as` は `/usr/lib/llvm-18/bin` を PATH に通した。各 n=1・直列・4 コア runner。

| 検証 (`d529f071`・fresh = `work/` 空) | rc | 所要 | stdout 行数 | 開始 load (1 分値) | 終了 load (1 分値) | 注記 |
|---|---|---|---|---|---|---|
| `p0c_e2e.sh` ([2] kernel_matrix 込み) run A | 0 | 515 s | 135 | 0.55 | 7.89 | 本表の初回 run |
| `p0c_e2e.sh` run B (競合解消報告) | 0 | 521 s | 未記録 | 未記録 | 7.80 | 開始 load 未記録 |
| `p0c2_e2e.sh 200` run A (1 回目) | 0 | 33 s | 75 | 7.26 | 4.49 | 直前の `p0c_e2e.sh` の負荷が残っていた可能性あり (未確定) |
| `p0c2_e2e.sh 200` run B (2 回目) | 0 | 9 s | 75 | 3.49 | 3.11 | 直前 run A の負荷が残っていた可能性あり (未確定) |
| `p0c2_e2e.sh 200` run C (競合解消報告) | 0 | 15 s | 未記録 | 未記録 | 2.90 | 開始 load 未記録 |

各 run は n=1・直列。run B・C は報告コメント (head `d529f071`) の実測で、実行順は報告から特定できない。`p0c2_e2e.sh` は全 run で `== p0c2 e2e OK ==` で終了。PR 本文の「検証」節は本表への参照のみとし、数値は本節が正本。
開始 load の値は負荷が残った状態での値を含むため、同一条件の再現値として扱わない。
run 3 の HEAD 行 (`b1e5f88a` の `p0c_e2e.sh` 6.7 s・`p0c2_e2e.sh 200` 7.5 s) は kernel_matrix・lift を skip した実行のため fresh 値ではなく、本表から除外した。

受入 2 の before/after 比較 (run 3 の記録。検証 HEAD `b1e5f88a` 時点で、main 取り込み前の tree。**現 HEAD `d529f071` では未検証**。現 HEAD で before/after を比較し直していない。`[WIN64]` と `[RETDEC]` の既存 install を before 側の旧パス参照先として symlink で用意、after は `FL_WIN64_DIR` のみ):

| 項目 | before (8af7eb0 + [4] 1 行修正) | after (856be6b) |
|---|---|---|
| `p0c_e2e.sh` 初回 (kernel_matrix 込み) | rc=0、354.4 s (開始時 uptime load 1 分値 0.55) | rc=0、350.9 s (開始時 uptime load 1 分値 3.57) |
| `p0c2_e2e.sh 200` | rc=0、9.4 s (load 未記録) | rc=0、14.7 s (load 未記録) |

判定 (run 3 の記録。現 HEAD では未検証): `p0c_e2e.sh` の stdout (132 行) と `p0c2_e2e.sh` の stdout (パス正規化後) は before/after で一致。`cmp` 一致 (`work/` 配下の成果物): `k80.final.ll` `table_verify.json` `kernel_matrix.json` `f80_classes.json` `f80_kernels.json` `p0c2_sweep.csv` `k80abi.json` `diff/k80.argfix.ll` `diff/k80.argfix.wasm.o`。
不一致は `build.log` と `k80diff` バイナリのみで、実行時プロセスのアドレス (`nat=` `ir=`) の ASLR 差。

段階 [4] の不具合: `p0c_e2e.sh` の `kernel_table.json` 参照が `p0c/work/` を見ていた (実体は `tools/plugins/work/`)。before 側の実行では、`8af7eb0` にこの 1 行修正を当てて比較した (修正は main の `72fb21d9` で反映済み。本 PR は修正を含まない)。#669 で扱う。
ネガティブコントロール・`/home/ubuntu` の grep は §15.2 のとおり。
