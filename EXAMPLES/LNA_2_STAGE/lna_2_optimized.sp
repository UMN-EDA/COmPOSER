.subckt lna
    drain_ind2 net55 net33 gnd 400 IND (68 38.5 -1 172)
    drain_ind1 net5 net3 gnd 400 IND (77.19 36.35 -1 159.4)
    source_ind net1 gnd gnd 800 IND (64 15 -1 -1)
    gate_ind net8 net12 gnd 200 IND (236.49 21.52 -1 94.92)

    cas_mos1 net5 net4 net12 net1 gnd CASMOS (18 1 60)
    cas_mos2 net55 net44 net1212 gnd gnd CASMOS (18 1 60)

    bias_mos1 net2 net13 gnd BIASMOS
    bias_mos2 net22 net1313 gnd BIASMOS

    xc1 gnd net5 gnd gnd 50e-15 CAP
    xc2 net010 net14 gnd gnd 500e-15 CAP
    xc3 gnd net4 gnd gnd 200e-15 CAP
    xc33 gnd net44 gnd gnd 200e-15 CAP

    xwg1 net8 net14 gnd gnd CPWD (60 9.475 3.92)

   
    xR0 net2 net4 2500 RES
    xR00 net22 net44 2000 RES
    xR1 net13 net2 3000 RES
    xR11 net1313 net22 3000 RES
    xR2 net7 net4 500 RES
    xR22 net77 net44 500 RES
    xR3 net2 net12 3000 RES
    xR33 net22 net1212 3000 RES

    vdd1 net3 PAD
    vdd2 net33 PAD
    input net010 PAD
    gnd0 gnd PAD
    gnd1 gnd PAD
    bias1 net7 PAD 
    bias2 net77 PAD    

    xCs net5 net1212 gnd gnd 100e-15 CAP
.ends lna



