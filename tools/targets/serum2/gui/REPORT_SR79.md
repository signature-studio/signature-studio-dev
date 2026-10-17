# REPORT — [SR-79 #4610] Serum 2 `0x1803573f0` の呼出元で、レジスタ値の間接 call の宛先を解決する (部分達成)

- 日付: 2026-10-15 / 親: #4484 (SR-76) / 前段: `REPORT_SR76.md` §5 (a)・§4 / 対象: `0x1803573f0` (`+0x20408` の書込元)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。FLEngine 起動・GUI は**動かしていない** (製品 KPI は測っていない)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` (REPORT_SR76 §1 と一致)。作業用 dir はリポジトリ外。
- 測定 commit (解析に使ったコード): `bcf0a20a3` (全経路版の `reg_call_resolve.py` の最後の解析ロジック変更)。後続の `e133faa04` は REPORT のみ。後続の修正 commit は docstring の限界記述だけを変え、解析ロジックは変えていない (§1.4)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `call reg`・`call [rsp+disp]` の宛先を定義元まで遡って解決する (解決不能は未解決として数える) | **部分達成**。`call reg` 1058 件・`call [rsp+disp]` 10 件 (計 1068 サイト) のうち 98 件を解決、970 件は未解決 (全経路版・§1.2)。解決した 98 件の宛先はいずれも R (`0x1803573f0` の direct 逆閉包 8 関数) に当たらない |
| 2. 1 の結果を含めて、setState 閉包 `0x1800c2b50`・getState 閉包 `0x1800c6090` と demo bit 関数 (`0x22792` を参照する関数) との交わりを示す | **部分達成**。C∩R = 0 (setState・getState とも)。demo bit 関数 2 件 (`0x1800c2b50`・`0x1800c6090`) は根そのもので、閉包との交わりは根自身のみ (demo∩C = 1)。C 内の未解決サイトは setState 28 件・getState 25 件あり、『交わり 0』はこれらを含めた完全な結論ではない (§3)。幅の広いスタック書込みの kill 漏れは修正済み (§1.4・結果は変わらず) |
| 3. REPORT に測定 commit と再現手順 | **達成** (§1・§5) |

**このため、本 REPORT は『R への経路が無い』とは主張しない。** 解決できた範囲と、未解決が残る範囲を分けて示す。

現行の測定値は §1.2 (全経路版・`bcf0a20a3`) が正本。§1 の md5 と所要時間は前版 (`d7d352b84`) の実測で、比較用に残す。

## 1. 再現手順と実測

```sh
# S: リポジトリ外の作業用 dir (例: $RUNNER_TEMP/s76)。P: tools/targets/serum2/gui
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/reg_call_resolve.py Serum2_win64.vst3 0x1803573f0 0x1800c2b50
venv/bin/python $P/reg_call_resolve.py Serum2_win64.vst3 0x1803573f0 0x1800c6090
```

| 実行 | 所要時間 (実測 wall) | 結果 |
|---|---|---|
| `reg_call_resolve.py` root `0x1800c2b50` (HEAD `d7d352b84`) | 10.24 秒 (user 10.08 秒) | rc 0。出力 md5 `40ba80074d23f2a91fed83ec281372c2` |
| `reg_call_resolve.py` root `0x1800c6090` (HEAD `d7d352b84`) | 10.17 秒 (user 9.96 秒) | rc 0。出力 md5 `2f0232a61d4c13c904f2c1a1bb8a15a3` |

実行前後の load average: 0.30 → 0.50 (1 分平均)。同 run 内で逐次実行。同一入力での再実行 (コミット前の版) でも出力 md5 は一致した。

### 1.1 前版 (`d7d352b84`) の解決ロジックの限界 (§1.2 で全経路化して修正)

- `resolve()` は分岐命令 (j*) とラベルを無視し、直前の 1 経路だけを後ろ向きに辿る。分岐の合流点で別経路の定義は見ていない。例: `mov rax, A; jne L; mov rax, B; L: call rax` は B だけを返す。したがって「解決 120」には合流を跨いで決めた宛先が含まれ、合流の他経路は未検証。
- `,` を含まない 1 オペランド命令 (inc/dec/neg/not/cdqe など) は読み飛ばす。これらは対象レジスタを変えるため、定義元の探索が 1 つ前の定義に届く場合がある (未検証)。
- 再測定は `plugins-serum2` の素材が要るため、本 PR では行っていない。上記の限界は、コードを直して再測定するまで『解決 120』の正確さを保証しない。

### 1.2 全経路化の再測定 (測定 commit `bcf0a20a3`・本 PR で修正済み)

`resolve()` を制御フローの全経路 (fall-through と direct jmp/jcc の逆辺) を辿る版に変えた。全経路が同じ値集合に解決したときだけ解決とする。部分レジスタ書込みと `xchg`/`mul`/`cdqe` 等も定義とみなす。間接 jmp (jump table) を含む関数は、逆辺を確定できないため全サイトを未解決にした (保守的)。

| 実行 (HEAD `bcf0a20a3`) | 所要時間 (wall) | 結果 |
|---|---|---|
| root `0x1800c2b50` | 7.13 秒 (user 7.01 秒) | rc 0。出力 md5 `37bf708239c5788e5a3a36ff174fe097` |
| root `0x1800c6090` | 7.38 秒 (user 7.26 秒) | rc 0。出力 md5 `a79105a0a6051b84a29a9236b2061c74` |

前版 (`d7d352b84`) との差 (同じ入力・同じ load 帯):

| 項目 | 前版 setState / getState | 全経路版 setState / getState |
|---|---|---|
| 解決サイト | 120 / 120 | 98 / 98 |
| 未解決サイト | 948 / 948 | 970 / 970 |
| 解決のうち R に当たる数 | 0 / 0 | 0 / 0 |
| C 内の未解決サイト | 28 (13 関数) / 25 (7 関数) | 28 (13 関数) / 25 (7 関数) |
| C∩R | 0 / 0 | 0 / 0 |
| demo∩C | 1 / 1 | 1 / 1 |

- 解決が 22 件減ったのは、前版が分岐の合流を跨いで 1 経路の値を採っていた分と解釈する (経路の全部を見ていない値を採らない方針の結果)。どの 22 件が誤っていたかは、個別には確認していない (未検証)。
- 間接 jmp を含む関数は 1128 件 (うち jump table の `jmp rdx` が 1137 箇所)。これらの関数の全サイトを未解決に数えた。jump table を解読すれば、この分の解決が戻る可能性がある (未了)。
- 結論は変わらない: 解決したどの宛先も R に当たらない。『C∩R = 0』は、未解決 948 → 970 サイトを含めた完全な結論ではない。

### 1.4 スタック書込みの kill 規則の修正 (測定 commit `ab5de1f01`・本 PR で修正済み)

- 修正前の kill は、宛先に `[rsp + disp]` を文字列として含む命令だけだった。範囲で重なる幅の広い書込み (例: `movups xmmword ptr [rsp + 0x58]` が `[rsp+0x60]` を含む) は kill されず、古い値を解決したままになりうる、という限界があった。
- 修正後の kill: `qword ptr [rsp + disp]` と完全一致する mov 以外で、宛先が `[rsp` を含む命令 (幅の広い書込みを含む)・`push`/`pop`・`rsp` 自体への書込みをすべて kill とする。
- 結果: 両 root とも出力 md5 が修正前と一致 (§1.5)。修正前後で解決集合が変わらなかったので、幅の広い書込みによる誤った解決は現行の解決 98 件に無かったことになる (kill は解決を未解決へ倒す方向にしか働かないため)。ただし、残る 98 件の宛先そのものが正しいことの検証ではない。

### 1.5 kill 規則修正後の再測定 (測定 commit `ab5de1f01`)

| 実行 (HEAD `ab5de1f01`) | 所要時間 (wall) | 結果 |
|---|---|---|
| root `0x1800c2b50` | 7.24 秒 (user 7.12 秒) | rc 0。出力 md5 `37bf708239c5788e5a3a36ff174fe097` (修正前と同一) |
| root `0x1800c6090` | 7.04 秒 (user 6.92 秒) | rc 0。出力 md5 `a79105a0a6051b84a29a9236b2061c74` (修正前と同一) |

load average: 0.64 → 0.72 (1 分平均、同 run 内で逐次実行)。両 root とも、解決 98・未解決 970・R に当たる解決 0・C∩R=0 は §1.2 と同じ。

### 1.6 jump table の解読 (測定 commit: 本 PR の最終 commit・HEAD と同一)

- `jmp R` の直前が `lea B,[rip+X]`・`cmp I,N; ja`・`movsxd R,[B+I*4]`・`add R,B` の型なら、表の N+1 項の遷移先を、関数内の命令境界に当たるときだけ制御フローの辺として採る (`jump_table_targets`)。
- 結果: 解読 300 表。間接 jmp を含む関数は 1128 → 938。ただし呼出サイトの解決は 98 のまま (解決 98・未解決 970)。解決が増えなかったのは、残る 938 関数の間接 jmp が pop 後の `jmp rax` (末尾呼出し) 型で、表の型に合わないため。
- 試した別案 (採用せず): pop 後の `jmp` を関数外への抜けとみなす案は、解決 99 (+1) しか増やさず、『関数外へ抜ける』仮定自体が未検証のため、コードから外した。
- 再測定 (HEAD・同一 md5 を 2 回確認): setState `0x1800c2b50` 12.04 秒 (md5 `096d72ac…`)・getState `0x1800c6090` 12.09 秒 (md5 `6c8e006c…`)。load 0.54〜0.64。前版の md5 (`37bf7082…`・`a79105a0…`) とは、表の遷移辺を加えたため異なる。
- 解決 98・R に当たる解決 0・C∩R=0・demo∩C=1 は変わらない。

### 1.3 残作業 (#4610 継続)

- 間接 jmp 関数 938 件の全サイト未解決 (§1.6)。pop 後の `jmp rax` 型の遷移先 (末尾呼出し先・関数外か内か) を解読すれば、その分を戻せる。(§1.4 の kill 修正は済み)
- C 内の未解決 28・25 サイトの供給元の個別解決 (`load[reg+other]`・`after-call`・`stack-arg`・`indirect-jmp-fn`)。
- disp がスロット途中の vptr で R に届くかの検証 (§3 (c))。

## 2. 解決の結果 (両 root 共通)

| 項目 | setState `0x1800c2b50` | getState `0x1800c6090` |
|---|---|---|
| R (`0x1803573f0` の direct 逆閉包) | 8 | 8 |
| C (root から direct call/jmp で到達する関数) | 854 | 291 |
| C∩R | 0 | 0 |
| サイト (call reg 1058・call [rsp+disp] 10) の解決 | 98 解決・970 未解決 (§1.2) | 同左 |
| 解決サイトのうち宛先が R に当たる数 | 0 | 0 |
| C 内の未解決サイト (関数数) | 28 (13) | 25 (7) |
| demo bit 関数 ∩ C | 1 (根自身) | 1 (根自身) |

解決ロジックは `reg_call_resolve.py` の `resolve()` (全経路版)。制御フローの全経路 (fall-through と direct jmp/jcc の逆辺) を後ろ向きに辿り、全経路が同じ値集合に解決したときだけ解決とする。`lea rip`・`mov reg, [rip+X]`・`mov reg, [reg2+off]` を解決し、呼出しを跨ぐ場合は volatile レジスタ (rax/rcx/rdx/r8-r11) だけ未解決にする。`call [rsp+disp]` は、同じ disp への各経路の直前の `mov` から辿る (kill 規則は §1.4)。

## 3. 未解決の内訳 (C 内)

| 供給元 | setState (28) | getState (25) |
|---|---|---|
| `load[reg+other]` (vtable 読みだが disp が 0x28・0x60 以外) | 19 | 12 |
| `after-call` (呼出し後の callee-saved レジスタ) | 6 | 7 |
| `stack-slot`・`stack-arg` (スタック渡し) | 2 | 4 |
| その他 (`sub`・`cmove`) | 1 | 2 |

- `load[reg+other]` の disp は 0x30・0x38・0x50・0x58 など。R のスロットの disp (0x28・0x60) とは一致しない。ただし vptr がスロットの途中を指す場合は別の disp でも R に届きうるため、『R に届かない』とは言えない (未検証)。
- `after-call` は、呼出し後も生きる callee-saved レジスタ (rbx・rsi・rdi・r12-r15) を、呼出し前の定義元まで辿れなかったもの。
- `stack-arg` の `call [rsp+0x60]` (`0x180571e89`・`0x180571ea9`) は、直前で `[rsp+0x60]` へ書かれる値を辿れていない。

## 4. R の関数アドレスの出現形

- `.text` 中の即値で R のアドレス (絶対 VA・RVA 一致) に当たるのは 8 件。すべて R 内・R への direct call の即値 (`call 0x...`)。
- R の関数アドレスを rip 相対で materialise する箇所は 0 件 (REPORT_SR76 §4 と一致)。
- したがって、R の関数ポインタがコード上に現れるのは `.rdata`/`.data` の vtable スロット 3 件 (`0x180a24030`・`0x180a240a8`・`0x180a24180`) だけ。

## 5. demo bit 関数 (`0x1800c2b50`・`0x1800c6090`) の間接 call

- `0x1800c2b50`: 非 direct call 1 件 `call qword ptr [rax + 0x30]` (`0x1800c2f05`)。
- `0x1800c6090`: 非 direct call 2 件 `call qword ptr [rdx + 0xe8]` (`0x1800c67b8`)・`call qword ptr [rax + 0x20]` (`0x1800c68ee`)。
- いずれの disp も R のスロット disp (0x28・0x60) と一致しない。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) `call reg`・`call [rsp+disp]` の 970 サイト (全体)。解決は 98 サイトのみ (§1.2) | 受入 1・2 の『交わり 0』は未解決サイトを含めた完全な結論ではない | #4610 (本 issue を継続) |
| (b) C 内の未解決 28 (setState)・25 (getState) サイトの供給元。`load[reg+other]`・`after-call`・`stack-arg` の個別解決 | 受入 2 の『C∩R = 0』が、これらのサイトを通る経路を除外できていない | #4610 (本 issue を継続) |
| (c) `load[reg+other]` の disp が vptr のスロット途中 (MI・別 vtable) を指す場合に R へ届くか | 一部検証 (SR-102 #6182・§6.1)。disp 0x58 の 2 候補 vptr だけが R を指すが、呼出しの receiver との結び付きが未了。残り 7 件は R を指す候補なし | #6182 (本 issue を継続) |
| (d) demo bit 関数が .text で 2 件 (根のみ) しかない。`0x22792` の読出しは別経路 (オブジェクト経由の間接読出し) の可能性 (REPORT_SR76 §5(b) と同じ) | 『demo∩C』の意味が根自身だけになる | #4610 (本 issue を継続) |

## 6.1 SR-102 (#6182): `load[reg+other]` 18 件の disp と vptr の対応 (§6(c))

- 測定 commit: `993bd8750` (分類の修正と `vt_disp_match.py` の追加)。素材: `plugins-serum2` の `Serum2.vst3` (sha256 `501e7bb3…`)。静的解析のみ。
- 分類の修正: `provenance()` が `[rip+X]` の global 読みを `load[reg+other]` と誤分類していた (`mem_re` が rip をベースレジスタとして拾う)。並べ替えで `global-load` に分けた。解決結果は不変 (解決 98・未解決 970・C∩R=0)。
- setState の `load[reg+other]` は 18 → 9。9 件は `global-load` (下記 (1))。残りは vtable 読み 7 件と、オブジェクトの関数ポインタ欄 2 件。

| 件 | 件数 | 結果 | 判定 |
|---|---|---|---|
| (1) `[rip+X]` の global 読み `0x1817bf760` (`.data`、PE の raw 外・初期値 0) | 9 (setState) | 同一の global を読む。コード中の書込みは 0 件 | **未解決**: 実行時に設定される値は静的に見えない |
| (2) vtable 読み disp 0x30 (`0x1801054fc`・`0x18010561d`) | 2 | `lea rip` で構築される候補 vptr V で V+0x30 が R の関数を指すものは 0 | **R に届く候補なし** |
| (3) vtable 読み disp 0x38 (`0x1801055de`・`0x18010567e`) | 2 | 同上 0 | **R に届く候補なし** |
| (4) vtable 読み disp 0x50 (`0x18048bbb9`) | 1 | 同上 0 | **R に届く候補なし** |
| (5) vtable 読み disp 0x58 (`0x18048bba5`) | 1 | 候補 2 件: `0x180a23fd8`・`0x180a24128` (どちらも `0x18003dcf0` の constructor が `lea rip` で構築) が R の `0x180064d60`・`0x1800506b0` を指す | **未解決**: 呼出し元の receiver (`rdi` = 関数の `this` 引数) と候補の結び付きが未了 |
| (6) vtable 読み disp 0x2f8 (`0x18048bb55`) | 1 | 同上 0 | **R に届く候補なし** |
| (7) オブジェクトの関数ポインタ欄 `[obj+0x6ac8]`・`[obj+0x6ad0]` (`0x18020ad9f`・`0x18020c861`) | 2 | vtable ではないため disp と vptr の対応を取る対象外 | **未解決** (供給元は別経路) |

- 注: (2)〜(6) の『候補なし』は、`lea rip` で構築される vptr に限った結果。データ中の定数 vptr・別経路の書込みは見ていない。
- 再現: `vt_disp_match.py <Serum2.vst3> 0x1803573f0 0x30 0x38 0x50 0x58 0x2f8` (実測 9.4 秒・load 0.2〜0.5)。
- 結論: disp と vptr の対応は、disp 0x58 の 2 候補を除き候補 0 で、R に届く経路は見つからなかった。ただし、0x58 の結び付き・global `0x1817bf760` の実行時値は未確定で、『R に届かない』とは主張しない。
- 起動・GUI: 静的解析のみ。FLEngine 起動・GUI は**動かしていない** (製品 KPI は測っていない)。

## 7. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。
