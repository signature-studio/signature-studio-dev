# #856: unit 56 の trap 元 `8c5eb0` の fail-fast 辺の到達可否と機械語対応の確定

**結論**: unit 56 (`0x16fde0`) の `unreachable` は、#699 が入れた `8c5eb0` の件数 0 ガードの fail-fast 辺 (`_t`) で起きる。この辺は unit 56 だけが到達する (survey の trap 25 件中 1 件のみ)。機械語では、この辺に対応する native の経路は `8c608d` の vtable 呼出し (`410360`) であり、fail-fast は native から外れた挙動である。native の呼出先は静的 PE からは確定できなかった (§4)。
検証 HEAD: `986e7415` (origin/main 取り込み時点) + 本 PR の `reach_856.sh` / 本 REPORT のみ。
既知類型との関係 (DEFECTS.md): D1b と同型の疑い (#699 §5 の行案が PM 判断待ち)。機構の切り分けは未着手 (#718 / M11-N35)。

## 1. 機械語 (`8c5eb0`, capstone 5.0.7, `block00031_PE.bin` を VA 直接逆アセンブル)

`bash tools/m11/trap_triage/disasm_fn.py 8c5eb0` の要点 (`FL_WIN64_DIR` 設定済み):

```
8c5f15: cmp [rbp+0x4c], ebx ; 8c5f18: jg 0x8c6066     件数 <= 0 で本体を飛ばす
8c6066: cmp qword [rbp+0x90], 0 ; je 0x8c6084          arg3 == 0 なら 8ca670 を飛ばす
8c6084: cmp byte [rbp+0x88], 0  ; je 0x8c60df          arg2 下位 byte == 0 なら戻る
8c608d: mov rcx, [rbp+0x80]; call 0x410360             arg2 下位 byte != 0: vtable 呼出し
8c6099: mov [rbp+0x80], rax ; jmp 0x8c60df
8c60df: mov rax, [rbp+0x80] ; ret
```

- `410360` (size 77) は `call qword [rbx-0x50]` (rbx = `[rcx]` = vtable) を行い、`[rbp+0x60]` (= 入力 rcx) を返す。
- 元の IR (`work/boot_final.ll`) の `function_8c5eb0` には `unreachable` / `llvm.trap` が無い。trap を入れたのは `m11_guard699.py --mode on` で、`_t` の `llvm.trap` は guard pass が追加したものである。

## 2. 到達可否の実測 (`bash trap_triage/reach_856.sh`)

`m11_gen_ir2.sh` で `ir_conditions.json` を作り直し (rc 0・`ldfix=applied`)、`m11_build.sh` (guard on 既定) → `m11_survey.mjs` の順で実行した。

| 項目 | 結果 |
|---|---|
| build | rc 0, 25 秒 |
| survey (942 unit) | ok 869 / trap 25 (oom 1) / miss 47 / noproc 1 / clobber 0 |
| unit 56 の trap | `RuntimeError: unreachable`, 最上位 frame `wasm-function[3471]:0x1aa1df` |
| trap unit のうち `wasm-function[3471]` を通るもの | **1 / 25** (unit 56 のみ) |
| 他 24 件の trap 元 | OOB 17 件 (`memory access out of bounds`)・`m11_throw_dllmain_done` 7 件 (`Error`) |
| 再現 (n=3, 本 HEAD) | 3 回とも unit 56 `unreachable`、ok 869 / trap 25 で同一 |

- 所要 (`reach_856.sh` 全体, 2 回の survey 込み): 28 秒。load average 0.47 (4 vCPU)。
- `wasm-function[3471]` の関数名 (`function_8c5eb0`) は #699 §3-1 の `-g` 付き名前リンクでの測定を引き継いだ。本 run では名前の再検証はしていない。

## 3. unit 56 のステータス (関数 `function_56fde0` 内の呼出し)

`function_56fde0` (`boot_final.ll` line 392, 405) の `8c5eb0` 呼出し:

```llvm
%262 = call i64 @function_8c5eb0(ptr inttoptr (i64 1469800), i64 %ce0n19_function_56fde0, i64 0)
```

- `arg3 = 0` は定数。`arg2 = x | 1` なので下位 byte は必ず非 0。よって件数 <= 0 であれば、この呼出しは必ず fail-fast 辺を取る。
- IR 定数 `1469800` は linear アドレス (`m11_passes.py` の `VA - 0x400000` の remap)。VA は `0x400000 + 1469800 = 0x566d68`。静的 PE の `.text` 内で `+0x14` (件数) は `00000000` (0)。第 2 呼出しの `1470128` (VA `0x566eb0`) も `+0x14` = 0。
- 静的値は実行時の値と一致するとは限らない。実行時の件数は `reach_856.sh` では読んでいないが、survey が 3 回とも `unreachable` で止まっているため、件数 <= 0 で辺を取ったことは実行結果から言える。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `8c608d` の native 呼出先 (`410360` → `call [vtbl-0x50]`) の確定。静的 PE では確定できない: object (VA `0x566d68`) の先頭 qword は `0x568b50` で、これは `.text` 内の関数 (prologue `55 41 55 57 56 53`) を指す。`0x568b00` の qword は `0xffffd3a8e8000000` で、有効な代入先ではない。実行時に object の先頭が書き換わるか、別の vtable を指すかは未切り分け | native が返す値が不明。fail-fast 版は unit 56 を止める。「unit 56 ok」は native 値の確定が前提 | #718 (M11-N35) へのコメント |
| fail-fast 辺が native と異なる挙動 (件数 0 ∧ arg2 下位 byte≠0 で、native は vtable 呼出しで値を返す) | unit 56 の trap は guard の仕様であり、survey の ok/trap では native との差を測れない | #718 へのコメント。挙動変更として #699 §6 (ii) に記録済み |
| count = INT_MIN の不一致 (#699 §6 (iii)) | 到達可否は未確認。本 run では件数の動的値を読んでいない | #718 |
| #699 §6 (i): 件数 >= 1 の戻り値の食い違い | 本 run の対象外 | #718 |

## 5. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"     # tar --zstd -xf fl-win64.tar.zst
cd tools/m11
bash m11_gen_ir2.sh          # work/ir_conditions.json を作る (capstone・pefile 必須)
bash m11_build.sh            # guard on 既定
bash trap_triage/reach_856.sh
```

## 6. 範囲 / 範囲外

- 範囲: 到達可否 (survey の trap 元の全件照合) と `8c5eb0` の機械語対応。本 PR は `tools/m11/trap_triage/` のスクリプトと本 REPORT のみ。
- 範囲外: 呼出先 (`8c608d`) の確定と native 値の比較 (#718)。`m11_guard699.py` の変更なし。`docs/DEFECTS.md` の編集 (PM 判断)。
- `work/` (`work-m11`・`ir_conditions.json`・`v856/`) は gitignore。20 MiB 超の blob は追加なし。
