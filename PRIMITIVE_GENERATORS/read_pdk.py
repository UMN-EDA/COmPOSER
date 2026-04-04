import json
#Reading layers.json file
def readLayerInfo(layerfile, scale): 
    layers_specs_sacle = scale
    layers = dict()
    layerSpecs = dict()
    layernames = dict()
    labellayers = dict()
    design_info = dict()
    with open(layerfile) as fp:
        layerdata = json.load(fp)
        if "Abstraction" in layerdata:
            for l in layerdata["Abstraction"]:
                if "Layer" in l and "GdsLayerNo" in l:# and "Direction" in l:
                    layer = l["Layer"]      #Layer Name (M1)
                    glno1 = l["GdsLayerNo"]    #Layer no. (15)
                    glno2 = dict()  #Dict for storing different datatypes of layer
                    specs = dict()
                    layernames[layer] = glno1   #Dict of layernames where key is layer number and value is layer name
                    if "GdsDatatype" in l:
                        for key, idx in l["GdsDatatype"].items():
                            glno2[key] = idx    #Storing values of gds data types where key is the Data type No (32) (idx) and  value is the data type name (Pin) (key)
                            if "Label"== key:   #If its data type of "Label"
                                labellayers[glno1] = (glno1, idx) #e.g. labelayers[(17,20)] = 17 WHICH IS FOR M2 Label
                            elif "Pin"== key:
                                labellayers[glno1] = (glno1, idx) #e.g. labellayers[(17,32)] = 17 WHICH IS FOR M2 Pin
                    if "LabelLayerNo" in l:
                        for ll in l["LabelLayerNo"]:
                            if len(ll) == 2:
                                labellayers[glno1] = (ll[0], ll[1])
                            elif len(ll) == 1:
                                labellayers[glno1] = (ll[0], 0)
                    layers[layer] = glno2
                    if "Width" in l:
                        specs["Width"] = l["Width"]/layers_specs_sacle
                    if "WidthMax" in l:
                        specs["WidthMax"] = l["WidthMax"]/layers_specs_sacle
                    if "WidthX" in l:
                        specs["WidthX"] = l["WidthX"]/layers_specs_sacle
                    if "WidthY" in l:
                        specs["WidthY"] = l["WidthY"]/layers_specs_sacle
                    if "SpaceX" in l:
                        specs["SpaceX"] = l["SpaceX"]/layers_specs_sacle
                    if "SpaceY" in l:
                        specs["SpaceY"] = l["SpaceY"]/layers_specs_sacle
                    if "Pitch" in l:
                        specs["Pitch"] = l["Pitch"]/layers_specs_sacle
                    if "VencA_L" in l:
                        specs["VencA_L"] = l["VencA_L"]/layers_specs_sacle
                    if "VencA_L" in l:
                        specs["VencA_H"] = l["VencA_H"]/layers_specs_sacle
                    if "VencA_L" in l:
                        specs["VencP_L"] = l["VencP_L"]/layers_specs_sacle
                    if "VencA_L" in l:
                        specs["VencP_H"] = l["VencP_H"]/layers_specs_sacle
                    if "Direction" in l:
                        specs["Direction"] = l["Direction"]
                    if "EndToEnd" in l:
                        specs["EndToEnd"] = l["EndToEnd"]/layers_specs_sacle
                    layerSpecs[layer] = specs

        if "design_info" in layerdata:
            di = layerdata["design_info"]
            # keys that should be scaled down
            scale_keys = {
                "bga_pitch_x",
                "bga_pitch_y",
                "periphery_pad_pitch"
            }

            for key, value in di.items():
                if key in scale_keys and isinstance(value, (int, float)):
                    design_info[key] = value * scale
                else:
                    design_info[key] = value

    return (layers, layernames, labellayers, layerSpecs, design_info)


# layers, layernames, labellayers, layerSpecs = readLayerInfo("../pdk/rf_65_pdks/65n_placer/layers.json")
# print(layers)


