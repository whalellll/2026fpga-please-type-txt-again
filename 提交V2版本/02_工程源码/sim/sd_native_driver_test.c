#include <stdint.h>

#include "soc.h"
#include "sd.h"

#define RESULT_PASS (*(volatile uint32_t *)(uintptr_t)0x80000000u)
#define RESULT_FAIL (*(volatile uint32_t *)(uintptr_t)0x80000004u)
#define TEST_MODE   (*(volatile uint32_t *)(uintptr_t)0x80000008u)

#define TEST_SECTORS 32u
#define TEST_LBA     64u
#define END_SECTORS  2u

static uint8_t sector[512] __attribute__((aligned(4)));
static uint8_t write_source[512u+3u] __attribute__((aligned(4)));
static uint8_t batch[TEST_SECTORS * 512u];
static uint8_t stream_source[8u * 512u + 3u] __attribute__((aligned(4)));
static uint32_t cancel_polls;

static int cancel_stream(void *user)
{
    (void)user;
    ++cancel_polls;
    /* Cancel a real active burst after its first complete programmed block. */
    return ((*(volatile uint32_t *)(uintptr_t)0x1fe13050u & 0x200u) != 0u &&
            *(volatile uint32_t *)(uintptr_t)0x1fe13038u >= 1u);
}

static void fail(uint32_t code) __attribute__((noreturn));
static void fail(uint32_t code)
{
    RESULT_FAIL = code;
    for (;;) {
    }
}

static void pass(void) __attribute__((noreturn));
static void pass(void)
{
    RESULT_PASS = 0x4e44534du;
    for (;;) {
    }
}

static uint8_t expected_byte(uint32_t lba, uint32_t offset)
{
    return (uint8_t)(lba * 17u + offset * 13u + 0x5au);
}

int main(void)
{
    const sd_card_info_t *info;
    uint32_t block;
    uint32_t offset;
    uint32_t alignment;
    int status;

    status = sd_init();
    if (status != SD_OK)
        fail(0x4e010000u | (uint32_t)(-status));

    info = sd_card_info();
    if (info->version2 != info->high_capacity || info->bus_width != 4u ||
        info->transfer_hz != SYS_CLOCK_HZ / 2u ||
        (info->ocr & 0x80000000u) == 0u ||
        info->sector_count != 1048576u)
        fail(0x4e020000u);

    if(TEST_MODE){
        status=sd_write_sectors(128u,2u,stream_source,0,0);
        if(status!=SD_ERR_PROTOCOL)fail(0x4e190000u|(uint32_t)-status);
        if(sd_write_sectors(128u,2u,stream_source,0,0)!=SD_ERR_IO)
            fail(0x4e1a0000u);
        pass();
    }

    /* The card model corrupts the data CRC for the first CMD17 attempt.
     * Retrying a single-block read must not issue CMD12 between attempts. */
    status = sd_read_sector(7u, sector);
    if (status != SD_OK)
        fail(0x4e030000u | (uint32_t)(-status));
    for (offset = 0u; offset < sizeof(sector); ++offset) {
        if (sector[offset] != expected_byte(7u, offset))
            fail(0x4e040000u | offset);
    }

    /* The first response to this CMD17 has a deliberately bad CRC7.  The
     * retry must begin directly, without sending CMD12 to a card that never
     * entered the single-block data phase. */
    status = sd_read_sector(8u, sector);
    if (status != SD_OK)
        fail(0x4e0a0000u | (uint32_t)(-status));
    for (offset = 0u; offset < sizeof(sector); ++offset) {
        if (sector[offset] != expected_byte(8u, offset))
            fail(0x4e0b0000u | offset);
    }

    /* The card model corrupts one lane CRC in the first CMD18 attempt.  The
     * public API must stop the transfer, retry it once, and return all 32
     * sectors from the successful retry. */
    status = sd_read_sectors(TEST_LBA, TEST_SECTORS, batch);
    if (status != SD_OK)
        fail(0x4e050000u | (uint32_t)(-status));
    for (block = 0u; block < TEST_SECTORS; ++block) {
        for (offset = 0u; offset < 512u; ++offset) {
            if (batch[block * 512u + offset] !=
                expected_byte(TEST_LBA + block, offset))
                fail(0x4e060000u | (block << 9) | offset);
        }
    }

    /* A legal CMD18 ending at the final user block may receive OUT_OF_RANGE
     * in the automatic CMD12 response.  The model first corrupts that
     * response CRC7; recovery must retry CMD18 without a duplicate CMD12. */
    status = sd_read_sectors(info->sector_count - END_SECTORS,
                             END_SECTORS, batch);
    if (status != SD_OK)
        fail(0x4e070000u | (uint32_t)(-status));
    for (block = 0u; block < END_SECTORS; ++block) {
        for (offset = 0u; offset < 512u; ++offset) {
            if (batch[block * 512u + offset] !=
                expected_byte(info->sector_count - END_SECTORS + block,
                              offset))
                fail(0x4e080000u | (block << 9) | offset);
        }
    }

    if (sd_read_sectors(info->sector_count - 1u, 2u, batch) !=
        SD_ERR_UNSUPPORTED)
        fail(0x4e090000u);

    /* Exercise one aligned word source and all three unaligned byte paths on
     * the actual RV32 CPU. Different data per alignment catches stale buffers. */
    for(alignment=0;alignment<4;alignment++){
        uint8_t *source=write_source+alignment;
        if(((uintptr_t)source&3u)!=alignment)fail(0x4e100000u|alignment);
        for(offset=0;offset<512;offset++)source[offset]=expected_byte(96u+alignment,offset);
        status=sd_write_sector(96u,source);
        if(info->high_capacity){
            if(status!=SD_OK)fail(0x4e0c0000u|(alignment<<8)|(uint32_t)-status);
            status=sd_read_sector(96u,sector);
            if(status!=SD_OK)fail(0x4e0d0000u|(alignment<<8)|(uint32_t)-status);
            for(offset=0;offset<512;offset++)
                if(sector[offset]!=expected_byte(96u+alignment,offset))
                    fail(0x4e0e0000u|(alignment<<9)|offset);
        }else if(status!=SD_ERR_UNSUPPORTED)fail(0x4e0f0000u|alignment);
    }

    if(info->high_capacity){
        /* Aligned and unaligned 8-sector streams must refill both banks and
         * retain every distinct sector through an independent card read. */
        for(alignment=0;alignment<2;alignment++){
            uint8_t *source=stream_source+alignment;
            for(block=0;block<8;block++)for(offset=0;offset<512;offset++)
                source[block*512u+offset]=expected_byte(128u+alignment*16u+block,offset);
            status=sd_write_sectors(128u,8u,source,0,0);
            if(status!=SD_OK)fail(0x4e110000u|(alignment<<8)|(uint32_t)-status);
            status=sd_read_sectors(128u,8u,batch);
            if(status!=SD_OK)fail(0x4e120000u|(alignment<<8)|(uint32_t)-status);
            for(block=0;block<8;block++)for(offset=0;offset<512;offset++)
                if(batch[block*512u+offset]!=expected_byte(128u+alignment*16u+block,offset))
                    fail(0x4e130000u|(block<<9)|offset);
        }
        for(block=0;block<8;block++)for(offset=0;offset<512;offset++)
            stream_source[block*512u+offset]=expected_byte(160u+block,offset);
        cancel_polls=0;
        status=sd_write_sectors(160u,8u,stream_source,cancel_stream,0);
        if(status!=SD_ERR_ABORTED||cancel_polls<2u)fail(0x4e140000u|(uint32_t)-status);
        /* Successful graceful cancellation must preserve the initialized card
         * for FAT rollback rather than forcing a reinitialization. */
        for(offset=0;offset<512;offset++)write_source[offset]=expected_byte(100u,offset);
        status=sd_write_sector(96u,write_source);
        if(status!=SD_OK)fail(0x4e150000u|(uint32_t)-status);
        status=sd_read_sector(96u,sector);
        if(status!=SD_OK)fail(0x4e160000u|(uint32_t)-status);
        for(offset=0;offset<512;offset++)if(sector[offset]!=expected_byte(100u,offset))
            fail(0x4e170000u|offset);
    }else if(sd_write_sectors(128u,8u,stream_source,0,0)!=SD_ERR_UNSUPPORTED)
        fail(0x4e180000u);

    sd_release();
    pass();
}
