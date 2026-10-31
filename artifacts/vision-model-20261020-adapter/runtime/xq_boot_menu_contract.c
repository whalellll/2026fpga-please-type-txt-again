#include "xq_boot_menu.h"
#include <string.h>
static int number(const char *s,unsigned base,uint32_t *value)
{
    uint32_t n=0;unsigned digits=0;
    while(*s){unsigned c=(unsigned char)*s++,d;
        if(c>='0'&&c<='9')d=c-'0';else if(c>='a'&&c<='f')d=c-'a'+10;
        else if(c>='A'&&c<='F')d=c-'A'+10;else return 0;
        if(d>=base||n>(UINT32_MAX-d)/base)return 0;
        n=n*base+d;++digits;
    }
    if(!digits||(base==16&&digits!=8))return 0;
    *value=n;return 1;
}
static int filename(const char *s)
{
    unsigned n=0;
    if(!strcmp(s,"XIANGQI.BIN")||!strcmp(s,"XQMENU.BIN"))return 0;
    while(*s&&*s!='.'){
        if(!((*s>='A'&&*s<='Z')||(*s>='0'&&*s<='9')||*s=='_')||++n>8)return 0;
        ++s;
    }
    return n&&strcmp(s,".BIN")==0;
}
int xqbm_parse(char *text,unsigned bytes,xqbm_menu *menu)
{
    unsigned lines=0;char *p=text;
    if(!text||!menu||!bytes||bytes>XQBM_CONFIG_MAX||text[bytes])return 0;
    for(unsigned i=0;i<bytes;i++)if(!text[i]||(unsigned char)text[i]>126||
        ((unsigned char)text[i]<32&&text[i]!='\n'&&text[i]!='\r'&&text[i]!='\t'))return 0;
    memset(menu,0,sizeof(*menu));
    while(*p){char *line=p,*field[4];unsigned nf=0;
        while(*p&&*p!='\n'&&*p!='\r')++p;
        if(*p){char end=*p;*p++=0;if(end=='\r'&&*p=='\n')++p;}
        if(!*line||*line=='#')continue;
        if(!lines++){if(strcmp(line,"XQ_BOOT_MENU_V1"))return 0;continue;}
        if(menu->count==XQBM_MAX)return 0;
        char *q=line;
        while(*q){while(*q==' '||*q=='\t')++q;if(!*q)break;
            if(nf==4)return 0;
            field[nf++]=q;while(*q&&*q!=' '&&*q!='\t')++q;
            if(*q)*q++=0;
        }
        if(nf!=4||!filename(field[1]))return 0;
        unsigned label_size=(unsigned)strlen(field[0]);
        if(!label_size||label_size>24)return 0;
        for(unsigned i=0;i<label_size;i++){char c=field[0][i];
            if(!((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='-'))return 0;
        }
        xqbm_entry *e=&menu->entry[menu->count];
        if(!number(field[2],10,&e->bytes)||!number(field[3],16,&e->crc)||
            !e->bytes||(e->bytes&3u)||e->bytes>0x100000u-16384u)return 0;
        for(unsigned i=0;i<menu->count;i++)if(!strcmp(menu->entry[i].label,field[0])||
            !strcmp(menu->entry[i].name,field[1]))return 0;
        strcpy(e->label,field[0]);strcpy(e->name,field[1]);++menu->count;
    }
    return lines&&menu->count;
}
