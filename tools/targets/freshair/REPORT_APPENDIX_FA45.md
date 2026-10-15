# Fresh Air REPORT 付録 (#3741 / FA-45): KH のみ snap-in の SC 側実機ハーネス (Stereo・VocalFilter・Resonator)

- 親: #52 (FA-5)。前段: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §3・§4 の「KH のみ」10 組のうち残る 3 組。
- 判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。本付録は bit 一致の判定をしない (smoke のみ)。

## §1. 結論

| クラス | SC 側ハーネス | smoke (fma 0/1, 各 20 case) | 残件 |
|---|---|---|---|
| VocalFilter (SC 0x1808e1f30 → 訂正: process 本体 0x1808e1fa0・#4071) | `lift2/native/native_vocalfilter.c` 作成 (root は 0x1808e1fa0 に訂正済み) | ERR 0・20 行 × 2 (訂正前の root。§5 注) | KH 側との同一入力の差分 (C4〜C6) は未実施 (子 #4071) |
| Stereo (SC 0x1805ee2a0) | `lift2/native/native_stereo.c` 作成 (P+0x9f88 = P の自己ポインタを harness で設定・§8) | ERR 0・20 行 × 2 (fma 0/1) | KH 側との同一入力の差分と param 写像は未実施 (子 #4997 (FA-62))。書き込みの実行順序は未確認 (子 #5011 (FA-63)) |
| Resonator | 未作成 | 未実行 | 子 issue: SC 側 process の特定 (共有関数 0x1803df070 の呼出元照合) |

## §2. 材料の確認 (測定 commit は §5)

- 素材 `work-liftlib-targets` を `$RUNNER_TEMP` に展開し、`SlateCore.core_64` (36,285,952 B) の実在を確認。
- mlift (`lift2/mlift/mlift.py`・`pokes.txt`・stub 3 本は `build_filter.sh` と同一) で lift:
  - Stereo `--root 0x1805ee2a0`: `lifted 56 funcs / 9399 B / 2179 insns, failed 0, imports 11`
  - VocalFilter `--root 0x1808e1f30`: `lifted 35 funcs / 3458 B / 913 insns, failed 0, imports 11`
- KH 側の登録 (`tools/targets/kilohearts/snapins/snapins.json`): `resonator` (204 行)・`stereo` (223 行)・`vocalfilter` (287 行) の key はいずれも有る。C3 の KH 側は揃っている。

## §3. Stereo: P+0x9f88 の初期化 (旧試行の失敗と特定・子 #4046)

- 旧試行 (未コミット・#3741 時点): ERR 20/20 (SIGSEGV)。`FA_DBG=1` で `sig=11 rip=0x1805ee0d1 addr=0x30`。`0x1805ee0d1` は `mov rdx, [rcx+8]` で、直前の `mov rcx, [rcx+0x9f88]` が 0。
- 本付録 (#4046) で、`0x1805ee010`・`0x1805ee090` の `[P+0x9f88]` 読み (`0x1805ee042`・`0x1805ee0c2`) の初期化を機械語で特定した。
  - 読み手: `0x1805ee042` と `0x1805ee0c2` の `mov rcx, [rcx+0x9f88]; add rcx, 0x28`。`rcx` は root `0x1805ee2a0` が `P = [S+0x90]` を渡したもの。
  - 書き手: `0x1805ec9f0` の `mov [rax+0x9f88], rcx` (`rax` = `rcx` = 同じ object)。関数 `0x1805cb150` (内部で `0x1803ddff0`・`0x1803b5a20` を呼ぶ)。同形の書込みが `0x1806233f0` (関数 `0x180601b60`) にもある。
  - 初期化の根拠: 書き手は `[this+0x9f88] = this` (自己ポインタ)。読み手は `[P+0x9f88]+0x28` を使うので、自己ポインタなら `P+0x28` を指す。`0x1805cb150` の呼出元は `0x1805ca8a8` の 1 箇所。
  - 限界: 「いつ」は呼出元 (構築の経路) までの特定で、実機での実行順序は確認していない。実行順序は子 #5011 (FA-63) に移した (#4046 の受入から外す)。
  - 全 SlateCore `.text` で disp32 `0x9f88` を含むバイト列は 10 件。そのうち読み手 2 件・書き手 2 件を確認した。残り 6 件 (`add eax/ecx, 0x9f88` 系) は未確認で、Stereo の P 用かどうかは判定していない。
- 再現: `native_stereo.c` の P 確保直後に `*(uint64_t*)(P + 0x9f88) = (uint64_t)P` を置く (`pokes.txt` ではなく harness で設定。`pokes.txt` は P の絶対番地を書けないため)。
- 対照実験 (commit `bc7c633a5` から store 1 行を除いた版): fma 0・1 とも 20/20 が ERR、`sig=11 rip=1805ee0d1 addr=30`。旧試行と同じ失敗形で、この store が原因であることを示す。

### §3.1 P+0x9f88 の書込み順 (#5011 実測・測定 commit `52c7e0ca0`)

- 書込み: `0x1805ec9f0` の `mov [rax+0x9f88], rcx` (`rcx = this`)。`0x1805cb150` (構築関数・`this` を `rcx` で受けて 0x9f90 の object を組む) から約 122 KB 先に在る。静的な逆アセンブルだけでは `0x1805cb150` の実行がこの命令に届くかは確定しない。届くことは下の実行で確かめた (ctor=1 で `[P+0x9f88]==P` が 20/20)。
- ハーネス: `tools/targets/freshair/lift2/native/native_stereo.c` (`ctor=1` は `0x1805cb150(P, A)` を先に実行し、`[P+0x9f88] == P` を確かめてから `0x1805ee2a0` を実行。`ctor=0` は構築を飛ばす対照)。
- 前提の修正: `0x1805cb150` の先頭の `__chkstk` (`0x18100c710`) が `gs:[0x10]` で SIGSEGV する (Linux は gs_base=0)。`native_ctrl.c` と同じく `0x18100c72c` の gs 読みを `xor r11,r11` + nop に差替えた (wasm 側 `@fa_teb=0` と同値)。
- 実測 (commit `52c7e0ca0`・`bash tools/targets/freshair/ks_sc_stereo_smoke.sh 20`・load 1 分値 0.07・nproc=4):

| 条件 | fma | 行数 | ERR | `[P+0x9f88]==P` | 所要 |
|---|---|---|---|---|---|
| ctor=1 (構築 → process) | 0 | 20 | 0 | 20/20 | 0.275 s (script 全 4 run 計) |
| ctor=1 (構築 → process) | 1 | 20 | 0 | 20/20 | (同上) |
| ctor=0 (構築を飛ばす) | 0 | 20 | 20 | — | (同上) |
| ctor=0 (構築を飛ばす) | 1 | 20 | 20 | — | (同上) |

- ctor=0 の ERR は全 20 case で `sig=11 rip=0x1805ee0d1 addr=0x30` (§3 の #4046 試行と同一)。
- 結論: process の読み (`0x1805ee0c2`・`0x1805ee0d1`) は、構築 `0x1805cb150` が `[P+0x9f88]=P` を書いた後でしか成立しない。書込みが無いと読み手が落ちることを機械語の実行で確かめた (依存)。書込みが読み手より前に実行されるという製品内の順序は、harness が ctor を先に呼ぶ設計のため確かめていない (限界を参照)。
- 限界: 本件は依存関係 (書込みが無いと読み手が落ちる) を確かめたもので、実製品の呼出し時刻 (`0x1805ca8a8` の構築経路の順序) は未測定。bit 一致・KH との比較は対象外。

## §4. Resonator: SC 側 process 未特定

- `ks_identity.py` の SC VA `0x1803df070` (907 B) は制御層の共有関数で、Resonator の process ではない (`REPORT_APPENDIX_2739.md` §3 の注記と同じ)。
- 呼出元と vtable の照合は本 run では未実施 (時間不足)。子 issue で行う。

## §5. 測定 (コミット済み HEAD で再現)

- 測定 commit: `08f473703` (ハーネス・smoke を commit した最後の commit)。nproc=4・load 1 分値 0.07〜0.15 (05:59)。
- 実行: `SC_CORE=<work-liftlib-targets の SlateCore.core_64> bash tools/targets/freshair/ks_sc_vf_smoke.sh 20 <outdir>`
- 実測 (commit `08f473703` で再実行): `real 2.926 s`・`user 2.688 s`・EXIT=0。(初回 3.035 s。)

| ハーネス | fma | 行数 | ERR | stderr |
|---|---|---|---|---|
| VocalFilter (`native_vocalfilter.c`) | 0 | 20 | 0 | 0 B |
| VocalFilter (`native_vocalfilter.c`) | 1 | 20 | 0 | 0 B |

- 出力 `vf_n0.txt` と `vf_n1.txt` の md5 は一致 (`9463356eead9`)。このシナリオでは fma の違いが出力に現れていない。判定はしない。
- 限界: 「SC 側ハーネスが実機機械語を実行できる」までの確認。値の正しさ (KH との一致) は未確認。

## §6. 受入条件への対応

- 受入 1 (Stereo・VocalFilter の SC 側ハーネス): 両方作成 (§3・§8)。
- 受入 2 (Resonator の process 特定): 未達 (§4・#4047)。
- 受入 3 (smoke fma 0/1 × 20 case・ERR 0・20 行): VocalFilter (§5) と Stereo (§8) で達成。
- 受入 4 (KH 側の登録の確認・param 写像の根拠): KH 登録は 3 組とも確認 (§2)。param 写像は未記載 (VocalFilter の差分未実施のため。残件は子 #4071 (FA-51))。
- 受入 5 (本付録の登録・親 #52 の残件更新): 本付録を DOC_MAP に登録。親 #52 の残件表の更新は、Stereo・Resonator が閉じるまで行わない (本 PR の範囲外)。

## §8. Stereo の smoke (#4046・FA-48)

- 測定 commit: `bc7c633a5` (`native_stereo.c` と `ks_sc_stereo_smoke.sh` を追加した最後の commit)。nproc=4・load 1 分値 0.13〜0.20 (13:46)。
- 実行: `bash tools/targets/freshair/ks_sc_stereo_smoke.sh 20 <outdir>` (素材 `work-liftlib-targets` の `SlateCore.core_64`)。
- 実測: `real 2.958 s`・`user 2.778 s`・EXIT=0。

| ハーネス | fma | 行数 | ERR | stderr |
|---|---|---|---|---|
| Stereo (`native_stereo.c`) | 0 | 20 | 0 | 0 B |
| Stereo (`native_stereo.c`) | 1 | 20 | 0 | 0 B |

- 出力 `st_n0.txt` と `st_n1.txt` の md5 は一致 (`9260a3bf89e2`)。このシナリオでは fma の違いが出力に現れていない (VocalFilter §5 と同じ)。判定はしない。
- 対照: store を除いた版は 20/20 が ERR (§3)。store がこの失敗を解消していることを示す。
- 限界: 「SC 側ハーネスが実機機械語を実行できる」までの確認。値の正しさ (KH との一致) は未確認。
- 測定 commit から HEAD までのコード差分 (`git diff bc7c633a5 HEAD -- tools/targets/freshair/`) は、本 PR の REPORT 追記のみ。

## §7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Stereo の KH 側との同一入力の差分と param 写像 (SC 側ハーネスは §8 で ERR 0) | Stereo の意味同一性は未判定 | #4997 (FA-62) |
| Stereo の `P+0x9f88` の書き込みの実行順序 (`0x1805cb150` が読み手より前に走るか) | 初期化の「いつ」は未確認 (§3・受入 1 の残り) | #5011 (FA-63) |
| Resonator の SC 側 process の特定 (0x1803df070 の呼出元と vtable の照合) | Resonator の差分の前提が無い | #4047 (FA-49) |
| VocalFilter の KH 側との同一入力の差分 (C4〜C6・param 写像) | VocalFilter の意味同一性は未判定 | #4071 (FA-51) |

注 (#4071 訂正): §5 の VocalFilter smoke は `0x1808e1f30` (deleting destructor) を実行していた。`ERR 0・20 行 × 2` は process の実行の証拠にならない。root は `0x1808e1fa0` に訂正済み (FA51 §6)。`ks_sc_vf_smoke.sh` の `--root` も同じ。
