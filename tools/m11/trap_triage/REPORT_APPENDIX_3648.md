# 付録: #3648 (LD-171) — page 保護を変えない 0x5ac308 の書込み監視 (ld_native・DR 方式)

> **正本**: 本付録が #3648 の測定値・方式・限界の正本。親 `REPORT_APPENDIX_2770.md` §8 (LD-129 の page 方式) の続きで、250 行上限のため分割した。結論の 1 行は `REPORT_APPENDIX_2770.md` §8.10。

## 0. 判定

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. page 保護を変えない store 監視 (書込み直後の RIP と値) | 実装済み | `rt/ld_native.c` の `LD_WATCH_MODE=hw` (ptrace の DR0・DR1)。hw モードは `mprotect` を呼ばない (§2)。 |
| 2. 陽性対照 `System.InitCount` (15eac98) で page 方式の窓内 248 件と同じ件数 | PASS | DR 方式 248 件 (CPU 0 の 2 run・CPU 2 の 1 run)。page 方式 248 件 (CPU 0)。1:1 一致 248/248 (§5)。 |
| 3. 0x5ac308 監視付き boot の状態 (img・heap・unit detail) が監視なしと一致 (CPU 固定) | PASS (CPU 0・2) | CPU 0: 監視 2 run・監視なし 2 run が全て一致。CPU 2: 1 run ずつ一致。監視の記録は 0 件 (§4)。CPU 3 の再測定はしていない (§7)。 |
| 4. 実測値・測定 commit・所要・PASS/FAIL を本付録へ | 済み | 本付録 §1・§4・§5。結論 1 行を `REPORT_APPENDIX_2770.md` §8.10 に追記。 |

- 監視 0x5ac308 は、この boot (928/942 unit・監視の有無で同じ) で書かれなかった。「native boot では書かれない」とは書かない (§7 の限界)。
- 書込み元 (wasm 側の特定) は #2770 の表で追跡する。本 PR では扱わない。

## 1. 測定条件

- 測定 commit: `dda07f5cf` (コードを変えた最後の commit。`feat(liftdiff): ld_native に page 保護を変えない DR 書込み監視 (LD_WATCH_MODE=hw) を追加`)。
- `git diff dda07f5cf HEAD -- tools/liftdiff tools/m11/trap_triage` の出力は 0 行 (本付録の追記のみ。コード差分 0)。
- ビルド: `tools/liftdiff` で `gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm`。`rt/ld_native.c` 自身の警告は 0 件 (`rt/ld_core.h:286` の既存警告 1 件のみ。#2770 §8.1 と同じ)。
- 素材: `fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開し `FL_WIN64_DIR` とした。`work-m11.tar.zst`・`work-liftdiff.tar.zst` は `tools/m11/work/`・`tools/liftdiff/work/` に展開 (`tar --zstd -xf`)。
- 実行: `tools/m11/trap_triage/hw_watch_3648.sh` (環境は `env -i` で固定。下記 §3)。直列 12 run。所要: 12 run 合計 183 s (1 run 約 15 s)。1 分 load average は開始 0.33・終了 0.97 (`uptime`)。
- 判定スクリプト: `tools/m11/trap_triage/hw_watch_3648_check.py` (出力は `work/probe3648/check.txt`。state 比較は `cmp_img_2770.py` と同じ項目)。

## 2. 方式 (`rt/ld_native.c` の `LD_WATCH_MODE=hw`)

- 有効化: `LD_WATCH_MODE=hw` と `LD_WATCH_ADDR=<VA hex>`・`LD_WATCH_OUT=<path>`。未設定なら従来の挙動 (page 方式は `LD_WATCH_ADDR` だけで従来どおり)。
- 親子: `main` が `fork` し、親が tracer (`hw_watch_parent`)、子が guest 本体。子は `PTRACE_TRACEME` の後に `load_pe`・`install_signals` を行い、`raise(SIGSTOP)` で止まる。親はそこで DR0 = va、DR1 = va-8 (各 8 byte) を設定し、DR7 = `0x990005` (L0・L1 = 1、RW = 01 書込み、LEN = 10 8 byte) を書いて再開する。以後の signal は子へ戻す (DR hit の SIGTRAP だけは戻さない。BS 同時の場合は戻す)。`PTRACE_O_EXITKILL` で親が死ねば子も死ぬ。
- 記録: trap 1 回につき 1 行 `hw rip=… dr6=… a0=… old0=… new0=… chg0=… a1=… old1=… new1=… chg1=… rsp rax rcx`。`dr6` の bit 0 が va (DR0)・bit 1 が va-8 (DR1)。RIP は書込み命令の直後 (trap-after)。`hwarm` 行で arm 時の値、`hwsum` 行で hits・stops・rc。
- page 保護: hw モードでは `wp_arm`・`wp_fault`・`wp_finish` が呼ばれず、`mprotect` を呼ぶ経路 (`wp_prot`) に入らない (`grep -n 'wp_prot(' rt/ld_native.c` で確認)。
- 窓: DR の枠は [va, va+8) と [va-8, va)。page 方式の窓 [va-15, va+7] とは一致しない。C の 248 件の内訳は va 側 247・va-8 側 1 で、窓の外の書込みは観測されなかった (§5)。
- 限界: カーネル内の書込み (`read(2)` の宛先など) を DR が捕まえるかは未確認 (§7)。8 byte を超える書込み、枠の外から始まる書込みは捕まらない場合がある。

## 3. 環境長と初期 rsp (測定の前提)

- guest の初期 rsp は環境変数の総長で決まり、16 byte 単位でずれる。rsp が `0x7fffffffbbe0` と `0x7fffffffbbd0` の組では、監視なしの run どうしでも img 9〜10 byte と heap の内容が変わった (例: 監視なし `X6` と `X6b` の比較)。同じ rsp の組の中では全 run が一致した。
- シェルの `OLDPWD`・`_` などで環境長が run ごとに変わっていたため、初回の比較 (rsp 不一致) で差が出た。以後の全 run は `env -i PATH=… HOME=… FL_WIN64_DIR=… LD_PIN_CPU=<n>` で環境を固定し、`LD_WATCH_MODE` と `LD_WATCH_ADDR` の長さを対照と揃えた (`hw`/`xx`・`5ac308`/`000000`・`15eac98`/`0000000`・`15eac98`/`15eac98`)。
- 陰性対照 (比較器の感度): CPU 0 と CPU 2 の監視なし run の比較で 1 byte 差 (`0x11e69bf`: 0 → 2)。CPU 番号 (#2770 §8.9 の既知の byte) で、比較器はこの差を検出する。

## 4. 実測 (測定 commit `dda07f5cf`・全 run 同じ rsp `0x7fffffffd8b0`・units_run 928/942)

| run | CPU | `LD_WATCH_MODE` | `LD_WATCH_ADDR` | 記録 (hw 行 / wp 行) | page faults | state (同 CPU・同 env 長の対照 (F は X6・C と Cp は X7) と比較) |
|---|---|---|---|---|---|---|
| X6e1 | 0 | xx (監視なし) | 000000 | — | — | 基準 |
| F6e1 | 0 | hw | 5ac308 | hits 0 | — | 一致 (byte_diff 0・heap 一致・detail 一致) |
| X6e2 | 0 | xx | 000000 | — | — | X6e1 と一致 |
| F6e2 | 0 | hw | 5ac308 | hits 0 | — | 一致 |
| X7e | 0 | xx | 0000000 | — | — | 基準 (陽性対照用) |
| C7e | 0 | hw | 15eac98 | hits 248 | — | 一致 |
| C7e2 | 0 | hw | 15eac98 | hits 248 | — | 一致 |
| Cp7e | 0 | xx + page 方式 | 15eac98 | wp 248 | 726 | 一致 |
| X6c2 | 2 | xx | 000000 | — | — | 基準 |
| F6c2 | 2 | hw | 5ac308 | hits 0 | — | 一致 |
| X7c2 | 2 | xx | 0000000 | — | — | 基準 |
| C7c2 | 2 | hw | 15eac98 | hits 248 | — | 一致 |

- 同じ CPU 内で、監視なし・監視あり (5ac308・15eac98 の hw と page) の全組で `byte_diff=0`・`heap_eq=True`・`state_eq=True`・`detail_eq=True`・units_run 928/928。
- `hwsum` (C7e): `hits=248 stops=253 rc=0`。`hwsum` (F6e1・F6e2・F6c2): `hits=0 stops=5 rc=0`。

## 5. 陽性対照 (15eac98) の 1:1 対応

- hw 248 件と page 248 件 (`wp`・`wpsum faults=726`) を、同じ env 長・同じ CPU 0 の run 同士で突き合わせた (C7e と Cp7e)。
- 1:1 一致 248/248。条件: 枠 (page の `addr` が va なら hw の dr6 bit 0、va-8 なら bit 1)・値 (`new`)・chg が一致し、hw の RIP が page の RIP より後 (差 4〜8 byte)。
- 枠の内訳: page の `addr - va` は 0 が 247 件・-8 が 1 件。hw の dr6 は bit 0 が 247 件・bit 1 が 1 件。
- RIP の差 (hw − page): +6 が 246 件・+4 が 1 件・+8 が 1 件 (page は書込み命令の先頭、hw は書込み直後)。
- 当初は DR 1 本 (va のみ) で 247 件だった。page 窓の 248 件の内訳 (va-8 の 1 件) を見て DR1 (va-8) を足し、248 件に合わせた。

## 6. 再現

```sh
export FL_WIN64_DIR=<fl-win64 の展開先の親 (extracted/ を含む)>   # [WIN64] (docs/REFERENCES.md §4)
cd tools/liftdiff
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
cd ../..
S=tools/m11/trap_triage/hw_watch_3648.sh
bash $S X6e1 xx 000000 0; bash $S F6e1 hw 5ac308 0; bash $S X7e xx 0000000 0; bash $S C7e hw 15eac98 0; bash $S Cp7e xx 15eac98 0
bash $S X6c2 xx 000000 2; bash $S F6c2 hw 5ac308 2; bash $S X7c2 xx 0000000 2; bash $S C7c2 hw 15eac98 2
python3 tools/m11/trap_triage/hw_watch_3648_check.py tools/liftdiff/work/probe3648
```

- 各 run の出力は `tools/liftdiff/work/probe3648/<tag>.{json,out,log}` (gitignore 対象)。
- 監視なしの対照は、監視ありと**同じ長さ**の `LD_WATCH_MODE`・`LD_WATCH_ADDR`・`LD_WATCH_OUT` を入れる (`xx`・`000000`/`0000000`)。`xx` は page 方式も arm しない。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| カーネル内の書込み (`read(2)` の宛先など) を DR が捕まえるかは未確認 | 監視が取りこぼす書込みがあり得る。0 件の記録は「user 側の書込みが 0 件」の根拠 | 本 PR 本文の未解決表 (追跡のみ。子 issue 不要) |
| 8 byte を超える書込み・枠 (va-8〜va+8) の外から始まる書込みは、今回の boot では観測されなかったが一般には保証されない | 件数が一致しても superset とは言えない | 本 PR 本文の未解決表 |
| CPU 3 の hw 再測定は未実施 (page 方式の CPU 3 は #2770 §8.9 で測定済み) | 受入 3 の CPU 範囲は 0・2 | 本 PR 本文の未解決表 |
| trace (呼出し列) の比較は範囲外 (#3648 の受入に含まれない) | 書込み値の一致は確認したが、呼出し列の一致は未確認 | 本 PR 本文の未解決表 (#2770 の未解決の続き) |
| 0x5ac308 への書込み元 (wasm 側) の特定 | 監視 0 件の意味づけに影響 | #2770 の未解決表 (LD-129 の経緯) |
