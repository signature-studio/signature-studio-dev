# Fresh Air REPORT 付録 (#3741 / FA-45): KH のみ snap-in の SC 側実機ハーネス (Stereo・VocalFilter・Resonator)

- 親: #52 (FA-5)。前段: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §3・§4 の「KH のみ」10 組のうち残る 3 組。
- 判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。本付録は bit 一致の判定をしない (smoke のみ)。

## §1. 結論

| クラス | SC 側ハーネス | smoke (fma 0/1, 各 20 case) | 残件 |
|---|---|---|---|
| VocalFilter (SC 0x1808e1f30) | `lift2/native/native_vocalfilter.c` 作成 | ERR 0・20 行 × 2 | KH 側との同一入力の差分 (C4〜C6) は未実施 |
| Stereo (SC 0x1805ee2a0) | 作成せず (`native_stereo.c` は試行のみで未コミット・§3) | ERR 20/20 (SIGSEGV) | 子 issue: P+0x9f88 の初期化を特定してから再実行 |
| Resonator | 未作成 | 未実行 | 子 issue: SC 側 process の特定 (共有関数 0x1803df070 の呼出元照合) |

## §2. 材料の確認 (測定 commit は §5)

- 素材 `work-liftlib-targets` を `$RUNNER_TEMP` に展開し、`SlateCore.core_64` (36,285,952 B) の実在を確認。
- mlift (`lift2/mlift/mlift.py`・`pokes.txt`・stub 3 本は `build_filter.sh` と同一) で lift:
  - Stereo `--root 0x1805ee2a0`: `lifted 56 funcs / 9399 B / 2179 insns, failed 0, imports 11`
  - VocalFilter `--root 0x1808e1f30`: `lifted 35 funcs / 3458 B / 913 insns, failed 0, imports 11`
- KH 側の登録 (`tools/targets/kilohearts/snapins/snapins.json`): `resonator` (204 行)・`stereo` (223 行)・`vocalfilter` (287 行) の key はいずれも有る。C3 の KH 側は揃っている。

## §3. Stereo: smoke が通らなかった記録 (子 #4046)

- 試行: `native_stereo.c` (`native_filter.c` の方式を複製し VA だけ差替え) で `gen_sc_smoke_scen.py` の 20 case を実行。fma 0・1 とも 20/20 が ERR。`FA_DBG=1` で `sig=11 rip=0x1805ee0d1 addr=0x30`。
- 原因の見立て (未確定): `0x1805ee0d1` は `mov rdx, [rcx+8]` で、直前の `mov rcx, [rcx+0x9f88]` が 0。`stereo.ll` の 2532・2933 行も同じ `P+0x9f88` を読む。Filter・VocalFilter の P には `+0x9f88` の初期化が無い (`pokes.txt` に無い)。Stereo 固有の初期化が必要と推定。
- 本 PR では `native_stereo.c` をコミットしない (通らないハーネスを残さない)。子 issue (#4046) が出発点にする。

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

- 受入 1 (Stereo・VocalFilter の SC 側ハーネス): VocalFilter のみ作成。Stereo は未達 (§3・#4046)。
- 受入 2 (Resonator の process 特定): 未達 (§4・#4047)。
- 受入 3 (smoke fma 0/1 × 20 case・ERR 0・20 行): VocalFilter で達成 (§5)。Stereo は未達 (#4046)。
- 受入 4 (KH 側の登録の確認・param 写像の根拠): KH 登録は 3 組とも確認 (§2)。param 写像は未記載 (VocalFilter の差分未実施のため。未起票の残件)。
- 受入 5 (本付録の登録・親 #52 の残件更新): 本付録を DOC_MAP に登録。親 #52 の残件表の更新は、Stereo・Resonator が閉じるまで行わない (本 PR の範囲外)。

## §7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Stereo の SC 側ハーネス (P+0x9f88 の初期化を特定し、smoke を ERR 0 にする) | Stereo の差分実行の前提が無い | #4046 (FA-48) |
| Resonator の SC 側 process の特定 (0x1803df070 の呼出元と vtable の照合) | Resonator の差分の前提が無い | #4047 (FA-49) |
| VocalFilter の KH 側との同一入力の差分 (C4〜C6・param 写像) | VocalFilter の意味同一性は未判定 | 未起票 (親 #3741 の受入 4 の残り。PR 本文に残す) |
