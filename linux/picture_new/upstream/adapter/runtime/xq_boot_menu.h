#ifndef XQ_BOOT_MENU_H
#define XQ_BOOT_MENU_H
#include <stdint.h>
#define XQBM_MAX 8u
#define XQBM_CONFIG_MAX 2048u
typedef struct {char label[25],name[13];uint32_t bytes,crc;} xqbm_entry;
typedef struct {unsigned count;xqbm_entry entry[XQBM_MAX];} xqbm_menu;
int xqbm_parse(char *text,unsigned bytes,xqbm_menu *menu);
#endif
