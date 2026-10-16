# 付録: icall #5843 (ICALL-119) — slot 関数の r13 全 ret 経路と間接呼出しの具象型 (部分達成)

> 親: #5044 (ICALL-108)。前付録: `REPORT_APPENDIX_5044.md` (§ 上界の測定は `cb_vtable_superset.py`・前の 3 PR #5851・#5867・#5882)。
> 測定 commit: `8d5eef183` (コードを変えた最後の commit。`tools/icall/ret_r13_check.py` の出口計上・関数境界の修正)。以降 `tools/icall/*.py` の変更は無い。
> 素材: `plugins-freshair` の `Fresh Air.Win.zip` から `SlateCore.core_64` (sha256 `2cf759f712adf955a56684df4b24454690ac878105d4433de16c88626a45dd3b`、PR 記載と一致を確認)。全量 dsm は `tools/icall/work/core64.dsm` (gitignore)。`work-icall` は未使用。

## 結論

- 受入 2 の残り (間接 `180cbba21` `call [rax+0x8]`・`180cbba36` `call [rax+0x10]`) の具象型は **未特定**。`r13` の保存も、この 2 件の具象型が決まらないと判定できない。受入 2 は部分達成 (#5843 に残す)。
- slot 関数の `r13` 保存分類 (`ret_r13_check.py`・`r13` を書く slot 関数 73 件): `class_saved_balanced` 56・`class_write_without_save` 1 (`180e2c460`)・`class_no_r13_on_paths` 9・`class_unresolved_indirect` 7・`class_write_before_save` 0・`class_no_exit` 0・`class_unbalanced` 0。`saved_balanced` は「保存あり・到達できる全出口で `push r13` と `pop r13` が釣り合い・r13 の書込みが保存より後」の意味で、出口は ret と本体外への直接 `jmp` (末尾呼出し) の両方を数える。
- 上界 (`cb_vtable_superset.py`・`vtable_r13.py` は `ret` 境界の旧版): slot 関数 745 件、`lea` 先 12,738、vtable 様の両 slot がコードを指すもの 1,724。`ret_r13_check.py` と境界が違うため、`r13` 書込み関数 56 件 (旧境界) と 73 件 (新境界) は別の母集団。`ret_r13_check.py` の件数は 73 だけを使う。

## 測定 1: 間接呼出し `180cbb930` の周辺 (手作業・objdump 出力)

- `180cbba21`: `ff 50 08` = `call QWORD PTR [rax+0x8]`。直前は `mov rax,[rbx]`・`mov rcx,rbx` (`rbx` = `[rsp+0x28]`)。
- `180cbba36`: `ff 50 10` = `call QWORD PTR [rax+0x10]`。直前は `mov rcx,[rsp+0x28]`・`mov rax,[rcx]`。
- 両 call の前で `lock xadd [rbx+0x8]` / `[rbx+0xc]` により参照カウントを減らし、0 になった時だけ呼ぶ (shared_ptr の `_Destroy`・`_Delete_this` の形)。`rbx` が指す control block の vtable が具象型を決める。
- `180cbb930` の本体は `r13` を一切使わない (本体の `r13` 文字列 0 件)。直接呼出し `180cbcd90`・`180cb9890` も前付録で `r13` 書込み 0 件。

## 測定 2: slot 関数の全出口 (`tools/icall/ret_r13_check.py`・測定 commit `8d5eef183`)

`cb_vtable_superset.py` の slot 関数のうち `r13` を書く関数について、関数内の分岐を辿り、到達できる経路を次の分類に分ける (`ret_r13_check.py` の出力 `class_*`)。保存・書込みは到達した経路の命令だけで判定する。

| 分類 (`ret_r13_check.py`) | 意味 | 件数 (`8d5eef183`) |
|---|---|--:|
| `class_saved_balanced` | `push r13` で保存し、到達できる全出口で `pop r13` と釣り合う | 56 |
| `class_write_before_save` | `r13` を書いた後に `push r13` で保存する経路がある | 0 |
| `class_write_without_save` | 到達経路に `r13` の書込みがあり、保存 (`push r13`) が無い | 1 (`180e2c460`) |
| `class_no_r13_on_paths` | 到達できる経路に `r13` の書込みが無い (後続関数の命令は数えない) | 9 |
| `class_no_exit` | 出口 (ret・本体外への直接 `jmp`・本体末尾の落下) が 1 つも無い | 0 |
| `class_unresolved_indirect` | 間接 `jmp` で経路が閉じない (未確認) | 7 |
| `class_unbalanced` | 出口で `push r13` と `pop r13` の差が 0 でない | 0 |

- 出力の他の項目: `slot_functions` = 918 (`ret_r13_check.py` の境界。`ret` と無条件 `jmp` の直後の `int3` 埋め草で関数を切る)・`r13_writing_slot_functions` = 73・`ret_paths_checked` = 71・`exit_paths_checked` = 74・`write_without_save_with_mov_spill` = 1 (`180e2c460`。`mov [rsp±X],r13` の退避だけで保存に見える件数)。
- `class_no_r13_on_paths` の 9 件: `1800d3170`・`1801d1460`・`1801f88d0`・`1802efa80`・`1802f13e0`・`180c93160`・`180d7ce80`・`180dc1850`・`180f96170`。
- `class_unresolved_indirect` の 7 件: `18016e2b0`・`1801dda00`・`1801f6b90`・`1801fd8f0`・`1802cd160`・`1802e1210`・`1802e3490`。
- `class_write_without_save` の 1 件: `180e2c460` (退避 `mov [rsp±X],r13` のみ)。
- `--selftest` は 9 パターン (保存なし書込み・保存あり・書込み後の保存・釣り合わない・間接 jmp・出口なし・末尾呼出しの不釣り合い・末尾呼出しの釣り合い・到達経路に書込み無し) すべて期待どおり PASS (`8d5eef183`)。

### 解析の注意 (偽陽性を潰した経緯)

- 退避 `mov [rsp±X],r13` を保存として数えると、値の退避 (スピル) を `push` と二重に数えて釣り合いが崩れる。保存は `push r13` だけを数える。
- `ud2`・`int3` の後ろは到達しない。ここで経路を打ち切る。
- 本体外への直接 `jmp` (末尾呼出し) は出口として数え、その時点の `d` を検査する。旧版はこれを `continue` で捨てており、ret 経路を持たない 4 関数を「釣り合う」に入れていた (round 4 指摘・`8d5eef183` で修正)。
- 関数境界は `ret` と無条件 `jmp` の直後の `int3` 埋め草で切る。旧版は `ret` だけで切っていたため、`jmp` 後の別関数の命令が前の関数本体に混ざり、到達しない `push r13` と `mov r13` を拾っていた。
- 間接 `jmp` は末尾呼出しと switch の両方がありうる。現版はどちらも「未確認」として分けるだけで、閉じた判定はしない。

## 測定 3: 再現と所要 (測定 commit `8d5eef183`)

| コマンド | 結果 | 所要 | load |
|---|---|--:|---|
| `python3 tools/icall/ret_r13_check.py <SlateCore.core_64> tools/icall/work/core64.dsm` | slot_functions 918・r13_writing_slot_functions 73・ret_paths_checked 71・exit_paths_checked 74・class_saved_balanced 56・class_write_before_save 0・class_write_without_save 1・class_no_r13_on_paths 9・class_no_exit 0・class_unresolved_indirect 7・class_unbalanced 0・write_without_save_with_mov_spill 1 | 7.56 s (real) | 1-min load 0.43 (測定時 15:48) |
| `python3 tools/icall/ret_r13_check.py --selftest` | 9/9 PASS | — | — |
| `python3 tools/icall/cb_vtable_superset.py <SlateCore.core_64> tools/icall/work/core64.dsm` | lea_targets 12738・vtable_like_both_slots_code 1724・distinct_slot_functions 745・slot_functions_writing_r13_unsaved 0・slot_functions_writing_r13_any 56 (with_push_r13 55・with_spill_only 1) | 7.49 s (real) | 同上 |
| `python3 tools/icall/vtable_r13.py <SlateCore.core_64> tools/icall/work/core64.dsm` | vtable_targets_stored 2457・vtables_with_slot1_slot2_code 1625・distinct_slot_functions 635・slot_functions_writing_r13_unsaved 0・slot_functions_r13_spill_only 1 (`180e2c460`) | 7.88 s (real) | 同上 |

- 入力 dsm は `objdump -d -M intel` の全量出力 (4,553,159 行)。
- `cb_vtable_superset.py`・`vtable_r13.py` は `ret` だけで関数を切る旧境界のまま。`ret_r13_check.py` と境界が違うので、件数 745・56 を 918・73 と混ぜて読まない。両者の境界を揃えるのは別作業 (未解決の表)。
- 旧判定 (`33aa87e6e`) の実測値と、境界修正前の `ea8e1ea70` の件数 (745 / 52 / 51 / 4) は採用しない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 `180cbba21`・`180cbba36` の具象型 (control block の vtable)・`r13` 保存 | 受入 2 の残り・受入 3 (`180703913` の到達判定) | #5843 (次 run) |
| `0x18040e0e0` の戻り値 `rax` と呼出し元 `180cb6965`・`180cb6a76` の `rdx` の出どころ | `[rdi+0xa80]` の具象型 | #5843 |
| `class_unresolved_indirect` の 7 件の間接 `jmp` の経路確定 | slot 関数の全出口の閉包 | #5843 |
| `cb_vtable_superset.py`・`vtable_r13.py` の関数境界を `ret_r13_check.py` と揃える | 上界の件数 (745・56) と分類の母集団 (918・73) の不一致 | #5843 |
| 受入 3 (`180703b7c` の届き判定) | #5044 の判定 | #5044 |
