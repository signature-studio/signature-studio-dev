# REPORT_1274 付録 — 5i (#2131)

## 5i. ON-only override の disp 除外による切り分け (#2131、測定 commit `c15a2907` = origin/main、ov.o 作り直し)

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開。`m11_gen_ir2.sh` rc=0 (34 s、ldfix=applied、F1=902、errors=0)。ON・OFF の build rc=0。
- 基準 (`SV_RAW=1`、全 942 unit): ON `ok 869 / oob 15 / abort 2 / halt0 7 / miss 47 / noproc 1 / other 1`、OFF `ok 870 / oob 16 / halt0 7 / miss 47 / noproc 1 / other 1`。§5 と一致。
- 変種 (`trap_triage/ablate_2131.py`、各変種で `ov.o` を作り直し、測定後に `m11_ov.c` を復元):

| 変種 (ON のまま外すもの) | ok / oob / halt0 | unit 190 |
|---|---|---|
| `41c130` の disp entry | 866 / 15 / 7 | oob |
| `9b4b00` の disp entry | 868 / 15 / 7 | oob |
| 両方 | 865 / 15 / 7 | oob |
| `413060` の C override (gate を `M11_OV_413060` のみに) | 868 / 16 / 6 | oob |

- 読み: 41c130・9b4b00 の disp、413060 の override は、単独でも両方でも unit 190 の oob を消さない。したがって ON で `407a50` の `[arg-8]` 参照先を変える書込元は、これら 3 つの override の中には無い。
- 未確定: 各変種は 1 回測定 (n=1)。残る候補は ON の build で変わる他の lift 本体 (`407a50` の呼出し先の書込み) と、ov.o 以外の gate。書込元の特定は未達 (受入条件 1・2 は未達、#2131 の次 run)。

## 5k. ON-only override の 4 要素同時除外と 410360 戻り値の切り分け (#2131 次 run)

- 記載上の測定 commit (出所未検証): `016cc403` (= origin/main)。
- 測定の実施: 下表の all_off・ret0_410360 の測定 run の run id と日付は記録されていない (本文書・PR・repo のどこにも残っていない)。測定時の素材の内訳も記録が無い。記録に残っている内容は「`m11_gen_ir2.sh` rc=0 (41 s、F1=902、errors=0)」のみである。
- 本 run の `$ARTIFACTS_DIR` には `fl-win64.tar.zst` (2.3 GB) しか実在せず、toolchain-retdec・toolchain-emsdk・work-m11 は無い。本 run では再測定していない。
- 基準 ON (`SV_RAW=1`、全 942 unit) の再測定は未実施。前 run の値 (`ok 869 / oob 15 / abort 2 / halt0 7`) は測定元が `a1d55799` 作業ツリーで、clean だった証跡が無く出所は未検証のため、本節の比較には使わない。`git diff a1d55799 016cc403 -- tools/m11` はビルド入力のコードに差分が無い (`REPORT_1676.md`・`REPORT_SHX-T27.md`・`store_watch_2217.sh` の 3 ファイル)。

| 変種 (ON のまま外すもの) | 測定 commit | ok / oob / abort / halt0 | unit 190 |
|---|---|---|---|
| `all_off`: 41c130 disp・9b4b00 disp・413060 gate・410360 vcall (`M11_NOVCALL=1`。shortcut 外の `ICALL_AT` dispatch だけ外れ、shortcut 内の icall 計数は残る) を同時に外す | 記載の `016cc403` は出所未検証 (run id 不明) | 869 / 16 / 2 / 6 (出所未検証) | oob (出所未検証) |
| `ret0_410360`: 410360 の C 版の戻り値だけ 0 にする | 記載上 `016cc403` (出所未検証) | 未測定 (記録上の記述・未検証: survey が 400 s で timeout) | 未測定 |

- 結論: 本節の測定結果は未確定。all_off の行は run id・日付・測定ログ・JSON のいずれも残っておらず、出所を示せないため、結論には使わない。「4 要素を同時に外しても oob は消えない」とは書かない。本節で確定しているのは、切り分けスクリプト (`ablate_2131.py` の `all_off`・`ret0_410360` 変種) の追加と、その変種の置換対象が `016cc403` の `m11_ov.c` と一致することまで。
- all_off の 869 / 16 / 2 / 6 が §5g の ON+NOVCALL 行 (`5229fe5f`、同じ値) と一致する点は、偶然の一致か、同値の取り違えかを判定できない。再測定まで比較に使わない。
- 基準 ON との unit 別比較は未実施。`ablate_2131.py` は変種ごとの JSON を引数で渡された出力先 (`OUT`) に書くが、all_off の JSON は repo に commit しておらず、`work/` にも残っていない。理由: 測定時の出力先 (`OUT`) を repo へ保存する手順を取らず、その作業ディレクトリも本 run には残っていない (記録が無いため、これ以上は確定できない)。このため `survey_diff` で比較できず、「halt0 から oob に移った 1 unit」の記述は採らず、移った unit の番号は未特定。unit 190 の結論 (oob のまま) には影響しない。
- `ret0_410360` は、記録上は survey が 400 s で timeout したと記載されている (記録上の記述・未検証)。通常時の所要時間は本 run で測っていないため、比較の根拠は無い。410360 の戻り値を 0 にすると、呼出し側が hang する可能性がある (推定。未検証)。原因は未切り分け。
- 測定に使った一時変更 (`all_off`・`ret0_410360` の define 差し替え) は本 PR の script にのみ残し、`m11_ov.c` は変更していない。
- 未達 (受入条件 1・2): ON の `407a50` の `[arg-8]` 参照先を変える書込元は未特定。次の候補は、ON の build で変わる `407a50` の呼出し先 (481790・412d60・4133f0) の書込み、または 410360 の戻り値 (呼出し側の観測) の扱い。

## 5j. origin/main での再現 (測定 commit `e082c4f1` = origin/main、#1274 再 run)

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開 (`FL_WIN64_DIR` = fl-win64 の展開先 `$RUNNER_TEMP/fl-win64`、`extracted/..` 形式は使わない)。`m11_gen_ir2.sh` rc=0 (F1=902、errors=0)。
- build: ON・OFF とも rc=0。ON は `ov.o` を作り直してから build、OFF も同様。
- survey: `SV_RAW=1 node survey_units.mjs` (全 942 unit)。JSON は `work/probe1274/{on,off}.json` (work/ 配下・commit 対象外)。

| build | ok / oob / abort / halt0 / miss / noproc / other |
|---|---|
| ON (`M11_OV_CLASSCREATE=1`) | 869 / 15 / 2 / 7 / 47 / 1 / 1 |
| OFF (`M11_OV_CLASSCREATE=0`) | 870 / 16 / 0 / 7 / 47 / 1 / 1 |

- `survey_diff.py` OFF→ON: ok 退行 unit は **190 の 1 件** (ok→oob)。kind 変化は 190 (ok→oob)・304・555 (oob→abort, #1275)。§2 と一致。
- 読み: 現 main で再現性は確認した。ただし本 run は trap 源の特定 (受入条件 1)・DEFECTS 類型への分類 (受入条件 2) には進めていない。ON の ok 退行 0 (受入条件 3) も未達 (unit 190 が残る)。
- 未達: 受入条件 1〜3 は未達のまま。起票先: #1642 (親 #1274)。

## 5k. origin/main での再現 (測定 commit `d33c763a` = origin/main、#1274 再 run・worktree ws-1274)

- 素材: fl-win64 (`FL_WIN64_DIR` = `$RUNNER_TEMP/fl-win64`)・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開。`m11_gen_ir2.sh` rc=0 (50 s、ldfix=applied、F1=902、errors=0)。
- 展開の注意: `work-m11` / `work-liftdiff` の tar は `tools/m11/work/` 等の相対パスを内包する。`-C tools/m11` で展開すると `tools/m11/tools/m11/work/` に二重化するため、`-C` を付けず repo 直下で展開する (本 run は誤展開後に移動して解消)。
- build: ON・OFF とも `ov.o` を作り直してから rc=0 (ON 24 s、OFF 19 s)。
- survey: 全 942 unit、`SV_RAW=1`、JSON は `work/probe1274/{on,off}.json` (work/ 配下・commit 対象外)。

| build | ok / oob / abort / halt0 / miss / noproc / other |
|---|---|
| ON (`M11_OV_CLASSCREATE=1`) | 869 / 15 / 2 / 7 / 47 / 1 / 1 |
| OFF (`M11_OV_CLASSCREATE=0`) | 870 / 16 / 0 / 7 / 47 / 1 / 1 |

- `survey_diff.py` OFF→ON: ok 退行 unit は **190 の 1 件** (ok→oob)。kind 変化は 190 (ok→oob)・304・555 (oob→abort, #1275)。§5j・§2 と一致。
- 読み: 現 main でも同じ数値が再現した。書込元の切り分け (ON-only override の除外や書込マスク) は本 run では未実施。§5h・§5i で否定済みの 3 要素 (9b4b00/9b5450 の書込み、41c130・9b4b00 の disp、413060 の override) を再実施しても新しい情報は得られないため、次の切り分けは別経路 (ON build で変わる lift 本体側の書込み、ov.o 以外の gate) に絞る必要がある。
- 未達: 受入条件 1 (書込元の特定)・2 (DEFECTS 類型への分類)・3 (ON の ok 退行 0: unit 190 が残る)。起票先: #1642 (親 #1274)。

## 5l. unit 190 の ON/OFF 分岐を同一メモリ状態で切り分ける (#2131 次 run・測定 commit `3b581236` = origin/main)

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開 (`FL_WIN64_DIR`=`$RUNNER_TEMP/fl-win64`、`RETDEC_ROOT`=`$RUNNER_TEMP/retdec`、`EMSDK`=`$RUNNER_TEMP/emsdk`)。`m11_gen_ir2.sh` rc=0 (51 s、ldfix=applied、F1=902、errors=0)。ON・OFF の build rc=0 (ov.o を毎回作り直した)。
- build 指紋 (fix round 2 の測定): ON (`M11_OV_CLASSCREATE=1`) の `m11_boot.cjs.wasm` sha256 `38d00710708d9b9cb1610648f8b4daa03db5d820daad47b30002e0ec2960a7f2`、OFF (`=0`) の `bb85e7ac0d69919a10791c24854bfac907ac3e468c0bb897a95ca8198c6c47ef`、`work/ir_conditions.json` の `ir_sha256` `b47a4d3a2555b74c8866d06794fb0b6a4535c4ac9d5a60015853975f512b70da`。IR の sha256 は実行ごとに変わるため、以下の raw 値はこの指紋の build でのみ成り立つ。
- 測定 commit: build 入力は `3b581236` から変えていない。fix round 2 で `trap_triage/lockstep_2131.mjs` の LS_FIX 行に `fix: diffPages now=` の出力を 1 行足した (診断のみ)。
- 測定: `trap_triage/lockstep_2131.mjs` (新規)。ON と OFF の wasm を同一プロセスの 2 インスタンスで unit 0..190 の順に並走させ、unit ごとに kind と HEAPU8 の差 (4 KiB ページ単位) と SP を比べる。survey_units.mjs と同じ呼出し順 (boot → unit 順、error 時のみ SP 復元)。
- 並走の基準 (強制なし、`LS_A=on LS_B=off LS_CKPT=189 LS_MAX=190 LS_TARGET=190 LS_MAXTESTS=0`、13 s): boot 直後の差分 2 ページ、unit 189 直後 24 ページ、SP は両者 `0x10a9fa10`、heap 長は両者 `1051590656`。unit 0..189 の kind 不一致 0 件、unit 190 は ON `oob` / OFF `ok`。
- 差分の出所: `0xfa5010` は unit 87 で最初に分かれる (値は IR に依存するため raw 値は書かない)。`0xfa5320` は unit 158 で最初に分かれる (ON `0x10bbe510` / OFF `0x10bbe5a0`、差 0x90。上の指紋の build で再現)。`0xfa5320` は 407a50 の chain が読むリスト先頭。

### 同一状態の切り分け (unit 189 直後のメモリと SP を揃えて unit 190 だけ走らせる)

- 測定: 表の各行を fix round 2 で 1 回ずつ実測した (n=1)。共通 env は `LS_CKPT=189 LS_MAX=190 LS_TARGET=190 LS_MAXTESTS=0`。`LS_A`・`LS_B` は行ごとに表の列のとおり。「強制後 diffPages now=」は lockstep が unit 189 の直後 (強制の直後・unit 190 の直前) に出力した値。
- 「強制」列の `LS_FORCEB` は A の差分ページと SP を B へ写す。`LS_REVERSE` は B の差分ページを A へ写す。`LS_FIX` は A の指定 u32 だけを B の値へ書き換える (ページ全体は写さない)。
- 「0..189 の不一致」は unit 0..189 で A と B の kind が違った unit の件数 (括弧内は unit 番号と kind)。

| 行 | 状態 (189 直後) | unit 190 を走らせる code | `LS_A` / `LS_B` | 強制 | コピーしたページ | 強制後 diffPages now= | unit 190 (A / B) | 0..189 の不一致 | n |
|---|---|---|---|---|---|---|---|---|---|
| 1 | OFF | ON | A=on, B=off | `LS_REVERSE=1` | 24 | 0 | oob / ok | 0 | 1 |
| 2 | ON | OFF | A=on, B=off | `LS_FORCEB=1` | 24 | 0 | oob / ok | 0 | 1 |
| 3 | OFF | vz | A=off, B=vz | `LS_FORCEB=1` | 11 | 0 | ok / oob | 0 | 1 |
| 4 | OFF | vy | A=off, B=vy | `LS_FORCEB=1` | 3 | 0 | ok / ok | 0 | 1 |
| 5 | OFF | vx | A=off, B=vx | `LS_FORCEB=1` | 3 | 0 | ok / ok | 0 | 1 |
| 6 | OFF | vall | A=off, B=vall | `LS_FORCEB=1` | 11 | 0 | ok / oob | 0 | 1 |
| 7 | ON | vall | A=on, B=vall | `LS_FORCEB=1` | 23 | 0 | oob / oob | 0 | 1 |
| 8 | ON | v413 | A=on, B=v413 | `LS_FORCEB=1` | 17 | 0 | oob / oob | 1 (unit 15: ok / miss) | 1 |
| 9 | ON | vnc | A=on, B=vnc | `LS_FORCEB=1` | 15 | 0 | oob / oob | 0 | 1 |
| 10 | ON | vdisp | A=on, B=vdisp | `LS_FORCEB=1` | 13 | 0 | oob / oob | 3 (unit 42・45・138: ok / miss) | 1 |
| 11 | ON | vx | A=on, B=vx | `LS_FORCEB=1` | 24 | 0 | oob / ok | 0 | 1 |
| 12 | ON | vy | A=on, B=vy | `LS_FORCEB=1` | 24 | 0 | oob / ok | 0 | 1 |
| 13 | ON | vz | A=on, B=vz | `LS_FORCEB=1` | 23 | 0 | oob / oob | 0 | 1 |
| 14 | ON (2 語だけ書換え) | ON | A=on, B=off | `LS_FIX=fa5320,fa5010` (A の 2 語だけ) | — | 23 (fix 直後の実測。2 語は同じ 4 KiB ページ `0xfa5000` 内) | oob / — | 0 | 1 |

- variant の定義は `trap_triage/variants_2131.py` (vdisp: 41c130・9b4b00 の disp entry を外す / v413: 413060 の C override を外す / vnc: 410360 の `m11_vcall` で shortcut (`target == R(0x10070)`) 以外の `ICALL_AT` dispatch だけを外す (`M11_NOVCALL=1`。shortcut 内の icall_bump 2 回は残る) / vall: vdisp+v413+vnc (shortcut 内の icall 計数は残る) / vx: vdisp+v413 で 410360 の本体を `return inst;` だけにする (VMT 読みも計数も外す) / vy: vdisp+v413 で 410360 の VMT 読み `Q(Q(inst)-0x50)` だけ残す / vz: vdisp+v413 で 410360 の `m11_vcall` の shortcut 内の icall_bump 2 回だけ残す (target は `R(0x10070)`))。
- 読み (表の実測・n=1): 行 1・2 で状態と code を入れ替えても結果は code で決まる (ON 状態 + OFF code は ok、OFF 状態 + ON code は oob)。行 3・4・5 (OFF 状態) と行 11・12・13 (ON 状態) を合わせると、vz (shortcut 内の icall 計数だけ残す) は oob、vy (VMT 読みだけ残す) と vx (両方外す) は ok。よって trap を起こすのは 410360 の shortcut 内の icall 計数 (`icall_bump` 2 回) で、VMT 読みだけでは起きない、と読める。計数が trap を起こす仕組みは未特定。
- vnc (shortcut 外の `ICALL_AT` dispatch だけ外す) でも ON は oob のまま (行 9) なので、trace の `inst=0xe660` の経路 (下の補助) は trap の必要条件ではない、と読める。
- vall は計数を残すため、vall からは計数の必要性は判定できない。判定に使うのは vz (計数のみ) / vy (VMT 読みのみ) / vx (両方なし) の比較。
- 注意: 差分ページを移す試験は 2 つの build のメモリを比べるため、build 間で配置の違うページを含みうる。boot 直後の差分ページの中身は補助の項を参照 (文字列の配置差ではない)。`0x10250000` 単独を写す試験は未実施のため、その寄与は未確認。`0xfa5320` を OFF の値へ直しても ON の trap は消えない (行 14) ので、リスト先頭の 0x90 ずれ単独では説明できない。

### 補助 (unit 158 と unit 190 の ON 専用 code の実行・boot 直後の差分)

- `ov_2131_trace.patch` を当てた ON build (instrumented、この run で build rc=0) では、差分が boot 直後 14 ページ・unit 189 直後 57 ページ、SP `0x10a9fab0` (OFF `0x10a9fa10`) になる。unit 190 は A=oob / B=ok。補助としてのみ使う。
  - unit 158 (`LS_TRACE=<dir> LS_TRACE_U=158`): ON 専用の `410360` が 17 回、`413060` (C 版 UStrFromPWCharLen) が 28 回。
  - unit 190: `410360` が 3 回 (うち 1 回は `inst=0xe660`。直後に `vcall-ret0` を経て `icall 0xf960`)、`413060` が 11 回。`41c130`・`9b4b00`・`9b5450` は走らない。
  - unit 190 の UStrAsg (`trace_on_190.txt` / `trace_off_190.txt` を数えた): ON (instrumented) 16 行、OFF 18 行。先頭行から dest・src が違う (ON `dest=0x10a9f8b8 src=0x38b00030` / OFF `dest=0x10a9f818 src=0x0`)。前の記述 (6 件目まで一致) は再現しなかったので取り下げる。
- v413 (`413060` の gate を外した ON 版) の並走: A=off, B=v413 では unit 15 が ok→miss (A=ok / B=miss)。`0xfa5320` は unit 190 まで一致 (DIFF 0 件、値は両方 `0x10bbe630`)。unit 190 は B (v413) で oob。0x90 のずれは 413060 の override が作るが、v413 は別の差 (unit 15) を持つため、ここでは trap の原因と結論しない。
- `boot_probe_2131.mjs` (新規・この run): boot 直後の差分ページは 2 (`0x10250000`・`0x10251000`)。`0x10250000` の先頭 96 バイトの ASCII は ON/OFF で同一 (両方とも `[m11][stub-notimpl] %s called` を含む)。差分は 8 バイト値の 19 スロット (例 `+0x320`: ON `0x1cf900000000` / OFF `0x1cf700000000`) で、文字列の配置差ではない。

### 結論 (部分達成)

- 実測の結論 (fix round 2、n=1、強制後 diffPages=0 を全行で確認。FIX 行は 23): unit 190 の ON 限定の trap は、同じメモリ状態 (unit 189 直後、SP 一致) で ON 専用 code を走らせたときだけ起きる、と読める。ON 専用 code のうち、410360 の m11_vcall の shortcut 内の icall 計数 (`icall_bump`) だけで OFF の状態から oob が再現する (行 3)。VMT 読みだけでは再現しない (行 4・5)。反復は n=1 のため、再現性の確認は別途必要。
- 未確定: icall 計数がなぜ oob を起こすか (計数表 `g_isite`・`g_itgt` の linear memory 上の位置と、407a50 の chain・スタックとの重なり)。`0xfa5320` の 0x90 ずれは 413060 override 由来 (v413 で消える) だが、単独では trap の原因ではない (行 14)。
- 受入条件: 1 (書込元の特定) は未達。2 (REPORT 記録) は本節で部分達成 (表の作り方・env・強制後 diffPages・n を記録)。3 (ok 退行 0) は未達 (unit 190 が残る)。

### 次 run の作業 (起票先 #2131)

- (a) `g_isite`・`g_itgt` の表 (`_e`・`_h`・`n`) の linear address を vz の build で特定し、unit 190 中の計数書込みの address を watch する (watch 版は挙動が変わるので、書込みの address だけを見る)。
- (b) vz の oob の frame (`SV_RAW=1` の生 frame) を、410360 の icall_bump の前後で比べ、どの load/store が範囲外かを切り分ける。
- (c) 0xfa5010 (unit 87) の値の出所 (build 間の定数配置か、実行時の書込みか) を、unit 87 の trace で切り分ける。
- (d) 410360 の呼出元で `this` が誤っている候補: trace の `inst=0xe660` は `M11_LB_BASE=0` (LVA=RVA) では image 内 (RVA 0xe660) を指し、ヒープ上のインスタンスには見えない。`icall 0xf960` の経路 (shortcut 外) は vnc で外れても ON は oob のままなので trap の必要条件ではないと読めるが、この `this` の出所は未確認で、否定もしていない。(a)〜(c) と合わせ、410360 の呼出元で `this` の値を記録して確かめる。
- (e) 表の再測定: fix round 2 で実施済み (上の表の作り方・env・強制後 diffPages・n を記録)。

### 差分 (測定 commit `3b581236` から本 PR の HEAD まで、tools/m11 の build 入力)

- `git diff 3b581236 HEAD -- tools/m11 ':(exclude)*.md'` の対象は本 PR で追加した `trap_triage/lockstep_2131.mjs`・`boot_probe_2131.mjs`・`variants_2131.py`・`ov_2131_trace.patch` の 4 ファイルのみ。`m11_ov.c` ほか build 入力は測定 commit から変えていない (作業ツリーで一時的に変えた `m11_ov.c` は各 variant・trace build の後に元へ戻した)。
