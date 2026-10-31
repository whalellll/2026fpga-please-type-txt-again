/* SPDX-License-Identifier: GPL-2.0 */
#ifndef PANGO_MAC_COPY_CHUNKS_H
#define PANGO_MAC_COPY_CHUNKS_H
#define PANGO_MAC_MODEL_COPY_CHUNK 4096u
/* Source/destination ownership and the device run_lock remain with caller. */
static inline void pango_mac_copy_chunks(void *context,unsigned bytes,
    void (*copy)(void *,unsigned,unsigned),void (*yield)(void *))
{
    unsigned offset=0;
    while(offset<bytes) {
        unsigned chunk=bytes-offset;
        if(chunk>PANGO_MAC_MODEL_COPY_CHUNK)chunk=PANGO_MAC_MODEL_COPY_CHUNK;
        copy(context,offset,chunk);
        offset+=chunk;
        if(offset<bytes)yield(context);
    }
}
#endif
