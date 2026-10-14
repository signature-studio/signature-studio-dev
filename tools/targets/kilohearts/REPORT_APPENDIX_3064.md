# KH-37 (#3064) 付録: x64c 閉包 148 と TSV 160 行の数え方 (REPORT_KH19.md §10 の本体)

## 1. #3064 (KH-37) x64c の閉包 148 と TSV 160 行の数え方 (測定 commit `a89f92b2`, 4 vCPU)

- 注記: issue 本文の `REPORT_KH19D.md` は repo に存在しない。KH-19 系の正本は本ファイルなので、本節を §10 として置く。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/*` → `HeartCore.core_64` (76,642,304 B)。`tar --zstd -xf` で展開し Windows 側だけを手で取り出した (作業は `$RUNNER_TEMP`・repo 外)。
- 再現: `tools/targets/kilohearts` で `python3 scripts/gain_x64c_closure.py <HeartCore.core_64> gain_before_160.tsv <out>`。
  roots = TSV の root 27 件を入力に `tools/flelift/x64c.py` の main (`--closure 1000`) を実行し、閉包を得てから TSV の各行を分類する。
  測定 (測定 commit `a89f92b2`): 実行 66.97 s・load average 0.49 → 0.83 (4 vCPU・1 回)。

| TSV の区分 | 件数 | 内容 |
|---|--:|---|
| x64c 閉包に入る (hit) | 148 | x64c の閉包関数 148 (roots 27 を含む) |
| `iat_thunk` | 2 | `0xfd81e4`・`0xfd81ec`。`jmp [rip+IAT]` の thunk。x64c は imp 呼出として別扱い |
| `tail_absorbed` | 9 | 親の `jmp` 先。x64c は親の本体に取り込み、関数として数えない (`6500` `4d400` `f87d40` `fd099c` `fd66a0` `fd8d08` `fd8d24` `fe3488` `1327348`) |
| `seh_landing_pad` | 1 | `0xfc7468` (親 `0xfd08d0`・call 位置 `0xfd0995`)。下の (2) |
| `site_unreached` | 0 | call 位置が CFG 上で未到達で、SEH 着地点でもない行 |
| `other` | 0 | 上記以外 |
| 合計 | 160 | 148 + 2 + 9 + 1 = 160 |

差 12 件 = `iat_thunk` 2 + `tail_absorbed` 9 + `seh_landing_pad` 1。未説明の差は 0 件。

1. 数え方の規則:
   - x64c 閉包 = roots から制御フロー (jcc・jmp・jump table) と `call` の即値先で辿った関数。既知の関数以外への `jmp` は親に取り込む (関数として数えない)。IAT thunk は閉包に入れない。
   - TSV = `.pdata` 範囲内の直接 `call`/`jmp` を線形に拾った閉包。SEH 着地点の `call` も拾う。
2. `0xfd0995` が x64c の降下で到達しない原因 (実測):
   - 直前の命令は `0xfd0994: ret`。`0xfd0995` へ向く分岐・jump table は親の中に無い。
   - 親 `0xfd08d0` の UNWIND_INFO は `flags=1` (UNW_FLAG_EHANDLER)。scope table は 1 件: try 範囲 `[0xfd08f1, 0xfd094a)`・filter `0x1385f03`・**JumpTarget `0xfd0995`** (`__except` の着地点)。
   - `.rdata` の `0x26706ec` に、この scope entry の JumpTarget 欄 (4 B RVA) が 1 件ある。分岐の即値参照は 0 件。
   - よって `0xfd0995` は例外 unwind でだけ到達する。x64c の CFG 降下は仕様どおりこれを辿らない。TSV の線形走査は拾う。
3. 判定:
   - 受入 1 (原因の特定): **達成**。原因は SEH 着地点 (死コードではない)。
   - 受入 2 (差 0 または数え方の規則で説明): **達成** (差 12 = 2 + 9 + 1、未説明 0)。
   - `tools/flelift/x64c.py` は変更しない。`descend` の辺の規則を変えると全ルートの閉包と lift 出力が変わるため。例外経路を閉包に含めるかは、全ルートに効く別の判断として残す。
   - 未解決: `0xfc7468` (例外経路でのみ呼ばれる) を lift に含めるかの判断と、例外経路の挙動の検証。起票先 #850 (KH-19d: lift の最初の失敗点)。
4. 鮮度の証跡: 測定 commit `a89f92b2` 以降で `git diff a89f92b2 HEAD -- tools/targets/kilohearts/scripts` の出力は空 (0 行)。
