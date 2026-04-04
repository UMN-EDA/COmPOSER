#!/usr/bin/env python3

import numpy
import gdspy
import json
import argparse
import os

ap = argparse.ArgumentParser()
ap.add_argument( "-p", "--pl_file", type=str, default="", help='<filename.placement_verilog.json>')
ap.add_argument( "-g", "--gds_dir", type=str, default="", help='<dir with all leaf gds files>')
ap.add_argument( "-i", "--def_dir", type=str, default="", help='<dir with all hier def files>')
ap.add_argument( "-t", "--top_cell", type=str, default="library", help='<top cell>')
ap.add_argument( "-u", "--units", type=float, default=1e-6, help='<units in m>')
ap.add_argument( "-s", "--scale", type=float, default=1e3, help='<scale>')
ap.add_argument( "-l", "--layers", type=str, default="", help='<layers.json>')
ap.add_argument( "-d", "--deff", type=str, default="", help='<route def file>')
args = ap.parse_args()
if args.pl_file == "" or args.gds_dir == "" or args.layers == "" or args.deff == "" :
    ap.print_help()
    exit()

print(f"placement verilog : {args.pl_file}")
print(f"gds dir           : {args.gds_dir}")
print(f"top cell          : {args.top_cell}")
print(f"units             : {args.units}")
print(f"layers.json       : {args.layers}")
print(f"route def file    : {args.deff}")
print(f"hier def dir      : {args.def_dir}")

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

def read_def(def_file, modu):
    with open(def_file) as fp:
        innets = False
        infills = False
        sca = args.scale
        layeridx = None
        currnet = None
        labeladded = False
        for line in fp:
            line.strip()
            if "UNITS" in line:
              if "DISTANCE" in line:
                s = line.split()
                if sca == 1 and len(s) == 5:
                  sca = int(s[3])
            if "NETS" in line:
                if "END" in line:
                    innets = False
                else:
                    innets = True
            if "FILLS" in line:
                if "END" in line:
                    infills = False
                else:
                    infills = True
            if infills:
                continue 
            if innets:
                if not currnet and "-" in line:
                    s = line.split()
                    if len(s) > 1:
                        currnet = s[1]

                if "RECT" in line:
                    s = line.split()
                    if len(s) > 10:
                        index = 0
                        if s[0] == "RECT":
                            index = 0
                        if s[1] == "RECT":
                            index = 1
                        layer = s[index + 1]
                        rect = [float(s[index + 3])/sca, float(s[index + 4])/sca, float(s[index + 7])/sca, float(s[index + 8])/sca]
                        l = layers[layer]
                        if args.top_cell in modules:
                            modu._cell.add(gdspy.Rectangle((rect[0], rect[1]), (rect[2], rect[3]),\
                                        layer=l[0], datatype=l[1]))
                        if currnet and (not labeladded) and (layer in labellayers) and ('M' in layer.upper()):
                            modu._cell.add(gdspy.Label(currnet, position=((rect[0] + rect[2])/2, (rect[1] + rect[3])/2),\
                                        anchor='o', layer = labellayers[layer][0][0], texttype = labellayers[layer][0][1]))
                            labeladded = True
                if ";" in line:
                    currnet = None
                    labeladded = False
            


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
            m._fname = args.gds_dir + '/' + j.lower() + '.gds'
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

gdslib = gdspy.GdsLibrary(name=args.top_cell, unit=args.units)

layers = dict()
labellayers = dict()
if args.layers:
    with open(args.layers) as fp:
        layerdata = json.load(fp)
        if "Abstraction" in layerdata:
            for l in layerdata["Abstraction"]:
                if "Layer" in l and "GdsLayerNo" in l:
                    layer = l["Layer"]
                    glno1 = l["GdsLayerNo"]
                    if "GdsDatatype" in l and "Draw" in l["GdsDatatype"]:
                        glno2 = l["GdsDatatype"]["Draw"]
                    else:
                        glno2 = 0
                    layers[layer] = (glno1,glno2)
                    if "LabelLayerNo" in l:
                        labellayers[layer] = l["LabelLayerNo"]
print(labellayers)
        
for j,m in modules.items():
    m.add()
    defname = args.def_dir + '/' + j + '.def'
    print(f'Reading def file : {defname}')
    if args.def_dir != "" and os.path.isfile(defname):
        read_def(defname, m)
    gdslib.add(m._cell)

if args.deff and args.top_cell in modules:
    read_def(args.deff, modules[args.top_cell])

print(f'writing gds file {args.top_cell}_out.gds')
gdslib.write_gds(args.top_cell + '_out.gds')
