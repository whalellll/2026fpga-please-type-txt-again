"""Check actual timer bridge C arithmetic against independent integer vectors."""
import argparse
import math
from pathlib import Path
import random
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('--gcc', default='gcc')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    maximum = (1 << 64)-1
    rng = random.Random(0x7050495)
    total = 0
    with tempfile.TemporaryDirectory(prefix='pg2l-timer-') as directory:
        work = Path(directory)
        profiles = [(str(d), d, 18) for d in range(12,19)]+[('dedicated70p875',44,63),('dedicated75',33,50)]
        for divisor, num, den in profiles:
            common = math.gcd(num, den)
            numerator, denominator = num//common, den//common
            bridge = ('''static u64 pg2l_timer_deadline(u64 event,u64 time,u64 mtime) {
                u64 remaining=event>time?event-time:0;
                u64 delta=(remaining/6)*5+(remaining%6)*5/6;
                u64 result=event==(u64)-1?(u64)-1:mtime+delta;
                if(event!=(u64)-1 && result==mtime) result++;
                return result;
            }''' if args.legacy else '#include "'+str(root/'linux/opensbi/pg2l_timer_bridge.h')+'"')
            program = f'''#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>
typedef uint64_t u64;
#define PG2L_TIME_NUMERATOR {numerator}
#define PG2L_TIME_DENOMINATOR {denominator}
{bridge}
int main(void) {{
    u64 e,t,m;
    while(scanf("%"SCNu64" %"SCNu64" %"SCNu64,&e,&t,&m)==3) {{
        printf("%"PRIu64"\\n",pg2l_timer_deadline(e,t,m));
    }}
    return 0;
}}
'''
            (work/'test.c').write_text(program)
            subprocess.run([args.gcc, '-O2', '-std=c99', '-Wall', '-Werror',
                            work/'test.c', '-o', work/'test'], check=True, capture_output=True)
            cases = [(74250, 0, 100), (maximum, 0, 0), (maximum, maximum-1, maximum-1)]
            for now in (0, 1, (1 << 32)-1, 1 << 32, maximum-2):
                for mtime in (0, 17, maximum-2):
                    for delta in (0, 1, 2, 3, 5, 6, 18, 74250):
                        cases.append((min(maximum, now+delta), now, mtime))
                    cases.append((0, now, mtime))
            cases += [(rng.randrange(1 << 64), rng.randrange(1 << 64), rng.randrange(1 << 64))
                      for _ in range(4096)]
            text = ''.join(f'{e} {t} {m}\n' for e, t, m in cases)
            result = subprocess.run([work/'test'], input=text, text=True,
                                    capture_output=True, check=True, timeout=15)
            actual = [int(line) for line in result.stdout.splitlines()]
            assert len(actual) == len(cases), 'Missing C results'
            for (event, time, mtime), observed in zip(cases, actual):
                delta = max(0, event-time)*numerator//denominator
                expected = maximum if event == maximum else min(maximum, mtime+max(1, delta))
                assert observed == expected, f'div={divisor}: {(event,time,mtime)} C={observed} expected={expected}'
            total += len(cases)
    print(f'PG2L_TIMER_BRIDGE_C_REFERENCE_PASS cases={total} div=12..18 dedicated=44/63,33/50 sentinel=past=rollover=saturation')


if __name__ == '__main__':
    main()
