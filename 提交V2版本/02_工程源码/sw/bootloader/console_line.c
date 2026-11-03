#include "soc.h"
#include "console_line.h"

#define HISTORY_DEPTH 8
#define HISTORY_WIDTH 160

static char history[HISTORY_DEPTH][HISTORY_WIDTH];
static int history_count;

static void line_copy(char *destination,const char *source,int capacity){
 int i=0;
 while(i<capacity-1&&source[i]){
  destination[i]=source[i];
  i++;
 }
 destination[i]=0;
}

static int line_equal(const char *left,const char *right){
 while(*left&&*left==*right){left++;right++;}
 return *left==*right;
}

static void history_save(const char *line){
 int i;
 if(!line[0]||(history_count&&line_equal(line,history[0])))return;
 for(i=HISTORY_DEPTH-1;i>0;i--)
  line_copy(history[i],history[i-1],HISTORY_WIDTH);
 line_copy(history[0],line,HISTORY_WIDTH);
 if(history_count<HISTORY_DEPTH)history_count++;
}

static int line_length(const char *line){
 int n=0;
 while(line[n])n++;
 return n;
}

static void line_redraw(const char *line){
 console_puts("\rsoc> \033[K");
 console_puts(line);
}

/* CH9350 and serial terminals both send ESC [ A/B for history navigation. */
void console_readline(char *line, int capacity){
 char draft[HISTORY_WIDTH];
 int pos=0,c,escape_state=0,escape_param=0,history_cursor=-1;
 if(capacity<1)return;
 if(capacity>HISTORY_WIDTH)capacity=HISTORY_WIDTH;
 line[0]=0;
 for(;;){
  c=console_getc_timeout(0xffffffffu);
  if(escape_state==1){
   escape_state=0;
   if(c=='['||c=='O'){
    escape_state=2;
    escape_param=0;
    continue;
   }
  }
  if(escape_state==2){
   if((c>='0'&&c<='9')||c==';'){
    escape_param=1;
    continue;
   }
   escape_state=0;
   if(!escape_param&&c=='A'&&history_cursor+1<history_count){
    if(history_cursor<0)line_copy(draft,line,capacity);
    history_cursor++;
    line_copy(line,history[history_cursor],capacity);
    pos=line_length(line);
    line_redraw(line);
   }else if(!escape_param&&c=='B'&&history_cursor>=0){
    history_cursor--;
    line_copy(line,history_cursor<0?draft:history[history_cursor],capacity);
    pos=line_length(line);
    line_redraw(line);
   }
   continue;
  }
  if(c==0x1b){escape_state=1;continue;}
  if(c=='\r'||c=='\n'){
   console_putc('\n');
   line[pos]=0;
   history_save(line);
   return;
  }
  if((c==8||c==127)&&pos){
   pos--;
   line[pos]=0;
   history_cursor=-1;
   console_puts("\b \b");
  }else if(c>=32&&c<127&&pos<capacity-1){
   line[pos++]=(char)c;
   line[pos]=0;
   history_cursor=-1;
   console_putc((char)c);
  }
 }
}
