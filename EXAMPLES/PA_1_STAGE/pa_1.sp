
.subckt pa


LIn_1 net10 net7 gnd 108 IND
Stage_1 net4 net34 net10 gnd gnd CASMOS
LD_1 net12 net4 gnd 104 IND
CShunt_D_1 net4 gnd gnd gnd 100e-15 CAP
CSeries_D_1 net4 net3 gnd gnd 23e-15 CAP

bias1 net7 net32 gnd BIASMOS
R1 net34 net7 800 RES
R10 net29 net34 100 RES
C28 net34 gnd gnd gnd 200e-15 CAP
R2 net7 net32 3000 RES
Cnew net7 gnd 200e-15 CAP

vdd0 net29 PAD
vdd1 net12 PAD

gnd0 gnd PAD
gnd1 gnd PAD

output net3 PAD

.ends pa1

