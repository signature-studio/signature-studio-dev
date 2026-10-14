# 付録: icall #1814 (ICALL-40) — Fresh Air SlateCore の native CRT 初期化 (部分達成)

> 親: #1606 (ICALL-34)。前回 1 run の受入条件 1 (CRT 初期化) を本 run で検証した。
> 本 run で満たすのは 2 (fail-fast import の列挙) と 3 (sweep 件数の実測) のみ。
> 受入条件 1 は子 issue へ移管した (§5)。

## 1. 結論

- 受入条件 1 (native 側で DllMain・.data 敷設を再現し SIGSEGV 66 関数を解消): **未達・子 issue へ移管**。
  DllMain (entry RVA `0x100be34`) を直接呼ぶと、image 外の libc 側で SIGSEGV する (§3)。
  `.data` は `ott_load` が既に敷設しており、残る不足は DllMain 内の実行経路と IAT の未実装 import。
- 受入条件 2 (解消できない import を fail-fast で列挙し REPORT に残す): **達成**。IAT 252 件のうち 226 件が未実装 (§4)。
  再現スクリプト `tools/icall/diff/fa_imports.py` を追加。
- 受入条件 3 (`fa_sweep.sh 8 60` の件数を更新): **達成**。今回の実測は 40 / 66 / 15 / 10 (§2)。前回 #1606 と一致。

## 2. sweep 実測 (`bash tools/icall/diff/fa_sweep.sh 8 60`)

測定 commit: `486eab5d` (`origin/main` = 作業ブランチ `1814-icall-native-crt` の起点)。
コード差分は本 PR で `tools/icall/diff/fa_imports.py` (新規・sweep 非参照) と本付録のみ。

| 項目 | 値 |
|---|---|
| 関数数 | 131 (`tools/icall/work/rt_freshair-core/map.json` の func_map) |
| 所要 | 73.4 s (real) / 69.5 s (user)。開始時 load 0.31・終了時 0.88 (4 vCPU) |
| 素材 | `work-icall` を worktree 直下に展開 (`tools/icall/work/`)。`plugins-freshair` を `FA_DL` 経由で `fetch.sh` 展開 (win 17 files・factory .epf 8 本) |
| wasm route | `bash tools/icall/fa_route_build.sh` OK (9.8 s)。`missing` は 4 関数 (`1801a9a6c` `1801a9b38` `1801c8c00` `1801c8cb8`) |
| 集計 | **bit一致 40 / native crash・timeout 66 / wasm のみ err 15 / 値の不一致 10** (合計 131) |

## 3. DllMain の直接実行 (受入条件 1 の切り分け)

- `ott_load` で SlateCore を敷設 (`.data` は PE のセクションからコピー済み) → `ott_call(0x18100be34, rcx=0x180000000, rdx=1, r8=0)`。
- 結果: `SIGSEGV rip=0x7ffff7202918 (libc 側) addr=(nil)`。DllMain 内の途中 (`rcx=6 rdx=1`) で image 外の関数へ飛んでいる。
- `1803de310` 単体 (`fa_cmp.py 1803de310 --n 2`) の SIGSEGV は再現 (`rip=0x1803de3a5 addr=0x60100000`)。
  `0x1803de3a5` は大きな 8 byte 単位のコピーループ内で、呼出し元から渡された `rcx=0x600ff810` (thunk 領域直後) を読んでいる。
  global を誰が設定するかは未特定。

## 4. 未実装 import (受入条件 2)

`python3 tools/icall/diff/fa_imports.py` の実測 (ott_native.c の IMPL 表と IAT の突合)。

| 項目 | 値 |
|---|---|
| IAT 総数 | 252 |
| 実装済み | 26 |
| 未実装 (実行時 `missing_import` で即 exit(99)) | **226** |

| DLL | 未実装件数 |
|---|---|
| KERNEL32.dll | 125 |
| USER32.dll | 74 |
| SHELL32.dll | 10 |
| GDI32.dll | 7 |
| ole32.dll | 7 |
| COMDLG32.dll | 2 |
| ADVAPI32.dll | 1 |

未実装の全名は `python3 tools/icall/diff/fa_imports.py` の出力 (1 行 1 件) を正とする。
CRT 初期化の実行経路で実際に呼ばれるものは §3 の経路と合わせて特定が必要 (子 issue の範囲)。

## 5. 残り (子 issue へ移管)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| DllMain (`0x18100be34`) の直接実行で libc 側 SIGSEGV (§3)・CRT 初期化の実経路の特定・未実装 import 226 件 (§4) のうち実経路で必要なもの | sweep の native crash 66 関数 | 子 issue #1874 (ICALL-47) |
| 値不一致 10 関数 | #1632 | #1632 |
| closure 外 missing 15 関数 | #1633 | #1633 |

## 6. 再現

```
cd <repo root>
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60          # 末尾に 4 区分の件数
python3 tools/icall/diff/fa_imports.py --md     # 未実装 import の一覧
python3 tools/icall/diff/fa_cmp.py 1803de310 --n 2   # SIGSEGV 確認
```

素材: `work-icall` (repo 直下に展開)・`plugins-freshair` (`FA_DL=<展開先> bash tools/targets/freshair/fetch.sh`)。
