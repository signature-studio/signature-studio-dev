# 付録: icall #5843 (ICALL-119) — slot 関数の r13 全 ret 経路と間接呼出しの具象型 (部分達成)

> 親: #5044 (ICALL-108)。前付録: `REPORT_APPENDIX_5044.md` (§ 上界の測定は `cb_vtable_superset.py`・前の 3 PR #5851・#5867・#5882)。
> 測定 commit: `ea8e1ea70` (コードを変えた最後の commit は `ea8e1ea70`・`tools/icall/ret_r13_check.py` の分類変更。以降 `tools/icall/*.py` の変更は無い)。
> 素材: `plugins-freshair` の `Fresh Air.Win.zip` から `SlateCore.core_64` (sha256 `2cf759f712adf955a56684df4b24454690ac878105d4433de16c88626a45dd3b`、PR 記載と一致を確認)。全量 dsm は `tools/icall/work/core64.dsm` (gitignore)。`work-icall` は未使用。

## 結論

- 受入 2 の残り (間接 `180cbba21` `call [rax+0x8]`・`180cbba36` `call [rax+0x10]`) の具象型は **未特定**。`r13` の保存も、この 2 件の具象型が決まらないと判定できない。受入 2 は部分達成 (#5843 に残す)。
- slot 関数の `r13` 保存分類 (`ret_r13_check.py`・`r13` を書く slot 関数 56 件): `class_saved_balanced` 51・`class_write_without_save` 1 (`180e2c460`)・`class_unresolved_indirect` 4 (`18016e2b0`・`1801dda00`・`1801f6b90`・`1802cd160`)・`class_write_before_save` 0・`class_unbalanced` 0。
- 上界 (`cb_vtable_superset.py`): slot 関数 745 件、`lea` 先 12,738、vtable 様の両 slot がコードを指すもの 1,724。`r13` を保存せず書く slot 関数は 0 件 (`push r13` 保存ありが 55、退避 `mov` のみが 1)。

## 測定 1: 間接呼出し `180cbb930` の周辺 (手作業・objdump 出力)

- `180cbba21`: `ff 50 08` = `call QWORD PTR [rax+0x8]`。直前は `mov rax,[rbx]`・`mov rcx,rbx` (`rbx` = `[rsp+0x28]`)。
- `180cbba36`: `ff 50 10` = `call QWORD PTR [rax+0x10]`。直前は `mov rcx,[rsp+0x28]`・`mov rax,[rcx]`。
- 両 call の前で `lock xadd [rbx+0x8]` / `[rbx+0xc]` により参照カウントを減らし、0 になった時だけ呼ぶ (shared_ptr の `_Destroy`・`_Delete_this` の形)。`rbx` が指す control block の vtable が具象型を決める。
- `180cbb930` の本体は `r13` を一切使わない (本体の `r13` 文字列 0 件)。直接呼出し `180cbcd90`・`180cb9890` も前付録で `r13` 書込み 0 件。

## 測定 2: slot 関数の全 ret 経路 (`tools/icall/ret_r13_check.py`)

`cb_vtable_superset.py` の slot 関数のうち `r13` を書く関数について、関数内の分岐を辿り、各 `ret` 経路を次の 5 分類に分けて数える (`ret_r13_check.py` の出力 `class_*`)。

| 分類 (`ret_r13_check.py`) | 意味 | 件数 (`ea8e1ea70`) |
|---|---|--:|
| `class_saved_balanced` | `push r13` で保存し、全 `ret` で `pop r13` と釣り合う | 51 |
| `class_write_before_save` | `r13` を書いた後に `push r13` で保存する | 0 |
| `class_write_without_save` | `r13` を書くが保存しない (保存の欠落) | 1 (`180e2c460`) |
| `class_unresolved_indirect` | 間接 `jmp` で経路が閉じない (未確認) | 4 (下記) |
| `class_unbalanced` | 保存と復元の個数が釣り合わない | 0 |

- 出力の他の項目: `ret_paths_checked` = 52 (確認した ret 経路数)・`write_without_save_with_mov_spill` = 1 (`180e2c460`。`mov [rsp±X],r13` の退避だけで保存に見える件数)。
- `ret_paths_checked` (52) が `r13_writing_slot_functions` (56) より 4 少ないのは、ret に到達しない 4 関数 (`180113460`・`1801f48c0`・`180c70f10`・`180c93160`) があるため。これらは ret 経路が 0 で、件数に入らない。
- `class_unresolved_indirect` の 4 件 (ret 1 経路ずつ): `18016e2b0`・`1801dda00`・`1801f6b90`・`1802cd160`。旧候補 4 件と一致した。
- `class_write_without_save` の 1 件: `180e2c460` (退避 `mov [rsp±X],r13` のみ)。
- `--selftest` は 5 パターン (保存なし書込み・保存あり・書込み後の保存・釣り合わない・間接 jmp) すべて期待どおり PASS (`ea8e1ea70`)。

### 解析の注意 (偽陽性を潰した経緯)

- 退避 `mov [rsp±X],r13` を保存として数えると、値の退避 (スピル) を `push` と二重に数えて釣り合いが崩れる。保存は `push r13` だけを数える。
- `ud2`・`int3` の後ろは到達しない。ここで経路を打ち切る。
- 間接 `jmp` は末尾呼出しと switch の両方がありうる。現版はどちらも「未確認」として分けるだけで、閉じた判定はしない。

## 測定 3: 再現と所要 (測定 commit `ea8e1ea70`)

| コマンド | 結果 | 所要 | load |
|---|---|--:|---|
| `python3 tools/icall/ret_r13_check.py <SlateCore.core_64> tools/icall/work/core64.dsm` | slot_functions 745・r13_writing_slot_functions 56・ret_paths_checked 52・class_saved_balanced 51・class_write_before_save 0・class_write_without_save 1・class_unresolved_indirect 4・class_unbalanced 0・write_without_save_with_mov_spill 1 | 3.97 s | 本 run 実測 (`time` の real) |
| `python3 tools/icall/ret_r13_check.py --selftest` | 5/5 PASS | — | — |
| `python3 tools/icall/cb_vtable_superset.py <SlateCore.core_64> tools/icall/work/core64.dsm` | lea_targets 12738・vtable_like_both_slots_code 1724・distinct_slot_functions 745・slot_functions_writing_r13_unsaved 0・slot_functions_writing_r13_any 56 (with_push_r13 55・with_spill_only 1) | 5.03 s | 本 run 実測 |
| `python3 tools/icall/vtable_r13.py <SlateCore.core_64> tools/icall/work/core64.dsm` | vtable_targets_stored 2457・vtables_with_slot1_slot2_code 1625・distinct_slot_functions 635・slot_functions_writing_r13_unsaved 0・slot_functions_r13_spill_only 1 (`180e2c460`) | 5.05 s | 本 run 実測 |

- 入力 dsm は `objdump -d -M intel` の全量出力 (4,553,159 行)。`ret_r13_check.py` の出力は、レビュワーの再測定と全項目で一致した。
- 旧判定 (`33aa87e6e`) の実測値は、保存の欠落を含む判定のため採用しない (数字は残さない)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 `180cbba21`・`180cbba36` の具象型 (control block の vtable)・`r13` 保存 | 受入 2 の残り・受入 3 (`180703913` の到達判定) | #5843 (次 run) |
| `0x18040e0e0` の戻り値 `rax` と呼出し元 `180cb6965`・`180cb6a76` の `rdx` の出どころ | `[rdi+0xa80]` の具象型 | #5843 |
| `class_unresolved_indirect` の 4 件 (`18016e2b0`・`1801dda00`・`1801f6b90`・`1802cd160`) の間接 `jmp` の経路確定 | slot 関数の全 ret 経路の閉包 | #5843 |
| 受入 3 (`180703b7c` の届き判定) | #5044 の判定 | #5044 |
