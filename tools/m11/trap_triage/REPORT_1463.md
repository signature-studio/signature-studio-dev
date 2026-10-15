# #1463: unit 149 の oob — `412e40` の `0x40` slot 非 0 の出どころ (中間報告)

**判定: 受入条件 1 は未達 (経路未特定)。受入条件 2・3 (修復・n≥3 survey・ネガコン) は未着手。Refs #1463 (Closes しない)。**

親: #1230 (M11-N75) / 前提: PR #1459 (REPORT_1230)。

## 0. 検証環境

- 測定 base: `origin/main` `cb3a89a6`、branch `1463-m11-unit149-oob-412e40` (worktree `ws-1463`)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR` は末尾 `/` 無し)。`work-m11` / `work-liftdiff` は tarball が `tools/...` の接頭辞を持つため、リポジトリ直下に展開する (tools/m11 直下へ展開すると誤配置になる)。
- `m11_gen_ir2.sh`: rc=0, 43.5 s, `ldfix=applied`, `boot_final.ll` 490693 行 (REPORT_1230 と一致)。
- `M11_FIX_652500=0 m11_build.sh`: rc=0 (25 s)。
- 注意: 本 run では `M11_FIX_652500=1` の build と n≥3 survey は未実施。

## 1. ベースライン再現 (OFF)

- `M11_SURVEY_STACK=149 node m11_survey.mjs` (n=1): unit 149 (`0x264260`) は `memory access out of bounds`。最上位 `wasm-function[75]:0x6b52f` (`function_412e40`) ← `[3904]` ← `[3905]` ← `[3983]` ← `[3985]` ← … (REPORT_1230 と一致)。

## 2. 静的解析で得た訂正

- REPORT_1230 §3 は「`6525b0` は slot の中身を書かない (機械語で確認)」としていた。本 run の `disasm_fn.py 6525b0` では、`6525b8` で引数 (`rcx`) を `[rbp+0x28]` に保存し、`6525e2` と `65260a` で `call 0x4133f0` に渡している。`6525b0` は `&slot` (= `rcx`) を callee へ転送する。**「書かない」は未確認で、`4133f0` が書く可能性が残る。** この点は REPORT_1230 の結論を訂正する。
- `653660` 内で `[rbp+0x40]` へ直接 store するのは `65367b` の 0 初期化のみ (再確認)。`653914` → `call 0x6525b0` → `653918` の経路で `&slot` を渡す。

## 3. 入口値の採取 (`412e40`, probe_entry.sh, n=1)

- `trap_triage/probe_entry.sh p412 412e40` (rc=0)。unit 149 の `412e40` 入口は 5 回。`[a1]` が非 0 の入口は `a=10a9f4a8` (`edx=2`) で `[a1]=10bbdb00`。直後の `a=10a9f958` (`edx=2`) は `[a1]=0`。
- **未解決の点**: `[a1]=10bbdb00` (非 0) が、このまま oob (`[%1-8]` の読み) に直結するかは未確定。`10bbdb00` は wasm のメモリ境界近傍にあり、`[%1-8]` の読みが境界外になる可能性がある。REPORT_1230 の「slot の中身が非 0 になる」前提は、この採取で確認し直す必要がある。
- `PROBE_WATCH` による書込元特定は未成立: `PROBE_WATCH` は link 時 VA の `lva:off` 形式を要求するが、本 run では実行時アドレスを渡して無効だった (結果は無効として扱う)。

## 4. 未達の受入条件と起票先

| 受入条件 | 状態 | 起票先 |
|---|---|---|
| 1. `0x40` slot 非 0 の store 経路の特定 (`&slot` を受ける callee 内部、wasm 入口 `%1` 採取を含む) | 未達。`6525b0` → `4133f0` の転送を確認。入口採取は n=1 のみ。`[a1]` 非 0 と oob の関係が未確定 | #1463 (続き) |
| 2. 修復と unit 149 の n≥3 survey (min–max) | 未着手 | #1463 (続き) |
| 3. ネガコン (修復を外すと oob 復帰) | 未着手 | #1463 (続き) |

次の手順: (a) `[a1]=10bbdb00` が wasm メモリ境界内か (メモリサイズと突き合わせる)、(b) `4133f0` 内で `&slot` への store を watch する (書込元の VA を link 時 VA で指定)、(c) 修復後に n≥3 survey。

## 5. 再着手 (2026-10-14 run) の結果

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` (`extracted/` と exe)、`work-m11` / `work-liftdiff` を worktree 直下に展開。`m11_gen_ir2.sh` rc=0 (`boot_final.ll` 490733 行、前回 490693 行と差。未確認)。`M11_FIX_652500=0 m11_build.sh` rc=0 (wasm 6,029,036 B)。
- (a) 解決: wasm 初期メモリは `INITMEM=0x12000000` (`m11_build.sh`)。入口値 `[a1]=10bbdb00` は `< 0x12000000` で、`[a1]-8=10bbdaf8` は初期メモリ内。よって**入口時点の `[a1]` 値だけでは `[%1-8]` は境界外にならない**。oob を起こす値はトラップ直前 (入口後) に書かれたもの。REPORT §3 の「境界近傍」は誤りで、境界内と訂正する。
- (b) 不成立 (既存ツールの不具合): `probe_entry.sh p412 412e40 149` は `[pe]` 行 0 件、終了 1。原因は `m11_build.sh` 157 行 `cc work/boot_final3.ll work/obj/boot.o` が毎回走り、`probe_entry.sh` が置いた probe 版 `boot.o` (`m11_pe` 入り) を非 probe 版で上書きするため。`boot.o` / `boot_final3.ll` に `m11_pe` が 0 件であることを確認。`PROBE_WATCH` の書込元追跡も同じ経路のため未成立。
- 修正は `m11_build.sh` の共有ビルドの変更になるため本 issue の範囲外。子 issue に分割する (下記)。
- 受入条件 2 (修復・n≥3 survey)・3 (ネガコン): 未着手 (受入条件 1 の結論に依存)。

起票先: 受入条件 1 (書込元特定) は #1463 続き。probe 基盤の修復は子 issue (下記)。

## 6. 再々着手 (2026-10-14 run) の結果: probe 経路の修復と trap 位置の訂正

- 測定 commit: `97647e7c` (probe 経路の修復)。素材: `fl-win64` を `$RUNNER_TEMP/fl-win64`、`work-m11` / `work-liftdiff` を worktree 直下に展開。`m11_gen_ir2.sh` rc=0 (51 s, `boot_final.ll` 490733 行)。
- 修復 (#1756): `m11_build.sh` の `boot.o` 再コンパイルを `M11_KEEP_BOOT_O=1` で止める (既定 0 は従来どおり)。`probe_entry.sh` は `M11_KEEP_BOOT_O=1` で build する。
- 実測 (n=1, `SV_ONLY=149`):
  - `probe_entry.sh p407 407a50 149`: rc=0, `[pe] 407a50` 1 行 (probe.o が link された)。`probe_entry.sh p412 412e40 149`: `[pe] 412e40` 0 行 (下記の理由で入らない)。
  - probe 無しのベースライン (`m11_build.sh` 既定): unit 149 は oob。最上位 frame は `function_407a50__lifted` ← `407a50` ← `409410` ← `412c20` ← `414ad0` ← `414bb0` ← `652500`。
- **訂正**: §5 までの「oob の最上位 frame は `412e40`」は、本 run の build では成立しない。最上位は `407a50` (ベースラインと probe 版で一致)。`412e40` は trap 時のスタックに無い。§1〜§5 の `412e40` 前提は、この build では再検証が必要。
- 未解決 (#1463 続き): 受入条件 1 (`0x40` slot 非 0 の書込元) は、まず trap 位置 (`407a50`) の `[a1]` 経路を特定してから進める。受入条件 2・3 は未着手。

## 7. 再々々着手 (2026-10-14 run, 5 回目): trap 命令の特定

- 測定 base: `origin/main` `82c44c61`、worktree `ws-1463b`。素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR` は末尾 `/` 無し)、`work-m11` / `work-liftdiff` を worktree 直下に展開。`m11_gen_ir2.sh` rc=0 (50.7 s, `boot_final.ll` 490733 行)。`M11_FIX_652500=0 m11_build.sh` rc=0 (24.4 s)。
- ベースライン (n=1, `SV_ONLY=149`): `oob`。最上位 frame `function_407a50__lifted` ← `407a50` ← `409410` ← `412c20` ← `414ad0` ← `414bb0` ← `652500` (§6 と一致)。
- `probe_entry.sh p407 407a50 149`: rc=0、`[pe] 407a50 a=16 0 0 0 | [a1]=dead [a1+8]=dead [[a1+8]+8]=dead [[a1+8]+0x10]=dead` 1 行。入口の `[a1]` は `0xdead` で、境界内の値。
- trap の wasm 位置 (`SV_RAW=1`, n=1): 最上位 `wasm-function[1874]:0x13ce55`。`oob_insn.py` で復号すると `i64.load offset=0` (アドレス = `local90 - 8`、`local90` は直前の `i64.load` の結果)。
- x86 対応: `407aae`〜`407ab2` の `and rcx, qword ptr [rax - 8]`。`rax` は `407a97` の `mov rax, [rdx+0x18]`、`rdx` は `[rbx+8]` で、プール free-list のノード。つまり trap は `0x40` slot への store ではなく、**プール allocator (`407a50`) の free-list 走査中に、`[rdx+0x18]` が `[rax-8]` の読みで境界外になる値を返す**。
- **訂正**: §4 以前の「`0x40` slot 非 0 → oob」の前提は、この trap 経路と一致しない。受入条件 1 の「`&slot` を受ける callee」は、この build では `407a50` の free-list ノードへの書込み (`407aae` 周辺の `mov [rax-8], rdx` / `mov [rdx+0x18], rcx`) に置き換わる可能性が高い。未確定。
- 未確定点: trap 直前に `[rdx+0x18]` へ入る値 (境界外の値) は未採取。入口値 `0xdead` はこの値そのものではない。
- 次の手順: (a) `407aae` の `rax` (= `[rdx+0x18]`) を trap 直前で採取する (`probe_entry.sh` 相当の内側 watch)、(b) その値を書いた store (free-list 更新の `407ab2` / `407ae1` / `407ae4` など) を特定、(c) 修復 → n≥3 survey → ネガコン。

## 8. 再々々々々着手 (2026-10-14 run, 6 回目): free-list 先頭の採取と書込元 watch (未特定)

- 測定 base: `origin/main` `6444b186`、worktree `ws-1463` (ブランチ `1463-unit149-oob`)。素材: `fl-win64` を `$RUNNER_TEMP/fl-win64`、`work-m11` / `work-liftdiff` を worktree 直下に展開。`m11_gen_ir2.sh` rc=0 (51.3 s, 490733 行)。`M11_FIX_652500=0 m11_build.sh` rc=0 (25.3 s)。
- ベースライン (n=1, `SV_ONLY=149`): `oob`、trap は `wasm-function[1874]:0x13ce55` (§7 と一致)。
- `probe_entry.sh p407 407a50 149` (rc=0, 44.5 s): `[pe] 407a50 a=16 0 0 0 | [a1]=dead ...` 1 行。`[chain407] b=0 rbx=fa5108 n=0 m=dead` (実 slot `0xfa5108` の `[+8]` が 0)。
- イメージ確認 (`work/m11_image.bin`): 線形 `0xfa5108` = `0x100000`、`0xfa5110` = `0`、`0xfa5118` = `0`。空リストの自己リンク (`rdx==rbx`) ではなく、`[rbx+8]` が 0 のまま trap 経路 (`[0+0x18]`→`[-8]`) に入る。
- `PROBE_WATCH=fa5110 probe_entry.sh pw2 all 149` (rc=0, 14m40s): `[chg]` は 1 行のみ (`ffffffffffffffff -> 0`, 初期化時)。全関数入口で値は変わらず、**`fa5110` を書く関数は入口単位の watch では検出されない** (書込は入口間の関数内で起きない、または watch 対象アドレスがずれている)。
- 注意: `PROBE_WATCH` の値は「1 段の線形アドレス」として解釈される (`fa5110` は 1 段)。`pw` (`fa5110:0`) は 2 段目が 0 を指し常に `dead` になるため無効 (本 run で誤設定を確認)。
- **未確定**: 受入条件 1 (0x40 slot / free-list 非 0 の書込元) は未特定。受入条件 2・3 は未着手。
- 本 run の知見: 入口時点で trap に使われる free-list 先頭は未初期化 (0)。`407a50` の pool 初期化 (`fa5108` 周辺) が、このビルドで実行されているかが次の確認点。

## 9. #3083 着手 run (M11-N167): 412e40 の trap 値の位置と残骸依存性 (中間報告)

**判定: 受入条件 1 (書込元の特定) は未達。trap の箇所 (配列要素) と、trap が残骸に依存することを実測で確定。Refs #3083。**

- 測定 commit: `12e2cf9a6` (`probe_entry.py` に `412e40` の配列ダンプ `[arr412]` を追加)。base: `origin/main` `fbc7ac973`、worktree `ws-3083`。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)、`work-m11` / `work-liftdiff` を worktree 直下に展開。`m11_gen_ir2.sh` rc=0 (50.5 s, `boot_final.ll` 490761 行。§6 の 490733 行とは差がある・未確認)。`M11_FIX_652500=0 m11_build.sh` rc=0 (24.8 s, `m11_boot.cjs.wasm` 6,033,354 B)。load average は未測定。
- 分母: unit は 942 (`survey_units.mjs` の `for i < 942`)。件数は `SURVEY_UNITS` の kind 別件数。

### 9.1 全 unit 順次の survey (本線)

| 実行 | unit 149 | kind 件数 (ok/miss/halt0/oob/noproc) | 秒 |
|---|---|---|---|
| `survey_units.mjs` (probe 無し, HEAD) | oob: `412e40` ← `653660` ← `6539e0` ← `664190` ← `664260` | 873/47/7/14/1 | 12.9 |
| `m11_survey.mjs` (`M11_SURVEY_STACK=149`) | oob: `412e40` (wasm-function[77]:0x6b705) | — | 18.7 |
| `SV_ONLY=149` (単体, 前 unit の状態なし) | oob: `407a50` ← `409410` ← `412c20` (§6-§8 の経路) | — | 0.4 |

- 単体実行 (`SV_ONLY=149`) の trap 位置 `407a50` は、前 unit の状態が無い場合の別経路。本線 (全 unit 順次) の trap は `412e40` で、§1・§5 の経路と一致する。

### 9.2 trap の箇所 (`412e40` の入口採取, probe 版, HEAD で再現)

- `412e40(p, n)` は `n` 個の 8 byte 要素を走査し、非 0 の要素 `q` について `[q-8]` (参照カウント) を読む (IR: `load i32, [q-8]`)。
- unit 149 の呼出 (`653660` から): `n=0xc` (`a=10aa1470`) は全要素 0。`n=2` (`a=10aa14e8`) は `[0, 0x8002e4d6e49969e0]`。後者で `q=0x8002e4d6e49969e0` の `[q-8]` が範囲外 → trap。
- `653660` の 2 要素配列の要素 0 は `%stack_var_-24`、要素 1 は `%stack_var_-16` (`[2 x i64]`)。native の `[rbp+0xb0]`・`[rbp+0xb8]` に対応する。IR は要素 1 を `-24 + 8` として読む (隣接前提)。
- `653660` の第 2 引数は `6539e0` の `rcx` で、probe 版 (`parr2`・`pe3`・`p653`) では `0x264208` (UTF-16 リテラル) と実測。`413480(-16, arg2)` (l.33) は常に実行されるので、trap 直前の `-16` の値は別経路で上書きされている。

### 9.3 IR 上の書込元候補 (`653660`)

- `stack_var_-16` への書込は 3 箇所: l.33 `413480(-16, arg2)` (常に実行)、l.72 `413480(-16, load -64)`、l.83 `413480(-16, load -72)`。l.72 と l.83 は `arg3 != 0` の経路のみ。l.83 の値は `43c870` の出力 (`43c870` は `44f5d0` の戻り値で `414ec0` (部分文字列) か `4133f0` (代入) を選ぶ)。
- **反証**: `p43c` build (`43c870` を probe) では unit 149 で `43c870` が呼ばれない (`arg3 == 0` の経路) のに、要素 1 は `0x8002…` のまま。よって l.72・l.83 では説明できない。`653660` の外 (callee の shadow stack 上書き・残骸の読み) から上書きされている可能性が高いが、未特定。

### 9.4 trap の有無は残骸に依存する (probe で振れる)

| 条件 | unit 149 | kind 件数 |
|---|---|---|
| probe 無し (HEAD) | oob | 873/47/7/14/1 |
| `SV_STK_FILL=00` (各 unit 前に SP 直下を 0 埋め) | ok | 875/47/7/12/1 |
| `SV_STK_FILL=a5` | oob `409c80` ← `4136a0` | 594/328/6/14/0 |
| `SV_STK_FILL=ff` | oob `412e40` ← `653660` | 870/47/7/17/1 |
| probe `412e40` のみ (`parr`, HEAD で再現) | oob (要素 1 = `0x8002…`) | 870/47/8/16/1 |
| probe `412e40`・`653660`・`6539e0`・`664190` (`parr2`) | ok | — |
| probe 18 関数 (`pe3`) | ok | 859/60/3/17/1 (abort 2) |
| probe 18 関数 + watch `0x10aa14d0` (`pw653`) | oob | 872/47/7/15/1 |
| probe `412e40`・`43c870`・`44f5d0`・`414ec0`・`4133f0` (`p43c`) | oob (`43c870` 未呼出) | — |

- probe の `fprintf` 自身が残骸を変えるため、probe を入れると trap の有無が振れる。`SV_STK_FILL` の結果と合わせると、trap は未初期化スタックの読み、または callee による shadow stack の上書きに依存している。
- 結論: 「非 0 の値を書いた store」を probe の入口採取だけで特定する方法は、この trap では成立しない (probe が trap を消す)。

### 9.5 前提の訂正

- §6〜§8 の `407a50` (free-list) を trap 位置とする前提は、単体実行 (`SV_ONLY=149`) に限る。本線 (全 unit 順次) の trap は `412e40` (§1・§5)。
- issue の「`0x40` slot」は native `653660` の `[rbp+0x40]` (`n=0xc` 配列の先頭) を指すが、trap の配列は `[rbp+0xb0]`・`[rbp+0xb8]` (`n=2`)。`n=0xc` 側は全要素 0 で trap に関与しない。

### 9.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 要素 1 (`-16`) を非 0 にする書込元の特定 (受入 1)。`653660` 外の callee か shadow stack 上書きか | 受入 2・3 (修復・n≥3 survey・ネガコン) が保留 | #3083 (続き) |
| 残骸依存の原因 (未初期化の読み、または alloca の隣接前提の破れ) | 修復方針が決まらない | #3083 (続き) |
| probe の `fprintf` が残骸を変え、観測で trap が消える | probe による特定が不安定。probe の観測方法の見直しが必要 | #3083 (続き) |

次の確認点: (a) `653660` の wasm 上の alloca 配置 (`-24`・`-16`・`-32`・`-48`) を確認し、要素 1 が `-16` と一致するか。(b) `414bb0`・`43c8f0`・`414c70`・`6525b0` の shadow stack 使用幅と SP 復元が `653660` の frame を越えて書かないか。(c) probe を使わず、wasm の store 単位で書込元を記録する方法を検討する。
