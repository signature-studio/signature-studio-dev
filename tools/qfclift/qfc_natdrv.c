/* qfc_natdrv.c — QuickFontCache_x64.dll (ImageBase 0x400000) の native 参照実行ドライバ。
 * tools/flelift/fle_native.c (ローダ + MS ABI 呼出) を #include で流用 (flelift は無改変)。
 * usage: qfc_natdrv <case-file> <out-jsonl> <PE>   (setarch -R 自己再 exec で 0x400000 を空ける)
 * case 行: CASE <id> <fn-hex> <g0> <g1> <g2> <g3> <nstk> [stk..] <nw> [<va> <hex>].. <nc> [<va> <len>]..
 * out 行 : {"id","status","rax","x0","mem":["<hex>",..]}  (mem = compare 領域の実行後バイト列) */
#include "../flelift/fle_native.c"
#include <ctype.h>

static void put_hex(FILE* o, const uint8_t* p, long n) {
    for (long i = 0; i < n; i++) fprintf(o, "%02x", p[i]);
}

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: qfc_natdrv <case-file> <out> <PE>\n"); return 2; }
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
    static char line[1 << 16];
    while (fgets(line, sizeof(line), cf)) {
        if (strncmp(line, "CASE ", 5) != 0) continue;
        char* tok[512];
        int nt = 0;
        for (char* p = strtok(line, " \t\n"); p && nt < 512; p = strtok(NULL, " \t\n")) tok[nt++] = p;
        const char* id = tok[1];
        uint64_t fn = strtoull(tok[2], NULL, 16);
        uint64_t gpr[4], xmm[4] = {0, 0, 0, 0};
        for (int i = 0; i < 4; i++) gpr[i] = strtoull(tok[3 + i], NULL, 0);
        int k = 7;
        long nstk = atol(tok[k++]);
        uint64_t stk[8] = {0};
        for (long i = 0; i < nstk && i < 8; i++) stk[i] = strtoull(tok[k++], NULL, 0);
        memset((void*)SCRATCH, 0, SCRATCH_SZ);
        long nw = atol(tok[k++]);
        for (long w = 0; w < nw; w++) {
            uint64_t va = strtoull(tok[k++], NULL, 16);
            const char* h = tok[k++];
            for (size_t i = 0; h[i] && h[i + 1]; i += 2) {
                char b[3] = {h[i], h[i + 1], 0};
                *(uint8_t*)(va + i / 2) = (uint8_t)strtoul(b, NULL, 16);
            }
        }
        long nc = atol(tok[k++]);
        uint64_t cva[16], clen[16];
        for (long c = 0; c < nc && c < 16; c++) { cva[c] = strtoull(tok[k++], NULL, 16); clen[c] = strtoull(tok[k++], NULL, 0); }
        uint64_t o2[2] = {0, 0};
        const char* status = "ok";
        if (sigsetjmp(g_case_jb, 1) == 0) {
            g_case_active = 1;
            fle_call(fn, gpr, xmm, stk, nstk, o2);
            g_case_active = 0;
        } else {
            status = "fault";
        }
        fprintf(out, "{\"id\":\"%s\",\"status\":\"%s\",\"rax\":\"0x%llx\",\"x0\":\"0x%llx\",\"mem\":[", id, status,
                (unsigned long long)o2[0], (unsigned long long)o2[1]);
        for (long c = 0; c < nc; c++) {
            fprintf(out, "%s\"", c ? "," : "");
            put_hex(out, (const uint8_t*)cva[c], (long)clen[c]);
            fprintf(out, "\"");
        }
        fprintf(out, "]}\n");
    }
    fclose(cf);
    fclose(out);
    return 0;
}
