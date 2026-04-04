
.subckt pa

LIn_1 net10 net7 gnd 108 IND
Stage_1 net4 net34 net10 gnd gnd CASMOS
LD_1 net12 net4 gnd 104 IND
CShunt_D_1 net4 net12 gnd gnd 100e-15 CAP
CSeries_D_1 net4 net3 gnd gnd 23e-15 CAP

LIn_2 net3 net24 gnd 56 IND
Stage_2 net16 net23 net3 gnd gnd CASMOS
LD_2 net17 net16 gnd 62 IND
CShunt_D_2 net17 net16 gnd gnd 50e-15 CAP
CSeries_D_2 net16 net9 gnd gnd 43e-15 CAP

LIn_3 net9 net124 gnd 56 IND
Stage_3 net116 net123 net9 gnd gnd CASMOS
LD_3 net117 net116 gnd 62 IND
CShunt_D_3 net116 gnd gnd gnd 50e-15 CAP
CSeries_D_3 net116 net19 gnd gnd 43e-15 CAP

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

bias3 net124 net125 gnd BIASMOS
R127 net123 net124 800 RES
R126 net126 net123 100 RES
C129 net123 gnd gnd 200e-15 CAP
R128 net124 net125 3000 RES
Cnew3 net124 gnd 200e-15 CAP

vdd0 net26 PAD
vdd1 net12 PAD
vdd2 net29 PAD
vdd3 net17 PAD
vdd4 net117 PAD

gnd0 gnd PAD
gnd1 gnd PAD
gnd2 gnd PAD
gnd3 gnd PAD
gnd4 gnd PAD

output net19 PAD

.ends pa2

