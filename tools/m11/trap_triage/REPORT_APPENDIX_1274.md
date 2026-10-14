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

- 素材: fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開 (`FL_WIN64_DIR`=`$RUNNER_TEMP/fl-win64`、`RETDEC_ROOT`=`$RUNNER_TEMP/retdec`、`EMSDK`=`$RUNNER_TEMP/emsdk`)。`m11_gen_ir2.sh` rc=0 (33 s、ldfix=applied、F1=902、errors=0)。ON・OFF の build rc=0 (ov.o を毎回作り直した)。
- 測定: `trap_triage/lockstep_2131.mjs` (新規)。ON と OFF の wasm を同一プロセスの 2 インスタンスで unit 0..190 の順に並走させ、unit ごとに kind と HEAPU8 の差 (4 KiB ページ単位) と SP を比べる。survey_units.mjs と同じ呼出し順 (boot → unit 順、error 時のみ SP 復元)。
- 並走の再現: unit 0..189 は ON/OFF の kind が全て一致 (不一致 0 件)。unit 190 は ON `oob` / OFF `ok` (全体 survey の値と一致)。
- 差分の出所: boot 直後の差分は 2 ページ (`0x10250000`-`0x10252000`)。unit 189 直後は 24 ページ、SP は両者 `0x10a9fa10`、heap 長は両者 `1051590656` で一致。`0xfa5010` は unit 87 で最初に分かれ (ON `0x26ec19` / OFF `0x26ec76`)、`0xfa5320` は unit 158 で最初に分かれる (ON `0x10bbe510` / OFF `0x10bbe5a0`、差 0x90)。`0xfa5320` は 407a50 の chain が読むリスト先頭。

### 同一状態の切り分け (unit 189 直後のメモリと SP を揃えて unit 190 だけ走らせる)

記録の範囲: 下表の「作り方」は `lockstep_2131.mjs`・`variants_2131.py` の分岐から書いた想定である。本測定で実際に渡した env (`LS_*` の値)・反復回数 n・強制後の `diffPages now=` の出力は記録が無い。よって本表は「記録上の結果」であり、同一状態の確認は未検証。`LS_FORCEB`・`LS_REVERSE` は差分ページを全て写すため、強制後の diffPages は構造上 0 になる (heap 長が違えば `heap length differs` が出る)。その出力の記録は無い。

| 状態 (189 直後) | code | unit 190 | 作り方 (スクリプト上の想定・env 未記録) | 強制後 diffPages now= | n |
|---|---|---|---|---|---|
| OFF の状態 | OFF | ok | 並走の B の自然な状態 (強制なし。checkpoint 189 の差分は 24 ページ) | 強制なし | 未記録 |
| ON の状態 | ON | oob | 並走の A の自然な状態 (強制なし) | 強制なし | 未記録 |
| ON の差分 24 ページを OFF へ (状態は ON と一致) | OFF | ok | `LS_FORCEB=1` (A=ON の差分ページと SP を B=OFF へ写す) | 未記録 (構造上 0) | 未記録 |
| OFF の差分ページを ON へ (状態は OFF と一致) | ON | oob | `LS_REVERSE=1` (B=OFF の差分ページを A=ON へ写す) | 未記録 (構造上 0) | 未記録 |
| ON の状態のまま、`0xfa5320`・`0xfa5010` の 2 語だけ OFF の値へ | ON | oob | `LS_FIX=fa5320,fa5010` (checkpoint 189 で A の 2 語へ B の値) | 0 にならない。2 語は同じ 4 KiB ページ `0xfa5000` 内にあり、差分 24 ページのうち高々 1 ページしか解消しないため、23 ページ以上が残る。同一状態の行ではない | 未記録 |
| OFF の状態 | vall | oob | `LS_FORCEB=1` (A=OFF、B=vall) | 未記録 (構造上 0) | 未記録 |
| ON の状態 | vall | oob | `LS_FORCEB=1` (A=ON、B=vall) | 未記録 (構造上 0) | 未記録 |
| ON の状態 | v413 | oob | `LS_FORCEB=1` (A=ON、B=v413) | 未記録 (構造上 0) | 未記録 |
| ON の状態 | vnc | oob | `LS_FORCEB=1` (A=ON、B=vnc) | 未記録 (構造上 0) | 未記録 |
| ON の状態 | vdisp | oob | `LS_FORCEB=1` (A=ON、B=vdisp) | 未記録 (構造上 0) | 未記録 |
| ON の状態 | vx | ok | `LS_FORCEB=1` (A=ON、B=vx) | 未記録 (構造上 0) | 未記録 |
| OFF の状態 | vx | ok | `LS_FORCEB=1` (A=OFF、B=vx) | 未記録 (構造上 0) | 未記録 |
| OFF の状態 | vy | ok | `LS_FORCEB=1` (A=OFF、B=vy) | 未記録 (構造上 0) | 未記録 |
| OFF の状態 | vz | oob | `LS_FORCEB=1` (A=OFF、B=vz) | 未記録 (構造上 0) | 未記録 |

- variant の定義は `trap_triage/variants_2131.py` (vdisp: 41c130・9b4b00 の disp entry を外す / v413: 413060 の C override を外す / vnc: 410360 の `m11_vcall` で shortcut (`target == R(0x10070)`) 以外の `ICALL_AT` dispatch だけを外す (`M11_NOVCALL=1`。shortcut 内の icall_bump 2 回は残る) / vall: vdisp+v413+vnc (shortcut 内の icall 計数は残る) / vx: vdisp+v413 で 410360 の本体を `return inst;` だけにする (VMT 読みも計数も外す) / vy: vdisp+v413 で 410360 の VMT 読み `Q(Q(inst)-0x50)` だけ残す / vz: vdisp+v413 で 410360 の `m11_vcall` の shortcut 内の icall_bump 2 回だけ残す (target は `R(0x10070)`))。
- 読み (記録上の結果。同一状態の確認値は未記録のため、下表の注を参照): 状態と code を入れ替えても、結果は code で決まる (ON の状態 + OFF code は ok、OFF の状態 + ON code は oob)。vx・vy・vz はいずれも vdisp+v413 を含む。その下で、vz (shortcut 内の icall 計数だけ残す) は oob、vy (VMT 読みだけ残す) は ok、vx (両方外す) は ok。よって、trap を起こすのは 410360 の shortcut 内の icall 計数 (`icall_bump` 2 回) で、VMT 読みだけでは起きない、と読める。計数が trap を起こす仕組みは未特定。
- vnc (shortcut 外の `ICALL_AT` dispatch だけ外す) でも ON は oob のままなので、trace の `inst=0xe660` の経路 (`icall 0xf960`、shortcut 外) は trap の必要条件ではない、と読める。
- vall は計数を残すため、vall からは計数の必要性は判定できない。判定に使うのは vz (計数のみ) / vy (VMT 読みのみ) / vx (両方なし) の比較。
- 注意: 差分ページを移す試験は 2 つの build のメモリを比べるため、build 間でデータ配置が違うページ (例: `0x10250000` の文字列定数。boot 直後の差分 2 ページの中身が ON と OFF で違うことは `boot_probe_2131.mjs` の出力で記録した) を含む。`0x10250000` が唯一の原因という読みは採らない。根拠はこの配置差のみで、ページ縮約 (overlay・minimal page set) の出力は記録が無いため根拠にしない。`0xfa5320` を OFF の値へ直しても ON の trap は消えない (表の 5 行目) ので、リスト先頭の 0x90 ずれ単独では説明できない。

### 補助 (unit 158 と unit 190 の ON 専用 code の実行)

- `ov_2131_trace.patch` (m11_ov.c の ON 専用 entry に `g_trace` で囲んだ trace を入れる差分。trace は unit 190 と 158 だけ有効にした。OFF の状態には無影響)。このパッチを入れた instrumented 版では、差分ページが 57 になり SP も `0x10a9fab0` (OFF `0x10a9fa10`) とずれるため、補助としてのみ使う。
  - unit 158: ON 専用の `410360` が 17 回、`413060` (C 版 UStrFromPWCharLen) が 28 回走る。
  - unit 190: `410360` が 3 回 (うち 1 回は `inst=0xe660`、直後に `icall 0xf960` を経て trap)、`413060` が 11 回。`41c130`・`9b4b00`・`9b5450` は走らない。
  - 同じ trace の UStrAsg 列は、ON と OFF で 6 件目まで一致し、ON は 6 件目の後で trap、OFF は 24 件まで続く。
- v413 (413060 の gate を外した ON 版) の並走では `0xfa5320` は unit 190 まで OFF と一致する (分岐 0 件)。一方 unit 15 の kind が `miss` (OFF は `ok`) に変わり、unit 190 は oob のまま。0x90 のずれは 413060 の override が作るが、v413 は別の差を持つため、ここでは trap の原因と結論しない。
- `boot_probe_2131.mjs` (新規): boot 直後の差分ページ (`0x10250000`) の中身を出す。ON は `"[m11][fail-fast] unresolved function call: %s"`、OFF は `"[m11][stub-notimpl] %s called ..."` の位置にあり、build ごとの文字列定数の配置差。

### 結論 (部分達成)

- 記録上の結果 (未検証。「確定」とは書かない): unit 190 の ON 限定の trap は、同じメモリ状態 (unit 189 直後、SP 一致) で ON 専用 code を走らせたときだけ起きる、と読める。ON 専用 code のうち、410360 の m11_vcall の shortcut 内の icall 計数 (`icall_bump`) だけで OFF の状態から oob が再現する (vz)。VMT 読みだけでは再現しない (vy)。ただし強制後の `diffPages now=` の出力と反復回数 n は記録が無いため、「同一状態」の主張は次 run の再測定 (次節 (e)) まで保留する。
- 未確定: icall 計数がなぜ oob を起こすか (計数表 `g_isite`・`g_itgt` の linear memory 上の位置と、407a50 の chain・スタックとの重なり)。`0xfa5320` の 0x90 ずれは 413060 override 由来 (v413 で消える) だが、単独では trap の原因ではない (LS_FIX)。
- 受入条件: 1 (書込元の特定) は未達。2 (REPORT 記録) は本節で部分達成。3 (ok 退行 0) は未達 (unit 190 が残る)。

### 次 run の作業 (起票先 #2131)

- (a) `g_isite`・`g_itgt` の表 (`_e`・`_h`・`n`) の linear address を vz の build で特定し、unit 190 中の計数書込みの address を watch する (watch 版は挙動が変わるので、書込みの address だけを見る)。
- (b) vz の oob の frame (`SV_RAW=1` の生 frame) を、410360 の icall_bump の前後で比べ、どの load/store が範囲外かを切り分ける。
- (c) 0xfa5010 (unit 87) の値の出所 (build 間の定数配置か、実行時の書込みか) を、unit 87 の trace で切り分ける。
- (d) 410360 の呼出元で `this` が誤っている候補: trace の `inst=0xe660` は `M11_LB_BASE=0` (LVA=RVA) では image 内 (RVA 0xe660) を指し、ヒープ上のインスタンスには見えない。`icall 0xf960` の経路 (shortcut 外) は vnc で外れても ON は oob のままなので trap の必要条件ではないと読めるが、この `this` の出所は未確認で、否定もしていない。(a)〜(c) と合わせ、410360 の呼出元で `this` の値を記録して確かめる。
- (e) 表の再測定 (記録の補完): 各 row について、実際に渡した env (`LS_A`・`LS_B`・`LS_FORCEB`・`LS_REVERSE`・`LS_FIX`・`LS_CKPT`・`LS_MAX`・`LS_TARGET`)、強制後の `diffPages now=` (0 であり、`heap length differs` が出ないこと)、反復回数 n を REPORT に残す。強制後 diffPages が 0 にならない `LS_FIX` の行は同一状態の結論に使わない。素材は `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff` で取得する (本 fix run では素材不足のため未実施)。

### 差分 (測定 commit `3b581236` から本 PR の HEAD まで、tools/m11 の build 入力)

- `git diff 3b581236 HEAD -- tools/m11 ':(exclude)*.md'` の対象は本 PR で追加した `trap_triage/lockstep_2131.mjs`・`boot_probe_2131.mjs`・`variants_2131.py`・`ov_2131_trace.patch` の 4 ファイルのみ。`m11_ov.c` ほか build 入力は測定 commit から変えていない (作業ツリーで一時的に変えた `m11_ov.c` は各 variant の後に元へ戻した)。
