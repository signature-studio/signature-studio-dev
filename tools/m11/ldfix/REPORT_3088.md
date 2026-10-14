# #3088 (LD-146): unexec 4 関数 (5c1030 / 737d10 / 7ff6e0 / d243c0) の native 実行条件を整えて wasm と突合

**判定: 達成**。4 関数とも native が走り、wasm と突合できた。4/4 で判定 `mismatch`、主タグ `icall_drop` (D15 類型: メモリ間接 call の欠落)。3 反復で判定一致。
親 #1594 の REPORT_1064 §3.2 (全パターン segv で突合不能) を解消した。

## 1. 測定条件

- 測定 commit: `7c197cd3` (本 PR のコード変更の最後の commit)。`git diff 7c197cd3 HEAD -- tools/liftdiff tools/m11/ldfix/unexec4_3088.sh` = 0 行 (以降は本 REPORT の追加のみ)。
- target: `tools/liftdiff/targets/m11.json` (IR = `tools/m11/work/boot_final3.ll`)。boot 状態 = `work/m11/boot_state.json`。wasm は HEAD の `rt/` から再 build (`wasm_size` 4457524・`sig_mismatch` 0)。
- 素材: fl-win64 (`extracted/block00031_PE.bin` のみ展開し、`FL_WIN64_DIR` は [WIN64] の展開先)・work-m11・work-liftdiff・toolchain-emsdk ([EMSDK])。
- 所要: 反復 3 回を含む `unexec4_3088.sh` 1 回 = 97.9 s (real)。load average 0.27 (終了時点)。

## 2. 受入条件

| 受入条件 | 結果 |
|---|---|
| unexec 4 関数 (5c1030 / 737d10 / 7ff6e0 / d243c0) の native 実行条件を整えて突合する | **達成** (§3.3。4/4 で native ok・wasm ok・判定 mismatch) |

## 3. 実測

### 3.1 unexec の原因 (3 点)

1. **古い native 実行器**: `work-liftdiff` の `work/ld_native` は `rt/ld_core.h` の VMT 仮 proc 域 (LD-48 / #1398) より前のビルドだった (`strings | grep -c vmslot` = 0。現行ビルドは 10)。`liftdiff.py run/batch` は native を再 build せず、再 build するのは `liftdiff_e2e.sh` [1/4] だけ。その結果、VMT の仮 proc (`0x50012060` 等) の thunk が敷かれず、fvm の case が全て segv した。
2. **fvm 候補の範囲**: `fvm_candidates` は fault addr の offset が `FVM_OFF` (0x40) 未満の引数だけを候補にする。d243c0 (`[this+0x23c]`)・737d10 (`[this+0x460]`)・7ff6e0 (`[this+0x524]`) は候補 0 件で、fvm 自体が走らない。
3. **VMT slot の位置**: 5c1030 / d243c0 は `call [VMT+0x18]` (slot 3・vmt blob の 8 slot 内)。737d10 / 7ff6e0 は `call [VMT+0x178]` (slot 47・8 slot の外)。

### 3.2 手順

- **A (harness 修正)**: `ldlib/build_wasm.ensure_native()` を追加。`work/ld_native` が `rt/ld_native.c`・`rt/ld_ms_call.S`・`rt/ld_core.h` より古ければ gcc で作り直す (`Session` の build 時に呼ぶ)。検証: `work/ld_native` の mtime を 2000-01-01 に戻して 1 関数を実行すると再 build が走り、判定は同じ (mismatch)。
- **B (this 疑似オブジェクトの与え方)**: 全 4 関数で this = 引数 0 = `arena+0x1000` (`i:a:0x1000`)、blob = `vmt` (既存)、引数 1 = `i:0x5`。
  - slot 3 の 2 関数 (5c1030 / d243c0) は vmt blob のまま。
  - slot 47 の 2 関数 (737d10 / 7ff6e0) は vptr を `arena+0x1e88` (= 0x2000 − 0x178) に差し替える (`--patch a:0x1000:q=a:0x1e88`)。これで `[V+0x178]` が VMT の slot 0 (仮 proc 256) を指す。
  - 実行: `liftdiff.py run targets/m11.json --fn <va> --state work/m11/boot_state.json --args ... --blob vmt [--patch ...]`。全手順は `tools/m11/ldfix/unexec4_3088.sh`。

### 3.3 突合結果 (HEAD `7c197cd3`・3 反復で同一)

| 関数 | 修正前 (古い実行器・`--nobuild`) | 既存 fvm 経路のみ (A 修正後) | 本件の手順 B (HEAD) | 判定 | 主タグ |
|---|---|---|---|---|---|
| 5c1030 | unexec (全 pattern native segv) | mismatch (fvm arg0 のみ native ok) | mismatch (native ok / wasm ok) | mismatch | icall_drop [high]・import_call_seq [medium] |
| 737d10 | unexec | unexec | mismatch (native ok / wasm ok) | mismatch | 同上 |
| 7ff6e0 | unexec | unexec | mismatch (native ok / wasm ok) | mismatch | 同上 |
| d243c0 | unexec | unexec | mismatch (native ok / wasm ok) | mismatch | 同上 |

- native の trace: 5c1030 / d243c0 は `?vmslot3`、737d10 / 7ff6e0 は `?vmslot0` (差し替えた vptr の先) を 1 回 call (`native_extra_call`)。wasm は call 0 件。
- 戻り値: native `rax` = 0x0 / wasm `rax` = 0x22073000 (5c1030・d243c0) または 0x22072e88 (737d10・7ff6e0)。call の欠落に伴う差。

### 3.4 IR での確認 (D15 類型)

`tools/liftdiff/work/m11/ir_instr.ll` で 4 関数とも、vptr (`arg1` の指す先の `load i64`・例 `%ldfxc269`) は読まれるが、その値を使う間接 call が無い。機械語の `call qword ptr [rbx+0x18]` (737d10 / 7ff6e0 は `+0x178`) に対応する IR が空。`docs/DEFECTS.md` D15 (メモリ間接 call の脱落) の m11 側の実例として確定した。修復 (`[icall]` pass) は本件の範囲外。

## 4. 未解決・限界

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 古い実行器で測った closure の unexec 件数 (REPORT_1064 §3.1 / flelift 系) の再測定。A 修正で fvm 経路が動くようになった | 全数の unexec・mismatch 件数が変わり得る。本 PR では closure は再測定していない | #1594 (survey 再測定と合わせる) |
| 手順 B (vptr の差し替え) は 4 関数の手動 case。slot 位置ごとの自動判定はない | 他の unexec 関数へ同じ手順を広げるには、関数ごとに slot 位置の判定が要る | 必要になった時点で子 issue (本 issue では起票しない) |
| 4 関数の mismatch (D15: 間接 call の欠落) の修復 | wasm 側の判定は mismatch のまま | DEFECTS.md D15 の既存の扱い (新規起票なし) |

## 5. 再現

```sh
export FL_WIN64_DIR=<fl-win64 の展開先>   # extracted/block00031_PE.bin
bash tools/m11/ldfix/unexec4_3088.sh <OUT>  # 4 関数 × 3 反復。OUT/<va>.r<n>.json
```

REPORT_1064 §3.2 の「unexec 4 件 (native 全パターン segv)」は、本 REPORT の §3.3 の値で置き換わる (REPORT_1064 側には参照のみ追記)。
