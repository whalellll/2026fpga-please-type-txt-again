/* String primitives for the freestanding SD tools; no dependency on libc. */
#include <stddef.h>
size_t strlen(const char *s){const char *p=s;while(*p)++p;return (size_t)(p-s);}
int strcmp(const char *a,const char *b)
{while(*a&&*a==*b){++a;++b;}return (unsigned char)*a-(unsigned char)*b;}
int strncmp(const char *a,const char *b,size_t n)
{while(n&&*a&&*a==*b){++a;++b;--n;}return n?(unsigned char)*a-(unsigned char)*b:0;}
char *strcpy(char *to,const char *from)
{char *result=to;while((*to++=*from++)!=0){}return result;}
