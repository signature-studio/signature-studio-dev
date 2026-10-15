# KH-18 (#781): Carve EQ (ksge) の IAT 19 件の扱い (実測)

- 親: #61 (KH-6) / 元 issue: #781 (分割 a)。測定 commit = `fcf3a630` (`snapins/scripts/carve_iat_census.py` を追加した commit。以後この commit の本体は変えていない)。測定起点 = origin/main `8303a813`。
- 対象: `GraphicEqDsp` (graphiceq namespace, id ksge)。本付録はその IAT 呼出 site 19 件の扱いだけを書く。closure の数は §0 を見る。
- 再現手順 (`tools/targets/kilohearts/` で実行。素材は `plugins-kilohearts` (`KH_SRC` に置いた installer の zip)。Windows 側だけ展開する):

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

- closure の数 (`closures.py` の出力。`REPORT.md` §4 の Carve EQ 行と一致):
  - **unique 142 関数** = `unique_funcs` = census の対象 `sets['graphiceq']` (infra 除外後)。census 実行の出力 `closure funcs=142` と一致する。
  - **固有 127 関数** = `own_funcs` (他 snap-in から到達されない関数のみ。`own_bytes` 50,109 B と同じ集合)。`REPORT_KH19.md` の「REPORT §4 の『固有』値は `own_bytes`」と同じ定義。127 は commit `3b4d9b71` で入った値で、`closures.py`・`callgraph.py`・`rtti_walk.py` は `3b4d9b71` 以降変わっていない (`git diff 3b4d9b71 origin/main -- tools/targets/kilohearts/scripts/{closures,callgraph,rtti_walk}.py` は 0 行)。同じ版の binary を前提に有効。
  - 旧版の「REPORT §5 と一致」は誤りで取り下げた。REPORT §5 には関数数の記載が無い。
- IAT 19 site の判定: **stub 0 件 / 実装 0 件 / fail-fast 19 件**。#12〜#14 (SRWLock の取得・解放 2 本と WakeAllConditionVariable 1 本。`0xf877fc` 内の IAT 呼出はこの 3 件だけ) は、規則 3 の前提 (b) を確認できないため stub にせず fail-fast (既定) とした。GetLastError (#18) は戻り値で分岐するため規則 2 で fail-fast (前版は stub)。
- **IAT 19 件のどの site も、process 直接 closure (145 関数) の unique 側 25 関数には含まれない** (その 25 関数の IAT 呼出は 0 件)。19 site はすべて slot 7 (`0x37c980`) か slot 13 (`0x37cbe0`) から到達する (slot 7 が 13 site、slot 13 が 6 site)。
- process 直接 closure の残り **120 関数**は共通基盤 (infra・unique 集合の外)。その IAT 件数は**未集計** (§3・§4)。
- 現行 pipeline (`snapins/lift/gen_stubs_sigs.py` の `IMP_SHIM`) は、名前付き import を `IMP_SHIM` にあれば定数返却、無ければ `abort()` にする。現行の扱いは GetLastError が `rax = 0` (既存の IMP_SHIM 値。判定 fail-fast と食い違う)、残り 18 件は `abort()`。判定の反映と #18 の扱いは子 issue (bit-exact 化) の仕事で、本 PR はコードを変えていない。
- 未解決 (起票先は PR 本文の表): 間接 call の先が追跡されていない (§3)、slot 7・13 が native 実行で呼ばれるかが未検証 (呼ばれるなら fail-fast のままでは trap する)、共通基盤側 IAT 未集計、#12〜#14 の lock/cv の同一性未確認。

## 1. 判定の規則

判定は次の順に当たった規則で決める: **2 → 4 → 3 → 5**。規則 1 は判定を変えず記録に使う。規則 6 は対の相手の判定に従う。

1. **process 非到達**: 直接辺で process 経路 (slot 14) から到達しない。bit-exact の対象外の記録。ただし到達経路が無いことだけで決めず、下の 2〜5 を全 site に適用する。
2. **戻り値が分岐に使われる** (成功/失敗・長さ・判定値で `je`/`jne`/`cmp`) → **fail-fast** (stub を選ぶと失敗分岐へ silently 入る)。規則 5 より優先する: IMP_SHIM の値は同じ import の既定値で、この site の分岐の正しさを保証しない。
3. **協調相手の無い同期 primitive** (SRWLock の取得/解放、WakeAllConditionVariable) → **stub (no-op)**。ただし次の 2 条件を両方満たすときだけ: (a) 呼出を含む関数に SleepConditionVariableSRW / WaitForSingleObjectEx が無い、(b) 同じ lock/cv を待つ site が closure 内に無い。(b) は lock/cv の RIP 相対アドレスの一致で確かめる。(b) を確認できない site は stub にせず fail-fast とする (既定。§4)。関数本体の副作用 (TLS 書込 `gs:[0x58]`) は残す。
4. **待機・協調の一部** → **fail-fast**: SleepConditionVariableSRW / WaitForSingleObjectEx、ReleaseSemaphore、および待機 site と同じ lock/cv を取得・解放する site (待機ループ内の取得/解放を含む)。(b) を満たさないので規則 3 より優先する。
5. 既存 `IMP_SHIM` に同じ import がある場合は、その値を流用する。ただし規則 2・4・3 に当たらない site に限る (規則 2 の GetLastError は流用しない)。
6. 対になる site (確保と解放、同じ関数内の取得と解放) は、規則 2〜5 で決まった相手と同じ判定にそろえる (LocalFree は #1 の確保と対で fail-fast)。

## 2. IAT 19 件の表 (実測)

経路は `carve_iat_census.py` が BFS で求めた最短呼出経路 (実行順ではない)。`slot7`・`slot13` は `GraphicEqDsp` の vtable slot 7・13 (VA `0x37c980`・`0x37cbe0`)。

| # | 関数 | 呼出 site | import | 最短呼出経路 (root → 関数) | 引数・戻り値の実測 | 判定 | 現行 (IMP_SHIM / 既定) |
|--:|---|---|---|---|---|---|---|
| 1 | `0x49450` | `0x1800494a8` | FormatMessageW | slot7 → `0x38b7b0` → `0x38a8f0` → `0x38b9b0` → `0x1faac0` → `0x4a5b0` → `0x4aa30` → `0x49450` | dwFlags=`0x1300` (ALLOCATE_BUFFER\|FROM_SYSTEM\|IGNORE_INSERTS)、MessageId=`edi`。戻り値 eax を `test`→`je` で分岐 | fail-fast (規則 2) | abort |
| 2 | `0x49450` | `0x1800494e1` | WideCharToMultiByte | 同上 | 戻り値 (長さ) を `ebx` に保存して `test`→`je` | fail-fast (規則 2) | abort |
| 3 | `0x49450` | `0x18004971f` | WideCharToMultiByte | 同上 | 戻り値 (長さ) を `lea ecx,[rax-1]` で使用 | fail-fast (規則 2) | abort |
| 4 | `0x49450` | `0x18004998c` | LocalFree | 同上 | 戻り値未使用 (1 の確保バッファを解放) | fail-fast (規則 6・#1 と対) | abort |
| 5 | `0x38a8f0` | `0x18038a9b0` | WaitForSingleObjectEx | slot7 → `0x38b7b0` → `0x38a8f0` | handle=`[rcx+0x18]`、timeout=`0xffffffff` (INFINITE)、alertable=0。戻り値未使用 | fail-fast (規則 4) | abort |
| 6 | `0x38b060` | `0x18038b0fc` | ReleaseSemaphore | slot7 → `0x38b7b0` → `0x38a8f0` → `0x38b060` | handle=`[r14+0x10]`、count=1、prev=NULL。戻り値未使用 | fail-fast (規則 4) | abort |
| 7 | `0x38b060` | `0x18038b12f` | ReleaseSemaphore | 同上 | handle=`[r14+8]`、count=ビット演算で算出 | fail-fast (規則 4) | abort |
| 8 | `0x38b060` | `0x18038b1cc` | ReleaseSemaphore | 同上 | handle=`[rdi+0x10]`、count=1 | fail-fast (規則 4) | abort |
| 9 | `0x38b060` | `0x18038b1ff` | ReleaseSemaphore | 同上 | handle=`[rdi+8]`、count=算出 | fail-fast (規則 4) | abort |
| 10 | `0x38bbb0` | `0x18038bc3b` | ReleaseSemaphore | slot7 → `0x38b7b0` → `0x38a8f0` → `0x38bbb0` | handle=`[rax+0x10]` (rax=`[rcx+0x10]`)、count=1 | fail-fast (規則 4) | abort |
| 11 | `0x38bbb0` | `0x18038bc92` | ReleaseSemaphore (tail jmp) | 同上 | count=`edi` (算出) | fail-fast (規則 4) | abort |
| 12 | `0xf877fc` | `0x180f8780c` | AcquireSRWLockExclusive | slot13 → `0xf877fc` | lock は RIP 相対の固定アドレス (#16 の lock と同一かは未確認)。戻り値未使用 | **fail-fast** (既定。規則 3 の (b) 未確認のため stub にしない・§4) | abort |
| 13 | `0xf877fc` | `0x180f8784c` | ReleaseSRWLockExclusive | slot13 → `0xf877fc` | 同上。戻り値未使用 | **fail-fast** (既定。規則 3 の (b) 未確認のため stub にしない・§4) | abort |
| 14 | `0xf877fc` | `0x180f8785e` | WakeAllConditionVariable (tail jmp) | slot13 → `0xf877fc` | この関数内に SleepConditionVariableSRW は無い。cv が #16 の cv と同一かは未確認 | **fail-fast** (既定。規則 3 の (b) 未確認のため stub にしない・§4) | abort |
| 15 | `0xf87868` | `0x180f87878` | AcquireSRWLockExclusive | slot13 → `0xf87868` | lock の状態を `cmp`/`or` で遷移 (`-1` = 排他)。#16 の SleepConditionVariableSRW と同じ待機ループ内 | fail-fast (規則 4) | abort |
| 16 | `0xf87868` | `0x180f8789d` | SleepConditionVariableSRW | 同上 | cv+lock、timeout=`0xffffffff` (INFINITE)。結果は分岐せず状態再判定の loop | fail-fast (規則 4) | abort |
| 17 | `0xf87868` | `0x180f878d9` | ReleaseSRWLockExclusive (tail jmp) | 同上 | 戻り値未使用 | fail-fast (規則 4、15・16 と対) | abort |
| 18 | `0xfd7518` | `0x180fd7676` | GetLastError | slot7 → … → `0x49450` → `0x493f0` → `0xfc10d4` → `0xfbf86c` → `0xfc032c` → `0xfd7518` | 戻り値 eax を `cmp eax,0x7a` (ERROR_INSUFFICIENT_BUFFER) で分岐 | **fail-fast** (規則 2。規則 5 の既存値 `rax = 0` は流用しない) | `rax = 0` (既存) |
| 19 | `0xfdfd00` | `0x180fdfda6` | WideCharToMultiByte (tail jmp) | … → `0xfd7518` → `0xfdfd00` | 戻り値は呼出元 `0xfd7518` へ素通し | fail-fast (規則 2) | abort |

- 判定の集計: stub 0 / fail-fast 19 (#1〜#11・#15〜#19 は規則 2・4・6 による。#12〜#14 は規則 3 の (b) 未確認による既定) / 実装 0。
- #18 と #19 は `0x49450` (#1〜#4 の文言生成) を経由する経路にある。`0x49450` 内で #1 (fail-fast) が先に呼ばれるかは本測定では確かめていない。#18 の 0 が正しい側かも、native 実行が無いため確かめていない。確かめるまで #18 は stub にしない。

## 3. process 経路と間接 call (下限見積の範囲)

- process root (slot 14 = `0x37d210`、`GraphicEqDsp` の vtable 20 slot 中の 14 番目。Gain の process `0x1804b0380` と同じ slot 番号) の直接 closure は **145 関数**。そのうち unique 集合 (infra 除外後) に入るのは 25 関数で、IAT 呼出は **0 件**。
- 残り **120 関数**は共通基盤 (infra)。`process 直接 closure ⊂ GraphicEqDsp の reach` で、unique 集合の外 = infra なので、`closures.py` の infra 188 関数の部分集合になる。REPORT §5 の『共通基盤 188 関数の合計 51 call』は 188 関数全体の数で、この 120 関数だけの内訳ではない。120 関数の IAT 件数は `callgraph.pkl` の `res[f]['iat']` を 145 関数で合計すれば出る (`plugins-kilohearts` 素材が要る。本 run では未実施)。
- 直接辺 closure は間接 call を辿らない。process 直接 closure の中で間接 call を含むのは 3 関数 (計 10 site): `0x1384040` (memmove shim・4 site)・`0x13846e0` (memset shim・4 site)・`0xfe2508` (CRT atexit runner・2 site)。shim 2 つは IAT を使わない。`0xfe2508` の間接先は未追跡。`IAT 0` は直接辺の下限であり、間接先の IAT は未検証。
- slot 7 (`0x37c980`・593 B・直接 closure 234 関数) と slot 13 (`0x37cbe0`・1,572 B・直接 closure 102 関数) は、共通基盤 infra を除いた unique 集合で IAT 19 件を持つ 2 本の経路。slot 7 はパラメータ設定系の名前 (Matrix の `set7` と同じ slot 番号) と推定するが、引数形は未確定。slot 13 は `prepare`/`reset` 系と推定 (未確定)。**両者が native harness の scenario で呼ばれるかは未検証**。呼ばれる場合、この PR のまま wasm 化すると fail-fast の trap になる。

## 4. 未解決 (起票先は PR 本文の表)

- 間接 call (process 経路の `0xfe2508` 等・unique 集合の間接 call 8 site) の追跡 → 子 issue (bit-exact 化) で `[icall]` 追跡を行う。
- 共通基盤側 (process 直接 closure の 120 関数) の IAT 件数は未集計 (§3)。
- #12〜#14 の lock/cv が #16 の SleepConditionVariableSRW と同一かは未確認 (規則 3 の前提 (b))。確認するには `plugins-kilohearts` 素材で census を再実行し、#12〜#14 と #16 の lock/cv の RIP 相対アドレスを比べる必要がある。(b) を確認できた site だけ stub にできる。同一なら規則 4 により fail-fast のまま。
- slot 7・13 の呼出順 (scenario で set/prepare が呼ばれるか) の確定 → 子 issue。呼ばれるなら slot 7 の協調を単一スレッドの同期実行に置換する (実装判定の追加) か、harness の呼出を避ける設計を決める。
- 判定 (fail-fast 19 件) と現行 `IMP_SHIM` の整合 (18 件は abort で一致。GetLastError の既存 `rax = 0` を fail-fast に合わせる件)、反映で既存 14 本の出力が変わらないことの確認 → 子 issue。
- `carve_iat_census.py` の `PROCESS_ROOT = 0x37d210` は固定 VA。vtable JSON から GraphicEqDsp の slot 14 を引く照合は未実装 (入力が変わると古い値を黙って使う)。本 run はスクリプトを再実行できない (素材なし) ため未変更。
