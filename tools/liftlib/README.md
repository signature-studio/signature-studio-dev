# liftlib — 共通 lift 修復基盤 (CAB-49 / CAB-54 / CAB-55)

RetDec の生出力 (`.ll`) を機械語 (正本) と突き合わせて **silent miscompile を検出・修復**し, SIMD helper を自動生成して wasm 化し,
**実機機械語 (VA 敷設・ms_abi 直接実行) と bit 比較**する, OTT / Fresh Air / Kilohearts 共通のパッケージ。
OTT (`tools/m5〜m10`)・Fresh Air (`targets/freshair/{ref,lift}`)・Kilohearts (`targets/kilohearts/poc_gain`) で別々に再実装されていた
pass と helper を 1 本に統合した (元 dir は無改変)。

```
bash tools/liftlib/liftlib_e2e.sh            # 回帰 (約 25 秒; RetDec キャッシュ利用): ユニット + FA 400/400 + KH 366/366 + OTT 7/0 + SIMD 281 form + 注入 94/94
bash tools/liftlib/liftlib_e2e.sh --quick    # 回帰のみ (FA/KH/OTT)
bash tools/liftlib/liftlib_e2e.sh --fresh    # FA/KH を RetDec の lift から再生成 (全体で約 1 分)
bash tools/liftlib/lowbase_e2e.sh            # lowbase 検証 (CAB-220): audit_va + OTT を低位 base で最初から生成 (2 base) + x64c native bit 一致 3 構成 150,708 cell (--full で CAB-90 e2e 全体も)
```

## CLI (`python3 -m liftlib …`, cwd=tools/liftlib)
| コマンド | 内容 |
|---|---|
| `lift targets/fa_gain.json` | RetDec → base 正規化 → P1/F7/F2 修復 → helper 自動生成 → emcc → **差分ハーネス** (実機 vs wasm) |
| `detect <cfg>` | 修復せず検出だけ (所見 JSON) |
| `diagnose <cfg>` | pass ごとに無効化して再評価 (どの修復が必須か) + 未修復所見 |
| `simd gen x.ll -o out.c [--canon y.ll]` | `__asm_*` 宣言から C helper 生成 (正規名化も) |
| `simd test` / `simd report` | 生成 helper を実機 inline asm と bit 突合 / KH census の被覆 before→after |
| `ott [--auto f7,p1] [--lb-base N]` | OTT を liftlib 側だけで再現 (各段 IR 一致 + m10_e2e 相当)。`--lb-base` で V-shift 先 newbase (=LB_BASE) を指定して低位 base・小 memory で最初から生成 (CAB-220, 例 `0x10000` = initial 24MiB / `0x1230000`。未指定は元 m10 chain と同一の 0x30000000) |
| `inject-eval` | パターン注入による検出器の検出力・偽陽性評価 |
| `specgen <image> <va>` | 機械語から harness spec の雛形を生成 |

## 構成
```
liftlib/ir.py        IR テキストモデル (insn.addr 保持)       liftlib/pe.py     PE 読取 / .pdata (CHAININFO 併合)
liftlib/mc.py        capstone: CFG / 到達定義 / live-in        liftlib/regbind.py 機械語レジスタ ↔ IR SSA 値の結合 (insn.addr)
liftlib/passes/      base(m2+m5 統合) p1 f7 f2 remap dataimage p1_legacy
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
- **F7** `mov r64,[b+d]` の load 脱落: dest がアドレス基準に使われるのに `load i64` が無い → base を bind して load 挿入 + 使用側置換。
- **F2** xmm 引数落ち: callee の入口 live-in xmm0..3 を到達定義から算出 (f32/f64/v128 は読取 mnemonic で判定) → define 引数追加 + undef 置換 + 全 call site で bind。
- **SIMD helper**: `(base mnemonic, 戻り型, 引数型)` だけで C を生成 (RetDec の引数規約=capstone の read operand 順)。IR は `__asm_<base>__<ret><args>` に正規名化。
- **差分ハーネス**: spec(JSON) の乱数 context を native(VA 敷設) と wasm の両方に与え, 全バッファ (+ guard 64B, ポインタ欄は buf+off トークン) を bit 比較。ステップ列 (状態持越し) 対応。

## 新ターゲットの追加
1. `targets/<name>.json` (`image`, `retdec.ranges`, `funcs`, `exports`, `spec`, `func_va`, `wasm_func`) を書く
2. `python3 -m liftlib specgen <image> <va>` で spec 雛形 → ループ回数など整数フィールドの範囲を手で絞る
3. `python3 -m liftlib lift targets/<name>.json` → 不一致なら `diagnose` で必須 pass / 未修復所見を確認
制約: 比較対象関数は自己完結 (IAT 呼出なし) が必要。NaN 入力は除外 (x86 と wasm の NaN payload 差の切り分け)。詳細は REPORT.md。
