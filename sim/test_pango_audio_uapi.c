#include "pango_audio_uapi.h"

_Static_assert(sizeof(struct pango_audio_info) == 64, "info ABI size");
_Static_assert(sizeof(struct pango_audio_stats) == 32, "stats ABI size");

int main(void)
{
    return 0;
}
