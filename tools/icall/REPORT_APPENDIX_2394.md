# 付録: icall #2394 (ICALL-75) — 値 `0x400000004` の 2 本の i32 store と元の機械語の突合

> 親: #2311 (ICALL-73)。`REPORT_APPENDIX_1998.md` §6 の未確定 (a)(b) を閉じる。測定対象は Fresh Air SlateCore の `function_181057b38`。
> **既知類型との関係**: `docs/DEFECTS.md` の D22 (escape 済み stack_var の内部 read が別 alloca になる) に近い (frame の slot を独立した alloca に分ける RetDec の前提が同根)。D17 (store 幅不足) とは別。脱落するのは store 命令そのものなので **新規類型 (D24 候補、行案は §6)**。

## 1. 結論

- **(a) 元の機械語でも 2 本の 4B store に分かれている**: `mov eax,4` → `mov dword [rbp-0x30],eax` (`89 45 d0`) → `mov dword [rbp-0x2c],eax` (`89 45 d4`)。元の x86 に、この 8B を qword で読む命令は無い (callee `181057a90` は `[rdx]`・`[rbx]` を 4B で読むだけ)。**`0x400000004` は元の機械語に存在しない値**で、wasm で別の読み方をしたときだけ現れる (§2)。
- **(b) alloca 配置は元の stack frame 由来ではなく lift 側 (RetDec + LLVM)**。真因は「2 本の store が 8B にまとまっていない」ことではなく、**`mov [rbp-8],rax` (`0x181057b71`) と `mov [rbp-0x20],rax` (`0x181057b87`) の 2 store が IR から脱落**していること (§3)。callee は `[r8+8]` (= `[rbp-8]`) → `[[r8+8]]` (= `[rbp-0x20]`) と読むため、wasm では `[rbp-0x10]` の alloca の 8B 先 (= 隣の alloca の `4,4`) を読んで `0x400000004` を得る。
- 脱落の段: RetDec の `LLVM instruction optimization using RDA` で `stack_var_-16` が alloca ごと消え、その後 `Combine redundant instructions` で `stack_var_-40` が消える (§3 表)。decode 直後 (`Input binary to LLVM IR decoding`) はレジスタ global と `inttoptr` 経由で alloca が無く、`Stack optimization` の直後は両方の slot に alloca と store がある。
- **回復実験**: 2 store を戻し、`[rbp-0x10]` と `[rbp-8]` を 16B の 1 alloca に置いた IR で route を作り直すと、`181057b38` は 8 入力で **TRAP 8 → OK 8**、BLK+0 (`0x36319008`) への "emsc" 書込みは **8 → 0**。負の対照 (store だけ戻し alloca は別のまま) は TRAP 8・"emsc" 書込み 8 のまま (§4)。`fa_sweep.sh 8 60` で行が変わる関数は `0x181057b38` の 1 件だけ (他 130 関数は不変)。
- **DEFECTS.md の分岐**: issue の「元からまとまった 8B store なら DEFECTS.md に類型追記」には該当しない (元から 2 本)。もう一方の分岐「RetDec の lift 側の欠陥として (a)(b) を閉じる」に該当。D24 の行案は §6 に置き、DEFECTS.md の編集は PM 判断 (`docs/WORKFLOW.md` §5)。
- **受入条件**: [x] `181057b38` 該当区間を元の機械語と突合 (§2)。[x] 付録 1998 §6 の未確定 (a)(b) を閉じた (本付録、1998 付録は本付録への参照に更新)。未達なし。

## 2. 元の機械語 (a)

**素材と限界**: この run の `oc_artifacts` に `plugins-freshair` が無く、`SlateCore.core_64` 本体は取得していない。代わりに `work-icall` の次の 2 つを使った。(1) `rt_freshair-core/before.0.drc.dsm` = `roundtrip.sh` の "before" (`map.json` の `pe` = 元 PE を RetDec で decode した結果。命令ごとの bytes 付き)。(2) `rt_freshair-core/rw.dll` = 元 PE + `.icall` section。元の VA 領域は書き換えずに残してある。(1) の bytes を capstone で再 decode し、(2) の同 VA の bytes と比較した: `0x181057b38`–`0x181057c05` の 205 B は **完全一致**。ファイル本体の sha256 との突合は未実施 (§8)。

| VA | 機械語 | frame slot | before IR (`before.0.drc.ll`) の store |
|---|---|---|---|
| `b41` | `mov [rbp-0x28], rcx` | `stack_var_-48` | あり |
| `b49` | `mov [rbp-0x18], rax` | `stack_var_-32` | あり |
| `b5f` / `b62` | `mov dword [rbp+0x20/0x28], eax` (=5) | `stack_var_24` / `32` | あり (24 は i64 5 の store、幅は 8B に広がる。別 alloca なので無害) |
| `b69` | `mov [rbp-0x10], rax` (= `&[rbp-0x28]`) | `stack_var_-24` | あり |
| **`b71`** | **`mov [rbp-8], rax` (= `&[rbp-0x20]`)** | `stack_var_-16` | **無い** |
| `b7a` | `mov dword [rbp-0x30], eax` (=4、`89 45 d0`) | `stack_var_-56` | あり (`i32 4`) |
| `b7d` | `mov dword [rbp-0x2c], eax` (=4、`89 45 d4`) | `stack_var_-52` | あり (`i32 4`) |
| **`b87`** | **`mov [rbp-0x20], rax` (= `lea [rip+0x2af159]` = `0x181306ce0`)** | `stack_var_-40` | **無い** |

IR の store の `!insn.addr` (`!2531`–`!2537`) を引いた対応は `b41 b49 b5f b62 b69 b7a b7d` の 7 件で、`b71`・`b87` は存在しない。

- 呼出し (`bea`–`bfa`): `rcx=&[rbp+0x18]`, `rdx=&[rbp-0x2c]`, `r8=&[rbp-0x10]`, `r9=&[rbp-0x30]` で `181057a90` を呼ぶ。
- callee `181057a90`: `rdi=r8`, `rbx=r9`。`mov ecx,[rdx]` (4B) → `181056a4c`、`mov rax,[rdi+8]` → `mov rdx,[rax]` → `mov rdx,[rdx]` (8B 3 段)、`mov rcx,[rdi]` → `mov rcx,[rcx]`、`mov ecx,[rbx]` (4B) → `181056aa0`。**8B で `[rbp-0x30]` を読む命令は無い**。元の frame では `[rdi+8]` = `[rbp-8]` = `&[rbp-0x20]` で、そこに b87 の `0x181306ce0` が入っている。

## 3. IR 側 (b): 脱落の段

`rw.dll` の元 VA 領域 (元 PE と同じ bytes) を `retdec-decompiler --select-ranges 0x181057b38-0x181057c05 --select-decode-only --print-after-all` で走らせ (13 s)、各段の module dump から `function_181057b38` の alloca・store・load・ptrtoint を数えた (`frame_slot_probe.py phase`。値は `alloca/store/load/ptrtoint`、遷移した段だけ):

| 段 | `-16` | `-40` | `-24` | `-56` / `-52` |
|---|---|---|---|---|
| Input binary to LLVM IR decoding | alloca 無し (レジスタ global 経由) | 同 | 同 | 同 |
| Stack optimization | 1/1/0/0 | 1/1/0/2 | 1/1/0/1 | 1/1/0/1 |
| Function parameters and returns optimization | 1/1/0/0 | 1/1/0/2 | 1/1/0/1 | 1/1/1/1 |
| **LLVM instruction optimization using RDA** | **0/0/0/0 (消滅)** | 1/1/0/1 | 1/1/0/1 | 1/1/1/1 |
| LLVM instruction optimization | 0 | 1/1/0/1 | 1/1/0/0 | 1/1/1/0 |
| Value protection optimization | 0 | 1/2/0/1 | 1/2/0/0 | 1/2/1/0 |
| **Combine redundant instructions** | 0 | **0/0/0/0 (消滅)** | 1/2/0/0 | 1/2/1/0 |
| Dead Store Elimination | 0 | 0 | 1/1/0/0 | 1/1/1/0 |

- `Value protection optimization` の段では `-40`・`-24`・`-56`・`-52` の store 数が 1→2 になる (理由は未確認)。
- `-16` は `ptrtoint` 0・`load` 0 (address を取られず読まれない slot) で、RDA 段が store ごと消す。`-40` は唯一の user (= `-16` に入る address) が消えたあと instcombine が消す。`-24` は `lea r8,[rbp-0x10]` で address が callee へ渡るので残る。**消す条件は観測からの推定** (RetDec 本体のソースは未読)。
- callee の IR は `@function_181057a90(i64* %arg1, i32* %arg2, i64* %arg3, i32* %arg4)` で、呼出しは `(stack_var_16, stack_var_-52, stack_var_-24, stack_var_-56)`。`a90` の IR は `%3 = ptrtoint %arg3` → `%6 = add i64 %3, 8` → `load i64` (`before.0.drc.ll`)。`stack_var_-24` は `alloca i64` (8B) なので、`+8` は **alloca の範囲外**を指す。LLVM では未定義で、backend の frame 配置次第で隣の alloca に当たる。
- wasm の配置 (1998 付録 §6 の実測。本 run では再測定していない): `stack_var_-24` = `0x104af3d8`、`stack_var_-56` = `0x104af3e0`、`stack_var_-52` = `0x104af3e4`。したがって `+8` = `0x104af3e0` の 8B = `0x400000004`。元の frame では `[rbp-0x10]` の 8B 先は `[rbp-8]` で、`-0x30`/`-0x2c` とは無関係。wasm backend が `-24` の直後に `-56`/`-52` を置いた。**配置は元の frame ではなく LLVM wasm backend の frame layout 由来**。

## 4. 回復実験

`frame_slot_probe.py restore` が `after.0.restored.ll` の `function_181057b38` だけを書き換える。fixed: `stack_var_-24` と `-16` を `alloca i128` (16B 1 つ) の下位・上位 8B に置き、`-40` の alloca と `store @global_var_181306ce0 → -40`、`store &-40 → -16` を足す (脱落した b87・b71 に相当)。negative: store は同じだが `-24` と `-16` を別 alloca のままにする。route は `fa_route_build.sh` に `FA_SRC` を渡して作り直し、`fa_wc_build.sh` → `fa_wc_drv.cjs <fa_wc.cjs> 181057b38` を 8 入力で実行。

| 条件 | 8 入力の結果 | WC 行 | "emsc" (`63736d65`) の WC 行 | BLK+0 (`0x36319008`) への "emsc" |
|---|---|---|---|---|
| base (現 IR) | OK 0 / TRAP 8 | 168 | 32 | 8 |
| fixed (2 store + 16B 1 alloca) | **OK 8 / TRAP 0** | 168 | **0** | **0** |
| negative (2 store のみ・別 alloca) | OK 0 / TRAP 8 | 168 | 32 | 8 |

`fa_sweep.sh 8 60` (131 関数・`FA_CORE` は rw.dll・測定 commit `2c8088f4`): base は bit 一致 47 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 9、fixed は 47 / 66 / 8 / 10。旧値 46 / 66 / 9 / 10 (`bfe8bffc`・`5eb91673`・`aa3c8758` の 3 回で同一) と ±1 異なる。同じコードでも 1 関数の判定が揺れるが、どの関数かは未特定 (#2302)。**行が変わる関数は `0x181057b38` の 1 件** (`2c8088f4` でも 1 件)で、`wasm_err` 8 → 0、`mismatch` は 8 のまま (wasm の xmm0 は 0、native は入力の xmm0 のまま。この不一致の原因は未調査)。他 130 関数の判定と `n/match/mismatch/wasm_err/native_err` は base と一致。
スクリプト末尾 (§6) で `work/fa_route`・`work/fa_wc` を base で作り直す。負の対照の route を後続の `fa_sweep.sh` が拾わないため。

## 5. 脱落 store の census (F.ranges 131 関数)

`frame_slot_probe.py census`: `before.0.drc.dsm` の命令を capstone で decode し、rbp 相対の `mov` store のうち、`before.0.drc.ll` に同じ `!insn.addr` の store が無いものを数える。frame pointer 型 (`mov rbp,rsp` か `lea rbp,[rsp+..]`) の関数だけを対象にした。

| 項目 | 値 |
|---|---|
| F 関数 / dsm に命令がある関数 | 131 / 130 |
| rbp 相対 store か lea を持つ関数 | 8 (frame pointer 型 4、rbp を汎用 reg に使う型 4 は除外) |
| frame pointer 型の rbp 相対 `mov` store | 29 件 |
| IR に store が無い (脱落) | 21 件 |
| 脱落のうち、`lea` で address を取られた slot の 0x40 以内上側にある (候補) | 12 件 / 2 関数 (`181057b38` が 2 件・`180da6e60` が 10 件) |

`181057b38` の 2 件は §3–§4 で確定。`180da6e60` は同じ形を含む (`mov [rbp-0x31],rcx`・`mov [rbp-0x29],rcx` の組を `lea rdx,[rbp-0x31]` → `call r10` で渡す。`[rbp-0x29]` の store が脱落) が、callee が `[rdx+8]` を読むことと wasm 上の挙動は未確認。残り 9 件の内訳は未確認。この関数は `fa_sweep.sh` で native crash/timeout のため比較できない。**候補は miscompile の確定ではない**。

## 6. DEFECTS.md 形式の行案 (D24 候補・DEFECTS.md は未編集)

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|---|---|
| D24 | opt (RetDec RDA + instcombine。decode 段は正しい) | **新規** (ICALL-75 / #2394) | frame 上の隣接 slot 群 (`{ptr, ptr}` の組・小配列) の先頭 address だけを callee に渡すと、先頭以外の slot への store が IR から消える。callee の `[arg+8]` は別 alloca (wasm では隣の `4,4` = `0x400000004`) を読み、そこから null ページの "emsc" を拾って BLK+0 に書き trap | RetDec は frame slot ごとに alloca を作り (Stack optimization)、address を取られず読まれない slot への store を dead とみなして alloca ごと消す (RDA 段、推定)。escape した slot の `+8` を callee が読む使い方は考慮されない。残った alloca の配置は wasm backend が決める | `181057b38`: `[rbp-8]`・`[rbp-0x20]` の 2 store が脱落。2 store と 16B 1 alloca を戻すと 8 入力 TRAP 8 → OK 8、BLK+0 への "emsc" 8 → 0。store だけ戻して別 alloca のままだと TRAP 8 のまま (§4) | 機械語の rbp 相対 store に対応する IR store が無く、その slot が `lea [rbp+e]` で address を取られた slot の上側 0x40 以内 (`frame_slot_probe.py census`)。F 131 関数で候補 2 関数 (確認済み 1) | 脱落 store を戻し、escape した slot とその隣を 1 つの alloca にまとめる IR pass (実験は `frame_slot_probe.py restore`。一般化は §8、#2427) |

## 7. 測定条件

| 項目 | 値 |
|---|---|
| コードを変えた最後の commit | `2c8088f4` (`tools/icall/frame_slot_2394.sh` の §6 後始末の追加。指摘 m3) |
| 測定に使った HEAD | `2c8088f4` で `SWEEP=1 bash tools/icall/frame_slot_2394.sh` を 1 回実行 (ログ `work/measure_2c8088f4.log`)。§1–§3 と §4 の 8 入力の結果は、前回 (`bfe8bffc`・`5eb91673`・`aa3c8758`) と一致。sweep の集計のみ ±1 (§4) |
| 所要 | 206.6 s (`2c8088f4`)。前回は 202.6 s (`bfe8bffc`)・191.9 s (`aa3c8758`)・187.4 s (`5eb91673`)。load (1 分平均) は `2c8088f4` の実行前 0.29 → 後 1.05 (`uptime`)。1 並列 (逐次実行) |
| 素材 | `work-icall` (`rt_freshair-core`)・RetDec v5.0 (commit `53e55b4b`、`toolchain-retdec` の `retdec-decompiler` と size・mtime が一致する [RETDEC])・`toolchain-emsdk` ([EMSDK])。`plugins-freshair` は未使用 (`toolchain-retdec` の tar は展開せず、runner に展開済みのものを使った) |
| `FA_CORE` | `rw.dll` (元 PE + `.icall`)。`data_gen.py` の .rdata/.data 敷設と native 実行に使う。元 DLL での base は 1998 付録 §4 の 47 / 66 / 9 / 9。rw.dll での base は本 run (`2c8088f4`) で 47 / 66 / 9 / 9、旧 REPORT で 46 / 66 / 9 / 10 (±1 の揺れは #2302 で追跡中。rw.dll 代替が原因かは未切り分け) |
| コード差分 | `git diff --name-only 2c8088f4 b965b56c -- tools/icall` の出力は `tools/icall/REPORT_APPENDIX_2394.md` の 1 行だけ (md。スクリプト・コードの差分は 0)。`b965b56c` は本付録の指摘対応の commit (この行を書いた commit の 1 つ前) |

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 脱落 store を戻す IR pass の一般化と `fa_route_build.sh` への組込み (現状は `181057b38` 専用の置換)、`180da6e60` の候補 10 件の判定、fixed 後も `181057b38` が 8/8 不一致の原因、RDA 段が store を消す条件の確認 | BLK+0 の trap は実験で解消するが、closure 全体の bit 一致は 46 のまま | ICALL-77 (#2427、本 PR で起票) |
| 元 `SlateCore.core_64` 本体の bytes との照合 (本 run は `plugins-freshair` なし) | (a) の根拠は元 PE の decode 結果 + `rw.dll` の同 VA。ファイル本体の sha256 とは未突合 | ICALL-77 (#2427) の run で `plugins-freshair` を取得して照合 |
| `docs/DEFECTS.md` への D24 行の追加 | 横断正本への反映 | PM 判断 (`docs/WORKFLOW.md` §5) |
| `fa_sweep.sh` の ±1 の揺れ (旧 46/66/9/10 と本 run の 47/66/9/9。同じコードで 1 関数の判定が揺れる) | 数値の正本の取り方 | #2302 (ICALL-71、既存) |

## 9. 再現

```
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .      # tools/icall/work/ へ
bash tools/ott/native/build.sh                                 # fa_sweep.sh に必要 (libottnative.so)
SWEEP=1 bash tools/icall/frame_slot_2394.sh                    # §2–§5 の全出力 (SWEEP 無しなら sweep を省く)
python3 tools/icall/frame_slot_probe.py mc --dsm tools/icall/work/rt_freshair-core/before.0.drc.dsm --va 0x181057b38
```

範囲外: 実機 (native) の `181057b38` の frame 上の値の直接観測、`180da6e60` の wasm 実行、他の PE (FLEngine 等) の census、RetDec 本体の pass の内部確認。
