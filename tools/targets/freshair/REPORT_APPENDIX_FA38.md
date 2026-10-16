# freshair 付録 #2739 / FA-38 (#3506): KH Compressor の機械語 harness

親 #2739 ([FA-34] Gain 以外への拡大) の子 #3506 の付録。SC 側 Compressor (0x180775220) と KH 側 `compressor::CompressorDsp` (0x1802abc20) の同一入力比較のうち、**KH 側の実機機械語 harness** の結果を置く。

- 結論: KH Compressor process を実機機械語のまま 200 case 実行する harness (`ks_kh_comp_native.c`) は ERR 0/200 で動く (seed 7・11・99 の 3 回)。決定性 (同 seed の 2 回が byte 一致) と感度の負例 (P+0x4 ×2 で 197〜200/200 が変化) を満たす。**SC との bit 比較は未実施** (KH 側 P フィールドの一部が出力に届いていない・未束縛 import の stub 依存があり、判定に使えない。子 #3534 (FA-41))。
- 測定 commit: `4ad994a19` (再測定。nproc=4、load 1 分 0.25〜0.27、seed 7・11・99 とも run1 0.03 s)。harness のコードは `739c90452` から変わったのが `ks_kh_comp_native.c` の根拠コメント 1 行 (REPORT_APPENDIX_FA38 への参照) だけで、実行結果は同一 (§5)。以後の差分は本付録のみ。

## 1. 対象 VA の確認 (RTTI)

- `tools/targets/kilohearts/scripts/rtti_walk.py` で HeartCore の `.?AVCompressorDsp@compressor@@` の vtable を引いた。**slot 14 = 0x1802abc20**。Gain の `.?AVGainDsp@gain@@` も slot 14 = 0x1804b0380 で、`snapins.json` の proc と一致する。よって slot 14 = process の規約は両者で同じで、issue 本文の VA は正しい。
- リポジトリ内に `0x1802abc20` の記録は無かった (`snapins.json` に Compressor の登録なし)。本付録が初出。
- 機械語 (`ks_identity.py` の `disasm` = pdata 関数境界): KH 0x1802abc20 = **1,724 B / 337 命令 / 直接 call 10 本**。SC 0x180775220 = 1,664 B / 333 命令 / 直接 call 10 本 + `call [rax+0x60]` (host 値の取得)。
- 直接 call 先: 0x180fb6830 / 0x180fbc1f4 / 0x180fc3640 (x2+) / 0x180295f20 / 0x18004cf20 (x3)。0x180fc3640 は pow 系の共通基盤 (SC 側の 0x18103fd60 と同系統と見られる。未確認)。
- 注: 「ID 一致 37 組の process 候補表」は親 #2739 の作業物で、本 PR の範囲外。この注は 739c90452 時点の記述。main 取り込み後 (4ad994a19) は main の `REPORT_APPENDIX_2739.md` §3 に同じ表がある。本付録は参照しない。

## 2. 引数・state・param の写像 (機械語の読み)

KH process の引数: `rcx = this`・`rdx = ctx`・`r8 = aud` (`mov rbx,rcx` @1802abc84 / `mov rdi,rdx` @1802abc81 / `mov rsi,r8` @1802abc7e)。Gain (`ks_semantic_gain.c`) と同じ 3 引数。

| 参照 | KH の命令 VA | 読み (役割) | harness の置き方 |
|---|---|---|---|
| `aud+0` = L・`aud+8` = R・`aud+0x28` = n | @1802ac06d・@1802ac080・@1802abee5 | 入出力の音声 | L/R を n 個。副入力は使わない |
| 副 entry の `+0x40` < 0 で aud を使う | @1802abec1-@1802abec8 (`js`) | 副入力 (sidechain) の有無 | entry+0x40 = -1 |
| `ctx+0x3188` = P | @1802abc87 | param block | 0x40 B |
| `ctx+0x3198` = Q | @1802abc8e | 状態 block (フラグ・係数) | 0x140 B |
| `ctx+0x31a8` = 副 entry 配列 | @1802abeae | 副入力の参照 | 先頭 1 件のみ |
| `ctx+0x31b0` = 通知 vector V | @1802ac18d | 通知 id の push 先 | begin +0x60 / end +0x68 / cap +0x70 |
| `ctx+0x3180` = id | @1802ac194 | 通知 id の基点 | 2000 |
| `this+0x60` = sample rate | @1802abcf8 (`movss xmm15,[rbx+0x60]`) | 時定数の換算 (`P×sr`) | 44100/48000/96000/22050 |
| `this+0xc4` = 初回フラグ | @1802abe03 (`cmp byte[rbx+0xc4],1`) | 初期化経路 | 0/1 |
| `P+0x00` = 時定数 A | @1802abc9a → ×sr @1802abf02 | attack 相当 | lg(-4,0) |
| `P+0x04` = 時定数 B | @1802abc9f → ×sr @1802abf07 | release 相当 (**出力に効く**・§4) | lg(-3,0.3) |
| `P+0x08` = mode (int) | @1802abca5 → `cmp 2` @1802abcd0 | モード 0/1/2 | 0..2 |
| `P+0x10` = 閾値 | @1802abc95 → `ucomiss xmm11,xmm6` @1802ac008・@1802ac110 | 閾値比較 (**出力に効かない**・§4) | RFS(0,2) |
| `P+0x14` | @1802abca8 (xmm10) → `divss` 系 | 係数 (**出力に効かない**・§4) | 0.1..2 |
| `P+0x18`・`P+0x20` | 出力 @1802ac1c7・@1802ac22f | 検出値の出力 | 読み出して記録 |
| `P+0x1c` | 読み @1802ac097・書き @1802ac171 | 状態 (平滑化値) | 0..1 |
| `P+0x24` (int)・`P+0x28` (int) | @1802abeca・@1802abeb5 | 副 entry の添字・引数 | 0 |
| `Q+0x68` (float) | @1802abcc2 (rcx=Q)・@1802abda4 | 係数の lerp (`C1+Q68×(C0−C1)`) | 0..1 |
| `Q+0xfc`・`Q+0xdc`・`Q+0x11c` | @1802ac17d・@1802ac1d4・@1802ac23b | 通知済みフラグ (id+7・+6・+8) | 0/1 |
| `this+0x60..0xc8` の state | @1802abf68 他 | 処理後 state | 乱数で初期化 |

SC との対応 (根拠の候補。未確定): SC 側の state は `S+0x98..0x100` で、KH の `this+0x60..0xc8` と **`S = this + 0x38`** で揃う。初回フラグは KH `this+0xc4` (@1802abe03) と SC `S+0xfc` (`cmp byte[rbx+0xfc],bpl` @180775446) で、差は同じ 0x38。SC 生成器 `lift2/gen_comp_scen.py` の state 書込み先 (0x98..0x100・0xfc) もこの範囲に入る。

P の写像は**一部だけ確定**: SC の `P+0x9dc4`・`P+0x9e0c` は sr (`[r8+0x9dc4]` @18077525f・`[r8+0x9e0c]` @180775274) と掛かる時定数で、KH の `P+0x00`・`P+0x04` と使われ方が揃う。`P+0x9e54` (mode) は `cmp 2` で分岐し KH `P+0x08` と揃う。`P+0x9ea8` は `comiss xmm12,[P+0x9ea8]` (@1807753ee) で閾値比較。host 値 (SC `[P+0xa098]` の vtable slot 0x60) は KH に対応する呼び出しが無い。残りの写像と Q フラグの対応 (SC `P+0x9ffb`・`P+0x9fb3`・`P+0xa043` ↔ KH `Q+0xfc`・`Q+0xdc`・`Q+0x11c`) は子 #3534 (FA-41) で確定する。

## 3. harness の仕組みと stub

- `ks_kh_comp_native.c`: PE を base に raw map (`MAP_FIXED_NOREPLACE`)。Gain 版 (`ks_semantic_gain.c`) と同じ方式。
- **未束縛 import**: 素材の HeartCore は import 379 件の IAT が hint/name RVA のまま。`patch_iat` で `GetLastError` を戻り 0 の stub に、他は戻り 0 かつ呼び出し回数を数える stub に置換した。
- **実測された未束縛呼び出し** (seed 7): 2 つの call site (呼び出し元 VA は `UNRES` 行に出る) が mode=1 の case で呼ばれた。
  - `0x180fd3189`: `e8` で thunk `0x180fd81ec` (`jmp [rip+0x3c9175]`) へ。thunk の参照先 slot `0x1813a1368` は KERNEL32 の FirstThunk (0x13a1178) の index 62 で、`KERNEL32!FlsSetValue` (8 B 整列の内側)。
  - `0x180fd31f3`: `ff 15` (6 B) の `call [rip+0x3ce0c7]` = slot `0x1813a12c0` = `KERNEL32!SetLastError` (戻り値は未使用)。`ff 15` (indirect call) の site は、harness の `UNRES` 表示 (`ra − 5`、`e8` 前提) が命令 VA より 1 B ずれて出る。
  - 件数は seed 7 で 67+67 = 134 (mode=1 の case 数と一致)。mode=1 の出力は stub 依存で、比較に使えない (§5)。
- **初回の ERR**: 最初の版は `GetLastError` の未束縛 slot (`0x13a1790`) を踏んで 67/200 が SIGSEGV (RIP = addr = `0x286e1e0`、hint/name RVA の値へ飛んだ)。stub 化で ERR 0 になった。

## 4. 実測 (再測定 commit `4ad994a19`・`bash tools/targets/freshair/ks_kh_comp.sh 200 <seed>`。元の測定 `739c90452` と数値は同一)

環境: nproc=4、load average (1 分) 0.10〜0.18 (各 run の前後。seed 7 は 0.10、seed 11・99 は 0.18)。実行時間は 200 case の run1 で 0.03 s (seed 7・11・99 とも実測 0.03 s)。

| seed | ERR | 音声が変化した case | 通知 id の総数 | 通知 0 件の case | 未束縛 import 呼び出し | 同 seed 2 回の一致 | 負例 (P+0x4 ×2) で変化した case |
|---|---|---|---|---|---|---|---|
| 7 | 0/200 | 197 | 294 | 25 | 134 | byte 一致 | 197/200 |
| 11 | 0/200 | 200 | 292 | 25 | 136 | byte 一致 | 200/200 |
| 99 | 0/200 | 198 | 293 | 29 | 102 | byte 一致 | 198/200 |

- 「音声が変化した case」= 出力 L/R が入力と byte 違い (process が音声に作用している)。
- 通知 id: 1 case あたり 0〜3 件 (id+7・+6・+8 の初回のみ)。

**感度の確認 (seed 7・200 case、基準出力との行差分)**:

| 摂動 | 変化した case | 読み |
|---|---|---|
| P+0x00 ×0 | 0 | 出力に届かない |
| P+0x04 ×2 | 197 | 出力に効く (負例に採用) |
| P+0x10 ×0 / ×0.5 / ×2 | 0 / 0 / 0 | 出力に届かない |
| P+0x14 ×0 / ×2 | 0 / 0 | 出力に届かない |
| P+0x1c ×0 | 20 | 出力に効く |

`P+0x00`・`P+0x10`・`P+0x14` が 200 case のどれにも効かないのは、(a) 写像の誤り、(b) 当該分岐が本シナリオの入力で到達しない、のどちらか。**SC と比べる前に確定が必要** (子 #3534 (FA-41))。このまま比べると一致は意味を持たない。

掃引 (`ks_kh_comp_sens.sh 200 7`・測定 commit `c6e92e8eb`・0.53 s・nproc=4・load 1 分 0.09〜0.25。基準は `ks_kh_comp.sh 200 7` の kh_a.txt):

| P フィールド | 乗数 0 | 1e-6 | 1e6 | -1 | 0.5 |
|---|---|---|---|---|---|
| P+0x00 | 0 | 0 | 0 | 0 | 0 |
| P+0x10 | 0 | 0 | 0 | 0 | 0 |
| P+0x14 | 0 | 0 | 0 | 0 | 0 |
| (対照) P+0x04 | 197 | 197 | 197 | 197 | 197 |
| (対照) P+0x1c | 20 | 20 | 133 | 20 | 19 |

- 読み: `P+0x10` の閾値比較 (`ucomiss xmm11,xmm6` @1802ac008) は機械語に存在する。全乗数で 0/200 のため、係数のずれ (×2 など) では説明できない。**(a) 写像の誤りか (b) 分岐の不到達かは、この掃引では未確定**。SC 側の `P+0x9dc4`・`P+0x9e0c`・`P+0x9ea8` との対応を機械語で決めるまで判定は未了。

## 5. 検証範囲・限界・確認

- 検証範囲: KH process の機械語を、本 harness の入力 (§2 の写像・乱数) で 200 case × 3 seed 実行。範囲外: SC との bit 比較、P フィールドの意味の確定、未束縛 import の実体の確定、mode=1 の出力の正しさ。
- 差分確認: `git diff 739c90452 4ad994a19 -- tools/targets/freshair/ks_kh_comp.sh tools/targets/freshair/ks_kh_comp_native.c` の出力は次の 1 行の comment 変更のみ。`git diff 4ad994a19 HEAD -- <同じ範囲>` は 0 行 (測定の後にハーネスは変えていない)。

  ```
  - * 入力の写像は HeartCore の機械語の読みで決めた (根拠は REPORT_APPENDIX_2739.md §2):
  + * 入力の写像は HeartCore の機械語の読みで決めた (根拠は REPORT_APPENDIX_FA38.md §2):
  ```
- smoke 未実施: `ks_sc_native_smoke.sh 200` (Compressor・Filter の fma 0/1 で ERR 件数と行数を見る) は本 run では実行していない。`SlateCore.core_64` (`work-liftlib-targets`) が runner に未展開のため、`missing:` で止まる (測定 commit なし・ERR 件数なし)。SC 側の ERR 0 は未確認のまま。
- 並列実行の確認 (739c90452 で seed 11・99 を `xargs -P 2` で同時実行。両 script の実行区間が重なり、開始時刻の差 0.30 ms、各 script 全体 0.25 s): 両 SUMMARY と kh_a.txt が直列実行と一致 (seed 11 = 200・292・25・136、seed 99 = 198・293・29・102、byte 一致)。
- blob 監査: 20 MiB 超の追加なし。`work/` (gitignore) は使用のみ。

## 6. FLS 実体化 (FA-57 / #4622・部分達成)

- 実装: `ks_kh_comp_native.c` で `FLS_IDX` を指定したときだけ、`FlsSetValue`・`FlsGetValue`・`SetLastError` を実体化する (index 表 `fls_val[64]`・`g_lasterr`)。index は絶対 VA `0x182989860` に書く。`FLS_IDX` 未指定は従来の stub のまま (`FlsSetValue` は FALSE を返す)。
- 対象 VA: `FlsSetValue` `0x1813a1368`・`SetLastError` `0x1813a12c0` (§3 の IAT 経路)。`GetLastError` は従来どおり 0 を返す stub。
- 測定 commit: `eb2fc311c` (`ks_kh_comp_native.c` を最後に変えた commit)。`git diff eb2fc311c HEAD -- tools/targets/freshair/ks_kh_comp_native.c` の差分 0 なら再測定は要らない。
- 環境: nproc=4、`work-liftlib-targets` 展開の `HeartCore.core_64` (76642304 B)。load average (1 分) 0.62 (各 run の前後、同値)。run1 は seed 7・11・99 とも 0.03 s。
- 測定コマンド: `bash tools/targets/freshair/ks_kh_comp.sh 200 <seed>` (既定) と `FLS_IDX=0 bash tools/targets/freshair/ks_kh_comp.sh 200 <seed>` (FLS 実体化)。各 run の `SUMMARY`・`FLS`・`UNRES` 行は以下のとおり (両経路とも `determinism: run1 == run2 (byte 一致)`・`RESULT: ... ERR 0`)。

| seed | 経路 | SUMMARY (cases・err・audio_changed・notify_total・no_notify・unresolved) | FLS | UNRES |
|---|---|---|---|---|
| 7 | 既定 | cases=200 err=0 audio_changed_cases=197 notify_total=294 no_notify_cases=25 unresolved_import_calls=134 | (なし) | 180fd3189 count=67・180fd31f4 count=67 |
| 7 | FLS_IDX=0 | cases=200 err=0 audio_changed_cases=197 notify_total=294 no_notify_cases=25 unresolved_import_calls=67 | fls_set_calls=134 fls_set_ok=134 | 180fd5222 count=67 |
| 11 | 既定 | cases=200 err=0 audio_changed_cases=200 notify_total=292 no_notify_cases=25 unresolved_import_calls=136 | (なし) | 180fd3189 count=68・180fd31f4 count=68 |
| 11 | FLS_IDX=0 | cases=200 err=0 audio_changed_cases=200 notify_total=292 no_notify_cases=25 unresolved_import_calls=68 | fls_set_calls=136 fls_set_ok=136 | 180fd5222 count=68 |
| 99 | 既定 | cases=200 err=0 audio_changed_cases=198 notify_total=293 no_notify_cases=29 unresolved_import_calls=102 | (なし) | 180fd3189 count=51・180fd31f4 count=51 |
| 99 | FLS_IDX=0 | cases=200 err=0 audio_changed_cases=198 notify_total=293 no_notify_cases=29 unresolved_import_calls=51 | fls_set_calls=102 fls_set_ok=102 | 180fd5222 count=51 |

- 出力差 (既定 vs `FLS_IDX=0`、`kh_a.txt` の行比較): seed 7・11・99 とも 0/200。`negative control` (`CHECK_NEG=1 NEG_OFF=0x4 NEG_MUL=2.0`) は seed 7 で 197/200、seed 11 で 200/200、seed 99 で 198/200 の case が変化 (感度あり)。
- 残存 site の同定 (IAT は PE 解析で確認): `UNRES` の表示は `ra − 5` (`e8` 前提)。`180fd5222` は実際には `0x180fd5221` の `ff 15 21 c5 3c 00` (`call [rip+0x3cc521]` = slot `0x1813a1748`) の戻り先 (ra=`0x180fd5227`) で、slot `0x1813a1748` は **KERNEL32!HeapAlloc**。`FLS_IDX=0` で残る未束縛呼び出しは HeapAlloc (戻り 0 の stub) だけ。
- 同定の補足: `0x182989860` は `.data` セクション (VA `0x182870000`〜`0x18436df0c`) の内側。ただし DLL 初期化がここに index を書く経路は未確認。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SC⇄KH 同一入力の bit 一致実測 (旧受入 2) と #52 への判定返し (旧受入 3) | Compressor の判定が未了 | #3534 (FA-41) |
| `P+0x00`・`P+0x10`・`P+0x14` が出力に届かない原因 (写像か分岐か) | 比較の意味。SC の P 写像の確定 | #3534 (FA-41) |
| 既定 (`FLS_IDX` 未指定) の stub 依存。`0x182989860` の index を DLL 初期化が書く経路 (DLL エントリから `0x180fd32dc` への到達) が未確認 | mode=1 の出力 | #4622 (残件・親 #3534) |
| 成功側で呼ばれる `HeapAlloc` (IAT `0x1813a1748`) が stub (戻り 0) のまま。`FLS_IDX=0` の残存未束縛呼び出し (seed 7・11・99 で 67・68・51) | `FlsSetValue` 成功側の出力は未変化 (0/200 差)。HeapAlloc 実体化後の出力は未測定 | #4622 (残件) |
| ID 一致 37 組の振り分け表は親 #2739 の付録 (main の `tools/targets/freshair/REPORT_APPENDIX_2739.md` §3) にある | 本付録は参照しない | 不要 (main に既存) |

## 8. 再現

```sh
# 素材: work-liftlib-targets (tools/targets/kilohearts/work/winpkg/HeartCore.core_64)
bash tools/targets/freshair/ks_kh_comp.sh 200 7   # ERR 0・決定性・負例を判定 (run1 実測 0.03 s)
FLS_IDX=0 bash tools/targets/freshair/ks_kh_comp.sh 200 7   # FLS 実体化の経路 (§6)
```
