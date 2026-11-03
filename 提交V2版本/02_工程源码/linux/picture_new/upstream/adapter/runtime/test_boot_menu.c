#include "xq_boot_menu.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int parse(const char *s){char b[4096];xqbm_menu m;strcpy(b,s);return xqbm_parse(b,(unsigned)strlen(b),&m);}
int main(void)
{
    char b[]="XQ_BOOT_MENU_V1\r\nPicture_new PN01BOOT.BIN 20468 12345678\r\nOther OT01BOOT.BIN 4096 abcdef01\n";
    xqbm_menu m;assert(xqbm_parse(b,sizeof(b)-1,&m)&&m.count==2);
    assert(!strcmp(m.entry[0].name,"PN01BOOT.BIN")&&m.entry[1].crc==0xabcdef01u);
    const char *bad[]={
      "XQ_BOOT_MENU_V1\nA ../PN01.BIN 4 12345678\n",
      "XQ_BOOT_MENU_V1\nA XIANGQI.BIN 4 12345678\n",
      "XQ_BOOT_MENU_V1\nA XQMENU.BIN 4 12345678\n",
      "XQ_BOOT_MENU_V1\nA lower.bin 4 12345678\n",
      "XQ_BOOT_MENU_V1\nA PN01BOOT.BIN 4294967296 12345678\n",
      "XQ_BOOT_MENU_V1\nA PN01BOOT.BIN 1048576 12345678\n",
      "XQ_BOOT_MENU_V1\nA PN01BOOT.BIN 3 12345678\n",
      "XQ_BOOT_MENU_V1\nA PN01BOOT.BIN 4 1234567\n",
      "XQ_BOOT_MENU_V1\nA PN01BOOT.BIN 4 12345678 extra\n",
      "XQ_BOOT_MENU_V1\nA PN01BOOT.BIN 4 12345678\nB PN01BOOT.BIN 4 12345678\n",
      "XQ_BOOT_MENU_V1\nA PN01BOOT.BIN 4 12345678\nA OT01BOOT.BIN 4 12345678\n",
      "BAD_HEADER\nA PN01BOOT.BIN 4 12345678\n",
      "XQ_BOOT_MENU_V1\n"};
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++)assert(!parse(bad[i]));
    char nul[]="XQ_BOOT_MENU_V1\nA PN01BOOT.BIN 4 12345678\n";nul[20]=0;
    assert(!xqbm_parse(nul,sizeof(nul)-1,&m));
    puts("BOOT_MENU_CONTRACT_PASS valid_two_branches=1 negative_cases=14");return 0;
}
