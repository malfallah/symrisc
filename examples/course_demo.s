// course_demo.s - the Phase 2 C program (course_demo.c) compiled by hand.
//
// Register allocation:
//   !S0 = x   !S1 = y   !S2 = w   !S3 = j   !S4 = i   !A0 = &A[0]
// Branches jump to the address held in a register, so every branch target is
// first loaded into an address register (!A1 - !A3).

        ASi  !A0, A             // base address of A[]
        ASi  !S0, 10            // x = 10
        ASi  !S1, 0             // y = 0
        ASi  !T0, 0             // temp = 0
        <<   !S2, !T0, 2        // w = 0 << 2
        ASi  !S3, 5             // j = 5
        ASi  !S4, 1             // i = 1
        ASi  !A1, Loop
        ASi  !A2, Condition
        ASi  !A3, Exit
        B=   !Z, !Z, !A2        // always taken: test the loop condition first

Loop:   i++  !T2, !S4, 2        // i + 2
        i*   !T3, !S4, 3        // i * 3
        --   !T2, !T2, !T3      // (i + 2) - (i * 3)
        /    !T2, !T2, !S3      // ((i + 2) - (i * 3)) / j
        ++   !S0, !S0, !T2      // x += ...
        i++  !S4, !S4, 1        // i++

Condition:
        B<   !S4, !S0, !A1      // if (i < x) goto Loop

        B<   !S0, !S2, !A3      // if (x < w)  skip the body
        B=   !S0, !S2, !A3      // if (x == w) skip the body

AddToArray:
        i||  !S2, !S0, 999      // w = x | 999
        &    !S1, !S0, !S2      // y = x & w
        i++  !T4, !A0, 4        // &A[1]
        SW   !S1, (!T4)         // A[1] = y
Exit:

        .data
A:      .word 0, 0, 0, 0
