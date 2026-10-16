# flp #5649: 実行時観測の前提 (wine64 + gdb で FL64.exe の VA にブレーク)

親: #5376 / 前提: #5614・#5615 (受入 1〜3 は #5614・#5615 に残す)。本 issue は環境構築と「ブレークを張れる」ことの実測だけを扱う。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. wine64 + 依存で FL Studio 26.1.7 win64 (`fl-win64`) を起動 | 達成 (起動は GUI 継続で 120 s 上限まで終了せず) | §2 |
| 2. gdb を wine の win64 プロセスにアタッチし、任意 VA にブレークを張る | 達成 (アタッチ・ブレーク挿入を 2 VA で確認)。命中は未確認 (60 s 内に無し・§3) | §3 |
| 3. 環境構築手順を本 issue の run の結果として記録 | 達成 (本ファイル §4) | §4 |

## 2. 起動 (受入 1)

- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 5.48 s)。インストーラ `flstudio_win64_26.1.7.5653.exe` と `extracted/` を得る。`extracted/` の通常ファイルは 25,166 件 (`find -type f`)。インストール木の 25,164 / 25,165 block は S1 の block 表 (path を付けた block 数 / 全 block 数) で、別の数え方。
- wine: apt の `wine64` 9.0 (`/usr/lib/wine/wine64`)・`xvfb`・`gdb` (15.1) を導入。`wine32` は未導入 (警告のみ・起動に不要だった)。
- インストール木: `tools/flp/s1_wine_probe.sh` をそのまま実行 (`RUNNER_TEMP` 配下に組立て)。インストール木 25,164 / 25,165 block にパスを付与。G03 (Authenticode) の 3 箇所を `s1_g03_patch.py` で書換え (既存 S1 と同じ。oracle ローカルコピーのみ)。
- 結果: `S1 rc=124` (120 s で終了せず GUI 継続)。所要 real 2 m 10 s。S1 の実行は `WINEDEBUG=-all` (log 先頭行)。`-all` は全チャネルを落とすため、log 上の `S1 MSGBOX_OnInit=0 FLEngine_x64.dll native-load=0` は『呼ばれなかった』の証拠にならず、MSGBOX / native-load は未計測として扱う。

## 3. gdb アタッチとブレーク (受入 2)

- 追加: `tools/flp/s3_gdb_attach_probe.sh` (起動 → FL64.exe の PID と image base を取得 → gdb `-p` でアタッチ → `break *<VA>` → `continue` → `detach`)。
- 実行条件: `WINEDEBUG` は script 既定の `-all,+module` (`mapping PE file` の行から PE base を取るため `+module` が要る)。この設定では MSGBOX はチャネルが落ちていて trace に出ないので未計測。
- entry VA `0x140030ed4` も同じ手順で実測 (`TARGET_VA=0x140030ed4 bash tools/flp/s3_gdb_attach_probe.sh`): `image_base(PE)=0x140000000` → `runtime_addr=0x140030ed4`、gdb `Breakpoint 1 at 0x140030ed4`、gdb rc=124 (60 s 内に命中せず・所要 real 1 m 1.16 s)。
- 前提の実測: 既定の `kernel.yama.ptrace_scope=1` では `Could not attach to process` (gdb rc=1)。runner で `sudo sysctl -w kernel.yama.ptrace_scope=0` を実行して解消 (このランナー限り・以降の run でも要再設定)。
- gdb は既定で i386 と解釈しブレーク先を 32 bit に切り詰めた (`Breakpoint 1 at 0x40006eaf`)。`set architecture i386:x86-64` で解消 → `Breakpoint 1 at 0x140006eaf`。
- 命中の確認: VA `0x140006eaf` (FL64.exe の `740b -> eb0b` パッチ箇所。PE image base `0x140000000` + `0x6eaf`) に挿入。`continue` 後 60 s 内に命中せず (`timeout` で終了・gdb rc=124)。SIGUSR1 (wine 内部) は `handle SIGUSR1 nostop noprint pass` で停止しないようにした。
- 判定: 受入 2 の「ブレークを張れる」は達成。「命中」は未確認。命中は起動直後の経路では起きない可能性がある (この VA は 0x140006eaf の判定分岐)。命中の確認は #5614・#5615 の範囲 (受入 1〜3)。

## 4. 手順 (再現)

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
sudo apt-get install -y wine64 xvfb gdb
sudo sysctl -w kernel.yama.ptrace_scope=0
bash tools/flp/s1_wine_probe.sh          # インストール木 $RUNNER_TEMP/fl-install を組立て・起動
bash tools/flp/s3_gdb_attach_probe.sh    # 別プロセスで起動し gdb をアタッチ、VA にブレーク
```

## 5. 未確認

- 受入 2 の命中 (ブレークで停止すること): 未確認 (60 s 内に無し)。
- `wine32` は未導入のまま。32 bit プロセスが要る経路は未確認。
