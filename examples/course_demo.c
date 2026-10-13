/*
 * Reference C program from the Phase 2 report.
 * Hand-compiled to SymRISC-32 assembly in course_demo.s.
 *
 * Expected final state: x = 6, y = 6, w = 999, A[1] = 6.
 */
int A[4];

void course_demo(void)
{
    int x = 10;
    int y = 0;
    int w = 0 << 2;
    int j = 5;

    for (int i = 1; i < x; i++) {
        x += ((i + 2) - (i * 3)) / j;
    }

    if (x > w) {
        w = x | 999;
        y = x & w;
        A[1] = y;
    }
}
