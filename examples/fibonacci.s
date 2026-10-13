// fibonacci.s - store the first N Fibonacci numbers in fib[0..N-1].
//
//   a, b = 0, 1
//   for (n = N; n > 0; n--) { *p++ = a; a, b = b, a + b; }

        ASi  !A0, fib           // p = &fib[0]
        ASi  !T0, 12            // n = N
        ASi  !S0, 0             // a = 0
        ASi  !S1, 1             // b = 1
        ASi  !A1, Loop

Loop:   SW   !S0, (!A0)         // *p = a
        ++   !S2, !S0, !S1      // t = a + b
        i++  !S0, !S1, 0        // a = b
        i++  !S1, !S2, 0        // b = t
        i++  !A0, !A0, 4        // p++
        i--  !T0, !T0, 1        // n--
        B>   !T0, !Z, !A1       // while (n > 0)

        .data
fib:    .space 48               // 12 words
