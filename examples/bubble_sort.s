// bubble_sort.s - sort an array of signed words in place (ascending).
//
//   for (end = N - 1; end != 0; end--)
//       for (k = 0; k < end; k++)
//           if (a[k] > a[k + 1]) swap(a[k], a[k + 1]);

        ASi  !A0, array         // &a[0]
        ASi  !S0, 7             // end = N - 1
        ASi  !A1, Outer
        ASi  !A2, Inner
        ASi  !A3, NoSwap
        ASi  !A4, Done

Outer:  B=   !S0, !Z, !A4       // if (end == 0) done
        ASi  !S1, 0             // k = 0
        i++  !T0, !A0, 0        // p = &a[0]

Inner:  LW   !T1, (!T0)         // a[k]
        i++  !T2, !T0, 4        // &a[k + 1]
        LW   !T3, (!T2)         // a[k + 1]
        B<   !T1, !T3, !A3      // in order (<)  -> no swap
        B=   !T1, !T3, !A3      // in order (==) -> no swap
        SW   !T3, (!T0)         // swap
        SW   !T1, (!T2)

NoSwap: i++  !T0, !T0, 4        // p++
        i++  !S1, !S1, 1        // k++
        B<   !S1, !S0, !A2      // while (k < end)
        i--  !S0, !S0, 1        // end--
        B=   !Z, !Z, !A1        // next pass
Done:

        .data
array:  .word 42, -7, 19, 0, 1000, -300, 7, 7
