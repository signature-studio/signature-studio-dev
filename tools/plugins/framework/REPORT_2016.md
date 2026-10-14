# #2016 REPORT — 0x4181e0 の基底構造体と戻り値 (native 境界の確定・途中経過)

- 担当 issue: #2016 `[PLG-P0b-12]` (親 #1933)。
- 起点: `origin/main` c171b9dc。branch `2016-plg-p0b-12-base-struct-retval`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-fw-stage1` を repo 直下に展開。`work-liftlib` / `toolchain-*` / `plugins-ott` は本 run で未使用。
- コード変更: なし (`fw_hostfix.py` は未変更)。

## 1. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | `0x418190` の引数規約と呼出元から、`0x4181e0` の戻り値が指す基底構造体 (`+24` / `+520`) を確定 | **未達**。§3.1 で native の挙動を確定。基底構造体の型は呼出元 60 件超の `rcx` 由来の読解が要るため未完 |
| 2 | `0x4181e0` の正しい戻り値を確定し `fw_hostfix.py` を修正 | **未達** (1 が前提。コード変更なし) |
| 3 | `0x52cf40` の `@441`/`@443` 文言を native 側で確認 | **未達** (未着手。§4) |
| 4 | `0x4e6060` / `0x4e5f50` の IR 名と native の VA 対応を確認 | **達成** (§3.2。両 VA は `.pdata` 外の RTTI 文字列領域と確定) |
| 5 | REPORT に実測 (所要時間・load・PASS/FAIL) と Phase A 回帰 `dispatch=38 ff=0` | **達成** (§2) |

## 2. 実測

環境: 4 vCPU・メモリ 15 GiB。load は `uptime` の 1 / 5 / 15 分値。

| 手順 | commit | 結果 | 所要時間 (real) | load (開始時) |
|---|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用・`FL_WIN64_DIR` 指定) | c171b9dc (コード変更なし) | exit 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 7 分 29.97 秒 | 0.41 / 0.38 / 0.17 (08:27) |
| `hs_e2e.sh --fresh` | c171b9dc | exit 1 / Phase A `dispatch=38 ff=0` (回帰 OK) / `Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` / `E2E FAIL: 1 項目` | 2 分 42.20 秒 | 1.91 / 2.17 / 1.08 (08:34) → 1.06 / 1.67 / 1.07 (08:37) |

- Phase B の失敗は REPORT_1933 §2・REPORT_1891 §2 と同一 (OOB・`plug=0x0 rec=7`)。本 run で変化なし。
- 測定 commit は c171b9dc (コード変更なし)。測定 commit から HEAD までのコード差分は 0。

## 3. 読解

### 3.1 `0x4181e0` の native 側 (受入 1・2 の前提を確定)

`hs_callee_disasm.py` (`.pdata` 関数先頭基準) の出力:

- `.pdata` 関数 `[0x418190, 0x41820c)` の先頭は `push rsi` (`mov rbx, rcx` で第 1 引数を保持)。
- `0x4181e0` は `je 0x4181f6` の位置で、**この関数の内部ラベル**。`.text` 全体の直接 `call` で `0x4181e0` を呼ぶ箇所は 0 (REPORT_1933 §3.2 と同じ)。
- 関数の処理: `rcx` (=`[rbx]` の値) を取り出し、参照カウントを `lock xadd` で減算。0 になった場合のみ `call 0x416230` / `call 0x409440` を経由し、最後に **`rax = rbx` (第 1 引数そのもの) を返す**。

よって native の `0x418190` は「引数 `rcx` の参照を解放し、その引数を返す」関数で、lift 側の `@function_4181e0()` (引数なし・戻り値 `i64`) は、この 0x418190 の内部の値を切り出したものと読める。

### 3.2 `0x4e5f50` / `0x4e6060` の VA 対応 (受入 4)

- `.pdata` に含まれない (`hs_callee_disasm.py` で関数境界なし)。
- 先頭 32 バイトは ASCII 文字列: `0x4e5f50` = `tem.Generics.Defaults` (RTTI 名の断片)、`0x4e6060` = `Object>.ParrayofT` (同)。
- よって両 VA は **関数の先頭ではなく RTTI 文字列領域**。lift 側 (`@function_4e5f50` / `@function_4e6060`) の IR 名が、この領域を関数として decode した artifact である可能性が高い。fail-soft の根拠 (`fw_hostfix.py` の 0x4e6060 注釈) はこの前提で再検討が要る。

### 3.3 呼出元の規模 (受入 1 の残り)

- stage-1 IR (`tools/plugins/work/fw/*.restored.ll`) の `call @function_4181e0` は計 60 件超 (fw0 14・fw1 10・fw2 7・fw4 6・fw5 12・fw6 8・fw7 8・r2 8・r3 8 ほか)。
- r3 系 (`function_4181e0(i64 %rcx...)`) は引数付きで呼ばれており、lift 側の 0 引数版と引数規約が一致していない箇所がある。
- 基底構造体 (`+24` / `+520`) の型確定は、これら呼出元それぞれの `rcx` の由来 (`[rbx]` の参照先) を追う必要があり、本 run の時間では完了しない。

## 4. 残作業 (子 issue)

- 受入 1・2 (呼出元から基底構造体を確定し `fw_hostfix.py` を修正): **#2069 `[PLG-P0b-13]`**。
- 受入 3 残 と 受入 4 の追加 (`0x52cf40` の文言、`0x4e5f50` / `0x4e6060` の RTTI artifact 整理): **#2070 `[PLG-P0b-14]`**。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1・2: `0x4181e0` の基底構造体と正しい戻り値 | `fw_hostfix.py` の 0 注釈が deref の障害になっている可能性 | #2069 `[PLG-P0b-13]` |
| 受入 3 残: `0x52cf40` の `@441`/`@443` 文言 | 「見つからない」の意味が推定のまま | #2070 `[PLG-P0b-14]` |
| `0x4e5f50` / `0x4e6060` の RTTI 文字列 decode | fail-soft 注釈の根拠が前提から崩れている可能性 | #2070 `[PLG-P0b-14]` |
| fold deref (`0x40d6e0` / `[0x710040]`) と `plug != 0` | Phase B が OOB のまま | #1890 `[PLG-P0b-8]` / #2008 `[PLG-P0b-11]` (既存) |

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $HOME/artifacts/work-fw-stage1.tar.zst          # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh                      # exit 0・SMOKE PASS
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh        # FAIL (Phase B OOB) が期待値
python3 tools/plugins/framework/hostshim/hs_callee_disasm.py 60 0x418190 0x4181e0
```
