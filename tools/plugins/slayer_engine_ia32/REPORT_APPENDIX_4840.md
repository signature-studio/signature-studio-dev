# REPORT_APPENDIX_4840 — `0x10009bc4` の ST(0) 全行不一致の原因 (PLG-G2-65)

既知類型との関係: `ott_x87.h` の制限 (4) (スタックの over/underflow を模型化しない) の範囲。 同じ類型は #4146 (PLG-G2-49)・#4185 (PLG-G2-51)。 `docs/DEFECTS.md` の既存 ID へは当てていない。 新しい類型は作らない。

- 親: #4080 (親 #4066)。 本付録は #4840 の測定。 #4080 の突合 (`0x10009bc4`・`0x1000bf1e` の PROBE) の結論は `REPORT_APPENDIX_4080.md` を参照。 その入口状態の根拠として本付録を使う。
- 測定 commit: `fcd5bca07` (main 取り込み後の HEAD。 コードを変えた最後の commit)。 素材: fl-win64 の `block22434_PE.bin`・toolchain-emsdk (emcc 6.0.12、`tools/m1/flags.sh` の pin)。 seed 2989。
- 起動・GUI に関わらない (製品 KPI は対象外)。

## 1. 結論

- **issue 本文の前提の訂正**: `0x10009bc4` は cdecl の double 引数を取らない。 本体は `[ebp+8]` を読まず、先頭の `fistp qword` で呼出し時の **x87 ST(0)** を整数化する (`0x10009bc4`〜`0x10009bea`)。 入力は引数でなく ST(0) である。
- **空スタックの読みが原因**: 既存の harness (`x87_fn_diff.py`) は `fninit` のあと空スタックで呼ぶ。 その入口では ST(0) が空で、native (実 x87) は default NaN (-qNaN `ffc00000`) を返し、wasm の模型は 0 を返す。 4,000 行すべてが `nan-num` になる原因はこれ。
- **分類**: 模型の限界 (`ott_x87.h` の制限 (4)・underflow) で、lowering の誤りではない。 double を ST(0) に積んだ入口では差が 0 (§2)。 これが lowering の正しさを示すのは、同じ経路で測ったこの関数の 4,000 行に限る。
- **入力を ST(0) に積むと一致**: 呼出し前に double を 1 個積むと (`X87_PUSH64=1`)、native と wasm は 4,000 行すべて eax・ST(0)・x87 深さ・bit が一致する。 特殊値 (NaN・±inf・非正規・±0・int32 境界) を含む 4,000 行も 4,000 / 4,000 で一致。
- **TARGETS の判定 (入れない)**: 下記 §3 の理由で既定ゲート (`TARGETS`) には入れない。 測定は `X87_PUSH64=1` の経路で行う。

## 2. 測定 (HEAD `fcd5bca07`・実測)

| 試験 | 入口状態 | 結果 (native vs wasm) | 判定 |
|---|---|---|---|
| `X87_PROBE=1`・`fn_10009bc4` (既存 harness) | 空スタック | 0 / 4,000 行 bit 一致・4,000 / 4,000 行 `nan-num` (native `ffc00000`・wasm `00000000`)。 eax 一致 | 空スタックの underflow (模型の限界) |
| `X87_PUSH64=1` (double を ST(0) に積む) | double を積む | 4,000 / 4,000 行 bit 一致。 構造 (eax・x87 深さ) 不一致 0 | PASS |
| `X87_PUSH64=1 --special` (NaN・inf・非正規・±0・int32 境界) | double を積む (特殊値) | 4,000 / 4,000 行 bit 一致 | PASS |
| 既定ゲート `python3 x87_fn_diff.py` | 既存 TARGETS (7 本) | PASS・rc 0。 構造不一致 0。 下の内訳 | 既存の入口状態は変えていない |
| `--nega` (既定経路の 1 bit 反転) | 既存 | bit 一致 22619 → 22618 (検出) | ネガコン OK |
| `--nega-lower` (lowering の取り違え) | 既存 | `fn_10002ee0` の float32 不一致 4000 / 4000 (検出) | ネガコン OK |

- 既定ゲートの内訳 (bit 一致 / 行数): `fn_10002ee0` 3890 / 4000・`fn_10005400` 3405 / 4000・`fn_1000b6c1` 4000 / 4000・`fn_1000b936` 4000 / 4000・`fn_10005d20` 200 / 200・`fn_100052d0` 3761 / 4000・`fn_10005550` 3363 / 4000。 float32 (ST(0)・OBJ 窓) は 7 本とも全行一致。 float64 の差は f80→f64 の 1 ulp (D28)。
- `X87_PROBE=1` の出力: rc 1 (想定どおり。 ゲートではない)。 `fn_1000bf1e` 4000 / 4000 一致。 FAIL は `fn_10009eb5` 0 / 4000・`fn_1000b526` 2036 / 4000・`fn_1000bf60` 1933 / 4000 (PROBE コメントの既知の不一致) と `fn_10009bc4` 0 / 4000 (空スタック基準線)。
- `X87_PUSH64=1` の PASS の判定には、戻り値 eax の種類が 2 以上であること (`x87_fn_diff.py` の `nontrivial` 判定) を含む。 OBJ 窓と stack 窓は書かない関数なので、非自明性はこれで示す。 種類数そのものは出力していない。

## 3. TARGETS の判定 (入れない)

| 理由 | 内容 |
|---|---|
| 既定の入口状態が模型の範囲外 | 既定ゲートは空スタックで呼ぶ。 `0x10009bc4` の実際の入口は ST(0) に値がある。 空の入口で通すと、underflow を模型に入れた値を比べることになる |
| 出力が eax だけ | OBJ 窓・stack 窓を書かないため、既定ゲートの「窓が変わった行」の判定が通らない。 通すには判定器を関数ごとに変える必要がある |
| 呼出し元の深さが未確認 | 50 箇所の呼出し元のうち、確認したのは `0x100013fb` の 1 件だけ (直前の `fmul` が ST(0) に残す)。 残り 49 件の呼出し時の x87 深さは未測定。 49 件は #4064 に起票済み (`docs/REFERENCES.md` への追記は外部資産の追加が無いため無し) |

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出し元 50 箇所の、呼出し時の x87 深さ (ST(0) に値があるか) | `0x10009bc4` を TARGETS に入れる判断の根拠が 1 件のみ | #4064 (親・OPEN。 入口状態の再判断) |
| 空スタック入口の扱い (default NaN か 0 か) | 既存の入口状態の決定 (#4146 CLOSED) と同じ論点 | #4064 (PM が再判断) |
| eax 専用の関数を既定ゲートで通す判定器の設計 | `0x10009bc4` を既定ゲートに入れる場合に必要 | #4064 |

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64   # 素材 [WIN64] (docs/REFERENCES.md)
python3 tools/plugins/slayer_engine_ia32/lift_text.py                 # work/lift_text/ott_lifted.c を作る
X87_PROBE=1 python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py     # 空スタックの基準線 (fn_10009bc4 は FAIL する)
X87_PUSH64=1 python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py    # double を ST(0) に積む (PASS)
X87_PUSH64=1 python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --special   # 特殊値 (PASS)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py                  # 既定ゲート (PASS・7 本)
```

測定 commit `fcd5bca07` の実測 (ログ抜粋): `lift_text.py` 17.57 s・rc 0。 既定ゲート wall 15.10 s・rc 0 (build native 0.21 s・wasm emcc 7.60 s / run native 0.378 s・wasm 0.689 s)。 `X87_PUSH64=1` wall 9 s・rc 0 (build wasm emcc 7.28 s)。 `--special` wall 8 s・rc 0。 `--nega` wall 7 s・rc 0。 `--nega-lower` wall 12 s・rc 0。 load は各 run 前後で 1.2〜1.4。
