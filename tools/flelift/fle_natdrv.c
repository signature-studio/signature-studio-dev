/* fle_natdrv.c — native 参照実行ドライバ (standalone 実行ファイル)。
 * python3 が non-PIE で 0x400000 を占有するため in-process ctypes は使えない →
 * PIE 実行ファイルとして build し setarch -R (ASLR off) で高位にロードして 0x400000 を空ける。
 *
 * usage: fle_natdrv <case-file> <out-jsonl> <PE>
 * case file (1 行 1 case):
 *   CASE <fn-hex> <id> <prep> <gpr0> <gpr1> <gpr2> <gpr3> <x0> <x1> <x2> <x3> <nstk> [stk...]
 *   prep: - | ustrasg | ustrasg_self
 * output: 1 case 1 行 JSON {"fn","id","status","rax","x0","mem":[{r,o,b,a}]} */
#include "fle_native.c"
#include <ctype.h>

static void trim(char* s) {
    while (isspace((unsigned char)*s)) s++;
    /* noop (tokenize で対応) */
}

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: fle_natdrv <case-file> <out> <PE>\n"); return 2; }
    if (!getenv("FLE_NOASLR")) {
        setenv("FLE_NOASLR", "1", 1);
        execvp("setarch", (char*[]){"setarch", "x86_64", "-R", argv[0], argv[1], argv[2], argv[3], NULL});
        perror("setarch");
        return 3;
    }
    fle_install_segv();
    if (fle_load(argv[3]) != 0) { fprintf(stderr, "fle_load failed\n"); return 4; }
    FILE* cf = fopen(argv[1], "r");
    FILE* out = fopen(argv[2], "w");
    if (!cf || !out) { perror("open"); return 5; }
    char line[1024];
    while (fgets(line, sizeof(line), cf)) {
        if (line[0] == '#' || line[0] == '\n') continue;
        char* tok[24];
        int nt = 0;
        for (char* p = strtok(line, " \t\n"); p && nt < 24; p = strtok(NULL, " \t\n")) tok[nt++] = p;
        if (nt < 13 || strcmp(tok[0], "CASE") != 0) continue;
        uint64_t fn = strtoull(tok[1], NULL, 16);
        const char* id = tok[2];
        const char* prep = tok[3];
        uint64_t gpr[4], xmm[4];
        for (int i = 0; i < 4; i++) gpr[i] = strtoull(tok[4 + i], NULL, 0);
        for (int i = 0; i < 4; i++) xmm[i] = strtoull(tok[8 + i], NULL, 0);
        long nstk = atol(tok[12]);
        uint64_t stk[8] = {0};
        for (int i = 0; i < nstk && i < 8 && 13 + i < nt; i++) stk[i] = strtoull(tok[13 + i], NULL, 0);
        fle_reset();
        if (!strcmp(prep, "ustrasg") || !strcmp(prep, "ustrasg_self")) {
            uint8_t buf[0x2000];
            memset(buf, 0, sizeof(buf));
            uint64_t st = 0x20001000 + 12;
            uint32_t off = (uint32_t)((st - 12) - 0x20000000);
            *(uint16_t*)(buf + off) = 1200;          /* codepage */
            *(uint16_t*)(buf + off + 2) = 2;         /* elemsize */
            *(uint32_t*)(buf + off + 4) = 1;         /* refcnt */
            *(uint32_t*)(buf + off + 8) = 8;         /* len */
            for (int i = 0; i < 16; i++) buf[(st - 0x20000000) + i] = 0x41 + i;
            *(uint64_t*)buf = !strcmp(prep, "ustrasg_self") ? st : 0;
            fle_write(0x20000000, buf, sizeof(buf));
        } else if (!strcmp(prep, "pat")) {
            uint8_t buf[0x2000];
            for (int i = 0; i < (int)sizeof(buf); i++) buf[i] = (uint8_t)(i * 13 + 7);
            fle_write(0x20004000, buf, sizeof(buf));
        }
        fle_scratch_base();   /* prep 後の状態を scratch の baseline に (wasm 側と同一条件) */
        uint64_t o2[2] = {0, 0};
        const char* status = "ok";
        const char* detail = "";
        /* fault (SEGV 等) は sigsetjmp で回収 → status=fault (case 毎に fle_reset 済) */
        if (sigsetjmp(g_case_jb, 1) == 0) {
            g_case_active = 1;
            fle_call(fn, gpr, xmm, stk, nstk, o2);
            g_case_active = 0;
        } else {
            status = "fault";
            detail = g_case_detail;
        }
        fprintf(out, "{\"fn\":\"0x%llx\",\"id\":\"%s\",\"status\":\"%s\",\"detail\":\"%s\",\"rax\":\"0x%llx\",\"x0\":\"0x%llx\",\"mem\":[",
                (unsigned long long)fn, id, status, detail,
                (unsigned long long)o2[0], (unsigned long long)o2[1]);
        int first = 1;
        if (!strcmp(status, "ok")) {
            long maxb = 512;
            static uint64_t blocks[512 * 3];
            const struct { const char* nm; uint64_t lo, hi; } RS[] = {
                {"image", 0x13a5000, 0x196f000}, {"teb", 0x1D00000, 0x1D00400},
                {"scratch", 0x20000000, 0x20100000}, {"arena", 0x2100000, 0x3100000}};
            for (unsigned rr = 0; rr < sizeof(RS) / sizeof(RS[0]); rr++) {
                long n = fle_diff_blocks(RS[rr].lo, RS[rr].hi - RS[rr].lo, blocks, maxb);
                for (long k = 0; k < n; k++) {
                    fprintf(out, "%s{\"r\":\"%s\",\"o\":\"0x%llx\",\"b\":\"0x%llx\",\"a\":\"0x%llx\"}",
                            first ? "" : ",", RS[rr].nm,
                            (unsigned long long)(blocks[k * 3] - RS[rr].lo),
                            (unsigned long long)blocks[k * 3 + 1], (unsigned long long)blocks[k * 3 + 2]);
                    first = 0;
                }
            }
        }
        fprintf(out, "]}\n");
    }
    fclose(cf);
    fclose(out);
    return 0;
}
