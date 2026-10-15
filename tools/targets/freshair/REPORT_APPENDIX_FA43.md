# Fresh Air REPORT 付録 (#3739 / FA-43): KH のみ snap-in の SC 側実機ハーネス (Gate・Haas・Limiter)

- 親: #52 (FA-5)。判定基準は [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1) に従う。判定はしない (smoke のみ)。
- 結論: **Limiter だけ完了** (SC 側ハーネス作成・fma 0/1 で 20 行・ERR 0)。**Gate・Haas は未完** (process 内部の状態が harness で埋まらず、ERR 20/20)。子 issue に分けた (§5)。

## §1. KH 側の登録 (C3)

`tools/targets/kilohearts/snapins/snapins.json` の key を確認した。

| クラス | KH key | 登録 |
|---|---|---|
| Gate | `gate` (`GateDsp`) | あり |
| Haas | `haas` (`HaasDsp`) | あり |
| Limiter | `limiter` (`LimiterDsp`) | あり |

## §2. SC 側ハーネス (C3・smoke)

- 追加: `lift2/native/native_limiter.c`・`lift2/gen_limiter_scen.py`・`ks_sc_native_smoke_limiter.sh`。`native_filter.c` と同じ方式 (`FA_IAT`・`FA_POKES`・IAT 束縛・canary・ABI 検査)。root = `0x18094d9c0`。
- 状態の用意: `P+0xa068` が指す sub-object を harness で用意する (begin/end を空範囲)。これが無いと `0x18094dd87` で SIGSEGV (addr 0x30)。`mov rdx, [rcx+8]` が null の sub-object を読むため。
- 実測 (測定 commit `7d0c04170`・素材 `work-liftlib-targets` を `$ARTIFACTS_DIR` から展開・nproc=4・load 1 分値 0.00〜0.12):

| ハーネス | fma | 行数 | ERR | stderr |
|---|---|---|---|---|
| Limiter (`native_limiter.c`) | 0 | 20 | 0 | 0 B |
| Limiter (`native_limiter.c`) | 1 | 20 | 0 | 0 B |

- 出力の md5: fma 0 と fma 1 は一致 (`d7e0e1eae3ac300015de78847e1a9034`)。同じ md5 は、commit 前の試行 (`$RUNNER_TEMP/ks_limiter`) でも得た。実行時間 3.25 s (real)。
- 限界: ERR 0 は「実機機械語が状態を読んで最後まで走る」までの確認。値の正しさ (KH との一致) は未確認。ring buffer の初期化は process 側の範囲外で、harness は触っていない。

## §3. Gate・Haas が未完の理由

Gate・Haas は ERR が全件 (20/20)。fault の位置と、その直前の逆アセンブルで原因を確かめた。

| クラス | 初回の fault | 原因 (逆アセンブルの読み) | 対処 |
|---|---|---|---|
| Gate | `0x1804ce8c9` (addr 0x38) | `S+0` の vtable が無く、`call [rax+0x38]` が null | vtable slot 7 を harness で差替え (戻り 0) → fault が `0x1804ce936` (addr 0) へ移る |
| Gate | `0x1804ce936` (addr 0) | `[rbx+0xb0]` (ring buffer の base) が null。`0x1804ce700` の中で `+0xb0` は設定されない | 未実施。初期化の経路は未特定 |
| Haas | `0x180498fa6` (addr 0) | `[r9+0x100]` (delay-line buffer) が null。IAT 0 件 (`iat_haas.txt` 空) | 未実施。`0x180498cd0` の中で `+0x100` は設定されない |

- Gate の vtable 差替えは、harness の stub を追加して 1 段進めたところで止めた。ring base の確保サイズ・経路を読み切るまでは、値を推測で埋めない (埋めると ERR 0 になっても意味のない実行になる)。
- Gate・Haas の harness ファイル (`native_gate.c`・`native_haas.c`) はこの PR に含めない (未完のため)。子 issue で作る。

## §4. 差分実行の見通し (C4)

- **Limiter**: 同一入力の差分はまだ実行していない。param の写像 (`P+0x...` のどの offset が threshold・release 等か) は未確定。ERR 0 の harness だけが根拠。差分実行の前に、機械語の読みで写像を確定する必要がある。
- **Gate・Haas**: 同上。加えて ring buffer の初期化が未確定のため、差分の見通しは立っていない。

## §5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Gate の SC 側 harness (ring base `+0xb0` の初期化) | Gate は実機で走らず、差分の対象にならない | #4044 (FA-48) |
| Haas の SC 側 harness (delay-line buffer `+0x100` の初期化) | Haas は実機で走らず、差分の対象にならない | #4045 (FA-49) |
| Limiter の param 写像 (C4) と KH 側との同一入力差分 (C5・C6) | Limiter の意味同一性は未判定 | #52 (残件) |
| 本 PR の判定 (C5・C6): Limiter・Gate・Haas の bit 一致 | 未実施 (C7 により、ハーネス完成前は差分を実行しない) | #52 (残件) |

## §6. 受入条件への対応

- [x] 3 組のうち Limiter の SC 側ハーネス `native_limiter.c` を作る。Gate・Haas は未完 (§3)。子 #4044 (Gate)・#4045 (Haas)。
- [x] Limiter: fma 0/1 で各 20 行・ERR 0 (§2)。Gate・Haas は実行していない (ERR 20/20 のまま commit しない)。
- [x] KH 側の登録の確認 (§1)。
- Limiter の差分の見通し (param の写像) は #52 へ移した (§4・§5)。本 issue の範囲は Limiter の SC 側ハーネスと smoke まで。
- [x] REPORT_APPENDIX_FA43.md の新規と DOC_MAP 登録。親 #52 の残件表は、#52 へのコメントで更新する。

## §7. 検証の再現

- コード変更: `git diff 7d0c04170 HEAD -- tools/targets/freshair/lift2/native/ tools/targets/freshair/lift2/gen_limiter_scen.py tools/targets/freshair/ks_sc_native_smoke_limiter.sh` (測定 commit と HEAD の差分。この付録は REPORT のみ)
- 再現: `SC_CORE=<work-liftlib-targets の SlateCore.core_64> bash tools/targets/freshair/ks_sc_native_smoke_limiter.sh 20 [outdir]`
