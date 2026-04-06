
.subckt pa

LIn_1 net7 net10 gnd 108 IND (437.12 -1 -1 -1)
Stage_1 net4 net34 net10 gnd gnd CASMOS (38 1 60)
LD_1 net12 net4 gnd 88 IND (172.63 -1 -1 -1)
CShunt_D_1 net4 gnd gnd gnd 100e-15 CAP (4.334698e-14)
CSeries_D_1 net4 net3 gnd gnd 23e-15 CAP (6.090399e-14)

LIn_2 net24 net3 gnd 56 IND (197.56 -1 -1 -1)
Stage_2 net16 net23 net3 gnd gnd CASMOS (76 1 60)
LD_2 net17 net16 gnd 62 IND (93.01 -1 -1 -1)
CShunt_D_2 net16 gnd gnd gnd 50e-15 CAP (5.000000e-14)
CSeries_D_2 net16 net9 gnd gnd 43e-15 CAP (1.190358e-13)

bias1 net7 net32 gnd BIASMOS
R1 net34 net7 800 RES
R10 net29 net34 100 RES
C28 net34 gnd gnd gnd 200e-15 CAP
R2 net7 net32 3000 RES
Cnew1 net7 gnd 200e-15 CAP

bias2 net24 net25 gnd BIASMOS
R27 net23 net24 800 RES
R26 net26 net23 100 RES
C29 net23 gnd gnd 200e-15 CAP
R28 net24 net25 3000 RES
Cnew2 net24 gnd 200e-15 CAP

vdd0 net26 PAD
vdd1 net12 PAD
vdd2 net29 PAD
vdd3 net17 PAD

gnd0 gnd PAD
gnd1 gnd PAD
gnd2 gnd PAD
gnd3 gnd PAD

output net9 PAD

.ends pa2

