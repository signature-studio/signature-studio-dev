# tools/plugins/p0c REPORT 付録 F (§16)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本ファイルは本体から**無変更で分割移動**した節の全文 (#378, `docs/DOC_MAP.md` §1)。節番号・見出しは移動前のまま。付録 E の行数上限 (250) のため E から分割移動。

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
