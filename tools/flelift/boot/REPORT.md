# tools/flelift/boot — FLE-2: x64c lift による FLEngine boot 連鎖 (DllMain → _InitLib → InitUnits)

## 0. 結論 (先出し)

- **判定: 大幅前進。unit#17 の停止原因を特定し修正。連鎖は unit#39 まで完走**。
  前ラウンドの blocker「unit#17 (0x454090) の `@DynArraySetLength` 旧 block FreeMem invalid pointer」は
  **FastMM の invalid ではなく boot override 側の実装バグ 3 件**だった:
  1. **FreeMem 戻り値の判定逆転** (`fle_ov_freemem`): 実機 `System._FreeMem` 0x409440 は
     `mov ebx,eax / test ebx,ebx / je ok / mov cl,2 / call @Error` — **0 = 成功 / 非 0 = エラー**
     (FastMM 側 0x40801f は `mov eax,-1`)。旧コードは `!ok` で判定し正常 free をエラー扱い。
  2. **guest stack の push/pop 不釣合** (`fle_ov_getmem`/`fle_ov_freemem`): C override が
     `ott_dispatch` 前に独自の偽 retaddr を push して釣合が取れず 1 呼出 8B 沈下。
     呼出元 `pop rbx` が 8B 低い slot を読み `rbx = 0x43000000000000` → OOB (§3-2)。
  3. **`gen_boot.py` のポインタ typedef 誤分割**: `typedef WCHAR* BSTR;` を
     `body='WCHAR* BST'` と誤分割し `BSTR` が `ptr_names` に入らず、
     `SysAllocStringLen` の戻り値型 kind が None → soft stub (常に 0) → nil → raise (§3-3)。
     22 typedef 対象、修正後戻り値型未解決 603 中 0。
- **boot 実測 (plain, closure 2)**: **40 unit dispatch / 39 完走** (前ラウンド 17 dispatch / 16 完走)。
   停止原因は **unlifted 0x527b5b** (VMT slot が指す fn 0x5274c0 の途中)。
   `0x403579/0x403582/0x40358b/0x40fb40/0x40f960/0x527b5b` を boot_roots.json に追加済。
- **survey (942 unit 隔離, closure 2)**: **ok 859 / oob 9 / unlifted 22 / trap 5 / empty 46 / noproc 1**
   = 非 ok 正味 **36** (前ラウンド 88 / baseline 95)。**oob 66→9、halt0 9→0**。
   outcome: equal 793 / native_fault 66 / diff 72 / wasm_trap 7 / both_fault 4。
- **回帰**: `fle_e2e.sh` = **PASS** (spot diff 16/16 bit 一致、D9 mismatch 0)。
   `boot_e2e.sh` = **4 variant 全て link 成功** (nosx は本 round で初)。
   **strict ≡ plain** (soft stub 0)、**nosx は unit 0 で exit** (shimx 必須の定量化)。
- 検証資産: `blkdiag` (System._GetMem/_FreeMem トラッキング + canary)、
   `rt/fle_cpu.c` の `fle_chk` 拡張 (bad guest address + RSP/RBP/regs + stack 探索)。
- `bash tools/flelift/boot/boot_e2e.sh` (1 コマンド) 。`FLE_LIFT_CLOSURE=2 bash ...` で closure 変更可。

## 1. 成果物 (tools/flelift/boot/)

| パス | 役割 |
|---|---|
| `boot_e2e.sh` | 1 コマンド検証: gen → lift (boot entries + override) → data gen → shimx obj → 4 link variant (plain/strict/nosx/chk) → 実行 |
| `build.sh` | **単一 variant 再 build** (診断・反復用。lift 済み C を再利用し fle_boot.c 等の差分だけ link) |
| `gen_boot.py` | entries (+entry 0x1376820 / longjmp 断片 / boot_roots 累積 / VMT harvest)、`.text` 全域データ窓 (#embed 16.4MB)、imp bridge (shimx thunk / soft stub / curated)。**FLE-2: ポインタ typedef 解析を修正** |
| `fle_boot.c` | boot ドライバ: 敷設 + shimx wiring (cbtrans/resolver/LB_BASE=0x10000) + 計数 + `--override` C 実装 (longjmp/GetMem/FreeMem/InitUnits) + curated import。**FLE-2: FreeMem 判定と RSP 釣合を修正** |
| `fle_boot.mjs` | runner: boot 実行 + 分類 + survey (942 隔離, FLE_SURVEY_FROM/TO) + summary/JSONL 出力 |
| `blkdiag` (fle_boot.c 内) | System._GetMem/_FreeMem トラッキング (alloc/free 時系列・16B snapshot canary・二重解放/未追跡/header dump・FastMM dispatch カウント)。`fle_boot_set_blkdiag(int)` / `fle_blkdiag_stat(int)` で外部操作 |
| `boot_roots.json` | 実行時発見 roots **82 本** (累積)。FLE-2 で 0x403579/0x403582/0x40358b (jump table thunk)・0x40fb40・0x40f960・0x527b5b (VMT slot) を追加 |
| `survey_drive.sh` + `merge_survey.py` | survey を 180s セグメント実行 (timeout 再開) → results/survey.json に統合 |
| `gen_verdict.py` | survey 差分 → liftdiff FORMAT v1 JSONL (results/verdict_boot.jsonl) |
| `iterate_roots.sh` / `dbg_u18.mjs` | root 収束ループ / boot 停止点の guest stack 復元 (再ビルド不要) |
| `results/` | boot_summary*.json / survey.json / survey.jsonl / verdict_boot.jsonl |

link 実績 (4 variant 全て): signature mismatch 0 / undefined 0 / duplicate 0。wasm 145.8MB (chk) / 126.1MB (その他) (work/, gitignore)。
**全 import が shimx/curated で応答 (soft stub 発火 0)** — `soft_uniq=0`。

## 2. boot 連鎖 実測 (plain variant, closure 2)

| 項目 | 前ラウンド (f555629) | **FLE-2 (closure 2)** |
|---|---|---|
| unit 進行 | 17 dispatch / 16 完走 | **40 dispatch / 39 完走** (unlifted 0x527b5b) |
| 停止原因 | FreeMem 失敗 → raise (**override バグ**) → 修正後 `rbx=0x43000000000000` OOB (**RSP 不釣合**) → 修正後 `SysAllocStringLen` nil → raise (**typedef バグ**) | unlifted `0x527b5b` (VMT slot = fn 0x5274c0 途中) |
| GetMem / FreeMem | 59 / 1 | **662 / 209** |
| FastMM | 0x407a50/0x407e20/0x408040、VirtualAlloc 1 回 1,310,704B | 同一 |
| longjmp / exit / getproc / soft | 0 / 0 / 4 / 0 | 0 / 0 / 6 / 0 (soft_uniq=0) |

RetDec baseline (m11) は 17 完走 + unit#18 OOB。x64c は **その unit#18 を突破し 39 完走**。
計数位置の注記: x64c の GetMem 計数は `System._GetMem` (0x409410 override)、m11 の 13 は FastMM 実体
(0x407a50) 計数で測定点が異なる (直接比較は非対応)。

## 3. unit#17 停止原因の特定 (本 round の主成果)

### 3-1. FreeMem 戻り値の判定逆転

`System._FreeMem` 0x409440 の実機機械語:

```
0x40944e  call qword ptr [rip + 0xf9c844]   ; = mm table FreeMem (0x407e20)
0x409454  mov  ebx, eax
0x409456  test ebx, ebx
0x409458  je   0x409461                     ; = 成功
0x40945a  mov  cl, 2
0x40945c  call 0x409730                     ; @Error(reInvalidPtr)
```

FastMM 側 (`0x407e20`) は**成功で `xor eax,eax` (0)**、異常で `0x40801f mov eax,0xffffffff` を返す。
旧 `fle_ov_freemem` は `if (!ok)` で `@Error` を呼んでいたため、**1 回目の正常 free で必ず raise**。
blkdiag の `FastMM dispatch: freemem=1` と `free 対象 p=0x11ef0cc0 ... refcnt=0 len=0x33`
(header 正常) から invalid ではないことを確認。

### 3-2. guest stack の push/pop 不釣合 (実測: ST64 宛先トラップ)

`--override` で置き換えた C 実装は `ott_dispatch` 前に偽 retaddr を 1 段 push する:

```c
R[4] -= 8; ST64(R[4], 0x409424ull);
ott_dispatch(t_);        // callee の ret が 1 段 pop
// -> guest の `call` が push した本来の retaddr は消費されない (8B 沈下)
```

lift 産物に `ST64/ST32/ST16/ST8/LD64` のワイルド宛先フックを一時実装 (work/ 内の診断 build) し、
OOB の瞬間の R[RSP]/R[RBP]/regs/stack slot を全出しして実測:

```
[f413060] entry rcx=0x1159a970 ... ret0=0x670061006d0049   (ret0 が UTF-16 文字列!)
[f413060-store] rbx=0x43000000000000 rax=0x11ef72b0 rsp=0x1159a8a0 rbp=0x1159a8a8
```

`rcx` は entry で `0x1159a970` (有効な stack アドレス) だったが store 時点の `rbx` は
`0x43000000000000`。guest の `call 0x409410` (0x412c4b) → `f_412c20` の `pop rbx` が 8B 低い
slot を読んだため。**`R[4] += 8` を dispatch 直後に追加して解決**。

### 3-3. gen_boot.py のポインタ typedef 誤分割 (実測: raise 0xEEDFADE 連鎖)

修正後の連鎖: unit#23 `0x457860` → `0x4149e0` → `0x4130c0` → `imp_SysAllocStringLen` (結果 nil)
→ `f_412d10` → `0x4096d0` → `@Error` → `@RaiseExcept` → RaiseException(0xEEDFADE)。

原因は `parse_shimx_h()` の typedef 正規表現が `typedef WCHAR* BSTR;` を
`body='WCHAR* BST' / names='R'` と分割し `BSTR` が `ptr_names` に入らなかったこと。
対象 22 typedef (`LPSTR/LPCSTR/LPWSTR/LPCWSTR/LPVOID/PVOID/LPDWORD/PLONG/LPBYTE/
LPSECURITY_ATTRIBUTES/LPOVERLAPPED/LPHANDLE/PHKEY/PCRITICAL_SECTION/PSRWLOCK/…/BSTR/PLARGE_INTEGER/LPFILETIME/LPCPINFO`)。
修正後 `noproto` は 0、shimx.h 603 prototype の戻り値型未解決も 0。

### 3-4. lift closure の重要性 (実測: closure 0 vs closure 2)

| closure | 関数数 | unlifted callees | unit 進行 | 停止原因 |
|---|--:|--:|--:|---|
| 0 | 20,479 | 5,807 | 16 | unlifted 0x40fb40 |
| 2 | 29,415 | 1,678 | **40** (39 完走) | unlifted 0x527b5b (fn 0x5274c0 の途中) |

VMT harvest を「.pdata 開始点」から「.text を指す全 word」に広げると root が 6 万超
(= 全域 lift, C が 700MB 超) で非実用的なため、関数途中の VMT スロットは
**boot_roots.json への累積** (実行時に unlifted として発見) で対応する既存方式を維持した。

## 3-5. FLE-2 で追加した診断 (再現)

- **blkdiag** (fle_boot.c): `fle_ov_getmem` / `fle_ov_freemem` の前後に alloc/free 時系列・
  live block 16B canary・block header dump を出力 (既定 ON)。`m._fle_boot_set_blkdiag(0)` で静黙化。
- **`fle_chk` 拡張** (rt/fle_cpu.c): `chk` variant で bad guest address 検出時に
  `RSP / ret / rip / stack[+0..63] / regs / rbp chain` を出して abort。OOB を 1 発で特定できる。
- **`boot/build.sh`**: lift 済み C を再利用して C 差分のみ再 link (診断ループを約 4 分 → 1 分に短縮)。

## 4. survey (942 unit 隔離) — baseline との unit 単位照合

boot 1 回実行後、同一インスタンス上で unit を 1 本ずつ `fle_run` (新 stack) で隔離実行して分類。
baseline = `tools/m11/work/shimx_link/baseline/m11_boot.survey.json`。照合は `gen_verdict.py`。
**closure 2 lift (29,416 関数) で 942/942 完走**。

| 分類 | x64c 前ラウンド (f555629) | **x64c FLE-2 (closure 2)** | baseline (m11 sx 純リンク) |
|---|--:|--:|--:|
| ok | 808 | **859** | 800 |
| oob | 66 | **9** | 50 |
| halt0 (raise 0xEEDFADE) | 9 | 0 | 44 |
| unlifted | 12 | 22 | — |
| trap | — | 5 | — |
| empty (対象外 filler: proc 先が 0) | 46 | 46 | closure外 46 (同一 46 unit) |
| noproc (i=941) | 1 | 1 | 1 |
| abort | 0 | 0 | 1 (unit#115 EnterCriticalSection) |
| **非 ok 合計 (empty/noproc 除く)** | **88** | **36** | **95** |

- **oob が 66 → 9** (§3-2 の guest stack 不釣合修正効果)、**halt0 が 9 → 0** (§3-3 の BSTR typedef 修正)。
- unlifted 22 は closure 外の残り直接 callee (例: i=45 `0x43307e`、i=95 `0x410b00`)。
  trap 5 は lift 側の未モデル (bit 演算のゼロ除算等)。

outcome (`gen_verdict.py`): **equal 793 / native_fault 66 / diff 72 / wasm_trap 7 / both_fault 4**。
前ラウンド (equal 781 / both_fault 47 / native_fault 27 / wasm_trap 19 / diff 68) と比べ **equal +12**。
native_fault 66 は「baseline は fault で x64c は ok」= x64c の勝ち筋。

### 4-1. variant 対照 (strict / nosx / chk、`boot_e2e.sh` が結果を results/boot_summary_*.json に出力)

| variant | link | boot 到達 | 所見 |
|---|---|---|---|
| plain | mismatch 0 / undef 0 / dup 0 | 40 dispatch / 39 完走 (unlifted 0x527b5b) | 本命 |
| strict | 同上 | **plain と同一 (40 / unlifted 0x527b5b)** | soft stub 発火 0 なので差異なし。**shimx への soft 依存は既に 0** という証拠 |
| nosx | 同上 (**FLE-2 で初めて link 成功**) | **unit 0 で exit** (`Runtime error 226 at 0x41D039` → ExitProcess) | shimx を link しないと CRT/序数系が機能せずboot 不可。**shimx 寄与は「boot 成立のために必須」** |
| chk | 同上 | 40 dispatch 相当 (`FLE_CHK` の住所ガードで abort) | 診断用 |

nosx の `exit code=0` は `Halt0` ではなく `0x412a12` の ExitProcess — unit#0 の
序数/CRT 初期化が shimx 依存であるため。**strict と plain が完全一致** = 現状 soft stub 0 の再確認。

## 5. 未解決・限界 (実測ベース)

1. **unlifted 0x527b5b が次の blocker**。`f_41a7b0` の `call [rax+8]` (VMT slot) が指すのが
   **fn 0x5274c0 の途中**。boot_roots.json に追加済だが closure 2 lift でも未到達
   (VMT 経由の dispatch は `ott_dispatch` の table に載らないため)。残り 1,678 unlifted callees と
   22 unlifted survey unit が同種。
2. **closure 0 (既定) では 16 unit、closure 2 で 40 unit**。`boot_e2e.sh` の既定を closure 2 に
   するか検討要 (当面 `FLE_LIFT_CLOSURE=2` で運用)。
3. D12 (Delphi landing pad, 879 site) は未対応 (CAB-227 管轄)。SEH 巻き戻しは raise → JS 例外化で代用中。
   Halt0→longjmp (0x4126f0 override) は lift 関数として実働するが boot では未発火。
4. GetProcAddress = 0 返却 stub (m11 旧挙動の踏襲) のまま — 6 回呼ばれたが unit init は続行した。
5. survey の unit i=283 の状態依存 hang は closure 2 + 39 unit 完走後は解消 (942/942 完走を確認)。
   ただし 1 プロセス通し実行は 10 分超のため、`survey_drive.sh` (セグメント + timeout 再開) を推奨。

## 6. CAB-129/231 (RetDec route 修正) の x64c での要否

**m11 の unit#18 OOB の直接原因 (0x188B record の alloca 縮退) は x64c に構造的に存在しない。**
x64c は `rep stosq` を正しく展開し (tools/flelift REPORT §2, §5.4)、定数折畳み最適化を持たないため
8B alloca への潰れが発生し得ない。したがって CAB-129 / CAB-231 の適用は x64c route では不要。
零定数折畳み (D7) / jump table (D10) / chained .pdata (D11) も x64c 非依存。

## 7. 引継ぎ (CAB-101 / CAB-233 / 次担当)

1. **unlifted 0x527b5b を突破すれば unit 進行がさらに伸びる**。VMT slot が指す関数途中
   (fn 0x5274c0 内) なので、`ott_dispatch` の table に載せるには当該 VA からの
   recursive descend が必要 (x64c の `known` に追加するか boot_roots + closure でカバー)。
2. **`boot_e2e.sh` の既定 closure を 0 → 2 に変更**するのが最優先の運用改善
   (16 unit → 40 unit、survey oob 66 → 9)。`FLE_LIFT_CLOSURE=2` で運用可能。
3. liftdiff 本格採点 (CAB-232/233): `results/verdict_boot.jsonl` の unit row と liftdiff の関数 row は
   `function.va` が同じ PE VA 空間 (恒等写像) — summary 集計にそのまま混在可能 (target 名 `flelift-boot`)。
   今 round の outcome: **equal 793 / native_fault 66 / diff 72 / wasm_trap 7 / both_fault 4**。
4. survey unlifted 22 本 (例: i=45 `0x43307e`、i=95 `0x410b00`) は closure 外の残り直接 callee。
   残り 1,678 unlifted callees を boot_roots に累積すればさらに減る。

## 8. 再現

```sh
FLE_LIFT_CLOSURE=2 bash tools/flelift/boot/boot_e2e.sh   # 全 variant + 実行 (数十分)
bash tools/flelift/boot/boot_e2e.sh --fast               # lift 済なら skip
bash tools/flelift/boot/survey_drive.sh                  # survey 942 (セグメント + 再開)
python3 tools/flelift/boot/merge_survey.py               # survey 統合
python3 tools/flelift/boot/gen_verdict.py                # baseline 突合 → verdict_boot.jsonl
node tools/flelift/boot/dbg_u18.mjs <boot.cjs>           # 停止点の guest stack 復元 (診断)
bash tools/flelift/fle_e2e.sh                            # 親チケットの回帰 (PASS)
```
前提: tools/flelift/fle_lift.sh と同一 (python3 capstone/pefile, emsdk 6.0.12, node)。PE = block00031_PE.bin。
生成物 (wasm 142.9MB / text.bin 16.4MB 等) は work/boot/ (gitignore)。20MB 超 blob は git に入れない。
