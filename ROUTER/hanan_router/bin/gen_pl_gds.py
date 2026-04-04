#!/usr/bin/env python3

import numpy
import gdspy
import json
import argparse
import os

ap = argparse.ArgumentParser()
ap.add_argument( "-p", "--pl_file", type=str, default="", help='<filename.placement_verilog.json>')
ap.add_argument( "-g", "--gds_dir", type=str, default="", help='<dir with all leaf gds files>')
ap.add_argument( "-t", "--top_cell", type=str, default="library", help='<top cell>')
ap.add_argument( "-u", "--units", type=float, default=1e-6, help='<units in m>')
ap.add_argument( "-s", "--scale", type=float, default=1e3, help='<scale>')
args = ap.parse_args()
print(f"placement verilog : {args.pl_file}")
print(f"gds dir           : {args.gds_dir}")
print(f"top cell          : {args.top_cell}")
print(f"units             : {args.units}")

if args.pl_file == "" or args.gds_dir == "":
    ap.print_help()
    exit()

orientLUT = [0, 90, 180, 270]

class Instance:
    def __init__(self, name = "", origin=(0,0), angle=0):
        self._name   = name
        self._angle  = angle
        self._modu   = None
        self._origin = origin
    def __str__(self):
        return f'{self._name} {self._origin} {self._angle}'

class Module:
    def __init__(self, name = "", leaf = False):
        self._name      = name
        self._instances = list()
        self._added     = False
        self._leaf      = leaf
        self._fname     = ""
        self._cell      = None
    def __str__(self):
        s = f"{self._name} '{self._fname}' {self._cell}"
        for i in self._instances:
            s += f' [{str(i)} {i._modu._name}]'
        return s
    def add(self):
        print(f'working on cell {self._name}')
        for i in self._instances:
            if i._modu:
                if not i._modu._added:
                    i._modu.add()
                bbox = i._modu._cell.get_bounding_box()
                angle, refl = 0, False
                oX, oY = i._origin[0]/args.scale, i._origin[1]/args.scale
                angle = i._angle
                print(f'{self._name} creating reference of {i._name} at {(oX,oY)} {refl} {angle})')
                ref = gdspy.CellReference(i._modu._cell, (oX, oY), x_reflection = refl, rotation = angle)
                if not self._cell:
                    self._cell = gdspy.Cell(self._name)
                self._cell.add(ref)
        self._added = True

modules = dict()
if args.pl_file:
    with open(args.pl_file) as fp:
        pldata = json.load(fp)
        if "modules" in pldata:
            modu = Module(args.top_cell)
            modules[modu._name] = modu
            for k,v in pldata["modules"].items():
                flname = v.get("gds_file")
                if flname and '/' in flname and '.gds' in flname:
                    flname = flname[flname.rfind('/') + 1:flname.rfind('.gds')]
                    tmpmodu = Module(flname, True)
                    modules[tmpmodu._name] = tmpmodu
                orient = v.get("orientation")
                angle = orientLUT[orient] if orient else 0
                origin = (v.get("x"), v.get("y"))
                wh = (v.get("w"), v.get("h"))
                if orient == 1:
                  origin = (origin[0], origin[1] + wh[1])
                elif orient == 2:
                  origin = (origin[0] + wh[0], origin[1] + wh[1])
                elif orient == 3:
                  origin = (origin[0] + wh[0], origin[1])
                modu._instances.append(Instance(flname, origin, -angle))

gdscell = dict()
if (args.gds_dir):
    if not os.path.isdir(args.gds_dir):
        print(f'{args.gds_dir} not found')
        exit()
    for j,m in modules.items():
        if not m._leaf:
            continue
        m._fname = args.gds_dir + '/' + j + '.gds'
        if not os.path.isfile(m._fname):
            print(f'leaf {m._fname} not found')
            exit()
        lib = gdspy.GdsLibrary(infile=m._fname)
        m._cell = lib.top_level()[0]
        m._cell.flatten()
        m._added = True


for j,m in modules.items():
    for i in m._instances:
        modu = modules.get(i._name)
        if modu:
            i._modu = modu

for j,m in modules.items():
  print(m)
gdslib = gdspy.GdsLibrary(name=args.top_cell, unit=args.units)
for j,m in modules.items():
    m.add()
    assert m._cell, f"module : {m._name} gds cell not found!"
    gdslib.add(m._cell)

print(f'writing gds file {args.top_cell}_out.gds')
gdslib.write_gds(args.top_cell + '_out.gds')
