.subckt lna
    drain_ind net5 net3 gnd 400 IND
    source_ind net1 gnd gnd 800 IND
    gate_ind net8 net12 gnd 200 IND
    cas_mos net5 net4 net12 net1 gnd CASMOS
    bias_mos net2 net13 gnd BIASMOS
    xc1 gnd net5 gnd gnd 50e-15 CAP
    xc2 net010 net14 gnd gnd 500e-15 CAP
    xwg1 net8 net14 gnd gnd CPWD
    xc3 gnd net4 gnd gnd 200e-15 CAP
    xR0 net2 net4 2500 RES
    xR1 net13 net2 3000 RES
    xR2 net7 net4 500 RES
    xR3 net2 net12 3000 RES
    vdd net3 PAD
    input net010 PAD
    gnd0 gnd PAD
    gnd1 gnd PAD
    gnd2 gnd PAD
    bias net7 PAD    
.ends lna



