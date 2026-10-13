# tools/plugins/p0c REPORT 付録 E (§14〜§16)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本ファイルは本体から**無変更で分割移動**した節の全文 (#378, `docs/DOC_MAP.md` §1)。節番号・見出しは移動前のまま。

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
| 0x5de3e0 の `[rdx]` store 欠落 (lift) | buf_diff 2000 | #331 |
| 0x5dee90 / 0x5df040 / 0x5e02b0 の残差 | buf_diff 約 2.57M | #331 |
| 0x5e12b0 の ucomiss 落ち (lift) | abi-mismatch のまま | #331 |

#331 の対象 kernel は 0x5de3e0 / 0x5dee90 / 0x5df040 / 0x5e02b0 / 0x5e12b0 の 5 つ (0x5e0d80 は含まない)。
| ext 精度が必要な kernel の wasm32 検証・framework 統合 | #269 §12.4 と同じ | #197 (既存提案) |

### 14.5 再現

```sh
export TMPDIR=$PWD/tools/plugins/p0c/work/tmp
python3 tools/plugins/p0c/f80_assess.py                       # work/f80_classes.json
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000                # sig11=0 / B6 ok を判定に含む
for v in WRITTEN_BASE ARGORD IDX_NOT_BASE CLIPRANGE PARTIAL_LOAD MEMW REGSRC STACKW INTERSECT; do
  env K80_NO_$v=1 python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000  # 負論対照 (rc は下記)
done
```
負論対照の rc (merge 後 HEAD 実測): **MEMW と REGSRC は rc=0** (受入判定を通る。MEMW は §14.2 のとおり buf_diff が
増えるが判定対象外、REGSRC は差なし)。**それ以外の 7 種は rc=1** (WRITTEN_BASE `run=67 ok=63 sig11=4` / ARGORD
`ok=65 sig11=2` / IDX_NOT_BASE `ok=66 sig11=1` / CLIPRANGE `ok=66 sig11=1` / PARTIAL_LOAD `run=65` / STACKW `run=66` /
INTERSECT `run=66`)。MEMW の差は CSV の buf_diff でのみ検出できる。
前提: `k80.lift.ll` は `bash tools/plugins/lift/lift_ranges.sh <PE> work/k80_ranges.txt tools/plugins/p0c/work k80 2400`
で再生成。`llvm-as` / `clang` は PATH に必要 (runner では `/usr/lib/llvm-18/bin`)。
`/opt/retdec` と `/home/ubuntu/work/{analysis,webstudio}` は runner 上の symlink で代替 (§12.4)。

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

## 16. P0c-8 (#311, 親 #197・先行 #269): ext IR の wasm32 検証 + framework 統合 (fw_f80.py → f80_lower --ext)

検証起点 commit: `d5e6f98` (origin/main)。担当 dir: `tools/plugins/p0c` / `tools/plugins/framework` (fw_f80.py, fw_stage2.sh のみ)。
既知類型との関係: DEFECTS.md の D1〜D16 に **該当なし** (ext 生成器の丸め論理バグ。native では乱数 case で顕在化せず、固定 edge/tie 集合でのみ出る)。

### 16.0 結論

1. **ext IR を wasm32 (emcc -O2) でビルドし native x87 と bit 比較: 24,001,062 case で 0 不一致** (§16.2)。ネガコン (Dekker 定数破壊) は 2,704,752 不一致で FAIL。
2. wasm32 比較で **f80_lower.py --ext の生成器バグを 4 件発見・修正** (§16.1)。native の ext_core_test (3M) と p0c4_e2e (7 kernel) はどれも検出できなかった。
3. **framework 統合**: `fw_f80.py --ext-funcs` が f64 coerce 後に `f80_lower.py --ext` を呼ぶ。`fw_stage2.sh` は `FW_EXT_FUNCS` 指定時のみ有効 (未指定なら従来と byte 一致)。指定関数が ext 化されなければ exit 1。
4. **受入条件 3 (fw_269_verify.sh / hs_e2e.sh 維持) は未検証**。理由は §16.4。したがって PR は `Refs #311` とし Closes にしない。

### 16.1 修正した生成器バグ (すべて f80_lower.py の --ext。ext_core_test.c の同一箇所も同期)

| # | 場所 | 症状 (固定集合 case) | 原因 | 修正 |
|---|---|---|---|---|
| E1 | `_ext_round64` grid shift | hi=-2^k, lo<0 の mul/add の lo が 2^-63 刻みで 1 ずれ | shift 64 の条件が lo<0 のみ。hi<0 では大きさが増える向きなのに shift 64 にしていた | `(hi>0 ? lo<0 : lo>0)` (大きさが減る向き) のときだけ shift 64 |
| E2 | `_ext_fist_round` (nearest) | hi=n+0.5, lo>0 / hi=n-0.5, lo<0 の fist が 1 ずれ | `d=(hi-n0)+lo` を f64 で丸めて 0.5 と比較し lo の符号を失う | `d0=hi-n0==±0.5` と lo の符号で tie 判定 |
| E3 | 同 em 選択 | tie の -0.5 側で even 判定が逆 | `em` の select の真偽の枝が逆 (odd→n0, even→n0-1) | odd→n0-1, even→n0 |
| E4 | `_ext_store_f32` | f32 store の tie (hi=1+2^-24, lo≠0) が 1ulp ずれ | `nearadj` (nd 条件抜き) を使用。さらに mid 判定 `lo_` が bit 0..51 全体を見ていた (正: 下位 29 bit) | `nearadj2` を使用、mask を 0x1FFFFFFF |

### 16.2 wasm32 検証 (1 コマンド: `bash tools/plugins/p0c/p0c8_e2e.sh`)

方法: `ext_wasm_gen.py` が `f80_lower.py` の実生成関数 (`_ext_arith` / `_ext_fist_round` / `_ext_store_f32`、chop=0/1) から .ll を作り、`ext_wasm_test.c` が決定的入力 (ext_core_test.c と同じ xorshift・mode 0..3 各 N 件×chop 2 + 固定 edge/tie 集合) で実行して mul/add/sub の (hi,lo) (TwoSum 正準化)・fist(i32)・f32 store 2 個を native x87 (`long double`、`-O0`) の期待値と bit 比較する。期待値は native 側 (`-DGEN`) が書き、wasm32 側 (emcc → node) が読む。

| 項目 | 実測 |
|---|---|
| case 数 (分母) | 24,001,062 (乱数 mode 0..3 × chop 2 × N=3,000,000 + 固定集合。固定集合は 506 組を既知限界で除外) |
| wasm32 (emcc -O2) 不一致 | **0** (dd 0 / fist 0 / f32 0) |
| wasm32 バイナリ | 26,009 B (試験 harness 込み) |
| native clang -O2 で同 IR を実行 | 不一致 0 (同一ファイル・同一入力) |
| ネガコン: Dekker 定数 2^27+1→2^26+1 | 2,704,752 不一致 → exit 1 (p0c8_e2e.sh が exit 非 0 を要求) |
| ext_core_test (native C, N=3,000,000) | 全 PASS (修正後) |
| p0c4_e2e 2000 case/kernel (修正後) | 0x5dfbe0 / 0x5dfc90 / 0x5dfd30 / 0x5dfdb0 / 0x5de820 / 0x5dedf0 / 0x5dfb60 すべて buf_diff=0。回帰 7 kernel も 0 (修正前と同一) |
| 実 kernel の ext IR | `llvm-as` OK・idempotent OK・wasm32 clang -O1 で 113,950 B (k80.ext.ll、80 define) |
| p0c8_e2e.sh 所要 | 33 s (load average 1 分値 0.72→1.02、直列、n=1) |

最初の実行 (修正前) は 948,340 / 2,401,568 case 不一致 (N=300,000)。内訳は試験 harness 側の native 参照の誤り (x87 を `-O2` で `(float)` 変換すると丸めモード切替が最適化で動く) と上記 E1〜E4。harness は参照側を `-O0` + volatile にして解消した。

数え方: case = (入力 a,b, chop) 1 組。不一致 = 1 case で dd / fist / f32 のいずれか 1 つでも bit 不一致。fist は |a|,|b|<1e9 の組のみ比較 (ext_core_test.c と同条件)。

### 16.3 framework 統合の検証

| 検査 | 結果 |
|---|---|
| `fw_f80.py` 既定 (--ext-funcs なし) の出力 | 変更前 (`d5e6f98`) と `cmp` で byte 一致 (入力 = k80.lift.ll、968 f80 token) |
| `--ext-funcs function_5dfd30,function_5dfbe0` | ext 2 関数・llvm-as OK・wasm32 clang -O1 で 106,942 B |
| ネガコン: `--ext-funcs function_nonexistent` | exit 1 (`ext 化されなかった関数: missing=[...]`) |

### 16.4 範囲外 / 未解決

範囲外: framework 全体 (fw_269_verify.sh / hs_e2e.sh) の再実行。stage-1 成果物 (fw_icall.dll・fw[0-7].restored.ll 等) は許可素材名 (WORKFLOW §11) に無く、RetDec で再生成すると 8 chunk の timeout 3600 s で 60 分上限に収まらない。したがって受入条件 3 は**未検証**。`fw_f80.py` 既定動作の byte 一致 (§16.3) までが根拠で、fw_stage2.sh の既定経路の差分は `EXT_ARGS=()` の空展開のみ (`bash -n` OK)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入条件 3 (fw_269_verify.sh / hs_e2e.sh 維持) 未検証 | framework 統合の回帰確認 | 新規 issue: stage-1 成果物を素材化 (`work-fw-stage1`) して再検証 |
| dd 積は al·bl を捨て、al·bh / ah·bl を f64 に丸める | lo 付き × 24bit 超 hi の積で不一致の可能性 (固定 506 組を除外。kernel 内の ext 値で顕在化した例は p0c4 2000 case で 0) | #197 に提案 |
| `FW_EXT_FUNCS` に入れる関数の選定 (framework 内の x87 関数一覧) | 統合は配線のみ。どの関数を ext 化するかは未決 | #197 に提案 |
