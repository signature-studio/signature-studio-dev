# freshair 付録 #2739 / FA-38 (#3506): KH Compressor の機械語 harness

親 #2739 ([FA-34] Gain 以外への拡大) の子 #3506 の付録。SC 側 Compressor (0x180775220) と KH 側 `compressor::CompressorDsp` (0x1802abc20) の同一入力比較のうち、**KH 側の実機機械語 harness** の結果を置く。

- 結論: KH Compressor process を実機機械語のまま 200 case 実行する harness (`ks_kh_comp_native.c`) は ERR 0/200 で動く (seed 7・11・99 の 3 回)。決定性 (同 seed の 2 回が byte 一致) と感度の負例 (P+0x4 ×2 で 197〜200/200 が変化) を満たす。**SC との bit 比較は未実施** (KH 側 P フィールドの一部が出力に届いていない・未束縛 import の stub 依存があり、判定に使えない。子 #40)。
- 測定 commit: `df31ee6e6` (harness コード)。以後の差分は本付録のみ (§5 の確認コマンド参照)。

## 1. 対象 VA の確認 (RTTI)

- `tools/targets/kilohearts/scripts/rtti_walk.py` で HeartCore の `.?AVCompressorDsp@compressor@@` の vtable を引いた。**slot 14 = 0x1802abc20**。Gain の `.?AVGainDsp@gain@@` も slot 14 = 0x1804b0380 で、`snapins.json` の proc と一致する。よって slot 14 = process の規約は両者で同じで、issue 本文の VA は正しい。
- リポジトリ内に `0x1802abc20` の記録は無かった (`snapins.json` に Compressor の登録なし)。本付録が初出。
- 機械語 (`ks_identity.py` の `disasm` = pdata 関数境界): KH 0x1802abc20 = **1,724 B / 337 命令 / 直接 call 10 本**。SC 0x180775220 = 1,664 B / 333 命令 / 直接 call 10 本 + `call [rax+0x60]` (host 値の取得)。
- 直接 call 先: 0x180fb6830 / 0x180fbc1f4 / 0x180fc3640 (x2+) / 0x180295f20 / 0x18004cf20 (x3)。0x180fc3640 は pow 系の共通基盤 (SC 側の 0x18103fd60 と同系統と見られる。未確認)。
- 注: 本付録 §1〜§3 に予定されていた「ID 一致 37 組の process 候補表」は main に存在しない (`git log --all -S REPORT_APPENDIX_2739` 0 件)。親 #2739 の作業で作られる表で、本付録は参照しない。

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

P の写像は**一部だけ確定**: SC の `P+0x9dc4`・`P+0x9e0c` は sr (`[r8+0x9dc4]` @18077525f・`[r8+0x9e0c]` @180775274) と掛かる時定数で、KH の `P+0x00`・`P+0x04` と使われ方が揃う。`P+0x9e54` (mode) は `cmp 2` で分岐し KH `P+0x08` と揃う。`P+0x9ea8` は `comiss xmm12,[P+0x9ea8]` (@1807753ee) で閾値比較。host 値 (SC `[P+0xa098]` の vtable slot 0x60) は KH に対応する呼び出しが無い。残りの写像と Q フラグの対応 (SC `P+0x9ffb`・`P+0x9fb3`・`P+0xa043` ↔ KH `Q+0xfc`・`Q+0xdc`・`Q+0x11c`) は子 #40 で確定する。

## 3. harness の仕組みと stub

- `ks_kh_comp_native.c`: PE を base に raw map (`MAP_FIXED_NOREPLACE`)。Gain 版 (`ks_semantic_gain.c`) と同じ方式。
- **未束縛 import**: 素材の HeartCore は import 379 件の IAT が hint/name RVA のまま。`patch_iat` で `GetLastError` を戻り 0 の stub に、他は戻り 0 かつ呼び出し回数を数える stub に置換した。
- **実測された未束縛呼び出し** (seed 7): 2 つの call site (呼び出し元 VA は `UNRES` 行に出る) が mode=1 の case で呼ばれた。
  - `0x180fd3189`: `e8` で thunk `0x180fd81ec` (`jmp [rip+0x3c9175]`) へ。thunk の参照先 `0x1813a1367` は KERNEL32 の FirstThunk (0x13a1178) の 8 B 整列位置から外れ、どの import かは未確定。
  - `0x180fd31f4`: `call [rip+0x3ce0c7]` = slot `0x1813a12c0` = `KERNEL32!SetLastError` (戻り値は未使用)。
  - 件数は seed 7 で 67+67 = 134 (mode=1 の case 数と一致)。mode=1 の出力は stub 依存で、比較に使えない (§5)。
- **初回の ERR**: 最初の版は `GetLastError` の未束縛 slot (`0x13a1790`) を踏んで 67/200 が SIGSEGV (RIP = addr = `0x286e1e0`、hint/name RVA の値へ飛んだ)。stub 化で ERR 0 になった。

## 4. 実測 (commit `df31ee6e6`・`bash tools/targets/freshair/ks_kh_comp.sh 200 <seed>`)

環境: nproc=4、load average (1 分) 0.01〜0.07 (各 run の前後)。実行時間は 200 case で 0.03 s (3 seed とも同じ丸め。min–max = 0.03–0.03 s)。

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

`P+0x00`・`P+0x10`・`P+0x14` が 200 case のどれにも効かないのは、(a) 写像の誤り、(b) 当該分岐が本シナリオの入力で到達しない、のどちらか。**SC と比べる前に確定が必要** (子 #40)。このまま比べると一致は意味を持たない。

## 5. 検証範囲・限界・確認

- 検証範囲: KH process の機械語を、本 harness の入力 (§2 の写像・乱数) で 200 case × 3 seed 実行。範囲外: SC との bit 比較、P フィールドの意味の確定、未束縛 import の実体の確定、mode=1 の出力の正しさ。
- 差分確認 (コード commit から HEAD まで): `git diff df31ee6e6 HEAD -- tools/targets/freshair/ks_kh_comp.sh tools/targets/freshair/ks_kh_comp_native.c` の出力は 0 行 (本付録の commit はこの範囲の外)。
- blob 監査: 20 MiB 超の追加なし。`work/` (gitignore) は使用のみ。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SC⇄KH 同一入力の bit 一致実測 (旧受入 2) と #52 への判定返し (旧受入 3) | Compressor の判定が未了 | 子 #40 (FA-40) |
| `P+0x00`・`P+0x10`・`P+0x14` が出力に届かない原因 (写像か分岐か) | 比較の意味。SC の P 写像の確定 | 子 #40 |
| 未束縛 import 2 経路 (mode=1 のみ。`0x1813a1367` の実体) の stub 依存 | mode=1 の出力 | 子 #40 |
| 本付録の §1〜§3 (ID 一致 37 組表) が main に無い | 親の作業物の所在 | 親 #2739 へコメント |

## 7. 再現

```sh
# 素材: work-liftlib-targets (tools/targets/kilohearts/work/winpkg/HeartCore.core_64)
bash tools/targets/freshair/ks_kh_comp.sh 200 7   # ERR 0・決定性・負例を判定 (約 0.1 s)
```
