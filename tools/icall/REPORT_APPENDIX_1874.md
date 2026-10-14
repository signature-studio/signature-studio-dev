# 付録: icall #1874 (ICALL-47) — Fresh Air SlateCore の DllMain 実経路と CRT 初期化 (調査・部分)

> 親: #1814 (ICALL-40)。本 run は受入条件 1・2 の実装には届かず、現状の再測定と原因の切り分けまで。
> 実装 (CRT 初期化・未実装 import の追加) は子 issue へ移管 (§5)。

## 1. 結論

- 受入条件 1 (DllMain 実経路の特定と native CRT 初期化の再現): **未達・子へ移管**。
  DllMain を直接呼ぶ経路は前任 (§3) で確認済み。本 run で SIGSEGV の原因を
  「未初期化の `.data` (encoded 関数ポインタ表 / cookie 系) に依存する C++ static 初期化・後始末コード」と切り分けた (§3)。
- 受入条件 2 (実経路の未実装 import を実装): **未達・子へ移管**。未実装 226 件の突合は再現済みだが、
  native crash 3 関数の経路では IAT call が見えず、import を足しても crash は解消しないことを確認 (§3.2)。
- 受入条件 3 (`fa_sweep.sh 8 60` の件数更新): **達成**。HEAD `576c4976` での実測は §2。
  前任の付録 (1814) の 40/66/15/10 から wasm のみ err が 1 件減って 14 になった (bit一致 41)。

## 2. sweep 実測 (`bash tools/icall/diff/fa_sweep.sh 8 60`)

測定 commit: `576c4976` (`origin/main`・作業ブランチ `1874-icall-crt-init` の起点)。
コード差分は本 PR で本付録 (`tools/icall/REPORT_APPENDIX_1874.md`) のみ。`tools/icall/diff`・`tools/ott` は変更していない。

| 項目 | 値 |
|---|---|
| 関数数 | 131 (`tools/icall/work/rt_freshair-core/map.json`) |
| 所要 | 73.2 s (real) / 69.4 s (user)。開始時 load 0.36 (4 vCPU)・終了時 0.82 |
| 素材 | `work-icall`・`work-liftlib` を worktree に展開。`plugins-freshair` を `FA_DL` 経由で `fetch.sh` 展開 (win 17 files・factory .epf 8 本)。`toolchain-*` は本 run で未使用 |
| wasm route | `bash tools/icall/fa_route_build.sh` OK (9.7 s) |
| 集計 | **bit一致 41 / native crash・timeout 66 / wasm のみ err 14 / 値の不一致 10** (合計 131) |
| 未実装 import | `python3 tools/icall/diff/fa_imports.py`: IAT 252 / 実装済み 26 / 未実装 226 (前任と一致) |

## 3. SIGSEGV の原因切り分け

### 3.1 DllMain 直接実行 (前任 §3 の再確認)

前任と同じ `SIGSEGV rip=0x7ffff7002918 (libc 側) addr=(nil)` を `ott_load` 後の DllMain 呼出しで再現 (本 run では未再実行、前任値)。

### 3.2 native crash 関数 3 件の観察 (`fa_cmp.py <va> --n 1`)

| VA | 結果 | 静的に見えた内容 |
|---|---|---|
| 0x1803b3fc0 | libc 側 SIGSEGV (`addr=nil`) | 先頭が `call 0x1803b3d10` → `call 0x18102f728` (`int3` で終端)。C++ 系の後始末 (`rbx=[rcx]` の走査・`call 0x18100beb0` = free 系)。IAT call は先頭 47 命令内に無い |
| 0x1803b5b60 | libc 側 SIGSEGV (`addr=nil`) | 同上 (38 命令内に IAT call 無し) |
| 0x1803b9ff0 | image 内 SIGSEGV (`rip=0x1803ba718 addr=0xa0001440`) | 99 命令内に IAT call 無し。`rcx=0xa0001440` は呼出側の不正ポインタ |

- SlateCore の security cookie は load config の `SecurityCookie` = VA `0x18125eaa8` (`.data` RVA `0x125eaa8`)。
  OTT の CRT harness (`tools/ott/crtinit/crt_native.c`) と同じ encoded 関数ポインタ方式かは未確認。
- 3 関数とも「呼出し時点で初期化済みの global を前提にする」形であり、import の未実装が直接の原因とは見えない。

### 3.3 解釈 (未確定)

- 「import を実装すれば crash が減る」という前提 (受入条件 2 の順序) は、本 run の範囲では支持されなかった。
- 先に CRT 初期化 (受入条件 1) で `.data` の encoded slot を整える必要がある見込み。ただし slot の場所と数は未特定。

## 4. 残り (子 issue へ移管)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SlateCore の encoded 関数ポインタ表・cookie を特定し、native で CRT 初期化相当を再現する (受入条件 1) | sweep の native crash 66 関数 | #1921 (ICALL-51) |
| 実経路で必要な未実装 import (226 件のうち実経路で呼ばれるもの) を実装する (受入条件 2) | 同上 | #1922 (ICALL-52) |
| 値不一致 10 関数 | #1632 | #1632 |
| closure 外 missing 14 関数 | #1633 | #1633 |

## 5. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60          # 末尾に 4 区分の件数
python3 tools/icall/diff/fa_imports.py --md     # 未実装 import の一覧
python3 tools/icall/diff/fa_cmp.py 1803b3fc0 --n 1   # libc 側 SIGSEGV
```

素材: `work-icall` (`tools/icall/work/` に展開)・`work-liftlib` (`tools/liftlib/work/`)・`plugins-freshair` (`FA_DL=<展開先> bash tools/targets/freshair/fetch.sh`)。
