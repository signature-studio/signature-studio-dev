/* cpi_host.c: CreatePlugInstance (VA 0x86ab10) の host object を guest メモリに再構成し、
 * host の vtable 呼びと未 lift の import を記録して返す (#2653)。
 * cpi_reach.sh が複製 C の ott_dispatch の default 分岐と ott_missing_import の先頭から呼ぶ。
 * host = CPI_HOST の qword[0] が vtable (CPI_VT)。vtable の各スロットは CPI_STUB + 8*i の仮想 VA を指し、
 * lift 側の間接 call がそこへ来たら、記録して CPI_OBJ (qword[0] が同じ vtable を指す fake object) を rax に返す。
 * slot 6 は 6 番目の引数 (&out) に空文字列の番地 CPI_STR を書き、rax = 1 を返す (観測した呼出しの形に合わせた最小の応答)。
 * host 領域 (CPI_HOST〜CPI_END) は PE イメージ [ImageBase, ImageBase+SizeOfImage) の外に置く (0x600000 台は .text 内で定数データを壊した: #2653 差し戻し)。 */
#include "ott_cpu.h"
#include <stdio.h>

#define CPI_HOST 0xA00000ULL
#define CPI_VT (CPI_HOST + 0x1000ULL)
#define CPI_STUB 0x7ff00000ULL
#define CPI_NSLOT 128
#define CPI_OBJ (CPI_HOST + 0x40000ULL)
#define CPI_STR (CPI_HOST + 0x41000ULL)
#define CPI_END (CPI_STR + 0x1000ULL)

int cpi_host_setup(unsigned long long img_lo, unsigned long long img_hi) {
    if (CPI_HOST < img_hi && CPI_END > img_lo) return 0;
    ST64(CPI_HOST, CPI_VT);
    for (unsigned i = 0; i < CPI_NSLOT; i++) ST64(CPI_VT + 8 * i, CPI_STUB + 8 * i);
    ST64(CPI_OBJ, CPI_VT);
    return 1;
}

int cpi_miss(uint64_t t) {
    if (t < CPI_STUB || t >= CPI_STUB + 8 * CPI_NSLOT) return 0;
    unsigned i = (unsigned)((t - CPI_STUB) / 8);
    fprintf(stderr, "[cpi] host slot %u rcx=%#llx rdx=%#llx r8=%#llx\n", i,
            (unsigned long long)R[RCX], (unsigned long long)R[RDX], (unsigned long long)R[R8]);
    R[RAX] = CPI_OBJ;
    if (i == 6) {
        uint64_t out = LD64(R[RSP] + 0x30);
        if (out) ST64(out, CPI_STR);
        R[RAX] = 1;
    }
    R[RSP] += 8;
    return 1;
}

int cpi_miss_imp(const char* nm) {
    fprintf(stderr, "[cpi] import stub %s rcx=%#llx rdx=%#llx\n", nm,
            (unsigned long long)R[RCX], (unsigned long long)R[RDX]);
    R[RAX] = 0;
    R[RSP] += 8;
    return 1;
}
