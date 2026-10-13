# tools/plugins/p0c REPORT 付録 F (§16)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本ファイルは本体から**無変更で分割移動**した節の全文 (#378, `docs/DOC_MAP.md` §1)。節番号・見出しは移動前のまま。付録 E の行数上限 (250) のため E から分割移動。

## 15.6 #346 受入 2: 現 HEAD での置換前後 e2e 一致 (検証 HEAD 4b3616e5 / before = 置換のみ戻した main)

素材: `fl-win64` `toolchain-retdec` `toolchain-emsdk` (`oc_artifacts`)。before = `4b3616e5` の `tools/plugins/p0c/*.py` を `856be6b` の置換差分で逆適用し、`p0c_e2e.sh` / `p0c2_e2e.sh` の 3 行 (`source env.sh`・`PE=`) を置換前の絶対パス既定値 (856be6b の差分の逆) に戻したもの。after = `4b3616e5` そのまま。before 用に、[WIN64] の解析 dir と、リポジトリ相対の作業 dir (webstudio) を symlink で用意。LLVM 18 の bin を PATH に追加。各 n=1・直列。

| 項目 | before | after |
|---|---|---|
| `p0c_e2e.sh` (kernel_matrix 込み・初回) | rc=0、459 s、load 0.27→8.33 | rc=0、462 s、load 4.85→7.93 |
| `p0c2_e2e.sh 200` | rc=0、14 s、load 6.49→5.27 | rc=0、10 s、load 7.29→6.32 |

一致 (sha256 先頭 12 桁。`work/` 配下の生成物):

| 出力 | before | after | 結果 |
|---|---|---|---|
| `kernel_matrix.json` | 487412af06e6 | 487412af06e6 | 一致 |
| `table_verify.json` | e5709ebd4e62 | e5709ebd4e62 | 一致 |
| `f80_classes.json` | ef4fdcd06cf9 | ef4fdcd06cf9 | 一致 |
| `f80_kernels.json` | 83e753172abc | 83e753172abc | 一致 |
| `k80abi.json` | 418bfc8e0783 | 418bfc8e0783 | 一致 |
| `p0c2_sweep.csv` | 82a16bfc80f8 | 82a16bfc80f8 | 一致 |
| `diff/k80.argfix.wasm.o` | 71a4050555e8 | 71a4050555e8 | 一致 |
| `k80.final.ll` | 953790e6932a | 953790e6932a | 一致 (同一 lift から再生成後) |
| `diff/k80.argfix.ll` | daa2d6b87a52 | daa2d6b87a52 | 一致 (同上) |
| `kernel_table.json` (`tools/plugins/work/`) | (cmp) | (cmp) | 一致 |

**RetDec 非決定の切り分け**: 初回の before 側 `k80.lift.ll` (f826f7ef815a) だけが after (d38a7c667c46) と違った。差は 40 行で、全て `alloca` 行の順序入れ替え (非 alloca 行の差 0)。同じ before コードで lift を 2 回取り直すと 2 回とも同一 (after とも 0 行差) だったため、置換由来ではなく初回生成時の RetDec の揺れ。揃え直した lift から下流 (`k80.final.ll`・`k80.argfix.ll`・`wasm.o`・`p0c2_sweep.csv`) を再生成すると全て一致した。

**結論**: 受入 2 (現 HEAD で置換前後の出力が同一) を満たす。ただし `k80.lift.ll` の alloca 順は RetDec 側で揺れるため、比較は揃えた lift を使う。

**未解決**: RetDec の alloca 順の非決定性。関連の #668 は CLOSED で、この件に対応する open issue は無い。起票先: 未起票 (新規 issue 番号は未発行。PM の起票待ち)。

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
