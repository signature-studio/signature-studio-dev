# tools/flelift/boot — REPORT 付録 (FLE-29 (#4806) A1: opt-in 経路 (FLE_IPP=1) で `0x15F34A0` が 0 に戻る経路)

> `REPORT.md` の付録。親 #4806 (PM 改訂 2026-10-15・代替条件 A1/A2)。診断は opt-in (`FLE_IPP=1`・`FLE_WWATCH`)。
> 既定経路 (`FLE_IPP` 未指定) の挙動は変えていない。`rt/` と `x64c.py` は変えていない。

## 結論 (先出し)

- **A1 の前提は一部誤り**: `dsp_ippv2_x64.dll` の `LoadLibraryW` は失敗していない。`fle_ipp_load_hook` は呼ばれ、非 0 (`0x7f0f0000`) を返す。`ippsZero_8u` の登録トークン `0x7f10001c` は unit 132 で `0x15F34A0` に書かれる。
- **mode 1 で終了時に 0 になる直接の原因**: unit 209 の GetMem 入口 (site 8) の直前で、`0x15F34A0` が `0x7f10001c` → `0` に**書き戻される** (`FLE_WWATCH` で ret `0x1078570`・16 バイト `STX` 書込み)。unit 209 の `[fill6a7b70]` (既定 root の fill) と同じ unit で起きる。
- 既定経路 (mode 3) では同じ slot が unit 209 を越えても `0x7f10001c` のまま (`ptr_15F34A0=0x7f10001c`・IPP 判定 OK)。mode 1 と mode 3 の差は ILT の分岐入力だけ。
- **未解決**: `ret=0x1078570` を書く関数 (guest の store 元) は、lifted C の該当 VA と突き合わせられなかった。次の 1 手は、この VA を含む関数の特定 (`dbg_lift.py --at 0x1078570` で行を引く)。

## 1. 測定 (HEAD `2bd8fecf6`・素材 fl-win64・emsdk 6.0.12・n=1・`fle6_measure.sh`)

| 経路 | FLE_IPP | mode | units_run | stopped_at | FLEBOOT_IPP_CHECK | rc |
|---|---|---|--:|--:|---|--:|
| shim | 1 | 1 | 209 | 209 | `ptr_15F34A0=0x0` (NG) | 3 |
| 既定 | 未指定 | 3 | 895 | 895 | `ptr_15F34A0=0x7f10001c` (OK) | 0 |

工程 (本 run): lift 76〜78 s・clang plain 76〜89 s・boot shim 24〜25 s・boot default 10 s。load は実行前 1.1〜2.5。

前 run との比較: 既存の REPORT (`REPORT_APPENDIX_4783`・`4983`・`5013`) と一致。

## 2. hook の呼出し (A1 の 1 点目)

`fle_ipp_load_hook` に stderr の 1 行を追加した (`[fleboot-ipp] load_hook ...`・dsp_ippv2 の要求時だけ出る)。

```
[fleboot-ipp] load_hook name=dsp_ippv2_x64.dll flags=0x0 ret=0x7f0f0000 n=1
```

- 呼出しは 1 回。戻り値は `IPP_HMOD` (`0x7f0f0000`)。
- `LoadLibraryExW` → `load_utf8` は `mod_resolve_locked` で未登録 → hook の順に進み、非 0 を返す。
- よって「0 を返す」仮説は**成立しない**。`f_6539e0` が受け取る値は非 0。

## 3. `0x15F34A0` の時系列 (A1 の 2 点目・`py_watch` の slot 追加)

`g_py_watch` に `0x15f34a0` を 8 本目として追加した (監視のみ・挙動は変えない)。`FLEBOOT_PY123` の events より:

| unit | site | proc | old | new | 意味 |
|--:|--:|--:|--:|--:|---|
| 0 | 0 | 0x0 | 0x0 | 0x0 | fle_run 直前 (初期値) |
| 132 | 8 | 0x1e | 0x0 | 0x7f10001c | `ippsZero_8u` の登録 (GetProcAddress 結果) |
| 209 | 8 | 0x74 | 0x7f10001c | 0x0 | GetMem(0x74) 入口で 0 に戻る |

site 8 = GetMem 呼出し直前 (`py_watch` の定義を参照)。書込み自体はその直前の guest 命令。

## 4. 書込み元 (A1 の 3 点目・`FLE_WWATCH`)

`-DFLE_WWATCH -DFLE_WWATCH_SLOTS=0x15f34a0ull` で再 lift・再 link して測定。

```
[fle_wwatch] ret=0x134891a slot=0x15f34a0 ... old=0 new=0x7f10001c   (登録・unit 132 付近)
[fle_wwatch] ret=0x1078570 slot=0x15f34a0 ... old=0x7f10001c new=0  (消去・16 バイト STX)
```

- 消去の戻り番地は `0x1078570`。直前の `call f_60a6c0` の戻り番地 `0x1078550` は同じ関数内 (推定)。
- 16 バイト書込み (`n=16`) なので、`STX` (`LDX`/`STX`・xmm 経由の store) である。
- **未解決**: `0x1078570` を含む関数の lifted C 上の行は、この work/ の出力では引けなかった (`grep` で 0 件)。`x64c` が別 VA 範囲の関数として出している可能性がある。次の 1 手は `dbg_lift.py --at 0x1078570` で行を引くこと。

## 5. 既定経路 (mode 3) との比較

既定 (`FLE_IPP` 未指定) は同じ slot が `0x7f10001c` のまま unit 895 まで進む (`ipp_called` の `ippsZero_8u` 3 回・`CreateCursorFromFont` 64 回)。mode 1 と mode 3 の差は ILT 分岐入力 (`ILTools_x64.dll` の擬似モジュール) で、この差が unit 209 の消去を止めている可能性 (未検証)。

## 6. 次の 1 手 (起票先)

- `0x1078570` を含む関数を特定し、消去の論理 (どの入力で 0 を書くか) を確認する → 本 issue の A1 の後続。範囲は別 run で扱う (未解決)。
- `0x15F34A0` の消去を止める (既定経路の挙動に関わる) のは本 issue の範囲外。
