# REPORT_3328 — スピル引数 deref の走査の定義 (取りこぼし・偽陽性・比較側・判定不能) (#3328 / CI-149)

親: #2555 (CI-103)。走査の元の定義は `scan_spill_deref_2502.py` (REPORT_2502 §4)。判定の元データは REPORT_2555 §2〜§4。
既知類型との関係: **DEFECTS.md D4** (引数 reg 経由の disp=0 deref 脱落)。新規類型ではない。

## 0. 結論

- 定義を `tools/m11/ldfix/scan_spill_deref_3328.py` に分けた。2502 の定義 (S→L→D→C) は変えず、その上に偽陽性の除外・複写経由・比較側を別の kind として足した。2502 の script は無変更。
- **偽陽性の除外 (EXCL)**: D と call の間で引数レジスタが spill 枠から再ロードされる候補を除外する。除外されるのは REPORT_2555 §3 の 3 件 (0x413c00・0x414c70・0x44f240) だけ (負の対照: 除外されない 3 件 = 0x47b4a0・0x47cf10・0xc40770 は演算で書き換わるだけで、REPORT_2555 で誤りと判定済み)。
- **2502 の数字との差**: 14 関数 / 16 箇所 = CALL 11 関数 / 13 箇所 + EXCL 3 関数 / 3 箇所。合計は一致する。
- **取りこぼし (複写経由 COPY)**: 正の対照 0x7888f0 を拾う (0x788954、REPORT_2555 で誤り判定済み)。ただし COPY は **49 関数 / 103 箇所** になり、機械的な条件では減らせなかった (§4)。103 箇所の IR 側判定は未実施 (子 #3382 [CI-153])。
- **比較側 (CMP)**: 候補に含める (別 kind)。**20 箇所 / 13 関数**。IR 判定は 20 箇所すべて済み (§6)。誤り **11 箇所** (11 関数)・判定不能 **9 箇所** (4 関数)。
- **判定不能の定義**: 機械語の呼出し (または比較) に対応する IR の呼出しが無い、または 1 対 1 に対応づけられないものを「判定不能」とし、誤り・正のどちらにも数えない。0x439f90 がこれに当たる (§5)。

## 1. 定義 (正本: `scan_spill_deref_3328.py` の docstring と本節)

機械語は capstone 線型逆アセンブル (`ldmach.py`)。関数は .pdata 区間。IR の `define function_<VA>` が対象。

| kind | 定義 | 出力先 |
|---|---|---|
| S→L→D | 2502 と同じ: 引数レジスタを `[rsp+X]` に退避 (S)、`[rsp+X]` を別レジスタへ読み直す (L)、その値を 1 段 deref して引数レジスタ Rb へ入れる (D)。D は `mov Rb,[Ra]` の形 (disp=0) | (中間) |
| CALL | S→L→D の後 6 命令以内に `call`、かつ D と call の間で Rb が spill 枠から再ロードされない。演算などで Rb が書き換わっても候補のまま (`rewrite_va` を記録) | `functions` の CALL |
| EXCL | CALL の条件を満たすが、D と call の間に Rb への spill 枠からの再ロードがある。call 時点の値は argK 自身なので偽陽性 (`excl_va` を記録) | `functions` の EXCL |
| COPY | `mov Rc, argreg` の複写 (Rc は引数レジスタ以外) を alias に入れた版。D の後 6 命令以内の call が直接呼出し (`call 0x...`) のもの。spill 由来の候補は含めない | `functions` の COPY |
| CMP | S→L→D の後、Rb が書き換えられる前に cmp/test が Rb を読む (比較側の逆参照)。call は無くてよい | `functions` の CMP |

- 再ロードの判定: D と call の間の命令が `mov Rb, qword ptr [rsp+X]` で、X が D より前に引数を退避した枠 (S) のとき。
- 判定不能 (後述 §5) は scan の出力ではなく、IR 側との対応で決める。

## 2. 数え方と再現

- 素材: `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` (`fl-win64.tar.zst` から `tar --zstd -xf ... '*block00031_PE.bin'` で取り出し。fl-win64 26.1.7.5653)。IR は `tools/m11/work/boot_final3.ll` (読込のみ・gitignore)。
- IR の出所: `work-m11.tar.zst` の `boot_final3.ll` (`tools/m11/work/` に展開。PR 本文の `oc_artifacts: fl-win64 work-m11`)。生成は `tools/plugins/lift/passes/m11_post.py` (boot_final.ll → boot_final3.ll の後処理)。`work-m11` は #516 以前の生成で、現 main の生成手順とは一致しない (`docs/WORKFLOW.md` §11)。
- IR の sha256: `010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e` (21,769,117 bytes・`work-m11.tar.zst` の `tools/m11/work/boot_final3.ll`)。測定 (commit `f602f9354`) の時点では指紋を取っていなかった。fix run (HEAD `250df8f61`) で `work-m11` を展開して取り、下の件数が一致したので、測定に使った IR と同じ入力とみなす。
- PE の sha256: `b2c64da40921cf262c15c5b25c2b0422e4d1851e953c87e0bc38ed2c19f9496d` (22,227,016 bytes・`fl-win64.tar.zst` の `block00031_PE.bin`)。
- 走査: `python3 tools/m11/ldfix/scan_spill_deref_3328.py tools/m11/work/boot_final3.ll --pe $RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin --out <json>`
- 出力 (実測・IR 入力): `IR 関数 7421 / .pdata 有り 6969 / CALL 11 関数 13 箇所 / CMP 13 関数 20 箇所 / COPY 49 関数 103 箇所 / EXCL 3 関数 3 箇所` (実行 3.6 s・load average 0.15 / 0.25 / 0.18)。fix run で HEAD `250df8f61` を再実行し、同じ件数になった (実行 5.0 s)。
- 2502 の走査 (`scan_spill_deref_2502.py`・無変更) は同じ PE・IR で 14 関数 / 16 箇所 (再実行で一致)。
- 測定 commit: `250df8f61` (§7)。件数は初回に `f602f9354` で数え、IR の指紋を取った `250df8f61` で再測定して一致した。

## 3. 偽陽性の除外 (EXCL) と負の対照

| 関数 | D (deref) | 再ロード (枠) | call | 2555 の判定 | 今回 |
|---|---|---|---|---|---|
| 0x413c00 | 0x413c55 `mov rcx,[rcx]` | 0x413c5d `mov rcx,[rsp+0x20]` | 0x413c65 | 偽陽性 | **EXCL** |
| 0x414c70 | 0x414cbf | 0x414cc7 `mov rcx,[rsp+..]` | 0x414ccf | 偽陽性 | **EXCL** |
| 0x44f240 | 0x44f250 | 0x44f25b | 0x44f264 | 偽陽性 | **EXCL** |
| 0x47b4a0 | 0x47b4f5 (rdx) | 0x47b503 は演算 (再ロードでない) | 0x47b50b | 誤り | CALL (rewrite_va) |
| 0x47cf10 | 0x47cf92 (rdx) | 0x47cf95 は演算 | 0x47cfa4 | 誤り | CALL (rewrite_va) |
| 0xc40770 | 0xc409c0 (rdx) | 0xc409cb は演算 | 0xc409d6 | 誤り | CALL (rewrite_va) |

- 負の対照: 0x47b4a0・0x47cf10・0xc40770 は、D の後に同じ引数レジスタが書き換わるが、再ロードでないので除外されない。2555 で誤りと判定済みの 3 件が残ることを確認した。
- EXCL は、D と call の間 (窓内) に、D より前に引数を退避した枠からの再ロードがある候補だけ。再ロードが無い候補は EXCL にならない。

## 4. 取りこぼし (COPY) の定義と偽陽性の抑え方

- 2502 の `--copy-alias` は 64 関数 / 123 箇所だった。spill 由来 16 (= CALL 13 + EXCL 3) を引いた copy 由来 107 のうち、直接呼出しが 103 箇所。残りの間接呼出し 4 箇所は差分 (123 − 16 − 103) で、fix run で実測した。deref VA 0x1280414・0x409484・0x40949e・0xc627ab の call (VA 0x1280422・0x409487・0x4094a1・0xc627c0) は、順に `call qword ptr [rbx + 0x268]`・`call qword ptr [rip + 0xf9c813]`・`call qword ptr [rip + 0xf9c7f1]`・`call qword ptr [rdi + 0x18]` (`pe_disasm_va.py` で逆アセンブル)。2502 の `--copy-alias` の集合から 3328 の CALL + EXCL + COPY の集合を引くと、この 4 件だけが残る (VA 一致)。
- 今回の COPY の抑え方と効果 (実測):
  - 直接呼出しのみ: 間接呼出し 4 箇所を除外する (3328 の COPY 103 箇所は全て直接呼出し)。
  - 複写先は callee-saved (rbx/rsi/rdi/rbp/r12〜r15) に限る: 今回の 103 箇所は全て callee-saved のため効果 0 (条件は残す)。
  - 再ロード除外 (EXCL): copy 由来は 0 件 (効果 0)。
- つまり機械的な条件で減ったのは 4 箇所だけ。残り 103 箇所 (49 関数) は正常な間接参照を含みうるが、機械語だけでは区別できない。IR 側の判定が要る (子 #3382 [CI-153])。
- 正の対照: **0x7888f0** は COPY に 3 箇所出る: 0x78890f (→ call 0x43c3f0)・0x78892d (→ call 0x414ec0)・0x788954 (→ call 0x4133f0)。0x788954 は REPORT_2555 §2 で誤り判定済み (`%arg2` を渡すべき所に `*arg1`)。残り 2 箇所は今回の新しい候補で、未判定。
- REPORT_2502 §4 の「`--copy-alias` は採用しない」は今回も変わらない。COPY は候補一覧として扱い、判定まで含めて採用はしない。

## 5. 判定不能の定義と 0x439f90

- **判定不能**: 機械語の 1 箇所 (呼出し・比較) に対応する IR の 1 箇所が、次のどちらかで決まらないもの。(a) IR 側に同じ呼出し先 (callee) の呼出しが機械語の出現件数より少なく、呼出しの順 (k 番目) が対応づけられない、(b) 比較の対応が 1 対 1 に取れない。判定不能は、誤りにも正にも数えない。
- 0x439f90 (CALL 0x43a0be → call 0x414850): 機械語は 0x414850 を 1 回呼ぶ。IR の `function_439f90` 本体には `@function_414850(` の呼出しが 0 件 (REPORT_2555 §2 の「IR に対応する呼出し無し」と一致)。→ **判定不能**。IR 欠落か機械語の経路の違いかは未確定。追跡 issue は無い (§8 の未解決表に残す)。

## 6. 比較側 (CMP) の判定

判定は機械語の窓 (D と cmp の前後) と IR の icmp 行の 1 対 1 対応で行った。判定は保守的に、IR の arg 由来の icmp が 1 件だけで、機械語の比較対象 (`*argK`) が IR で `%argK` になっている場合だけ「誤り」とした。

| 関数 | D → cmp | 機械語の比較対象 | IR の対応 | 判定 |
|---|---|---|---|---|
| 0x413c00 | 0x413c55 → 0x413c58 | `*arg1` (rcx) | `icmp eq i64 %arg1, %arg2` (REPORT_2555 §4) | **誤り** (2555) |
| 0x414c70 | 0x414cbf → 0x414cc2 | `*arg1` (rcx) | `icmp eq i64 %arg1, %arg2` (REPORT_2555 §4) | **誤り** (2555) |
| 0x12e1990 | 0x12e19c5 → 0x12e19c8 | `*arg1` (`test rcx,rcx`) | `%10 = icmp eq ptr %arg1, null` (arg 由来の icmp は 1 件) | **誤り** |
| 0x44f240 | 0x44f250 → 0x44f253 | `*arg1` (`test rcx,rcx`) | `%4 = icmp eq i64 %arg1, 0` (icmp は 1 件) | **誤り** |
| 0x44f270 | 0x44f280 → 0x44f283 | `*arg1` | `%4 = icmp eq i64 %arg1, 0` (icmp は 1 件) | **誤り** |
| 0x44f530 | 0x44f540 → 0x44f543 | `*arg1` (r8) | `%2 = icmp eq i64 %arg1, 0` (icmp は 1 件) | **誤り** |
| 0x4504a0 | 0x4504b4 → 0x4504b7 | `*arg1` (`test rcx,rcx`) | `%1 = icmp eq ptr %arg1, null` (icmp は 1 件) | **誤り** |
| 0x44f040 | 0x44f069 → 0x44f06c | `*arg1` (rcx = [rsp+0x60] = arg1) | `%6 = icmp eq i64 %arg1, 0` (arg 由来の icmp は 1 件) | **誤り** |
| 0x44f2c0 | 0x44f2cf → 0x44f2d2 | `*arg1` (rcx = [rsp+0x20] = arg1) | `%1 = icmp eq i64 %arg1, 0` (1 件) | **誤り** |
| 0x44f2c0 | 0x44f30e → 0x44f314・0x44f381 → 0x44f387 | `*arg1` の要素 (`cmp word [rcx+rbx*2], r9w`。word の比較ループ) | IR に i16 の icmp は 6 件あるが、被演算子 (%10・%11・%35 等) を `*arg1` の要素に 1 対 1 で結べない | **判定不能** |
| 0x44fb40 | 0x44fb71 → 0x44fb74 | `*arg1` (rcx = [rsp+0x50] = arg1) | `%5 = icmp eq i64 %arg1, 0` (1 件) | **誤り** |
| 0x450420 | 0x450465 → 0x450468 | `*arg1` (r8 = [rsp+0x30] = arg1) | arg1 由来の icmp が 0 件。IR は arg3==0 の分岐で `*arg1` を読まず return 0 する (機械語は同じ分岐で `*arg1` を test する) | **判定不能** |
| 0x4506e0 | 0x4506f4 → 0x4506f7 | `*arg1` (rcx = [rsp+0x30] = arg1) | `%1 = icmp eq ptr %arg1, null` (1 件) | **誤り** |
| 0x4506e0 | 0x450710 → 0x450716・0x450723 → 0x450729・0x45074f → 0x450755・0x450773 → 0x450779 | `*arg1` の要素 (`cmp word [rdx+r8*2], 0x20`。空白の走査) | IR の `icmp ult i16 %x, 33` (= 0x20 以下) は対応するが、要素の読込みが `arg1` の値ではなく `arg1-4` の長さ由来の整数からの inttoptr。`*argK` の経由が 1 対 1 に決まらない | **判定不能** |
| 0x12f9730 | 0x12f97c8 → 0x12f97cb・0x12f97d5 → 0x12f97da | 比較は `**([rsp+0x38])+4` と `[rdx]` (枠 0x38 を 2 段逆参照)。IR の `%30`・`%65` は call 戻り値 `+4` と `[%22+4]` (枠 0x4c 由来の値) を比べる | 機械語は枠 0x38 由来、IR は call の戻り値と枠 0x4c 由来で、比較の被演算子が 1 対 1 に対応しない | **判定不能** |

- 判定の集計: **誤り 11 箇所** (既存 7 = REPORT_2555 の 2 箇所を含む + 本節の 4 箇所)・**判定不能 9 箇所**。関数単位では、誤り 11 関数 (0x12e1990・0x413c00・0x414c70・0x44f040・0x44f240・0x44f270・0x44f2c0・0x44f530・0x44fb40・0x4504a0・0x4506e0)。判定不能の 9 箇所は 4 関数 (0x12f9730・0x450420 は判定不能のみ、0x44f2c0・0x4506e0 は誤りの箇所も含む)。判定不能は誤りにも正にも数えない (§5)。
- 正 (誤りでないと確定した箇所) は 0 件。
- 判定の型: 「誤り」は、機械語の比較対象が `*argK` で、IR の arg 由来の icmp が 1 件だけでその対象が `%argK` の場合 (既存の 7 箇所と同じ基準)。要素の比較・深さの違う比較は、1 対 1 で決まらないので判定不能。
- 0x450420 は、IR の分岐 (arg3==0 → return 0) と機械語の分岐 (arg3==0 → `*arg1` を test) が一致しない。IR 側の欠落か機械語の経路の違いかは未確定。判定不能として §8 に残す。
- CMP は CALL と重なる: 0x413c00・0x414c70・0x44f240 は CALL/EXCL の D と同一の D。CMP 側の判定は call 側の判定とは独立に数える。
- **IR 側の再照合 (work-m11 展開・HEAD `da286db`・PE/IR の sha256 は §2 と一致)**: 誤り 4 箇所 (新規) と判定不能の関数の IR 行を `boot_final3.ll` で確認した (行番号は IR ファイルの行)。
  - 0x44f040: 機械語 0x44f069 `mov rcx,[rcx]`・0x44f06c `test rcx,rcx` ↔ IR 行 156662 `%6 = icmp eq i64 %arg1, 0` → 誤り。
  - 0x44f2c0: 機械語 0x44f2cf `mov rcx,[rcx]`・0x44f2d2 `test rcx,rcx` ↔ IR 行 157016 `%1 = icmp eq i64 %arg1, 0` → 誤り。
  - 0x44fb40: 機械語 0x44fb71 `mov rcx,[rcx]`・0x44fb74 `test rcx,rcx` ↔ IR 行 157696 `%5 = icmp eq i64 %arg1, 0` → 誤り。
  - 0x4506e0: 機械語 0x4506f4 `mov rcx,[rcx]`・0x4506f7 `test rcx,rcx` ↔ IR 行 158601 `%1 = icmp eq ptr %arg1, null` → 誤り。
  - 判定不能 (0x12f9730・0x450420): IR の関数本体 (行 96769〜96951 (0x12f9730)・158471〜158511 (0x450420)) の icmp は、機械語の比較対象 (`**([rsp+0x38])+4` / arg3==0 の分岐後の `*arg1`) と 1 対 1 に対応しない (§6 の理由のとおり)。
  - 判定不能 (0x44f2c0 の word ループ・0x4506e0 の空白走査): IR の i16 の icmp (0x44f2c0 は行 157037 以降・0x4506e0 は行 158620 以降) は被演算子が `*argK` の要素に結べない (§6 の理由のとおり)。
  - 0x439f90: IR の関数本体 (行 136011〜136106) に `@function_414850(` の呼出し無し (§5 のとおり)。

## 7. 2502 の数字との差・測定 commit・検証

- 2502 (14 関数 / 16 箇所) → 3328 の CALL 11 関数 / 13 箇所 + EXCL 3 関数 / 3 箇所。除外した 3 件 (0x413c00・0x414c70・0x44f240) は REPORT_2555 §3 の偽陽性と一致。減った 3 件の内訳は再ロードの枠 0x413c5d・0x414cc7・0x44f25b (§3 の表)。
- 追加されたもの (新 kind): COPY 103 箇所 (49 関数) と CMP 20 箇所 (13 関数)。どちらも 2502 の数字とは別に数える。
- 測定 commit: `250df8f61` (IR 入力で件数を数えた commit。以後、走査 2 本・ldmach.py・pe_disasm_va.py は変えていない)。`git diff 250df8f61 HEAD -- tools/m11/ldfix/scan_spill_deref_3328.py tools/m11/ldfix/scan_spill_deref_2502.py tools/m11/ldfix/ldmach.py tools/m11/ldfix/pe_disasm_va.py` の出力は 0 行 (差分 0)。
- 参考: 初回測定 commit `f602f9354` から `250df8f61` までの走査スクリプトの差分 (`unused import` の削除と、CMP の docstring の `call の前` の削除。走査の判定は変えていない)。`git diff f602f9354 250df8f61 -- tools/m11/ldfix/scan_spill_deref_3328.py tools/m11/ldfix/scan_spill_deref_2502.py` の出力:
  ```diff
  -  CMP  : 比較側。S→L→D の後、Rb が call の前 (窓内・書換え前) に cmp/test で読まれる。
  +  CMP  : 比較側。S→L→D の後、Rb が書換え前 (窓内) に cmp/test で読まれる。call は無くてよい。
  -from collections import Counter
  ```
  (2502 の script は 0 行)
- 同じ差分の後で、判定の出力が変わらないことを確かめた。仮 IR (`ldmach.Machine(PE).fns` の全 57,816 関数を `define void @function_<VA>(i64 %arg1)` にした `$RUNNER_TEMP/m11_3328/synth.ll`) を、修正前と修正後の script で走査し、出力 JSON を `cmp` で比べた → 一致。件数は CALL 39 関数 67 箇所・EXCL 3 関数 3 箇所・CMP 31 関数 47 箇所・COPY 202 関数 336 箇所 (実行 36 s)。仮 IR の CALL + EXCL は 42 関数 / 70 箇所 (母集団が全 .pdata なので、IR 入力の 14 関数 / 16 箇所とは比較しない)。
- 仮 IR は IR 入力の代わりにならない。IR 入力 (`work-m11` の `boot_final3.ll`) での再測定は fix run (HEAD `250df8f61`) で実施し、§2 の件数と一致した。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| CMP 判定不能 9 箇所 (4 関数・§6 の表の「判定不能」の行: 0x12f9730 ×2・0x44f2c0 ×2・0x450420・0x4506e0 ×4)。0x450420 は IR の分岐と機械語の分岐が一致しない (§6) | 比較側の誤り候補が増減しうる | 本 PR の未解決表に残す (追跡 issue は立てない。WORKFLOW §3 の「未解決の追跡だけの子は起票しない」) |
| COPY 103 箇所 (49 関数) の IR 側判定。0x7888f0 の残り 2 箇所 (0x78890f・0x78892d) を含む | 複写経由の取りこぼしの数 | 子 #3382 [CI-153] |
| 0x439f90 の判定不能 (IR に 0x414850 の呼出し無し) の原因 (IR 欠落か経路の違い)。判定不能の定義 (§5) は本 REPORT で確定 | 1 箇所 | 追跡 issue なし (#2555 は CLOSED のため参照先にしない)。本 PR の未解決表に残す |
