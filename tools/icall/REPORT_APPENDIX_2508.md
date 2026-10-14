# 付録: icall #2508 (ICALL-78) — frame slot 復元の残件 (0x180da6e60 の候補分類・0x181057b38 の xmm0 不一致の切り分け)

> 親: #2427 (ICALL-77, PR #2514 merge 済み・`FA_FRAME_SLOT=1` の pass)。受入 3 (`SlateCore.core_64` 205 B の sha256 照合) は #2675 (ICALL-80) で解決済み (`REPORT_APPENDIX_2675.md`・§6)。受入 4 (16B 結合 merge 規則の検証) は本 PR で §8 に実施。
> 測定 commit: `05194cdc` (`origin/main` (`9b352bd7`) 取り込みの merge。コードを変えた最後の commit)。`fa_cmp.py` の harness 修正は `0d29b5f4`。

## 1. 結論

- **0x181057b38 の 8/8 不一致は harness 由来**。関数と callee の機械語は xmm0 を一度も書かず、native は入力 xmm0 をそのまま返す (素通し)。wasm 側は戻り値の出力スロット BLK+0x88 を `ott_run` が初期化しないため、0 を返していた。`tools/icall/diff/fa_cmp.py` で入力値を BLK+0x88 に置いてから呼ぶよう修正し、0x181057b38 は **8/8 一致** (修正前 0/8)。
- 同じ修正で、素通しの関数 8 件が「不一致」から「一致」に変わった (§3.4)。fixed route の `fa_sweep` (131 関数・HEAD で再実行) は **値の不一致 11 → 3、bit 一致 46 → 54** (旧 harness → 新 harness)。PR 初版の bit 一致 55 は HEAD の再実行で再現せず、差は `0x1803dee20` の 1 件 (§3.5)。
- **0x180da6e60 の候補 10 件は部分分類**。route が使う IR (`after.0.restored.ll`) に store が無いのは 8 件。うち 2 件はこの関数内に読みが無く (無害とは断定しない)、6 件は仮想 call に渡す構造体の内部または cookie 検査の入力で、読み先・値の出所が静的に確定せず「誤り疑い」のまま。残り 2 件は route IR に store があり、before IR との比較による誤検出 (§4)。
- 受入 4 (16B 結合 merge 規則の検証) は本 PR で完了 (§8)。merge 規則が成立するのは 0x181057b38 の 2 組だけで、0x180da6e60 は 3 条件のいずれかが欠けて不成立。
- 残件は子 issue に移した (§6)。受入 3 は #2675 (ICALL-80) で解決済み (`REPORT_APPENDIX_2675.md`)。0x180da6e60 の誤り疑い 6 件と 0x1803dee20 → #2695 (ICALL-81)。0x180da4030 の脱落修復 → #2708 (ICALL-83)。0x180da4030 と 0x18105d9fc の xmm0 の説明 → 解決済み (`REPORT_APPENDIX_2674.md` §1)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `05194cdc` (`origin/main` (`9b352bd7`) の merge。`fa_cmp.py` の harness 修正は `0d29b5f4`)。以降のコード差分は §7 |
| 素材 | `work-icall` (`tools/icall/work/rt_freshair-core`: `rw.dll`・`before.0.drc.{dsm,ll}`・`after.0.restored.ll`・`map.json`・`F.ranges`)。`toolchain-retdec` ([RETDEC] 展開済み)・`toolchain-emsdk` ([EMSDK] 展開済み)・`fl-win64` (未使用)。`plugins-freshair` は未使用 (`FA_CORE=rw.dll`) |
| 測定 | `FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh` (fixed) と既定 (base) の 2 route。各 `bash tools/icall/diff/fa_sweep.sh 8 60` (131 関数・1 並列) |
| 所要・load | `05194cdc` で実測。fixed sweep 74.1 s (load 0.14 → 0.81)、base sweep 74.1 s (load 0.78 → 0.94)。HEAD `50112f92` では fixed 74.0 s・73.4 s、base 73.8 s。sweep 前後の load (1 分平均) は `uptime` の値 |
| 比較 | `fa_cmp.py` の判定 (xmm0 の 64bit 比較、同一入力 8 点、seed 3) |

## 3. 0x181057b38 の切り分け (受入 2)

### 3.1 機械語: xmm0 を書く命令はあるか

dsm の連続領域を capstone で decode し、xmm0 を書く命令と call を数えた (静的確認は限定的: dsm に載っている連続命令のみ、CFG 全体は追っていない)。

| 関数 | 連続命令 | xmm0 への書込み | call |
|---|--:|--:|---|
| `0x181057b38` (205 B) | 53 | 0 | `0x181057a10`, `0x181057a90` |
| `0x181057a10` | 21 | 0 | `0x181056a4c`, `0x181056aa0` |
| `0x181057a90` | 26 | 0 | `0x181056a4c`, `0x181057d20`, `0x181056aa0` |
| `0x181057d20` | 30 | 0 | `0x1810665b8`, `0x1810663b8`, `0x18106632c` |
| `0x181056a4c`・`0x181056aa0` | 9 each | 0 | (dsm が途中で切れる。非連続) |

0x181057b38 自体は `rcx` を `[rbp-0x28]` に退避して 2 callee を呼ぶだけで、戻り値 (rax) も xmm0 も返していない。

### 3.2 native と wasm の値 (fixed route・同一入力 8 点)

| 条件 | 8 入力の xmm0 出力 | 入力との一致 |
|---|---|---|
| native (`fa_cmp.py`) | 出力 = 入力の bit (先頭 `c000c5300342457c` = seed 3 の x0) | — |
| wasm 旧 harness (`0d29b5f4` より前) | `0000000000000000` (8/8) | 0/8 |
| wasm 新 harness (`0d29b5f4`・BLK+0x88 := 入力) | 入力と同一 | **8/8** |

### 3.3 原因

- `rt/icall_rt.c` の `ott_run` は入力 xmm0 を `BLKQ(0x28)` に置き、戻り値は `ott_xmm0()` が `BLKQ(0x88)` を読む。素通しの経路では `BLK+0x88` が初期化されないまま出る (wasm の線形メモリは 0)。
- lift 後の IR (`after.0.restored.ll` の `function_181057b38`): entry は xmm0 を `BLK+0x28` から読み、call の後は `BLK+0x88` から読み、出口で `BLK+0x88` に書く (`%49 = load BLK+0x88` → `store BLK+0x88`)。callee が xmm0 を書かないので、出口の値は `BLK+0x88` の初期値そのまま。
- 切り分け: 入力 xmm0 を harness が `BLK+0x88` に置くと一致 (§3.2)。native と揃うのは「関数 entry の xmm0 レジスタ状態 = 入力」であり、`BLK+0x88` の初期化は harness の契約の欠落。**harness 由来**と判定。
- 修正: `tools/icall/diff/fa_cmp.py` の `blk_xmm0_out()` で BLK+0x88 を入力で初期化してから `ott_run` を呼ぶ。`rt/icall_rt.c` は変更しない (OTT matrix など他 route への影響を避けるため)。
- **lift 側の残論点 (未解決・§6)**: lift の ABI 仮想化は関数 entry で `BLK+0x88 := BLK+0x28` を行わない。xmm0 を素通しする関数を nested に呼び、直後に xmm0 を読む caller で同じ不一致が出るかは未確認。Win64 ABI では void 関数の xmm0 は戻り値ではないため、実害の有無は未確定。

### 3.4 sweep への影響 (fixed route・同一 commit で再測定)

> 注: この節の fa_sweep 数値 (54/66/8/3 など) は測定時の tree (`05194cdc`・HEAD `50112f92`) の値。その後 main で `tools/icall/ir_fix_vstore.py` (`fa_route_build.sh` が呼ぶ) と `tools/icall/diff/fa_cmp.py` (#2674) が変わったため、現在の tree で引用するには再測定が要る。

| 関数 | 旧 harness (3dbb35e の `fa_cmp.py`) | 新 harness (`0d29b5f4`) | native の先頭出力 |
|---|---|---|---|
| `0x1803de190`・`0x180829c20`・`0x180c98240`・`0x180c99430`・`0x181055400`・`0x181056a4c`・`0x181056aa0`・`0x181057b38` (8 件) | 値の不一致 8/8 | bit 一致 8/8 | 全件 `c000c5300342457c` (= 入力) |

fixed route の集計: 旧 harness **46 / 66 / 8 / 11** → 新 harness **54 / 66 / 8 / 3** (bit 一致 / native crash・timeout / wasm のみ err / 値の不一致)。
base route (新 harness): **53 / 66 / 9 / 3**。base → fixed で判定が変わる関数は `0x181057b38` の 1 件だけ (wasm のみ err 9 → 8、bit 一致 53 → 54)。2427 の主張 (変わるのは 0x181057b38 だけ) は新 harness でも成り立つ。

残る値の不一致 3 件 (新 harness, base と fixed で同じ):
- `0x1803dee20`: native 0 / wasm 入力。`FreshAirDsp` の ctor (267 B・`tools/targets/freshair/REPORT.md` §3.1)。戻り値は rax (`mov rax, rdi`) で、関数本体に xmm 命令は無い。xmm0 は callee の残留値で、最後に呼ぶ `0x18100be74` (2 回目) の先で決まる (`0x180ca3260` は xmm 命令なし・vtable と 2 フィールドを書いて `rax=rcx` を返す)。旧 harness でも不一致で、seed 修正とは無関係。xmm0 を比べるオラクルが戻り値の比較として適切かも未確定。深い連鎖 (`0x18100be74` → `0x1810553d0` 付近) は未追跡で、原因は未特定 (§3.5・§6)。
- `0x180da4030`: native 0 / wasm 入力。関数の連続命令と callee `0x180da3f80` に xmm0 の書込みは見つからない (CFG 全体は未追跡)。**説明できない差**として未解決 (§6)。
- `0x18105d9fc`: native `0x50400010` / wasm `0x104af418`。native と wasm のヒープポインタ値が xmm0 に乗っていて、アドレスが一致しない。比較のオラクルとして不適切 (harness 由来・未修正)。

### 3.5 PR 初版の一致 (55 / 66 / 8 / 2) の再現

測定 commit `0d29b5f4` の PR 初版では fixed の bit 一致が 55 で、`0x1803dee20` が一致側に入っていた。HEAD `50112f92` で同じ手順 (`fa_sweep.sh 8 60`) を 2 回、`fa_cmp.py 1803dee20 --n 8` を 3 回実行したが、いずれも `0x1803dee20` は一致せず (native `0000000000000000`、wasm `c000c5300342457c` ほか)、sweep は 54 / 66 / 8 / 3 だった。レビュー環境の再実行も同じ値だった。ASLR を無効にした場合 (`setarch -R`) と `FA_ENC_INIT=1` の場合も結果は変わらなかった。

PR 初版でこの 1 件が一致した理由は特定できていない。1 関数分の揺れとして #2302 に追記した ([コメント](https://github.com/signature-studio/signature-studio-dev/issues/2302#issuecomment-6172956250))。

## 4. 0x180da6e60 の候補 10 件の分類 (受入 1)

### 4.1 手順

1. `frame_slot_restore.py` の scan (`before.0.drc.ll` の insn.addr と比べた候補) を 10 件得る (2427 と同じ定義)。
2. **route が使う IR (`after.0.restored.ll`) に同じ insn.addr の store が残っているか**を確認する。before IR と after IR は別の lift (元 PE と rw.dll) なので、候補の判定基準として before IR を使うのは不正確。
3. 候補の書込み先が、関数内で lea で取られた領域 (O1〜O3) のどれに入るかを見る。

| 領域 | 範囲 | lea | 渡し先 (仮想 call) |
|---|---|---|---|
| O1 | `[rbp-0x31, rbp-0x21)` (2 qword) | `lea rdx,[rbp-0x31]` (0x180da6f60) | `call r10` (`[rcx+0x10]`) |
| O2 | `[rbp-0x21, rbp-9)` (3 qword) | `lea rdx,[rbp-0x21]` (0x180da729f) | `call r9` (`[rcx+0x10]`) |
| O3 | `[rbp-9, rbp+0xf)` (3 qword) | `lea rdx,[rbp-9]` (0x180da7314) | `call r8` (`[rcx+0x10]`) |

仮想 call の宛先は `[rcx+0x10]` で、`rcx` は実行時オブジェクトなので、callee の読み先は静的に確定しない。

### 4.2 候補ごとの分類

| No | VA | 候補の store | route IR の同 insn.addr | 読み先 (静的) | 分類 |
|--:|---|---|---|---|---|
| 1 | `0x180da6e8e` | `[rbp+0x2f] = rax` (stack cookie ^ rsp) | 無 | 出口の cookie 検査 (`call @function_18100c1e0`) が IR に残る。その引数 rcx の出所は IR 上で追えず (`0x180da7373` の load は IR に無い) | **未確定 (誤り疑い)** |
| 2 | `0x180da6f4d` | `[rbp-0x29] = rcx` (`= [rdx+8]`) | 無 | O1 の +8。O1 は `call r10` の第 2 引数 | **未確定 (誤り疑い)** |
| 3 | `0x180da7278` | `[rbp+0xf] = rdx` | 無 | どの lea 領域にも入らず (O3 の直後)、この関数に直接の読みも無い | **この関数内に読みは無い** (無害とは断定しない) |
| 4 | `0x180da7280` | `[rbp+0x17] = rbx` | 無 | 同上 | **この関数内に読みは無い** (無害とは断定しない) |
| 5 | `0x180da7293` | `[rbp-0x21] = rdx` | **有** (`store %466`) | (O2 の +0) | 誤検出 (route IR に存在) |
| 6 | `0x180da7297` | `[rbp-0x19] = r15` | 無 | O2 の +8。値 r15 は同じ BB で未定義 | **未確定 (誤り疑い)** |
| 7 | `0x180da729b` | `[rbp-0x11] = rcx` | 無 | O2 の +16。値は `[rdi+0x100130]` 由来 | **未確定 (誤り疑い)** |
| 8 | `0x180da7308` | `[rbp-9] = 0` (`xor ecx,ecx` 直後) | **有** (`store i64 0`) | (O3 の +0) | 誤検出 (route IR に存在) |
| 9 | `0x180da730c` | `[rbp-1] = 0` | 無 | O3 の +8。値 0 は確定 | **未確定 (誤り疑い)** |
| 10 | `0x180da7310` | `[rbp+7] = 0` | 無 | O3 の +16。値 0 は確定 | **未確定 (誤り疑い)** |

集計: この関数内に読みが無い 2 (3・4。無害とは断定しない) / 誤り疑い 6 (1・2・6・7・9・10) / 誤検出 2 (5・8)。

### 4.3 判定できない理由と限界

- 6 件の「誤り疑い」は、O1〜O3 を受け取る仮想 callee が**その offset を読むかどうか**に依存する。callee は実行時に決まり、静的には特定できない。値 0 の 2 件 (9・10) も、読まれれば wasm はスタックの残り値を読む。
- native 実行は起動直後に SIGSEGV (`rip=0x180da6e99`、`inc dword ptr [rax+0x19a4]` で rax=0。`rax = [rcx+0x10] = 0` で、rcx は harness が渡す heap 領域)。引数の構造体を harness が用意していないことが原因で、global 参照ではない (訂正: 付録 2674 §1)。native との比較で動的に判定できない。
- 2427 の候補検出 (before IR 比較) は本件で 2/10 の誤検出を出した。`frame_slot_restore.py` の restore 対象 (値を解決できたもの) は本件では 0 件なので、route の挙動は変わらない。候補の定義を after IR 基準にする改善は未実施 (§6)。

## 5. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .          # tools/icall/work/ へ (展開後 5.6 GB・実測 15 s)
bash tools/ott/native/build.sh                                    # fa_cmp / fa_sweep に必要
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"   # plugins-freshair が無いときの代替
FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh               # fixed route (base は FA_FRAME_SLOT を付けない)
python3 tools/icall/diff/fa_cmp.py 181057b38 --n 8               # 期待: match 8 / mismatch 0
bash tools/icall/diff/fa_sweep.sh 8 60 | tail -1                 # 期待 (fixed・HEAD 50112f92 で実測。測定時の tree の値・§3.4 の注): bit一致 54 / 66 / 8 / 3
python3 tools/icall/frame_slot_restore.py --ir tools/icall/work/rt_freshair-core/after.0.restored.ll \
  --dsm tools/icall/work/rt_freshair-core/before.0.drc.dsm --before-ll tools/icall/work/rt_freshair-core/before.0.drc.ll \
  --ranges tools/icall/work/rt_freshair-core/F.ranges --out tools/icall/work/fa_exp/x.ll --report tools/icall/work/fa_exp/x.json   # 候補 12 件 (0x180da6e60 の 10 件 + 0x181057b38 の 2 件)
```

## 6. 未解決 (起票先)

> 起票先 (現在の issue 本文に合わせた): 受入 3 は #2675 (ICALL-80) で解決済み。0x180da6e60 の誤り疑い 6 件と 0x1803dee20 → #2695 (ICALL-81)。0x180da4030 の脱落修復 → #2708 (ICALL-83)。0x180da4030 と 0x18105d9fc の xmm0 の説明 → 解決済み (`REPORT_APPENDIX_2674.md` §1)。受入 4 は §8 で解決。PM 判断 (コメント 6174007294) のとおり、lift ABI の仮想化は起票せず本付録に「未確認」として残す (未起票)。候補検出の基準は変えず before IR 基準を維持する (誤検出は §4.2 に残す)。`docs/DEFECTS.md` への追記は本 PR では編集しない (未起票・`docs/WORKFLOW.md` §5)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 3: `SlateCore.core_64` の `0x181057b38`–`0x181057c05` (205 B) の sha256 照合 | 解決済み。`rw.dll` の同 VA と一致 (`REPORT_APPENDIX_2675.md` §1) | 解決済み (#2675・`REPORT_APPENDIX_2675.md`) |
| 0x180da6e60 の「誤り疑い」6 件 (§4.2 の 1・2・6・7・9・10) と 0x1803dee20 の値の不一致 | 仮想 callee の読み先と cookie 検査の入力の出所が未確定。native は起動時 SIGSEGV | #2695 (ICALL-81) |
| lift の ABI 仮想化: 関数 entry で `BLK+0x88 := BLK+0x28` が無い (xmm0 素通しの nested 呼出し) | nested 呼出し後に xmm0 を読む caller で不一致の可能性。未確認 | 未起票 (PM 判断: 起票しない。本付録に「未確認」として残す) |
| `0x180da4030` の native 0 / wasm 入力 (xmm0 の差。連続命令に書込み無し) | closure 内の 1 関数で silent 差分の可能性。説明 (xmm0 の出所) は解決済み。脱落修復 (dsm の data 区分に入っている実コード 0x180da4081–0x180da4176) は未修復 | 解決済み (`REPORT_APPENDIX_2674.md` §1) (説明)・#2708 (ICALL-83) (修復) |
| `0x1803dee20` の native 0 / wasm 入力 (ctor。戻り値は rax、xmm0 は callee の残留値。旧 harness でも不一致) | 値の不一致 1 件。seed 修正とは無関係。深い連鎖 (`0x18100be74` → `0x1810553d0` 付近) は未追跡 | #2695 (ICALL-81) |
| `0x18105d9fc` の xmm0 がヒープポインタ (native と wasm でアドレスが違う) | 比較オラクルの問題は `fa_cmp.py` の PTR 正規化で解決 (0/8 → 8/8) | 解決済み (`REPORT_APPENDIX_2674.md` §1) |
| 候補検出の基準を route IR (after) にする | 誤検出 2/10 (本件) | 未起票 (PM 判断: 変えない。before IR 基準を維持し、誤検出は §4.2 に残す) |
| `fa_sweep` の揺れ: PR 初版の fixed 55/66/8/2 が HEAD の再実行 (2 回) で 54/66/8/3 に変わった (差は `0x1803dee20` の 1 件・§3.5)。旧 46/66/9/9 とも違う | 原因未特定。1 関数分の揺れとして追記済み | #2302 (追記済み: [コメント](https://github.com/signature-studio/signature-studio-dev/issues/2302#issuecomment-6172956250)) |
| `docs/DEFECTS.md` への新類型 (passthrough の出力スロット未初期化) の追記 | 横断正本への反映 | 未起票 (PM 判断: 本 PR では編集しない。`docs/WORKFLOW.md` §5) |

## 7. 測定 commit からの差分

測定 commit `05194cdc` から HEAD `a62ff3cf` までの測定経路 (`tools/icall`・`tools/ott`・`tools/m2`・`tools/m5`・`tools/m11`・`tools/targets/freshair`・`tools/liftlib`) のコード差分は 0 行。`git diff 05194cdc HEAD -- tools/icall tools/ott tools/m2 tools/m5 tools/m11 tools/targets/freshair tools/liftlib ':!tools/icall/REPORT_APPENDIX_2508.md'` の出力は空。

`05194cdc` は `origin/main` (`9b352bd7`) を取り込んだ merge。`faa2ed97` (`f3102162` 取り込み。`frame_slot_restore.py` の block 境界をまたぐ挿入の抑止を含む) と `05194cdc` の判定は、fixed・base とも全 131 関数で一致。後から入った `icall_rewrite.py`・`mk_franges.py`・`check_blk_domain.py` は測定経路 (`fa_route_build.sh`・`frame_slot_restore.py`・`fa_sweep.sh`・`fa_cmp.py`) から呼ばれない (`ir_flatten.py`・`vex_gen.py` のコメントに名前があるのみ)。0x181057b38 の復元は 2 件 (`frame_slot.json` の `restored` 2) のまま。fixed sweep は 54/66/8/3 で `ca7bd804` と同じ。base は 53/66/9/3。`fa_cmp.py 181057b38 --n 8` は fixed match 8 / mismatch 0、base wasm_err 8。

## 8. 受入 4: 16B 結合 merge 規則の検証 (本 PR)

> 測定 commit: `d35279ab` (`origin/main`)。本 PR はコードを変えず、付録だけを足す。§8.4 が import・実行する `tools/icall/frame_slot_restore.py`・`frame_slot_probe.py` の `git diff d35279ab HEAD` は 0 行 (§8 の実行経路はこの 2 files に絞る。`fa_route_build.sh`・`diff/fa_cmp.py`・`diff/fa_sweep.sh` は §8.4 の手順では実行しない)。`05194cdc..d35279ab` では `tools/m11/shimx_link/` の 4 ファイルだけが変わっており、fa route が使う `tools/m11/m11_simd2.py`・`msimd11_core.h` は変わっていない。main 取り込み (`5d4fc937`・`origin/main` `363c39ed`) 後の測定経路の差分は `git diff --stat d35279ab HEAD -- tools/icall tools/ott tools/m2 tools/m5 tools/m11 tools/targets/freshair tools/liftlib ':!tools/icall/REPORT_APPENDIX_2508.md'` = 41 files・2317 insertions・31 deletions。`tools/icall/diff/fa_cmp.py` (13 行・#2674 の PTR 正規化) と `tools/icall/ir_fix_vstore.py` (26 行) などを含み、いずれも §8.4 の実行経路の外。

### 8.1 結論

- 対象は `F.ranges` の 131 関数。dsm に関数 entry があるのは 130 件で、`0x18100beb0`–`0x18100beb5` は entry が無い 5 B の thunk (`jmp 0x18100c99c`・store を含まない)。`frame_slot_restore.py` は `mov rbp, rsp` (または `lea rbp, [rsp+d]`) で frame pointer を立てる関数だけを scan する (fp ゲート・対象 4 関数: `0x180da6e60`・`0x18103d218`・`0x181057b38`・`0x18105bb90`)。fp ゲートを外して 130 関数すべてを scan しても候補は 12 件 (`0x180da6e60` の 10・`0x181057b38` の 2) のままで、ゲートで外れた関数の候補は 0 件 (本 PR の再検証で確認)。
- merge 規則 (`frame_slot_restore.py` の `ensure`) が成立するのは、`F.ranges` の 131 関数のうち **0x181057b38 の 2 組だけ**。
- 0x180da6e60 は、値の解決 (条件 1) が 10/10 で不成立。結合先の相手 (条件 2) は 3 件で成立するが、相手の `i64` alloca が IR に無く (条件 3) 結合されない。
- 候補 (脱落 store) を持つ関数は、この closure では 0x181057b38 と 0x180da6e60 の 2 つだけ。したがって他関数への一般化は、この closure では検証対象が無い。

### 8.2 手順と結果

1. `frame_slot_restore.py` を `F.ranges` の全 131 関数に適用し、`--report` の JSON で候補・復元・merge を集計した (候補 12 件・解決して戻す 2 件)。
2. 復元前の IR (`after.0.restored.ll`) と復元後の IR を関数単位で比べた。変わった関数は `0x181057b38` だけ (131 関数中 1)。
3. 候補ごとに、merge 規則の 3 条件を確認した。

| 関数 | 候補 | (1) 値が解決 | 復元 | merge | (2) X が lea の disp と一致 | (3) E の `i64` alloca が IR にある |
|---|--:|--:|--:|---|--:|--:|
| `0x181057b38` | 2 | 2 | 2 | 2 組: E=-24・X=-16 / E=-48・X=-40 | 2 / 2 | 2 / 2 |
| `0x180da6e60` | 10 | 0 | 0 | 0 | 3 / 10 (No 2・6・9) | 0 / 3 |

- 条件 (1): 戻す store の値が、同一基本ブロック内の lea (frame slot の address か global の VA) で解決できること。
- 条件 (2): 結合先 X (store の target slot) が lea の disp と一致すること (E = X−8 が lea で取られている)。実装は `scan` の `escaped` (= lea の disp − 8) に E が入るかの判定で、これと同じ。
- 条件 (3): E の `i64` alloca が IR にあり、まだ結合されていないこと。

### 8.3 適用条件 (成立しない関数の理由)

merge 規則は 3 条件がすべて成り立つときだけ起きる。成り立たないときは、`ensure` が X 用の `i64` alloca を単独で作るか、値が解決できないため候補のまま残る。コードには、さらに (a) 挿入点が同一基本ブロック内であること (外れると `skipped` に入る) と、(b) §8.1 の fp ゲートがある。131 関数では `skipped` は空で、(a) は発火していない。

- **0x180da6e60 の値 (条件 1) が解決できない理由**: No 2 は `[rdx+8]`、No 7 は `[rdi+0x100130]` 由来の値 (load)。No 3・4 は `[rcx]`・`[rcx+8]` の load (rcx = `[rdi+0x100130]`)。No 6 は `r15` が同一 BB で未定義、No 9・10 は `xor ecx,ecx` によるゼロ化 (resolver は lea だけを解決する)、No 1 は stack cookie。No 5・8 は route IR に store があり検出の誤り (§4.2 の分類どおり)。
- **0x180da6e60 の E が無い理由 (条件 3)**: (2) が成立する No 2・6・9 の E は、それぞれ `stack_var_-57`・`-41`・`-17`。この関数の `i64` alloca は `stack_var_-104`・`-128`・`-144` だけで、E の alloca が無い。値の解決を足しても、結合ではなく単独の alloca が増えるだけになる。
- 条件 (1) の拡張 (`xor` ゼロ化の解決) は、No 9・10 を復元対象にし得る。ただし条件 (3) が不成立のため merge は起きない。拡張の要否は ICALL-79 の分類結果を見て決める (本 PR では未実施)。

### 8.4 再現

素材は `work-icall` の `rt_freshair-core/` だけで足りる (`tar --zstd -xf work-icall.tar.zst -C . --wildcards 'tools/icall/work/rt_freshair-core/*'` (リポジトリ直下で実行・展開 6 s))。`toolchain-retdec`・`toolchain-emsdk` は使わない。

```sh
cd tools/icall
mkdir -p work/fa_exp2
python3 frame_slot_restore.py --ir work/rt_freshair-core/after.0.restored.ll --dsm work/rt_freshair-core/before.0.drc.dsm \
  --before-ll work/rt_freshair-core/before.0.drc.ll --ranges work/rt_freshair-core/F.ranges \
  --out work/fa_exp2/x.ll --report work/fa_exp2/x.json
python3 - <<'PY'
import re, sys
sys.path.insert(0, '.')
import frame_slot_probe as fsp, frame_slot_restore as fsr
D = 'work/rt_freshair-core/'
b = open(D + 'after.0.restored.ll', errors='replace').read()
n = open('work/fa_exp2/x.ll', errors='replace').read()
fn = lambda t: {m.group(1): m.group(0) for m in re.finditer(r'^define [^\n]*@function_([0-9a-f]+)\(.*?^\}', t, flags=re.M | re.S)}
fb, fx = fn(b), fn(n)
print('changed:', ['0x' + k for k in fb if fb[k] != fx.get(k)], 'of', len(fb))
irb = fsp.ll_store_addrs(D + 'before.0.drc.ll')
md = {int(k): int(v) for k, v in re.findall(r'^!(\d+) = !\{i64 (\d+)\}', b, flags=re.M)}
for va in ['0x180da6e60', '0x181057b38']:
    v = int(va, 16)
    cands, restores, escaped = fsr.scan(fsr.decode(fsp.dsm_funcs(D + 'before.0.drc.dsm', {v}).get(v) or []), irb.get(v, set()))
    al = set(int(x) for x in re.findall(r'%stack_var_(-?\d+) = alloca i64', fb[va[2:]]))
    for c in cands:
        X = c['disp'] - 8; E = X - 8
        print(va, c['va'], 'X', X, 'E', E, '(1) value', c['value'], '(2) E in escaped', E in escaped, '(3) E i64 alloca', E in al)
    if va == '0x181057b38':
        for E in (-24, -48):
            f2 = re.sub(r'^  %%stack_var_%d = alloca i64, align 8\n' % E, '', fb[va[2:]], count=1, flags=re.M)
            print('NC drop alloca', E, fsr.edit(f2, restores, escaped, md, b)[1])
PY
```

期待値 (実データ・`F.ranges` 131 関数): `changed: ['0x181057b38'] of 131`。(1)(2)(3) は §8.2 の表と一致する。`0x181057b38` の 2 候補は (1) が解決、(2) が True、(3) が True。`0x180da6e60` の 10 候補は (1) がすべて None。(2) が True になるのは No 2・6・9 (X = −49・−33・−9、E = −57・−41・−17) の 3 件だけで、その 3 件の (3) は False。(2) は `scan` の `escaped` (= lea の disp − 8) との比較で、`E in escaped` ⇔ X が lea の disp と一致する。`0x180da6e60` の lea の disp は −0x31 (−49)・−0x21 (−33)・−9・+0x1f (31、`0x180da7111`) で、+0x1f に対応する候補は無い。ネガティブコントロール (NC): `0x181057b38` の E = −24・−48 の alloca を 1 件ずつ外すと、`merged` からその組が消え `created` に X (−16・−40) が入る。実測済み (HEAD `5d4fc937`・`git archive` で一時ディレクトリに取り出した `tools/icall`・素材 `work-icall` の `rt_freshair-core/` のみ展開。§8.4 が使う `frame_slot_restore.py`・`frame_slot_probe.py` は `d35279ab` と同一): `changed: ['0x181057b38'] of 131`、候補 12・復元 2。(1)(2)(3) は上の期待値と一致。NC は E = −24 を外すと merged `[[-48,-40]]`・created `[-16]`、E = −48 を外すと merged `[[-24,-16]]`・created `[-40]` (コードの分岐からの予測どおり)。
