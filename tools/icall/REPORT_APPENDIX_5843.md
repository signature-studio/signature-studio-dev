# 付録: icall #5843 (ICALL-119) — slot 関数の r13 全 ret 経路と間接呼出しの具象型 (部分達成)

> 親: #5044 (ICALL-108)。前付録: `REPORT_APPENDIX_5044.md` (§ 上界の測定は `cb_vtable_superset.py`・前の 3 PR #5851・#5867・#5882)。
> 測定 commit: `33aa87e6e` (`tools/icall/ret_r13_check.py` の追加)。`git diff 33aa87e6e HEAD -- tools/icall/*.py` は 0 行。
> 素材: `plugins-freshair` の `Fresh Air.Win.zip` から `SlateCore.core_64` (36,285,952 B・sha256 `2cf759f712adf955a56684df4b24454690ac878105d4433de16c88626a45dd3b`)。全量 dsm は `tools/icall/work/core64.dsm` (gitignore)。`work-icall` は未使用。

## 結論

- 受入 2 の残り (間接 `180cbba21` `call [rax+0x8]`・`180cbba36` `call [rax+0x10]`) の具象型は **未特定**。`r13` の保存も、この 2 件の具象型が決まらないと判定できない。受入 2 は部分達成 (#5843 に残す)。
- 新規に分かったこと: slot 関数 (vtable の slot1・slot2 の 745 関数のうち `r13` を書く 56 関数) について、**全 `ret` 経路で `push r13` と `pop r13` が釣り合う関数は 52 件**。残る 4 件は switch テーブルの間接 `jmp` で経路が閉じておらず、未確認。
- 上界 (`cb_vtable_superset.py`) の再現: `lea` 参照先 12,738 件 → 両 slot が関数開始の vtable 1,724 件 → slot 関数 745 件・`r13` 未保存で書く関数 0 件。前付録と一致。

## 測定 1: 間接呼出し `180cbb930` の周辺 (手作業・objdump 出力)

- `180cbba21`: `ff 50 08` = `call QWORD PTR [rax+0x8]`。直前は `mov rax,[rbx]`・`mov rcx,rbx` (`rbx` = `[rsp+0x28]`)。
- `180cbba36`: `ff 50 10` = `call QWORD PTR [rax+0x10]`。直前は `mov rcx,[rsp+0x28]`・`mov rax,[rcx]`。
- 両 call の前で `lock xadd [rbx+0x8]` / `[rbx+0xc]` により参照カウントを減らし、0 になった時だけ呼ぶ (shared_ptr の `_Destroy`・`_Delete_this` の形)。`rbx` が指す control block の vtable が具象型を決める。
- `180cbb930` の本体は `r13` を一切使わない (本体の `r13` 文字列 0 件)。直接呼出し `180cbcd90`・`180cb9890` も前付録で `r13` 書込み 0 件。

## 測定 2: slot 関数の全 ret 経路 (`tools/icall/ret_r13_check.py`)

`cb_vtable_superset.py` の slot 関数 745 件のうち `r13` を書く 56 件について、関数内の分岐を辿り、`push r13` の個数と `pop r13` の個数が全 `ret` で釣り合うかを見た。

| 項目 | 件数 |
|---|--:|
| `r13` を書く slot 関数 | 56 |
| 全 `ret` 経路で釣り合う | **52** |
| 間接 `jmp` で経路が閉じない (未確認) | 4 |
| 釣り合わない経路 | 0 |

未確認の 4 件: `18016e2b0`・`1801dda00`・`1801f6b90`・`1802cd160`。いずれも間接 `jmp` を経由する経路が残る。`18016e2b0` の `jmp rax` (`18016e3bb`) は関数内のジャンプ表 (switch) と読めるが、`1801dda00` は `rex.W jmp rax` (`1801dda79`) で末尾に間接ジャンプする形。4 件の種別 (switch か末尾間接ジャンプか) と、各経路の復元の確認は未実施。

### 解析の注意 (偽陽性を潰した経緯)

- 退避 `mov [rsp±X],r13` を保存として数えると、値の退避 (スピル) を `push` と二重に数えて釣り合いが崩れる。保存は `push r13` だけを数える。
- `ud2`・`int3` の後ろは到達しない。ここで経路を打ち切る。
- 間接 `jmp` は末尾呼出しと switch の両方がありうる。現版はどちらも「未確認」として分けるだけで、閉じた判定はしない。

## 測定 3: 再現と所要 (commit `33aa87e6e`)

| コマンド | 結果 | 所要 | load |
|---|---|--:|---|
| `python3 tools/icall/ret_r13_check.py <SlateCore.core_64> tools/icall/work/core64.dsm` | 745 slot 関数・`r13` 書込み 56・経路 52 件釣り合い・未確認 4 | real 5.91 s / user 5.48 s | 0.33 → 0.33 |
| `python3 tools/icall/cb_vtable_superset.py <SlateCore.core_64> tools/icall/work/core64.dsm` | `lea` 12,738・vtable 1,724・slot 関数 745・`r13` 未保存 0 | real 6.12 s | 0.27 付近 |
| `python3 tools/icall/vtable_r13.py <SlateCore.core_64> tools/icall/work/core64.dsm` | vtable 2,457 (格納)・両 slot code 1,625・slot 関数 635・`r13` 未保存 0 (`180e2c460` は rsp 退避) | real 5.98 s | 同上 |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 `180cbba21`・`180cbba36` の具象型 (control block の vtable)・`r13` 保存 | 受入 2 の残り・受入 3 (`180703913` の到達判定) | #5843 (次 run) |
| `0x18040e0e0` の戻り値 `rax` と呼出し元 `180cb6965`・`180cb6a76` の `rdx` の出どころ | `[rdi+0xa80]` の具象型 | #5843 |
| 間接 `jmp` を含む 4 関数 (`18016e2b0`・`1801dda00`・`1801f6b90`・`1802cd160`) の全 ret 経路 | 4 件は未確認 | #5843 |
| 受入 3 (`180703b7c` の届き判定) | #5044 の判定 | #5044 |
