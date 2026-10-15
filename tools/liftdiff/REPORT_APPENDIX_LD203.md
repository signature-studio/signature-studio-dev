# LD-203 (#4200): 691dd0 の有効オブジェクト case と 653c80 の間接 call slot

親: #3864 (LD-181)。対象は `691dd0` と `653c80` の native segv (unexec)。

## 1. 結論

| 関数 | 結果 | 根拠 |
|---|---|---|
| `653c80` | **埋めた。** boot 状態の間接 call slot `VA 0x15f3480` (RVA `0x11f3480`) に仮 proc `0x50012000` (VMT slot 0) を入れると、native segv が消え、判定に入る (`outcome=diff`) | §3 |
| `691dd0` | **未達。** 有効オブジェクトを渡しても、native / wasm とも小サイズ確保のビン読みで segv する。ビンの先頭が boot 状態で null | §2 |

## 2. 691dd0

- native fault: `addr=0x18`・`rip=0x407a97`。wasm trap も同じ経路 (`function_407a50` → `function_409410` → `function_691dd0`)。
- `407a97` の `mov rax,[rdx+0x18]` は、`407a50` が `[rbx+8]` から読んだビンの `fd` を逆参照する。segv 時 `rdx=0`。
- ビン表 (VA `0x13a5108`・16B 間隔) の index 0 と 1 は boot 状態にあり、`fd` は自身を指す (空ビンの番兵)。`fd=0` になるのは、boot 状態に含まれない size class のビン (未捕捉の領域は 0)。どの index を踏むかは未検証。
- 試したこと (いずれも segv のまま): rcx=arena `0x1000` の object を `q=0x3000` で繋ぐ / `+0x78`・`+0x94` に 0 や 1 を入れる。
- 残り: size class のビンを埋める、もしくは heap の boot 状態を作り直す。これは実装作業で、1 run に収まらないため子 issue に分ける (本 PR の未解決表を参照)。

## 3. 653c80

- 呼出し `653c8d`: `call qword ptr [rip+0xf9f7ed]` → VA `0x15f3480`。
- 書き手の探索: 全実行セクションの線形走査 (5,022,467 命令) で、slot を指す rip 相対参照は 2 件。`653c8d` (call) と `65426f` (`lea rdx,[rip+0xf9f20a]`)。`65426f` は `653dd0` (解決関数) への引数。
- 試行 (`liftdiff.py run targets/m11.json --fn 0x653c80 --args i:0x3,i:0x5,i:0x7`):

| slot の値 | native | wasm | 結果 |
|---|---|---|---|
| (埋めない・対照) | segv | ok | `native_fault` |
| `0x50010000` | ok (`?freeproc`) | ok | `diff` (calls: native のみ 1 件) |
| `0x50012000` | ok (`?vmslot0`) | ok | `diff` (calls: native のみ 1 件) |

- 再現: 同一条件で 2 回とも `diff` (`0x50012000`)。
- 残る差分: native は仮 proc (`?vmslot0`) を 1 回呼ぶが、wasm 側は呼ばない (`wasm_len=0`)。`ret` は両者 0 と wasm の `0x2000000000001` で、これは callee 側の差分で、slot 埋めの欠陥ではない。判定に入った (unexec ではない) ことは確定。

## 4. 検証

- 単体: `tests/test_ld203_slot_fill.py` PASS。規則 (`PATCH_BY_VA`) を `""` に変えると rc=1 (ネガコン)。`tests/test_ld52_machine_sig.py` 等の既存テストも `liftdiff_e2e.sh` の [0/4] で PASS。
- e2e (`liftdiff_e2e.sh --m11-only`): **未実行 (素材 `work-m11` 待ち)。** 実測値 (wall・load) は無い。過去の run の値は、同じ run と確定できないため採用しない。
- 再測定を試みた結果: 取得済みの素材は `fl-win64` のみ。`work-m11` が無いため、`liftdiff_e2e.sh` は [0/4] の単体テスト (`test_compare_ld11` / `test_ld52_machine_sig` / `test_ld179_tagpoint_tr` / `test_ld203_slot_fill`) の後、`missing input: ../m11/work/boot_final3.ll` で止まる。e2e の [1/4] 以降は未実行。
- 単体: 上記 4 件は PASS (rc=0)。
- 測定 commit: `acf54ba0e` (コード変更の最後の commit)。
- 検証 HEAD `457ee8cc3` (main 取り込み merge)。`git diff acf54ba0e HEAD -- tools/liftdiff ':!tools/liftdiff/REPORT_APPENDIX_LD203.md'` の出力: 161 行。内訳は main 側の変更 (`ldlib/pe.py` +9、`ldlib/session.py` +26/-、`REPORT.md` 1 行、`REPORT_APPENDIX_LD177.md` +67)。本 PR のコード差分は 0。
- 測定 commit 以降に `tools/liftdiff/ldlib` のコードが変わった (main 由来、`git diff acf54ba0e 7dd604e1d -- tools/liftdiff/ldlib` は 33 行)。`WORKFLOW.md` §6 の免除は差分 0 の場合だけなので、再測定が要る。素材 `work-m11` が無いこの run では実行できず、e2e の [1/4] 以降は未了。PR 本文に `oc_artifacts: fl-win64 work-m11` を入れ、`liftdiff_e2e.sh --m11-only` を完走させて実測値を本節に書く。
