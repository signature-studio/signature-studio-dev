# liftlib #1270 (HB-H29, 部分達成→受入 1〜2・4 達成) — ott_getparam の入口 this/idx 受渡しと switch 表の敷設で leafspec match 1.0 (付録)

親: #883 (HB-H21)。前提: #1269 (closed・残件は #1583 / #1586 へ分割済み)。
既知類型との関係: [DEFECTS.md](../../docs/DEFECTS.md) の D1a〜D23 のどれにも直接は当たらない (silent miscompile の類型名は未確認)。

## 0. 結論

| 受入 (#1270 本文) | 結果 (実測) |
|---|---|
| 1. 入力の受渡し方式を決め、根拠を書く | **達成**。方式 (a): 入口の BLK+0x08/+0x10 読みを仮引数 `%arg1` / `%arg2` へ張り替える。根拠は §2 |
| 2. `leafspec targets/ott_getparam.json --n 200` が rc=0・match 1.0・idx 0..19 × 200・wasm_trap 0 | **達成** (測定 commit `e13cd45c`: rc=0, match 200 / mismatch 0 / native_crash 0 / wasm_trap 0, §4.1) |
| 3. ネガコン (修正を外すと match が戻る) と jtchain / leafabi の切り分け | **部分**。修正を 1 つずつ外した実測は §4.2 (match 200 → 147 / 11)。jtchain 外しは emcc が落ちるため切り分け不能、leafabi 外しは 15 (§4.3)。`baseline=0` (本文の想定) は実測では 147 (this=0 でも一致する scenario が残る) |
| 4. `liftlib_e2e.sh` の regress に `ott_getparam` を登録 | **達成** (`liftlib_e2e.sh` の (g) 節。PASS の状態で登録) |
| 5. #883 の受入 4 件を満たせる状態にする | 本付録の範囲では #883 の残件 (`tools/liftlib` の他 target・#883 本文の受入) は未確認。#1270 は `Refs` で残す |

## 1. 測定 config

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `e13cd45c` (`fix(liftlib): ott_getparam の switch 表 (image 内 .text) を線形メモリへ敷設し leafspec match 1.0 (refs #1270)`) |
| 前段 commit | `896115a7` (入口 this/idx の張り替え)。両 commit は `tools/liftlib/liftlib/{passes/icall.py,pipeline.py}`・`targets/ott_getparam.json`・`liftlib_e2e.sh` のみ |
| 素材 | `$ARTIFACTS_DIR`: `work-liftlib` (→ `tools/liftlib/work/`)・`work-icall` (→ `tools/icall/work/`、`ott_F.txt`)・`work-m6-ott` (→ `tools/m6/work/` ほか)・`analysis-ott-binaries` (→ `[ANALYSIS-PLUGINS]` の `ott/binaries/OTT_vst2_win64.dll`)・`toolchain-emsdk` (→ `[EMSDK]`)・`toolchain-retdec` (→ `[RETDEC]`)。`fl-win64` は本測定に不要 |
| 再現 | `cd tools/liftlib && OTT_DLL=<[ANALYSIS-PLUGINS]>/ott/binaries/OTT_vst2_win64.dll python3 -m liftlib leafspec targets/ott_getparam.json --n 200` |
| 測定値 | wall 61.98 s (`real 1m1.976s`)・開始時 load 0.74 / 0.83 / 0.57 (runner 4 コア, 単発) |

確認コマンド (測定 commit から HEAD までのコード差分。0 なら測定値は現 HEAD で有効):

```
git diff e13cd45c HEAD -- tools/liftlib/liftlib tools/liftlib/targets | wc -l
```

## 2. 方式 (受入 1): 入口 this/idx は `%arg` から読む

- 機械語 (`OTT_vst2_win64.dll` の `0x18011e5a0`): `sub rsp,0x28; cmp edx,0x1e; ja …; lea r9,[rip-…]; movsxd rax,edx; mov r8d,[r9+rax*4+0x11e6f0]; add r8,r9; jmp r8`。this は rcx (`movss xmm0,[rcx+0x2dc]` 等)、idx は rdx。
- harness (`liftlib/harness/spec.py`): spec `args = [ptr this, int idx]` → 出力 `A 0 ptr this` / `A 1 i <idx>` (slot 0 = this, slot 1 = idx)。
- `native_runner.c` (`M pos` = abi `ms_pos`): slot k → `gpr[k]` (k=0 → rcx, k=1 → rdx)。機械語と一致。
- `wasm_runner.mjs` / `wasm_sig`: slot 0 → `i32 %arg1` (this)、slot 1 → `i64 %arg2` (idx) を wasm 関数の引数として渡す。
- RetDec 由来の IR の入口は `load BLK+0x08` (this) / `load BLK+0x10` (idx) で、引数 `%arg1` / `%arg2` を読まない。`icall_rewrite.py` が rcx/rdx を BLK に退避する約束 (BLK_RCX=0x08, BLK_RDX=0x10) の入口版。
- 選ばなかった方式 (b) (harness が `__icall_blk` へ this/idx を書く): leaf は呼出し元を持たない root のため BLK を埋める主体が無い。wasm 側の `__icall_blk` の番地を harness へ出す export も要る。(a) は native の ABI そのものに合わせるだけなので、こちらを採る。
- 実装: `passes/icall.py` の `entry_blk_args(fn)` (入口ブロックで BLK への store・非 asm の call より前にある `load i64` の BLK+0x08/+0x10 を `zext`/`add` で `%argN` に置換。置換数を log)。`pipeline._repair_ll` が `iargs` の後・`f2` の前に `passes.icall.entry_args: true` のときだけ呼ぶ。`ott_getparam` だけ有効 (`targets/ott_getparam.json`)。置換数は `function_18011e5a0: 2`。

## 3. switch 表の敷設 (受入 2 の残り)

- 入口の `switch` は `movsxd rax,edx` → `[r9+rax*4+0x11e6f0]` の相対オフセット表を読む。表は `.text` の中 (RVA `0x11e6f0`, VA `0x18011e6f0`, 31 entries = 0x7c byte)。
- IR はこれを絶対アドレス `inttoptr (0x3011e6f0 + idx*4)` で読むが、gdata の global (`@global_var_*` 528 件) はこの番地を含まない。`.text` は敷設されていないため、wasm 上の表は 0 → `switch` が default に落ち、`this+0x2dc` を返していた。
- 対応: `cfg.image_bytes = ["0x18011e6f0-0x18011e76c"]` を指定すると、`pipeline.image_bytes_c` が PE の該当バイト列を `passes.shift.newbase` へ写して起動時 (`__attribute__((constructor))`) に `memcpy` する C (`<name>_imgbytes.c`) を書き、emcc の source に加える。`.rdata`/`.data` 全体ではなく範囲を指定するのは、`.text` 全体 (約 2 MB) を C 配列にすると生成物が重すぎるため。
- 範囲は機械語の `cmp edx,0x1e; ja` (idx 0..30) から決めた。他の target には影響しない (`image_bytes` が無いと `image_bytes_c` は None を返し、従来どおり)。

## 4. 実測

### 4.1 HEAD `e13cd45c` (受入 2)

| 設定 | rc | wall | match / mismatch / native_crash / wasm_trap | gate |
|---|---|---|---|---|
| `e13cd45c` (entry_args + image_bytes) | 0 | 61.98 s | **200 / 0 / 0 / 0** | PASS (rate 1.000) |

### 4.2 ネガティブコントロール (修正を 1 つずつ外す)

| 設定 | rc | match / mismatch / native_crash / wasm_trap | gate | 解釈 |
|---|---|---|---|---|
| entry_args **off** (image_bytes on) | 1 | 147 / 53 / 0 / 0 | FAIL (0.735) | 表は敷設されるが this=0 のまま。53 件は this に依る戻り値 (xmm0 不一致) |
| image_bytes **off** (entry_args on) | 1 | 11 / 189 / 0 / 0 | FAIL (0.055) | this は正しいが表が 0 → default 分岐。表の敷設が無いと一致は 11 件のみ |
| 両方 off (`bb9530a4` 相当の挙動) | 1 | 147 / 53 / 0 / 0 | FAIL (0.735) | #2128・#2181 の測定値と同じ (本付録の再測定と一致) |

- 本文の想定「修正を外すと match 0」は実測と一致しない (両方 off でも 147。this=0 でも native が 0 を返す scenario は一致する)。上の表の値を正とする。

### 4.3 jtchain / leafabi の切り分け (受入 3 の残り)

| 外したもの | 結果 | 解釈 |
|---|---|---|
| `passes.icall.jtchain = false` | emcc が失敗 (`wasm-ld: symbol exported via --export not found: function_18011e5a0`) | 入口関数が lift されない。jtchain は leaf の成立条件。match の寄与は測れない |
| `passes.leafabi` (`ret_xmm0`) | rc=1, match 15 / mismatch 185 / wasm_trap 0 | 戻り値 (xmm0) の読み出しに必須。寄与は大 |

## 5. 検証範囲 / 範囲外

- `python3 tests/test_unit.py` (`tools/liftlib`): 27/28 ok。**T6 は FAIL**: `targets/freshair/work/win/...SlateCore.core_64` が無い (`work-liftlib-targets` が本 run の `oc_artifacts` に無い)。本変更とは無関係の既存の素材不足 (#2128 付録の T6 と同じ)。T24 (blk_global) を含む他は ok。
- `liftlib_e2e.sh` 全体は未実行 (素材 `work-liftlib-targets` 不足のため。(g) 節の leafspec 行は HEAD の単発測定で代替)。
- `ott_route` / `ott_iargs` の出力は未測定 (新フラグは `ott_getparam` の JSON にしか立てていない。コード上は `entry_args` / `image_bytes` が無い cfg で従来の分岐に入る)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| jtchain の寄与の切り分け (jtchain 外しは入口関数が消えて build 不能。代替の切り分け方法は未検討) | 受入 3 の一部が未達 | #1270 (Refs のまま) |
| `#883` 本文の残件 (他 target・受入 4 件の充足確認) | #883 は本付録の範囲外 | #883 |
| `work-liftlib-targets` 素材での T6 (freshair/kilohearts) 回帰 | 既存 recipe の回帰は T1〜T5・T7〜T27 のみ | 次 run で `oc_artifacts` に `work-liftlib-targets` を指定 |
