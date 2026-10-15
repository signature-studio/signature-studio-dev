# REPORT_APPENDIX_3715 — x87 leaf 関数の native vs wasm 差分試験の拡張 (#3715 PLG-G2-31)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 ST(0) の f80→f64 の丸め差は ADR D28 の帰結で、行案は `REPORT_APPENDIX_1099.md` §6 (D24 (案)) にある。 本付録は関数単位の観測のみを足す (`DEFECTS.md` は編集しない)。

- 親 issue: #3715 (PLG-G2-31・親 #2989)。 前付録: `REPORT_APPENDIX_2989.md`。
- 測定 commit: `54ea02944` (main (`861c6aef8`) 取り込み後の merge commit。 試験コードを変えた最後の code commit)。 旧測定 commit `e706cc113`・`b3275dc1c` の実測は、main 取り込みで試験ハーネスが変わったため、本記録の値として使わない (§6 の鮮度の証跡)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` と乱数 (seed 2989) で生成した試行のみ。

## 1. 結論

- 受入条件 (残り leaf x87 関数 36 本の突合) は **満たせなかった**。 lift 済みで x87 を含み、call・間接分岐・未対応命令を含まない関数は、本 run の走査で 42 本 (既存 2 本を含む)。 そのうち **構造 (eax・x87 深さ・行数) が全行一致して突合が成立したのは 5 本** (既存 2 本 + 新規 3 本)。
- 残りの 37 本は、§2 の 5 種類に分かれた。 うち 4 本は構造が一致せず (eax の不一致、または比較結果の差)、12 本は試験ランナーが異常終了した。 これらは未解決 (§5)。
- 判定器 (`x87_fn_diff.py`) の PASS は、構造が一致した 5 本だけで成立する。 構造の不一致行は FAIL に数える (従来どおり)。 ただし非自明性の判定は**緩めた** (§3): 旧判定 (OBJ 窓が変わった行 > 0) では、ST(0) だけを返す関数を数えられないため。 この緩和により、定数関数 11 本は突合の対象から外した。
- ネガコン 2 種 (判定器の 1 bit 反転・lowering の SUB→SUBR の取り違え) は HEAD で検出した。

## 2. 対象の分類 (lift 済み・x87 を含み・call / 間接分岐 / 未対応命令を含まない 42 本)

| 分類 | 本数 | 関数 (VA) | 扱い |
|---|---:|---|---|
| 突合が成立 (構造 全行一致・非自明) | 5 | `10002ee0`・`10005400` (既存 2 本)・`10005d20`・`1000b3a2`・`10001290` | `TARGETS` に入れて PASS |
| 構造が一致しない | 3 | `10009eb5` (eax 全 200 行不一致)・`1000b526` (eax 101 行不一致)・`1000bf60` (eax 4 行不一致) | 除外・§5 |
| ST(0) が NaN と −0 で不一致 (構造は一致) | 1 | `1000d6fb` (native NaN・wasm −0) | 除外・§5 |
| 試験ランナーが異常終了 (native) | 6 | `10003fe0`・`100051f0`・`100085a0`・`100096d0`・`1000a95a`・`1000ba05` | 除外・§5 |
| 試験ランナーが異常終了 (wasm のみ) | 6 | `1000b6c1`・`1000b8a2`・`1000b8cd`・`1000b8cf`・`1000b8f7`・`1000b936` | 除外・§5 |
| 単独の入口として扱えない断片と見られるもの (`add esp, 0x2c` で始まり、呼出し元のスタックを動かす。 本 run では `1000c084` の単独試験で、2 行目以降が出力されない現象を確認) | 10 | `100052d0`・`10005550`・`10009bc4`・`1000bf1e`・`1000c084`・`1000c08f`・`1000c09a`・`1000c0a0`・`1000c0a6`・`1000c0ac` | 除外・§5 |
| 非自明性なし (OBJ 窓を書かず、ST(0) が 0 / −0 固定の定数関数) | 11 | `100011a0`・`10001200`・`10001ac0`・`1000b390`・`1000b4e6`・`1000b4f4`・`1000b6d1`・`1000b894`・`1000b89d`・`1000d684`・`1000d691` | 除外 (突合しても情報が無い) |

計 5 + 3 + 1 + 6 + 6 + 10 + 11 = 42。 受入条件の「36 本」との差 (4 本) の理由は未確認。 本 run は「lift 済み・x87 を含む・call / 間接分岐 / 未対応命令を含まない」を機械的に数えた (`ott_lifted.c` の関数本体を正規表現で判定)。 候補の一覧は §2 の表を一次情報とする。

## 3. 方法の変更 (本 run)

- 新規 3 本は引数の型が関数ごとに分からないので、`gen: 'mixed'` (a0 は一様な float32 (±100)、a1..a5 は 0..15 の整数) で生成した。 1 関数 200 行 (`N_PER_MIXED`)。 既存 2 本の入力列 (seed 2989・4000 行) は変えていない。
- 非自明性の判定を『OBJ 窓が変わった行 `> 0`』から、『OBJ 窓が変わった行、または ST(0) が 0 / −0 でない行 `> 0`』に変えた (OBJ 窓を書かず ST(0) だけを返す関数のため)。 既存 2 本は OBJ 窓が毎行変わるので、判定結果は変わらない。
- native のバッファを 32MiB から 64MiB に広げた (`IBUF_SZ`・`OBUF_SZ`)。 40 本 × 200 行の入力と出力が 32MiB に収まらないため。
- 試験ランナーが異常終了したとき native は exit 0 で抜けて出力が欠ける (本 run で確認: `1000c084` の 2 行目以降が出ず、`rc=0`)。 そのため、行数の突合 (`件数 native / wasm / 期待`) が、欠損の検出の役割を果たした。 ランナーの exit 規約は変えていない (この欠陥は §5 で未解決として扱う)。

## 4. 実測 (測定 commit `54ea02944`・HEAD で再現)

| 関数 | n | 行の全項目が bit 一致 | float32 結果 (ST(0)・OBJ 窓) のみ一致 | ST(0) float64 の一致 / 1ulp / 2ulp / ≥3ulp | eax 不一致 | x87 深さ不一致 | OBJ 窓が変わった行 |
|---|---:|---:|---:|---|---:|---:|---:|
| `10002ee0` | 4,000 | 3,890 (97.25%) | 4,000 / 4,000 | 3,890 / 64 / 22 / 24 | 0 | 0 | 4,000 |
| `10005400` | 4,000 | 3,405 (85.12%) | 4,000 / 4,000 | 3,405 / 595 / 0 / 0 | 0 | 0 | 4,000 |
| `10005d20` | 200 | 200 (100.00%) | 200 / 200 | 200 / 0 / 0 / 0 | 0 | 0 | 200 |
| `1000b3a2` | 200 | 200 (100.00%) | 200 / 200 | 200 / 0 / 0 / 0 | 0 | 0 | 0 |
| `10001290` | 200 | 200 (100.00%) | 200 / 200 | 200 / 0 / 0 / 0 | 0 | 0 | 0 |

- OBJ 窓の float32 語 (1,344 B): `10002ee0` 1,344,000 語・`10005400` 1,344,000 語・`10005d20` 67,200 語 = 全語一致。 `1000b3a2`・`10001290` は OBJ 窓を書かず、ST(0) が非ゼロで一致 (本付録では ST(0) の一致で非自明性を示す)。
- 所要 (`54ea02944`・foreground の wall 時間。 `lift_text.py` 20 s (rc 0)、通常 `x87_fn_diff.py` 21 s (rc 0・load1 開始時 0.69)、`--special` 15 s (rc 0・load1 開始時 0.85)、`--nega` 2 s、`--nega-lower` 10 s、`--special --nega-nan` 8 s。 native build・emcc の内訳は本 run では未計測)。
- 再現: 同じ seed で 2 回実行し、`work/x87fn/native_out.txt` の md5 は実行ごとに同一 (ネガコン後の再測定で確認)。

## 5. ネガコン・未解決

ネガコン (HEAD で実行。 exit 0 = 検出):

- (a) 判定器: wasm 側の bit 一致行 (行 0) の ST(0) の最下位 bit を反転 → bit 一致 `7895 → 7894` (`python3 x87_fn_diff.py --nega`)。
- (b) 意味の誤り: `f_10002ee0` の最初の `fsubp` の SUB→SUBR を取り違えると float32 結果が一致しない行 `4,000 / 4,000` (`python3 x87_fn_diff.py --nega-lower`)。

未解決 (起票先は PR 本文の表を正とする):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 構造が一致しない 3 本: `10009eb5` (eax が全 200 行不一致。 native `0x4d41`・wasm `0x4800`。 ST(0) は native NaN・wasm 0)・`1000b526` (eax 101 行の不一致。 差は eax の `0x228`/`0x229` で、C1 (`0x200`)・PE (`0x20`)・OE (`0x08`)・IE (`0x01`) の bit。 C0/C2/C3 ではない。 `ott_x87.h` の制限 (6) は C1 だけを扱うので、例外フラグの模型化の範囲かは未確認)・`1000bf60` (eax 4 行の不一致。 原因未確認) | 比較・状態語の lowering の差か判定器の模型の限界かが未確定。 受入の構造一致を満たせない | #4064 (PLG-G2-40) |
| ST(0) が NaN と −0 で不一致する `1000d6fb` (構造は一致) | 無効演算・0 除算の NaN の扱いの差の可能性 (未確認) | #3716 (PLG-G2-32・例外的な入力) |
| 試験ランナーが異常終了する 12 本 (native 6 本・wasm 6 本)。 原因は未確定。 wasm 側の `1000b6c1` は `A_(0x10024d50)` (イメージ外の絶対アドレス) を読むことまで確認した。 他は未確認 | ランナーが入力を入れられない。 native は異常終了時も exit 0 で出力が欠ける (§3) | #4065 (PLG-G2-41) |
| 単独の入口として扱えない断片 10 本 (`add esp, 0x2c` で始まる) | 単独の入口として呼べない。 判定規則は #4084 で main 済み (`x87_fn_diff.py --classify`)。 入口 4 本と断片 6 本の試験は #4080 | #4080 (親 #4066・PLG-G2-42。 #4066 は CLOSED) |
| 定数関数 11 本 (非自明性なし) | 突合しても情報が無い。 入力の範囲を変えても観測できるかは未確認 | 起票しない (PR 本文の未解決表で扱う。 #3715 の範囲外として縮める) |
| 超越関数・`frndint`・`fscale`・`fprem` 等 | 対象外 (lift が `ott_unsup` のまま) | 対象外 (前段は完了済みの #3687・#2967) |
| `fld`/`fstp` m80 の差分試験 | 80bit メモリ経路は未試験 | 対象外 (前段は完了済みの #3687・#2967) |
| f80→f64 の丸め差 (ST(0) の double で 1 ulp 以上。 分布は §4) | float32 結果には伝播しなかった。 方式の帰結 | ADR D28 (方式)。 行案 D24 (案) は `REPORT_APPENDIX_1099.md` §6 |

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 EMSDK=$RUNNER_TEMP/emsdk/emsdk   # fl-win64 は extracted/block22434_PE.bin のみで足りる
source $EMSDK/emsdk_env.sh                                                 # emsdk 6.0.12 (toolchain-emsdk)
python3 tools/plugins/slayer_engine_ia32/lift_text.py                      # work/lift_text/ott_lifted.c を作る (前提)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py                    # 突合 (exit 0・PASS)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --nega             # ネガコン (a) (exit 0)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --nega-lower       # ネガコン (b) (exit 0)
```

- 鮮度の証跡 (WORKFLOW §6): main 取り込み前の測定 commit `d5afb6ae5` から `b3275dc1c` までの試験コードの差分は次のとおり (`x87_fn_diff.py` に `--classify` 分岐を追加した。 #4084 の変更。 `x87_fn_native.c` は差分 0)。 この分岐は全ての実行で評価されるため、本記録の値は `b3275dc1c` で取り直した。
  ```
  git diff d5afb6ae5 b3275dc1c -- tools/plugins/slayer_engine_ia32/x87_fn_diff.py tools/plugins/slayer_engine_ia32/x87_fn_native.c
  → x87_fn_diff.py | 52 +++++++++++++++++++++++++  (1 file changed, 52 insertions(+))
  ```
  次に main (`946ea5588`・#4064 の PROBE 追加と `run_chunked`) を取り込んだ `b3275dc1c..e706cc113` の差分は、測定ハーネスの変更 (`PROBE` は `X87_PROBE=1` のときだけ加わる。 `run_chunked` は入出力を 8,000 行ずつに分ける。 判定規則は不変)。
  ```
  git diff b3275dc1c e706cc113 -- tools/plugins/slayer_engine_ia32/x87_fn_diff.py tools/plugins/slayer_engine_ia32/x87_fn_native.c
  → x87_fn_diff.py | 32 +++++++++++++++++++++++++-  (1 file changed, 29 insertions(+), 3 deletions(-))
  ```
  次に main (`861c6aef8`) を取り込んだ `e706cc113..54ea02944` の差分は、`x87_fn_native.c` の RBP 初期化 (`x87_fn_glue.c` と揃えた `GUEST_STACK_TOP - 0x1000`) の 1 行ずつ。 `--special` の一部の bit 一致の数値がこれで変わった (`10005d20` 3,488 → 3,490・`10005400` の NaN 併記 637 → 639)。 上の実測は全て `54ea02944` で取り直した値。
  ```
  git diff e706cc113 54ea02944 -- tools/plugins/slayer_engine_ia32/x87_fn_glue.c tools/plugins/slayer_engine_ia32/x87_fn_native.c
  → x87_fn_glue.c | 2 +- / x87_fn_native.c | 2 +-  (2 files changed, 2 insertions(+), 2 deletions(-))
  ```
  測定 commit `54ea02944` から HEAD までの試験コード差分 (`git diff 54ea02944 HEAD -- tools/plugins/slayer_engine_ia32/x87_fn_diff.py tools/plugins/slayer_engine_ia32/x87_fn_native.c tools/plugins/slayer_engine_ia32/x87_fn_glue.c tools/ott/rt`) は、この記録を commit する時点で 0 件 (文書のみ)。
- `--special` (例外値の入力) の実測 (`54ea02944`・20,000 行): PASS (exit 0)。 bit 一致は `10002ee0` 3,140 / 4,000・`10005400` 3,098 / 4,000・`10005d20` 3,490 / 4,000・`1000b3a2` 3,999 / 4,000・`10001290` 4,000 / 4,000。 構造 (eax・x87 深さ) は全行一致 (`10005400` は NaN どうし 639 行を別計上)。 ネガコン `--special --nega-nan` (NaN を 1.0 に置換) は nan-num 0 → 1・判定 FAIL で検出。
