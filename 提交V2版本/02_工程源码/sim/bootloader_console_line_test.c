#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "console_line.h"

static const unsigned char *input;
static size_t input_pos;
static char output[4096];
static size_t output_pos;

int console_getc_timeout(unsigned int cycles){
 (void)cycles;
 if(!input[input_pos]){
  fputs("Input fixture exhausted\n",stderr);
  exit(2);
 }
 return input[input_pos++];
}

void console_putc(char c){
 if(output_pos+1>=sizeof(output))exit(3);
 output[output_pos++]=c;
 output[output_pos]=0;
}

void console_puts(const char *s){while(*s)console_putc(*s++);}

static void run(const char *keys,const char *want){
 char line[160];
 input=(const unsigned char *)keys;
 input_pos=0;
 output_pos=0;
 output[0]=0;
 console_readline(line,sizeof(line));
 if(strcmp(line,want)){
  fprintf(stderr,"CONSOLE_HISTORY_REPRO_FAIL got='%s' want='%s'\n",line,want);
  exit(1);
 }
}

int main(void){
 run("info\r","info");
 run("sdinfo\r","sdinfo");
 run("\033[A\r","sdinfo");
 if(!strstr(output,"\rsoc> \033[Ksdinfo")){
  fputs("CONSOLE_HISTORY_REDRAW_FAIL\n",stderr);
  return 1;
 }
 run("\033[A\033[A\r","info");
 run("draft\033[A\033[B\r","draft");
 run("\033[B\033[A\r","draft");
 run("\033OA\r","draft");
 run("helx\177p\r","help");
 run("\033[3~info\r","info");
 run("\033\r","");
 puts("BOOTLOADER_CONSOLE_HISTORY_PASS");
 return 0;
}
