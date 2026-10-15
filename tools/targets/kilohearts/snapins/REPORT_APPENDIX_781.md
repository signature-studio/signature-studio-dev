# KH-18 (#781): Carve EQ (ksge) の IAT 19 件の扱い (実測)

- 親: #61 (KH-6) / 元 issue: #781 (分割 a)。測定 commit = `fcf3a630` (`snapins/scripts/carve_iat_census.py` を追加した commit。以後この commit の本体は変えていない)。測定起点 = origin/main `8303a813`。
- 対象: `GraphicEqDsp` (graphiceq namespace, id ksge)。closure の数値は `REPORT.md` §4・§5 が正本。本付録はその IAT 呼出 site 19 件の扱いだけを書く。
- 1 コマンド再現 (`tools/targets/kilohearts/` で実行。素材は `KH_SRC` に置いた installer の zip を使う。Windows 側だけ展開する):

```sh
mkdir -p work/win work/blobs work/winpkg
unzip -q -o "$KH_SRC/Kilohearts Offline Installer.zip" -d work/win
unzip -q -o work/win/payload.dat index.json 'windows.zip/*' -d work/blobs
W=$(ls work/blobs/windows.zip/* | grep -v '/$' | head -1); unzip -q -o "$W" -d work/winpkg
python3 scripts/rtti_walk.py work/winpkg/HeartCore.core_64 work/rtti_vtables.json
python3 scripts/callgraph.py work/winpkg/HeartCore.core_64 work/rtti_vtables.json work/callgraph.pkl 4
python3 scripts/closures.py work/callgraph.pkl work/rtti_vtables.json work/closures.json
python3 snapins/scripts/carve_iat_census.py work/winpkg/HeartCore.core_64 work/callgraph.pkl work/closures_sets.pkl work/rtti_vtables.json work/carve_iat_sites.json
```

- 実測時間 (commit `fcf3a630` の run・load average 1.14 / 4 CPU): `rtti_walk.py` 1.8 s、`callgraph.py` (4 proc・120,856 関数 sweep) 6.9 s、`closures.py` 0.2 s、`carve_iat_census.py` 0.4 s。

## 0. 結論

- IAT 19 site の判定: **stub 4 件 / 実装 0 件 / fail-fast 15 件**。stub は単一スレッドで競合の起きない SRWLock 2 本と WakeAllConditionVariable 1 本、既存 shim にある GetLastError の 4 件。残り 15 件は fail-fast (到達したら trap)。
- **process 経路 (vtable slot 14 = VA `0x37d210`) の直接 closure 145 関数には IAT が 0 件**。19 site はすべて slot 7 (`0x37c980`) か slot 13 (`0x37cbe0`) から到達する (slot 7 が 13 site、slot 13 が 6 site)。
- 現行 pipeline (`snapins/lift/gen_stubs_sigs.py` の `IMP_SHIM`) は、名前付き import を `IMP_SHIM` にあれば定数返却、無ければ `abort()` にする。現行の扱いは GetLastError が `rax = 0` (既存)、残り 18 件は `abort()`。stub 4 件を反映するのは子 issue (bit-exact 化) の仕事で、本 PR はコードを変えていない。
- 未解決 (起票先は PR 本文の表): 間接 call の先が追跡されていない (下記 §3)、slot 7・13 が native 実行で呼ばれるかが未検証 (呼ばれるなら fail-fast のままでは trap する)。

## 1. 判定の規則

1. **process 非到達**: 直接辺で process 経路 (slot 14) から到達しない。bit-exact の対象外。ただし判定は到達経路が無いことだけで決めず、下の 2・3 を全 site に適用する。
2. **戻り値が分岐に使われる** (成功/失敗・長さ・判定値で `je`/`jne`/`cmp`) → stub を選ぶと失敗分岐へ silently 入るため **fail-fast**。
3. **単一スレッドで協調相手が存在しない同期 primitive** (SRWLock の取得/解放、待機者 0 の WakeAll) → **stub (no-op)**。ただし関数本体の副作用 (TLS 書込 `gs:[0x58]`) は残す。
4. **待機・セマフォ協調** (`WaitForSingleObjectEx` / `SleepConditionVariableSRW` / 対になる `ReleaseSemaphore`) → 単一スレッドでは相手が無く永久待ち・状態不整合になるため **fail-fast**。
5. 既存 `IMP_SHIM` に同じ import がある場合は、その値を流用する (GetLastError のみ該当)。

## 2. IAT 19 件の表 (実測)

経路は `carve_iat_census.py` が BFS で求めた最短呼出経路 (実行順ではない)。`slot7`・`slot13` は `GraphicEqDsp` の vtable slot 7・13 (VA `0x37c980`・`0x37cbe0`)。

| # | 関数 | 呼出 site | import | 最短呼出経路 (root → 関数) | 引数・戻り値の実測 | 判定 | 現行 (IMP_SHIM / 既定) |
|--:|---|---|---|---|---|---|---|
| 1 | `0x49450` | `0x1800494a8` | FormatMessageW | slot7 → `0x38b7b0` → `0x38a8f0` → `0x38b9b0` → `0x1faac0` → `0x4a5b0` → `0x4aa30` → `0x49450` | dwFlags=`0x1300` (ALLOCATE_BUFFER\|FROM_SYSTEM\|IGNORE_INSERTS)、MessageId=`edi`。戻り値 eax を `test`→`je` で分岐 | fail-fast (規則 2) | abort |
| 2 | `0x49450` | `0x1800494e1` | WideCharToMultiByte | 同上 | 戻り値 (長さ) を `ebx` に保存して `test`→`je` | fail-fast (規則 2) | abort |
| 3 | `0x49450` | `0x18004971f` | WideCharToMultiByte | 同上 | 戻り値 (長さ) を `lea ecx,[rax-1]` で使用 | fail-fast (規則 2) | abort |
| 4 | `0x49450` | `0x18004998c` | LocalFree | 同上 | 戻り値未使用 (1 の確保バッファを解放) | fail-fast (1 と対) | abort |
| 5 | `0x38a8f0` | `0x18038a9b0` | WaitForSingleObjectEx | slot7 → `0x38b7b0` → `0x38a8f0` | handle=`[rcx+0x18]`、timeout=`0xffffffff` (INFINITE)、alertable=0。戻り値未使用 | fail-fast (規則 4) | abort |
| 6 | `0x38b060` | `0x18038b0fc` | ReleaseSemaphore | slot7 → `0x38b7b0` → `0x38a8f0` → `0x38b060` | handle=`[r14+0x10]`、count=1、prev=NULL。戻り値未使用 | fail-fast (規則 4) | abort |
| 7 | `0x38b060` | `0x18038b12f` | ReleaseSemaphore | 同上 | handle=`[r14+8]`、count=ビット演算で算出 | fail-fast (規則 4) | abort |
| 8 | `0x38b060` | `0x18038b1cc` | ReleaseSemaphore | 同上 | handle=`[rdi+0x10]`、count=1 | fail-fast (規則 4) | abort |
| 9 | `0x38b060` | `0x18038b1ff` | ReleaseSemaphore | 同上 | handle=`[rdi+8]`、count=算出 | fail-fast (規則 4) | abort |
| 10 | `0x38bbb0` | `0x18038bc3b` | ReleaseSemaphore | slot7 → `0x38b7b0` → `0x38a8f0` → `0x38bbb0` | handle=`[rax+0x10]` (rax=`[rcx+0x10]`)、count=1 | fail-fast (規則 4) | abort |
| 11 | `0x38bbb0` | `0x18038bc92` | ReleaseSemaphore (tail jmp) | 同上 | count=`edi` (算出) | fail-fast (規則 4) | abort |
| 12 | `0xf877fc` | `0x180f8780c` | AcquireSRWLockExclusive | slot13 → `0xf877fc` | lock は RIP 相対の固定アドレス。戻り値未使用 | **stub (no-op)** (規則 3) | abort |
| 13 | `0xf877fc` | `0x180f8784c` | ReleaseSRWLockExclusive | slot13 → `0xf877fc` | 同上。戻り値未使用 | **stub (no-op)** (規則 3) | abort |
| 14 | `0xf877fc` | `0x180f8785e` | WakeAllConditionVariable (tail jmp) | slot13 → `0xf877fc` | 待機者は同 process に存在しない (16 は fail-fast) | **stub (no-op)** (規則 3) | abort |
| 15 | `0xf87868` | `0x180f87878` | AcquireSRWLockExclusive | slot13 → `0xf87868` | lock の状態を `cmp`/`or` で遷移 (`-1` = 排他) | fail-fast (規則 4) | abort |
| 16 | `0xf87868` | `0x180f8789d` | SleepConditionVariableSRW | 同上 | cv+lock、timeout=`0xffffffff` (INFINITE)。結果は分岐せず状態再判定の loop | fail-fast (規則 4) | abort |
| 17 | `0xf87868` | `0x180f878d9` | ReleaseSRWLockExclusive (tail jmp) | 同上 | 戻り値未使用 | fail-fast (規則 4、15・16 と対) | abort |
| 18 | `0xfd7518` | `0x180fd7676` | GetLastError | slot7 → … → `0x49450` → `0x493f0` → `0xfc10d4` → `0xfbf86c` → `0xfc032c` → `0xfd7518` | 戻り値 eax を `cmp eax,0x7a` (ERROR_INSUFFICIENT_BUFFER) で分岐 | **stub (ret 0)** (規則 5) | `rax = 0` (既存) |
| 19 | `0xfdfd00` | `0x180fdfda6` | WideCharToMultiByte (tail jmp) | … → `0xfd7518` → `0xfdfd00` | 戻り値は呼出元 `0xfd7518` へ素通し | fail-fast (規則 2) | abort |

- 判定の集計: stub 4 (#12・#13・#14・#18) / fail-fast 15 / 実装 0。
- 18 と 19 は `0x49450` (#1〜#4 の文言生成) を経由する経路にある。`0x49450` 内で #1 (fail-fast) が先に呼ばれるかは本測定では確かめていない。確かめるまで #18 の stub は「到達しても判定値 0 を返す」ことだけを主張する。

## 3. process 経路と間接 call (下限見積の範囲)

- process root (slot 14 = `0x37d210`、`GraphicEqDsp` の vtable 20 slot 中の 14 番目。Gain の process `0x1804b0380` と同じ slot 番号) の直接 closure は **145 関数**。そのうち unique 集合 (infra 除外後) に入るのは 25 関数で、IAT 呼出は **0 件**。
- 直接辺 closure は間接 call を辿らない。process 直接 closure の中で間接 call を含むのは 3 関数 (計 10 site): `0x1384040` (memmove shim・4 site)・`0x13846e0` (memset shim・4 site)・`0xfe2508` (CRT atexit runner・2 site)。shim 2 つは IAT を使わない。`0xfe2508` の間接先は未追跡。`IAT 0` は直接辺の下限であり、間接先の IAT は未検証。
- slot 7 (`0x37c980`・593 B・直接 closure 234 関数) と slot 13 (`0x37cbe0`・1,572 B・直接 closure 102 関数) は、共通基盤 infra を除いた unique 集合で IAT 19 件を持つ 2 本の経路。slot 7 はパラメータ設定系の名前 (Matrix の `set7` と同じ slot 番号) と推定するが、引数形は未確定。slot 13 は `prepare`/`reset` 系と推定 (未確定)。**両者が native harness の scenario で呼ばれるかは未検証**。呼ばれる場合、この PR のまま wasm 化すると fail-fast の trap になる。

## 4. 未解決 (起票先は PR 本文の表)

- 間接 call (process 経路の `0xfe2508` 等・unique 集合の間接 call 8 site) の追跡 → 子 issue (bit-exact 化) で `[icall]` 追跡を行う。
- slot 7・13 の呼出順 (scenario で set/prepare が呼ばれるか) の確定 → 子 issue。呼ばれるなら slot 7 の協調を単一スレッドの同期実行に置換する (実装判定の追加) か、harness の呼出を避ける設計を決める。
- 判定 stub 4 件の `IMP_SHIM` への反映と、反映で既存 14 本の出力が変わらないことの確認 → 子 issue。
