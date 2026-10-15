# KH-19c (#849) 付録: rip_data 参照先の CFG/XFG dispatch 同定と、呼び先 rax の出所の分類

- **測定 commit** (コードを変えた最後の commit): `5e1162712` (`rax_source` の rip 相対 load 分類 `bea32d40f` の後、push/bt を rax 書き込みから除く修正)。以下の実測はすべてこの commit の `scripts/` で行った。
- 修正前の測定 commit は `aa5897d56`。修正後の 8 条件 (§2) は、修正前の値と全 8 条件で一致した。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B、sha256 先頭 16 桁 `d55ce8b4c0ad7ebe`)。作業は repo 外 (`$RUNNER_TEMP` 配下)。4 vCPU。
- 再現 (`tools/targets/kilohearts` で実行): `python3 scripts/rtti_walk.py <core> <work>/rtti_vtables.json` → `callgraph.py <core> <work>/rtti_vtables.json <work>/callgraph.pkl 14` → `vtable_closure.py <core> <work>/callgraph.pkl <work>/rtti_vtables.json <ns> <all|nogui> <out.json>` (8 条件: ns は micropass / multipass / phaseplant / gain、モードは nogui / all)。出力 JSON の `cfg_call_resolution`・`after_cfg_*` が本付録の値。
- 単体テスト: `cd scripts && python3 test_rax_source.py` (capstone の機械語で `rax_source` の分類を固定)。

## 0. 結論

- rip_data の参照先 2 slot (`0x1813a1d38` / `0x1813a1d40`) は、load config の `GuardCFDispatchFunctionPointer` / `GuardXFGDispatchFunctionPointer` と**一致**した。`call [slot]` は CFG/XFG の dispatch で、呼び先は**直前に rax に入った値**で決まる (参照先の thunk は `jmp rax`)。
- 修正後の再測定 (`5e1162712`・8 条件・§2) で、修正前の結論は確定した。rip 相対 load (`mov rax, qword ptr [rip+X]`) は、CFG 経由 call の rax 出所として 0 件 (`rip_load` は 8 条件とも 0 件)。vtable 形 (`vtable_cfg`) の件数は修正前と同じ (対照 Gain・all は 40 件)。よって §3 の判定 (vtable 形 40/54 件の候補確定・閉包は不変) は修正後も変わらない。
- 残りの未確定件数 (対照 Gain・all は 14 件: call_ret 8・reg_copy 2・other_write:ror 2・other_write:mov 1・label 1) は修正前と同じ。呼び出し戻り値などの追跡は子 issue **#3363 (KH-55)**。
- 確定した slot 側の候補は 0 件 (変わらず)。after_cfg = after (差 0) で、全 8 条件で新規の関数は 0 件。before / after / after_rip / after_cfg は修正前の全 8 条件と一致 (§2)。`rax_source` は after_cfg の計算だけに使うため、after / after_rip は修正の影響を受けない。

## 1. 規則 (`scripts/vtable_closure.py`・#849 の追加分)

1. `cfg_dispatch_slots`: load config の `GuardCFDispatchFunctionPointer` / `GuardXFGDispatchFunctionPointer` の VA を集める (pefile)。
2. `is_cfg_call`: `call [rip+X]` で X が `cfg_dispatch_slots` に入る site を CFG 経由とする。
3. `rax_source`: 同一関数内で CFG call の直前から逆向きに、rax (eax/ax/al/ah を含む) を書く最後の命令を探す。rax を書かない命令 (`cmp`・`test`・`push`・`bt`) は読み飛ばす。
   - 暗黙に rax を書く命令 (`cdqe`・`cwde`・`cmpxchg`・`lods*`・`cpuid`・`rdtsc` 等、1 オペランドの `mul`・`imul`・`div`・`idiv`、rax を相手に取る `xchg`・`xadd`) → `other_write:<mn>`。
   - `mov rax, qword ptr [R+d]` (R は rip 以外) → `vtable_cfg` (arg = d)。呼び先は `[R+d]` で、`call [R+d]` と同じ。
   - `mov rax, qword ptr [rip+X]` (rip 相対 load) → `rip_load` (arg = X の参照先 VA)。
   - `lea rax, [rip+F]` で F が関数先頭 → `lea_fn`、それ以外 → `lea_nonfn`。
   - それ以外は `reg_copy` / `other_write:<mn>` (`ror`・`mov` (indexed) 等)。
   - 間に `call` があれば `call_ret` (戻り値。未追跡)。分岐先 (label) を跨げば `label_barrier` (経路が一意でない)。
4. `after_cfg` = 不動点。`vtable_cfg` は vtable 規則 (同 ns の slot `d/8`)、`lea_fn` は F を加える。`after` / `after_rip` の計算は変えていない。

## 2. 実測 (修正後・測定 commit `5e1162712`・4 vCPU・各 1 回)

| ns | モード | CFG 経由 call | before 関数 / B | after 関数 / B | after_rip 関数 | after_cfg 関数 / B | vtable_cfg | call_ret | reg_copy | other_write:ror | other_write:mov | label | lea_fn | rip_load |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Snap Heap (micropass) | nogui | 20 | 311 / 97,327 | 1,531 / 722,713 | 1,531 | 1,531 / 722,713 | 8 | 7 | 1 | 2 | 1 | 1 | 0 | 0 |
| Snap Heap (micropass) | all | 54 | 311 / 97,327 | 3,094 / 1,388,293 | 3,094 | 3,094 / 1,388,293 | 40 | 8 | 2 | 2 | 1 | 1 | 0 | 0 |
| Multipass (multipass) | nogui | 20 | 321 / 113,050 | 1,802 / 817,610 | 1,802 | 1,802 / 817,610 | 8 | 7 | 1 | 2 | 1 | 1 | 0 | 0 |
| Multipass (multipass) | all | 54 | 321 / 113,050 | 3,328 / 1,476,922 | 3,328 | 3,328 / 1,476,922 | 40 | 8 | 2 | 2 | 1 | 1 | 0 | 0 |
| Phase Plant (phaseplant) | nogui | 56 | 504 / 228,241 | 3,767 / 1,791,711 | 3,767 | 3,767 / 1,791,711 | 41 | 9 | 2 | 2 | 1 | 1 | 0 | 0 |
| Phase Plant (phaseplant) | all | 56 | 504 / 228,241 | 5,582 / 2,768,378 | 5,582 | 5,582 / 2,768,378 | 41 | 9 | 2 | 2 | 1 | 1 | 0 | 0 |
| 対照 Gain (gain) | nogui | 8 | 160 / 39,357 | 555 / 178,451 | 555 | 555 / 178,451 | 3 | 2 | 0 | 2 | 0 | 1 | 0 | 0 |
| 対照 Gain (gain) | all | 54 | 160 / 39,357 | 1,995 / 731,396 | 1,995 | 1,995 / 731,396 | 40 | 8 | 2 | 2 | 1 | 1 | 0 | 0 |

- 各行: CFG 経由 call = vtable_cfg + call_ret + reg_copy + other_write:ror + other_write:mov + label + lea_fn + rip_load (行和で一致)。`CFG 経由 call` 列は `REPORT_KH19.md` §2・§4 の `rip_data` 列と同じ数。
- `rip_load` は 8 条件とも 0 件 (`cfg_call_resolution` に出ない)。rip 相対 load は CFG 経由 call の直前の rax 出所に現れなかった。
- 修正前 (`aa5897d56`) の同じ表 (rip 相対 load は `vtable_cfg` 列に含まれていた) と、全 8 条件の数値が一致 (差 0)。修正 (`bea32d40f`・`5e1162712`) は、この 8 条件では分類を変えなかった。
- 呼び先の未解決 call 内訳 (vtable 部位・iat・rip_data・reg・other・indexed) も `REPORT_KH19.md` §2 と 8 条件で一致 (再測定で確認)。
- 所要: `rtti_walk.py` と `callgraph.py` で 9 s。`vtable_closure.py` 1 回 11〜14 s (`date` の差)。load average は各 run 終了時 1.09〜1.41。

## 3. 判定 (#849 の受入・修正後の実測に基づく)

- 受入 (rip_data の候補): CFG 経由 call のうち `vtable_cfg` 形 (rip 以外の `mov rax, [R+d]`) を vtable 規則で候補確定とし、閉包に加えた結果 `after_cfg` = `after` (差 0)。全 8 条件で新規の関数は 0 件。rip 相対 load は CFG 経由 call に現れない (`rip_load` 0 件) ため、修正前の判定は変わらない。
- 未確定件数の種別別 (対照 Gain・all): 14 件 (call_ret 8・reg_copy 2・other_write:ror 2・label 1・other_write:mov 1)。残りは子 #3363 (KH-55)。他の ns・モードは §2 の列の値から同様に読める。
- 閉包内の既存 vtable 呼び出しの slot 別件数に基づく説明は、再現可能な形でコミットしていない。本付録の判定の根拠には使わない。

## 4. 検証 (単体テスト・コード差分・鮮度)

- 単体テスト (`scripts/test_rax_source.py`): `python3 test_rax_source.py` → 10 件 OK (capstone 5.0.7・`5e1162712`)。
  - `bea32d40f` の 8 件を修正前の `vtable_closure.py` (`aa5897d56`) に当てると 4 件 FAIL (rip 相対 load・`cdqe`・`mul rcx`・`xchg rax, rcx` の各ケースが誤って `vtable_cfg` になる)。
  - 追加の 2 件 (`push rax`・`bt rax, 3` の直後の CFG call) を `bea32d40f` の `vtable_closure.py` に当てると 2 件 FAIL (rax を書かない命令で打ち切られ、`vtable_cfg` が出ない)。
- 鮮度 (`docs/WORKFLOW.md` §6): 測定 commit `5e1162712`。`git diff 5e1162712 HEAD -- tools/targets/kilohearts/scripts` の出力は 0 行 (本節を含む commit は REPORT のみ)。
- 修正前から修正後までの scripts の差分は git 履歴 (`git diff aa5897d56 5e1162712 -- tools/targets/kilohearts/scripts`) で再現できる。

## 5. 制限

- 閉包の over-approximation (slot 番号一致) は変えていない。`vtable_cfg` の候補も同じ規則なので、型による絞り込みは #848 の結論 (呼び出し鎖の伝播が要る) のまま。
- `rax_source` は同一関数内の直線区間のみ。分岐越えは打ち切る (`label_barrier`)。callee の戻り値 (`call_ret`) は追わない。
- `mov rax, [rsp+d]` / `[rbp+d]` の load も `vtable_cfg` 形として扱う (スタック上の関数ポインタかどうかを区別していない。未検証)。
- `lea_fn` (exact) は 0 件 (修正前・修正後とも)。XFG の hash (`movabs r10`) は呼び先の判定に使っていない。
- 素材は `plugins-kilohearts` のみ (fl-win64 は不要)。lift / build は行っていない (#850・#3063 の範囲)。
