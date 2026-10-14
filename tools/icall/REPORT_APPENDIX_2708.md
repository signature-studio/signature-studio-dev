# 付録: icall #2708 (ICALL-83) — RetDec が fall-through 先を data 区分にする原因と、A 型候補 11 件の判定

> 親: #2696 (ICALL-82) の子。前提 #2699 (ICALL-79) は merge 済み。受入 1 (`0x180da4030` の IR 修復) と受入 2 (修復後の sweep 比較) は本 PR では未達で、子 #3198 (ICALL-87) に移した (本 PR 本文の未解決表)。本 PR は受入 3 (11 件の判定) と受入 4 (原因の特定) を完了単位とする。
> 既知類型との関係 (`docs/DEFECTS.md`): 新規。D3 (store 消失)・D1b (jcc 先の dead code 削除) とは別。`icall_rewrite.py` の chained 断片の複製が fall-through を辿らない形で、下の §3 に機構を書く。

## 1. 結論

- **原因 (受入 4)**: `.pdata` で親関数の断片 (hot/cold 分割。`UNW_FLAG_CHAININFO`) として登録された後続コードが、親の再配置範囲 `[S, E)` の外にある。`icall_rewrite.py` は chained 断片を、`j*` の即値ジャンプで参照されたときだけ参照元へ複製する (552〜568 行)。親の末尾から断片へ **fall-through** で落ちる経路は数えられず、断片は複製されずに捨てられる (574 行 `del funcs[g]`)。RetDec は入力範囲に無い断片を data 区分として出す。
- **A 型 11 件の判定 (受入 3)**: 11 件すべてに、E から始まる chained 断片が pdata に実在する (構造的に実コード)。fa_cmp (8 点) で 8/8 不一致が 4 件 (`0x180da4030` は wasm が違う値を返す。`0x1803b5500`・`0x18040c950`・`0x180da5f20` は wasm が全点で例外)。修復対象の候補として扱う。8 点一致が 4 件、native の SIGSEGV で判定保留が 3 件。偽陽性 (実コードでない) は 0 件 (§4)。
- **修復 (受入 1・2) は未着手で子 #3198 へ**。原因の修正 (rewriter の断片複製の条件) は元の PE (`plugins-freshair`) で rewriter を再実行しないと検証できない。今回の素材 (`work-icall`) には元の PE が無い。
- 追加の発見: A 型の定義 (先頭 16 B に `00 00` が無いこと) の条件で `0x180ca1480` が除外されたが、これも同じ形の断片。先頭の `00 00` は `call rel32` の上位バイトで、実コードである (§4.2)。

## 2. 測定条件

- 測定 commit: route・fa_cmp・sweep は `1b37410c` (測定時点の origin/main。fix 時点の origin/main は `a4c5ea16`)。
- `chain_chunk_check.py` は本 PR の `fdf6576c` で追加され、以後変更していない。ネガティブコントロール `chain_chunk_negctl.py` の測定 commit は `f8b1ca46` (route の入力ではない)。
- 素材: `work-icall` (`tools/icall/work/rt_freshair-core/`)・`toolchain-retdec`・`toolchain-emsdk` (展開先は `[EMSDK]`・`[RETDEC]`。`docs/REFERENCES.md` §4)。`FA_CORE=rw.dll` の代替 (`plugins-freshair` は不使用)。
- 出力の基準 (本 run の実測):

| コマンド | 結果 | 所要 | 備考 |
|---|---|--:|---|
| `bash tools/icall/fa_route_build.sh` | OK (`fa_route.cjs`) | 11.4 s | base (`FA_FRAME_SLOT` 未設定) |
| `python3 tools/icall/diff/fa_cmp.py 180da4030 --n 8` | match 0 / mismatch 8 (native `0000000000000000`・wasm `c000c5300342457c` ほか) | 0.16 s | REPORT 前版と一致 |
| `bash tools/icall/diff/fa_sweep.sh 8 60` | **bit 一致 55 / crash・timeout 65 / wasm のみ err 9 / 値の不一致 2** (計 131) | 73.7 s | 前版 REPORT の基準 54/66/9/2 と 1 件違う (§6) |
| `python3 tools/icall/diff/chain_chunk_check.py` | closure 131 中、pdata 終端 E に chained 断片がある関数 12 件 | — | §4 の表 |
| `python3 tools/icall/diff/chain_chunk_negctl.py` | none 12 / empty 0 / drop1 11 (`0x180da4030` が消える) | — | 検査の入力 `pdata_chained` を壊すと件数が変わる (ネガティブコントロール・§2.1) |

### 2.1 測定の鮮度 (`docs/WORKFLOW.md` §6)

```sh
git diff 1b37410c HEAD --stat -- tools/icall/fa_route_build.sh tools/icall/icall_rewrite.py tools/icall/audit_icall.py tools/icall/diff/fa_cmp.py tools/icall/diff/fa_sweep.sh tools/icall/ir_icall_restore.py tools/icall/frame_slot_restore.py tools/m2 tools/m5 tools/m11 tools/ott
git diff fdf6576c HEAD --stat -- tools/icall/diff/chain_chunk_check.py
```

- 上の出力は 0 行 (route 入力・`chain_chunk_check.py` は測定 commit から変わっていない)。PR の差分は 4 ファイル (`docs/DOC_MAP.md`・`REPORT_APPENDIX_2708.md`・`chain_chunk_check.py`・`chain_chunk_negctl.py`)。

## 3. 原因の機構 (受入 4)

`0x180da4030` を例にする。`.pdata` の項目は次の 3 つ (`rw.dll` の `.pdata` を `audit_icall.Image` で読んだ値):

| pdata 項目 | 範囲 | chained |
|---|---|---|
| 親 | `0x180da4030`–`0x180da4081` | no |
| 断片 1 | `0x180da4081`–`0x180da4177` | yes |
| 断片 2 | `0x180da4177`–`0x180da419e` | yes |

1. 親の最後の命令は `0x180da407f: xor eax, eax` (2 B)。次の命令 `0x180da4081: mov qword ptr [rsp+0x20], rbp` は断片 1 の先頭で、親の制御は fall-through でここへ落ちる (before dsm の全アドレスを見ても、この先頭へのジャンプは 0 件)。断片 1 は `jne 0x180da4177` で断片 2 へ、断片 2 は `jmp 0x180da40c5` で断片 1 へ戻る。断片 1 の末尾は `add rsp,0x28; pop …; ret` で、親の epilogue を含む。
2. `icall_rewrite.py` の関数範囲は `img.func_range(va)` = `pdata[va]` の終端 = `[S, E)`。断片は含まれない。再配置コピー (`map.json` の `func_map` `0x180da4030 → 0x1823205d0`、範囲 `func_range_new` `0x1823205d0`–`0x1823206bb`、0xeb B) は親の 0x51 B に、サイトの展開を足したもので、断片を含まない。
3. 断片の複製は `frags` (= chained な関数) を、非断片関数の命令のうち **`ins.mnemonic.startswith('j')` かつ即値ターゲットが断片の先頭** のときだけ行う (552〜568 行)。`0x180da4081` へのジャンプは無いので複製されない。断片 2 は断片 1 からの `jne` でしか参照されず、同じ理由で複製されない。最後に `for g in frags: del funcs[g]` (574–575 行) で、複製されなかった断片は捨てられる。
4. RetDec: 入力 (再配置コピー) は `ret` で終わるブロックになり、`0x180da4081`–`0x180da419e` は選択範囲に入らない。before の側 (元 PE の `F.ranges` = `[S, E)`) では `; data inside code section at 0x180da4081 -- 0x180da41a0` と出る。data 区分の判定は、このような「範囲外の実コード」を写したもの。RetDec 自体の誤りではなく、入力範囲の欠落が原因。

E 直前の命令の内訳 (before dsm): 11 件中 9 件は不成立の `je`/`jle` (not-taken 経路で E へ落ちる)、1 件は `sub rsp, 0x20`、1 件 (`0x180da4030`) は `xor eax, eax`。いずれも直進 (fall-through) で E へ入る。E へのジャンプは 12 件すべて 0 件。

### 3.1 DEFECTS.md の行案 (`docs/WORKFLOW.md` §5。直接編集はしない・番号は PM 採番)

既存の D1a〜D23 と突き合わせ、既存行に同じ類型は無いことを確認した (新規)。列は `docs/DEFECTS.md` の表に合わせた。

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|---|---|
| D24 (案) | 前処理 (icall_rewrite) → fe | **新規** (D3・D1b とは別) | 親関数の末尾が hot/cold 断片 (UNW_FLAG_CHAININFO) へ fall-through するとき、断片が RetDec の入力範囲に入らず data 区分になる。`0x180da4030` は wasm が別の値を返す (fa_cmp 0/8)。他 3 件は wasm が例外 (`missing function`) | `icall_rewrite.py` 552〜568 行は chained 断片を `j*` の即値参照でしか複製せず、親末尾の fall-through で入る断片は複製されない。574〜575 行で複製されなかった断片を捨てる | `0x180da4030` (断片 `0x180da4081`–`0x180da419e`・fa_cmp 0/8)。修復対象の候補 4 件 (§4.1)。同形の `0x180ca1480` は A 定義から偽陰性 (§4.2)。詳細は本 §3 | `chain_chunk_check.py` の `chained_at_E` が 1 件以上の E について、before dsm 全体で E を即値に持つ `j*`・`call` が 0 件 (E は直進で入る) | 非断片関数の末尾 fall-through 先が断片の先頭なら、その断片も複製する (§5。子 #3198 で検証・未実装) |

## 4. A 型候補 11 件の判定 (受入 3)

### 4.1 判定の根拠 (fa_cmp は 1 関数ずつ別プロセス・`--n 8`)

| 関数 | E | 断片 (E→終端) | E 直前 | fa_cmp (8 点) | 判定 |
|---|---|---|---|---|---|
| `0x180da4030` | `0x180da4081` | `0x180da4081–0x180da419e` | `xor eax,eax` | match 0 / mismatch 8 (wasm 値が違う) | **修復対象** (受入 1 の対象。子 #3198) |
| `0x1803b5500` | `0x1803b550f` | `–0x1803b5546` | `je` | match 0 / mismatch 8 / wasm_err 8 | **修復対象の疑い** (wasm が全点で例外) |
| `0x18040c950` | `0x18040c9c7` | `–0x18040ca0d` | `je` | match 0 / mismatch 8 / wasm_err 8 | **修復対象の疑い** (同上) |
| `0x180da5f20` | `0x180da5f51` | `–0x180da6084` | `je` | match 0 / mismatch 8 / wasm_err 8 | **修復対象の疑い** (同上) |
| `0x1803de190` | `0x1803de1b7` | `–0x1803de20d` | `je` | match 8 / mismatch 0 | 症状なし (8 点一致)。修復の要否は未判定 |
| `0x180829c20` | `0x180829c37` | `–0x180829caa` | `je` | match 8 / mismatch 0 | 症状なし。同上 |
| `0x180c98240` | `0x180c98256` | `–0x180c982ca` | `je` | match 8 / mismatch 0 | 症状なし。同上 |
| `0x180c99430` | `0x180c9946a` | `–0x180c99598` | `je` | match 8 / mismatch 0 | 症状なし。同上 |
| `0x180829930` | `0x18082993a` | `–0x1808299a6` | `sub rsp,0x20` | native SIGSEGV (rip `0x180829958` = 断片内) | **判定保留** (断片が実行される入力で native が落ちる。ヒープ 0x400 B の初期化では前提を満たさないと推定) |
| `0x180c97f20` | `0x180c97f3c` | `–0x180c98030` | `je` | native SIGSEGV (rip `0x180c97fba` = 断片内) | **判定保留** (同上) |
| `0x180da6720` | `0x180da67cc` | `–0x180da6850` | `jle` | native SIGSEGV (rip `0x180da672d` = 親本体) | **判定保留** (断片に入る前に落ちる) |

- 「修復対象の疑い」は、fa_cmp の失敗が wasm 側の例外として出る形 (8/8) で、欠落した実コードに到達している兆候と整合する。断片を補った後の再測定 (子 #3198) で確定する。
- 8 点一致の 4 件は、この入力では断片の挙動が出ないだけ。偽陽性とは言えない (断片は pdata 登録の実コード)。
- 3 件の判定保留は、native が断片内 (2 件) か親本体 (1 件) で SIGSEGV するため、fa_cmp の入力 (ヒープの 0x400 B) が関数の前提を満たしていないと**推定**する (根拠は SIGSEGV の rip の位置だけで、前提の中身は未検証)。入力を変える測定は本 PR の範囲外。

### 4.2 偽陽性の確認と、定義 A の除外 1 件

- 断片判定 (`chain_chunk_check.py`) は byte の条件を使わず、pdata の登録だけで決まる。よって、非コードが候補に入るという data_code_count の欠点 (REPORT_APPENDIX_2696 §3.3) は受けない。12 件すべてが実コードである。
- `0x180ca1480` (E = `0x180ca152d`、E 直前は `add rcx, 0xa8` の直進) は、断片が同じ形だが A 定義から外れていた。ここでいう A 定義の『先頭 16 B』は、断片の先頭 E から読んだ 16 B を指す。`0x180ca152d` から読んだ 16 B は `48 89 5c 24 50 48 8d 54 24 20 e8 74 68 00 00 48` で、`00 00` の条件 (`call rel32` の上位 2 B) に当たった。関数先頭 `0x180ca1480` から読んだ 16 B (`48 89 74 24 10 57 48 83 ec 40 49 8b f0 48 8b fa`) とは別物 (`audit_icall.Image.read` で確認)。`00 00` の条件は実コードを落とす (偽陰性)。この 1 件は同じ原因の候補として子 #3198 の検証に入れる (判定はしない)。

## 5. 修復の方針 (子 #3198 へ)

- 候補 (未検証): `icall_rewrite.py` の断片複製で、非断片関数の末尾の fall-through 先 (`fe`) が断片の先頭なら、その断片も複製する (`j*` の即値ターゲットと同じ扱いにする)。断片内のジャンプ先は既存の pending 処理がそのまま扱う。複製されなかった断片を捨てる処理 (574–575 行) は残す。
- 検証 (子): (1) `fa_cmp 180da4030 --n 8` が match 8 / mismatch 0。(2) `fa_sweep 8 60` の比較。基準は本 run の実測 55/65/9/2 (`REPORT.md` の旧値 54/66/9/2 とは揃えない)。変化した関数は理由を書く。(3) 4.1 の 3 件の wasm 例外が消えるか、消えなければその理由。(4) 0x180ca1480 の判定。
- 元の PE が要る (`plugins-freshair`)。rewriter を再実行しないと rw.dll は変わらない。

## 6. 既知の揺れ (base sweep)

- 本 run の sweep base は 55/65/9/2。前版 (REPORT_APPENDIX_2696 §4) の 54/66/9/2 と 1 件違う (crash/timeout → bit 一致の 1 件)。旧 sweep.jsonl が無いため、どの関数かは特定していない。前版でも同種の揺れ (`0x1803dee20`・#2302) を記録している。本 PR は差を記録するだけで、追跡は #2302 のまま。
- 本 run の `0x1803dee20` の fa_cmp は match 0 / mismatch 8 (本 run 内の値)。

## 7. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C . tools/icall/work/rt_freshair-core/
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"
python3 tools/icall/diff/chain_chunk_check.py                     # 期待: closure 131 / chained_at_E 12 (A 11 + 0x180ca1480)
python3 tools/icall/diff/chain_chunk_negctl.py                    # 期待: none 12 / empty 0 / drop1 11 (0x180da4030 が消える)
bash tools/ott/native/build.sh                                    # fa_cmp に必要
bash tools/icall/fa_route_build.sh                                 # base route (約 11 s)
python3 tools/icall/diff/fa_cmp.py 180da4030 --n 8                # 期待: match 0 / mismatch 8
for va in 1803b5500 180da5f20; do python3 tools/icall/diff/fa_cmp.py $va --n 8; done   # 期待: mismatch 8・wasm_err 8
bash tools/icall/diff/fa_sweep.sh 8 60                            # 期待 (base): 55/65/9/2 前後 (約 74 s)
```

注: `fa_cmp.py` は複数 VA を 1 プロセスで回すと native の SIGSEGV で止まる。`fa_sweep.sh` が 1 関数ずつ別プロセスで回すのはこのため。
