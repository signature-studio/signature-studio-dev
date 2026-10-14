/* cpi_probe.c: CreatePlugInstance (VA 0x86ab10) の入場ログと、命令単位の直近 256 件 ring (#829)。
 * cpi_reach.sh が複製 C の f_86ab10 先頭 (cpi_enter) と各命令コメント行 (cpi_at) から呼ぶ。
 * trap 後も wasm メモリは残るため、node 側は cpi_ring_addr / cpi_count で ring を読む。 */
#include <stdint.h>
#include <stdio.h>

#define CPI_RING 256
static volatile uint64_t cpi_buf[CPI_RING];
static volatile uint64_t cpi_n;

void cpi_at(unsigned long long va) {
    cpi_buf[cpi_n & (CPI_RING - 1)] = va;
    cpi_n++;
}

void cpi_enter(unsigned long long va) {
    cpi_at(va);
    fprintf(stderr, "[cpi] enter %#llx\n", va);
}

uint32_t cpi_ring_addr(void) { return (uint32_t)(uintptr_t)cpi_buf; }
uint32_t cpi_count(void) { return (uint32_t)cpi_n; }
