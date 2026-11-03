#include <stdio.h>
#include <stdlib.h>
#include "xq_sha256.h"
int main(int argc,char**argv){size_t n=argc>1?strtoul(argv[1],0,10):0;unsigned char *p=malloc(n?n:1);for(size_t i=0;i<n;i++)p[i]=(unsigned char)(i*37+11);char h[65];xq_sha256_hex(p,n,h);puts(h);free(p);return 0;}
