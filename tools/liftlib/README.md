# liftlib — 共通 lift 修復基盤 (CAB-49 / CAB-54 / CAB-55 / CAB-239 / CAB-256)

RetDec の生出力 (`.ll`) を機械語 (正本) と突き合わせて **silent miscompile を検出・修復**し, SIMD helper を自動生成して wasm 化し,
**実機機械語 (VA 敷設・ms_abi 直接実行) と bit 比較**する, OTT / Fresh Air / Kilohearts 共通のパッケージ。
OTT (`tools/m5〜m10`)・Fresh Air (`targets/freshair/{ref,lift}`)・Kilohearts (`targets/kilohearts/poc_gain`) で別々に再実装されていた
pass と helper を 1 本に統合した (元 dir は無改変)。

```
bash tools/liftlib/liftlib_e2e.sh            # 回帰 (OTT = auto f2,f7,p1 既定 (checks 8/0 = param 0.0/0.1/0.9/1.0 sweep 付き) + 旧既定 --auto none + leaf spec。所要は REPORT_APPENDIX_A.md §12 参照): ユニット + FA 400/400 + KH 366/366 + OTT + SIMD 281 form + 注入 94/94 + OTT leaf native spec
bash tools/liftlib/liftlib_e2e.sh --quick    # 回帰のみ (FA/KH/OTT)
bash tools/liftlib/liftlib_e2e.sh --fresh    # FA/KH を RetDec の lift から再生成 (全体で約 1 分)
bash tools/liftlib/stdbuild_e2e.sh           # 標準ビルド設定 + 署名ガード (PERF-P1 / #155): 合成入力で全変種署名一致 + ネガコン (plugin バイナリ・RetDec 不要。数秒)
bash tools/liftlib/lowbase_e2e.sh            # lowbase 検証 (CAB-220): audit_va + OTT を低位 base で最初から生成 (2 base) + x64c native bit 一致 3 構成 150,708 cell (--full で CAB-90 e2e 全体も)
```

## CLI (`python3 -m liftlib …`, cwd=tools/liftlib)
| コマンド | 内容 |
|---|---|
| `build <cfg> [--profile std] [--variants ref,o2,o3,std] [--expect SIG]` | **標準ビルド入口 (PERF-P1)**: RetDec → 修復 → helper → 標準設定 (`-O3 -flto` + gc-sections + 最小 export; 正本 `data/std_build.json` / `liftlib/stdbuild.py`) で全変種ビルド → 同一シナリオの wasm 出力署名が全一致のときだけ `<name>.cjs` を確定 (不一致 exit 1)。shell は `python3 liftlib/stdbuild.py flags std` / `guard` |
| `lift targets/fa_gain.json` | RetDec → base 正規化 → P1/F7/F2 修復 → helper 自動生成 → emcc → **差分ハーネス** (実機 vs wasm) |
| `python3 tools/liftlib/ott_census.py <ott.cjs> [--f248 0\|1] [--expect-junkhi N] [--max-junkhi N]` | OTT 出力の junk census (junkHi 等) の再計算と期待値突合 (#478。定義は REPORT_APPENDIX_C.md §20) |
| `detect <cfg>` | 修復せず検出だけ (所見 JSON) |
| `diagnose <cfg>` | pass ごとに無効化して再評価 (どの修復が必須か) + 未修復所見 |
| `simd gen x.ll -o out.c [--canon y.ll]` | `__asm_*` 宣言から C helper 生成 (正規名化も) |
| `simd test` / `simd report` | 生成 helper を実機 inline asm と bit 突合 / KH census の被覆 before→after |
| `ott [--auto none\|f7\|p1\|f7,p1] [--lb-base N]` | OTT を liftlib 側だけで再現 (m10_e2e 相当)。**`--auto` 既定 = `f2,f7,p1` (CAB-238・LIFTLIB-3)**: 汎用 F7 (ir9_outcopy 包含) + 語彙拡張 P1 を適用し, checks 7/0 + census 改善 (junkHi ≤104) をゲートにする。出力 SHA は修復由来で m10 参照と分離 (差分理由は REPORT_APPENDIX_A.md §12)。`--auto none` = 旧既定 (修復無し m10 chain 再現, 各段 IR 一致 + SHA 42/42 ゲート)。`--lb-base` で V-shift 先 newbase (=LB_BASE) を指定して低位 base・小 memory で最初から生成 (CAB-220, 例 `0x10000` = initial 24MiB / `0x1230000`。未指定は元 m10 chain と同一の 0x30000000) |
| `leafspec targets/ott_leaf.json` | OTT leaf closure を base→f2→P1→leafabi→emcc で構築し, 実機機械語と乱数 scenario で bit 突合 (CAB-239。xmm0 戻りは IR ret 差替で搬送) |
| `inject-eval` | パターン注入による検出器の検出力・偽陽性評価 |
| `specgen <image> <va>` | 機械語から harness spec の雛形を生成 |

## 構成
```
liftlib/ir.py        IR テキストモデル (insn.addr 保持)       liftlib/pe.py     PE 読取 / .pdata (CHAININFO 併合)
liftlib/mc.py        capstone: CFG / 到達定義 / live-in        liftlib/regbind.py 機械語レジスタ ↔ IR SSA 値の結合 (insn.addr, 定数 def 合成)
liftlib/passes/      base(m2+m5 統合) p1(語彙拡張 mini-lifter) f7 f2 leafabi(xmm0 入出力 ABI) remap(dataimage 外) dataimage p1_legacy
liftlib/lb_layout.py lowbase レイアウト (LB_BASE/ARENA/GLOBAL_BASE; tools/hostbridge/lowbase と共有)   liftlib/runtime_lb.py  C ランタイムの LB_IMG_BASE/LB_MAX_MEM マクロ化
liftlib/simd/        kernels(x86 命令意味 C) gen(宣言駆動生成/正規名) simdtest(実機 asm 突合) liftlib_simd.h
liftlib/harness/     spec(乱数 context) native_runner.c+ms_call.S(実機参照) wasm_runner.mjs diff.py specgen.py
liftlib/recipes/     ott.py + ott/ (OTT 固有 recipe を無改変 vendored)
targets/*.json specs/*.json  data/kh_mnemonics.json  tests/test_unit.py
```

## 設計の要点
- **insn.addr が鍵**: RetDec raw `.ll` の `!insn.addr` を最後まで保持し, 機械語 (capstone) と IR 命令を 1 対 1 に対応づける。
  P1/F7/F2 は「機械語にある命令が IR に無い/配線が違う」を直接検出する (関数名・VA・`__asm_` 接尾番号に依存しない)。
- **P1** `comis*` 後の分岐: (a) br がある=miswired → jcc の cc と taken 先から `fcmp` で条件を再構成 (向きは機械語の taken 先で決定)
  (b) br が無い=folded/dropped → 脱落側断片を mini-lifter で IR 化して分岐を再構成 (reg2mem alloca への merge store を含む)。
  語彙 (CAB-239): rsp 基準 spill slot / 断片内 call (callee 側スタック引数含む) / 整数フラグ分岐 (cmp/test+jcc+setcc+cmov+rcr) /
  GPR load・ALU・movabs・shift・extract・lea・断片内 ret / call 跨ぎ定数 def の bind 合成。範囲外は `UNSUPPORTED <理由>` で IR 不変。
  **LIFTLIB-2 (CAB-256) DAG 化 + phi 合成**: 領域内合流を許す — 合流点では pred 間で値が不一致の reg を「関数入口 alloca +
  各 pred 終端 store + 合流点先頭 load」で合成 (reg2mem phi)。RetDec が 1 ブロックにマージした巨大 block (ラベル = 末尾 VA) では
  脱落側入口が head 自身と衝突して自己辺 (= 無限ループ, CAB-238 §6) になるため, tail を割って合流点を独立 block にし,
  その値を脱落側でもマージする。非支配の bind 値は候補から外し, alloca load の再発行 / cmov select 合成 /
  CRT 数学関数の i64 戻り (= xmm0 ビット) の合成にフォールバックする。
- **leafabi** leaf 関数の xmm0 入出力: 入口は f2 の `%xmmK_bits` 引数, 戻りは各 `ret` の xmm0 到達定義を
  `ret i64 (trunc i128 …)` に差替 (double bits)。RX: ret_xmm0 callee の call 直後の最初の xmm0 読みを call 戻りへ差替。
- **F7** `mov r64,[b+d]` の load 脱落: dest がアドレス基準に使われるのに `load i64` が無い → base を bind して load 挿入 + 使用側置換。
- **F2** xmm 引数落ち: callee の入口 live-in xmm0..3 を到達定義から算出 (f32/f64/v128 は読取 mnemonic で判定) → define 引数追加 + undef 置換 + 全 call site で bind。
- **SIMD helper**: `(base mnemonic, 戻り型, 引数型)` だけで C を生成 (RetDec の引数規約=capstone の read operand 順)。IR は `__asm_<base>__<ret><args>` に正規名化。
- **差分ハーネス**: spec(JSON) の乱数 context を native(VA 敷設) と wasm の両方に与え, 全バッファ (+ guard 64B, ポインタ欄は buf+off トークン) を bit 比較。ステップ列 (状態持越し) 対応。

## 旧 dir (tools/m2〜m10) pass → liftlib 対応表 (LIFTLIB-1 / #224 検収条件 3)
旧 dir は**参照専用** (既存 e2e 成果物・REPORT は残置、新規 lift/修復は liftlib 経由)。昇格元ごとの置換先と一致検証:

| 昇格元 | pass | liftlib の置換先 | 一致の担保 |
|---|---|---|---|
| m2 `ir_normalize.py` | A0 (opaque ptr / datalayout) | `passes/base.py` `m2_normalize` | unit T1 (base == m2+m5, IR テキスト完全一致) |
| m3 `ir_patch.py` / m5 `ir5_patch.py` | A1–A8, A9L/A9L2, B1, S1a/S1b, C1/C9/C11–C13 | `passes/base.py` (`normalize`/`lift_residual_constexpr`/`lower_asm_store`/`closure_select`/`redirect_calls`, `run_base`) | unit T1 + `ott` O1 (ott_lift.ll と一致) |
| m6 `ir6_pass.py` | [P1] (SSA 名パターン) | `passes/p1_legacy.py` (参照実装, IR 完全一致) / `passes/p1.py` (insn.addr 駆動の正本) | unit T2 (ir7e_p1.ll と一致) / `ott` O2a |
| m6 `ir6_shift.py` | VA remap | `passes/remap.py` `shift_va` | unit T2 (ir7e_p2.ll) / O2b |
| m6 `ir6_gdata.py` + `m6_data_gen.py` | データ実体化 | `passes/remap.py` `gdata`/`gdata_legacy` + `passes/dataimage.py` | unit T2 (ir7e_p3.ll) / O2c |
| m6 `gen_msimd6.py` + `m6_simd_check.py` | SIMD helper 生成 | `simd/gen.py` + `simd/kernels.py` | `simd test` (192 mnemonic / 281 form / 95,400 vector) |
| m9 `ir9_outcopy.py` / targets ir_kh_f7 / FA F7' | F7 (load 脱落) | `passes/f7.py` | `inject-eval` / FA 400/400 / KH 366/366 |
| m7 `ir7_argpass` / m8 `ir7_argpass_fixed`・`ir8_valueflow` の引数接続 | F2 (xmm 引数落ち) | `passes/f2.py` (本体再生は固有) | FA 400/400 / `ott` 7 段 |
| m6 `m6_memfix.py`・`m6_full_extract.py` / m8 `ir7_argpass_fixed.py`・`ir8_valueflow.py` / m9 `ir9_bootstraps.py`・`ir9_outcopy.py` / m9 `m9_tablebind` / m10 `m10_boot` | OTT 固有 (固定名・dsm・VA) | `recipes/ott` (vendored 無改変, `runtime_lb.py` が C ランタイムをマクロ化) | `ott --auto none` の 7 段 IR 一致 + 出力 SHA 42/42 |

範囲外 (別起票): vendored 固有部 (#12–16, 18) の insn.addr 駆動汎用化。

## 新ターゲットの追加
1. `targets/<name>.json` (`image`, `retdec.ranges`, `funcs`, `exports`, `spec`, `func_va`, `wasm_func`) を書く
2. `python3 -m liftlib specgen <image> <va>` で spec 雛形 → ループ回数など整数フィールドの範囲を手で絞る
3. `python3 -m liftlib lift targets/<name>.json` → 不一致なら `diagnose` で必須 pass / 未修復所見を確認
制約: 比較対象関数は自己完結 (IAT 呼出なし) が必要。NaN 入力は除外 (x86 と wasm の NaN payload 差の切り分け)。詳細は REPORT.md。
