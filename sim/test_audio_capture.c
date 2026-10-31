#define main capture_program_main
#include "../linux/audio/xqaudio_capture.c"
#undef main
#include <assert.h>

int main(void)
{
    unsigned char header[44];
    char *help[] = { "xqaudio-capture", "--help", NULL };
    char *bad[] = { "xqaudio-capture", "/tmp/unused.wav", "0", NULL };
    char *too_long[] = { "xqaudio-capture", "/tmp/unused.wav", "61", NULL };
    make_wav_header(header, 64000);
    assert(!memcmp(header, "RIFF", 4));
    assert(header[4] == 0x24 && header[5] == 0xfa);
    assert(!memcmp(header + 8, "WAVEfmt ", 8));
    assert(header[20] == 1 && header[22] == 1);
    assert(header[24] == 0x80 && header[25] == 0x3e);
    assert(header[28] == 0 && header[29] == 0x7d);
    assert(header[32] == 2 && header[34] == 16);
    assert(!memcmp(header + 36, "data", 4));
    assert(header[40] == 0 && header[41] == 0xfa);
    assert(capture_program_main(2, help) == 0);
    assert(capture_program_main(3, bad) == 2);
    assert(capture_program_main(3, too_long) == 2);
    make_wav_header(header, 60 * 32000);
    assert(header[40] == 0 && header[41] == 0x4c && header[42] == 0x1d && header[43] == 0);
    puts("AUDIO_CAPTURE_HOST_PASS");
    return 0;
}
