# KH-19c (#849) 付録: rip_data 参照先の CFG/XFG dispatch 同定と、呼び先 rax の出所の分類

- 測定 commit (コードを変えた最後の commit): `aa5897d56`。検証 HEAD は PR の最終 commit (本付録と REPORT の追記のみ)。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。作業は repo 外 (`$RUNNER_TEMP` 配下)。4 vCPU。
- 再現 (`tools/targets/kilohearts` で実行): `python3 scripts/rtti_walk.py <core> <work>/rtti_vtables.json` → `callgraph.py <core> <work>/rtti_vtables.json <work>/callgraph.pkl 14` → `vtable_closure.py <core> <work>/callgraph.pkl <work>/rtti_vtables.json <ns> <all|nogui> <out.json>` (8 条件)。出力 JSON の `cfg_dispatch_slots`・`cfg_call_resolution`・`after_cfg_*` が本付録の値。

## 0. 結論

- rip_data の参照先 2 slot (`0x1813a1d38` / `0x1813a1d40`) は、load config の `GuardCFDispatchFunctionPointer` / `GuardXFGDispatchFunctionPointer` と**一致**した。`call [slot]` は CFG/XFG の dispatch で、呼び先は**直前に rax に入った値**で決まる (参照先の thunk は `jmp rax`)。前回 (§4 の結論) の「thunk の先は実行時に決まる」は、この rax の出所を追えば確定できる対象である。
- 対照 Gain (all) の rip_data 呼び出し 54 件のうち **40 件**は `mov rax, qword ptr [R+d]` 直後の呼び出し。これは `call [R+d]` と同じ呼び先 (vtable slot `d/8`) で、既存の vtable 規則で候補が決まる。`after_cfg` は `after` と**差 0** (1,995 関数 / 731,396 B)。slot 0/1/2/3/8 は閉包内の既存 vtable 呼び出しで既に使われ、新規の関数は加わらない (§3)。
- 残り **14 件** (対照 Gain・all) は rax の出所が未確定: 呼び出し戻り値 8・reg コピー 2・`ror rax, cl` 2・分岐越え 1・indexed 1。callee の戻り値の追跡が要るため子 issue **#3363 ([KH-55])** に移した。
- 確定した slot 側の候補は 0 件 (変わらず)。before / after / after_rip は全 8 条件で前回 REPORT_KH19.md の値と一致した (退行なし)。

## 1. 規則 (`scripts/vtable_closure.py`・#849 の追加分)

1. `cfg_dispatch_slots`: load config の `GuardCFDispatchFunctionPointer` / `GuardXFGDispatchFunctionPointer` の VA を集める (pefile)。
2. `is_cfg_call`: `call [rip+X]` で X が `cfg_dispatch_slots` に入る site を CFG 経由とする。
3. `rax_source`: 同一関数内で CFG call の直前から逆向きに、rax (eax/ax/al/ah を含む) を書く最後の命令を探す。
   - `mov rax, qword ptr [R+d]` → `vtable_cfg` (arg = d)。呼び先は `[R+d]` で `call [R+d]` と同じ。
   - `lea rax, [rip+F]` で F が関数先頭 → `lea_fn` (exact)。0 件だった。
   - それ以外は `rip_load` / `reg_copy` / `other_write:<mn>` (ror・mov 等)。
   - 間に `call` があれば `call_ret` (戻り値。未追跡)。分岐先 (label) を跨げば `label_barrier` (経路が一意でない)。
4. `after_cfg` = 不動点。`vtable_cfg` は vtable 規則 (同 ns の slot `d/8`)、`lea_fn` は F を加える。`after` / `after_rip` の計算は変えていない。

## 2. 実測 (測定 commit `aa5897d56`・4 vCPU・各 1 回)

| ns | モード | CFG 経由 call | before 関数 / B | after 関数 / B | after_rip 関数 | after_cfg 関数 / B | vtable_cfg | call_ret | reg_copy | ror | mov 系 (indexed) | label | lea_fn |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Snap Heap (micropass) | nogui | 20 | 311 / 97,327 | 1,531 / 722,713 | 1,531 | 1,531 / 722,713 | 8 | 7 | 1 | 2 | 1 | 1 | 0 |
| Snap Heap (micropass) | all | 54 | 311 / 97,327 | 3,094 / 1,388,293 | 3,094 | 3,094 / 1,388,293 | 40 | 8 | 2 | 2 | 1 | 1 | 0 |
| Multipass (multipass) | nogui | 20 | 321 / 113,050 | 1,802 / 817,610 | 1,802 | 1,802 / 817,610 | 8 | 7 | 1 | 2 | 1 | 1 | 0 |
| Multipass (multipass) | all | 54 | 321 / 113,050 | 3,328 / 1,476,922 | 3,328 | 3,328 / 1,476,922 | 40 | 8 | 2 | 2 | 1 | 1 | 0 |
| Phase Plant (phaseplant) | nogui | 56 | 504 / 228,241 | 3,767 / 1,791,711 | 3,767 | 3,767 / 1,791,711 | 41 | 9 | 2 | 2 | 1 | 1 | 0 |
| Phase Plant (phaseplant) | all | 56 | 504 / 228,241 | 5,582 / 2,768,378 | 5,582 | 5,582 / 2,768,378 | 41 | 9 | 2 | 2 | 1 | 1 | 0 |
| 対照 Gain (gain) | nogui | 8 | 160 / 39,357 | 555 / 178,451 | 555 | 555 / 178,451 | 3 | 2 | 0 | 2 | 0 | 1 | 0 |
| 対照 Gain (gain) | all | 54 | 160 / 39,357 | 1,995 / 731,396 | 1,995 | 1,995 / 731,396 | 40 | 8 | 2 | 2 | 1 | 1 | 0 |

- 各行: CFG 経由 call = vtable_cfg + call_ret + reg_copy + ror + mov 系 + label + lea_fn (行和で一致)。`CFG 経由 call` 列は REPORT_KH19.md §2・§4 の `rip_data` 列と同じ数。
- before / after / after_rip は REPORT_KH19.md §2・§4 の値と全 8 条件で一致。
- 所要: `vtable_closure.py` 1 回 7.3〜8.8 s (`date` の差)。load average は開始時 0.23、終了時 1.18。

## 3. 判定 (#849 の受入)

- 受入 (rip_data の候補): CFG 経由 call のうち `vtable_cfg` 形は vtable 規則で候補が確定し、閉包に加えた結果 `after_cfg` = `after` (差 0)。全モードで新規の関数は 0 件。
  理由: slot 0/1/2/3/8 (`vtable_cfg` の `d/8`) は閉包内の既存 vtable 呼び出しで既に使われている。確認 (対照 Gain・all の閉包内 vtable 呼び出しの slot 別件数): k=0 115・k=1 662・k=2 670・k=3 29・k=8 7。
  この確認は一回限りの probe (未コミット) で行い、閉包 1,995 関数は本 commit の `after` と一致した。
- 未確定件数の種別別 (受入): 対照 Gain・all は 14 件 (call_ret 8・reg_copy 2・ror 2・label 1・mov 系 1)。他の ns・モードは §2 の列の値から同様に読める。残りは子 #3363 (KH-55)。

## 4. 検証 (コード差分)

- `git diff aa5897d56 HEAD -- tools/targets/kilohearts/scripts` の出力は空 (0 行)。本付録と REPORT_KH19.md のみが後続 commit の変更。

## 5. 制限

- 閉包の over-approximation (slot 番号一致) は変えていない。`vtable_cfg` の候補も同じ規則なので、型による絞り込みは #848 の結論 (呼び出し鎖の伝播が要る) のまま。
- `rax_source` は同一関数内の直線区間のみ。分岐越えは打ち切る (`label_barrier`)。callee の戻り値 (`call_ret`) は追わない。
- `lea_fn` (exact) は 0 件。XFG の hash (`movabs r10`) は呼び先の判定に使っていない。
- 素材は `plugins-kilohearts` のみ (fl-win64 は不要)。lift / build は行っていない (#850・#3063 の範囲)。
