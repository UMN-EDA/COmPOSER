#include <sstream>
#include "nlohmann/json.hpp"
#include "Util.h"
#include "Placement.h"
#include <cmath>

namespace Placement {
using json = nlohmann::json;
using ordered_json = nlohmann::ordered_json;
const auto& npos = std::string::npos;

static std::string getPrimitiveName(const std::string& instr)
{
  auto pos = instr.rfind('/');
  auto pos1 = instr.rfind(".gds");
  if (pos != std::string::npos && pos1 != std::string::npos) {
    return instr.substr(pos + 1, pos1 - pos - 1);
  }
  return instr;
}

Netlist::Netlist(const std::string& plfile, const::std::string& leffile, const DRC::LayerInfo& lf, const int uu, const std::string& ndrfile, const std::string& ildir, const std::string& topname) : _uu(uu), _valid{1}
{
  if (plfile.empty()) {
    CERR<< "missing placement file" <<std::endl;
    _valid = 0;
    return;
  }
  std::ifstream ifs(plfile);
  if (!ifs) {
    CERR << "unable to open placement file " << plfile <<std::endl;
    _valid = 0;
    return;
  }
  ordered_json oj = json::parse(ifs);
  ifs.close();
  auto it = oj.find("modules");
  std::map<std::string, Geom::Rect> leafData;
  // modules refers to leaf cells in this placement json file
  if (it != oj.end()) {
    for (auto& kv : it->items()) {
      auto mname = kv.key();
      auto& m = kv.value();
      if (_modules.find(mname) != _modules.end()) continue;
      auto aname = m.find("gds_file");
      std::string primName(mname);
      if (aname != m.end()) {
        primName = getPrimitiveName(aname->dump());
      }
      auto modu = new Module(primName, primName, 1, _uu);
      COUT << "adding leaf : " << primName << '\n';
      /*
      auto params = m.find("pins");
      if (params != m.end()) {
        for (unsigned i = 0; i < params->size(); ++i) {
          auto pinName = std::to_string(i);
          auto p = modu->addPin(pinName);
          modu->addNet(pinName);
          modu->net(pinName)->addPin(p);
        }
      }*/
      auto tmpx = m.find("x");
      auto tmpy = m.find("y");
      auto tmpw = m.find("w");
      auto tmph = m.find("h");
      if (tmpx != m.end() && tmpy != m.end() && tmpw != m.end() && tmph != m.end()) {
        leafData[modu->name()] = Geom::Rect(*tmpx, *tmpy, (int(*tmpx) + int(*tmpw)), (int(*tmpy) + int(*tmpw)));
      }
      _modules[modu->name()] = modu;
    }
  }
  it = oj.find("chip");
  Geom::Rect boundary;
  if (it != oj.end()) {
    if (it->find("W") != it->end() && it->find("H") != it->end()) {
      auto x = int((*it)["W"]);
      auto y = int((*it)["H"]);
      boundary.set(0, 0, x, y);
      std::cout << boundary.str() << std::endl;
    }
  }
  it = oj.find("modules");
  if (it != oj.end()) {
    auto modu = new Module(topname, topname, 0, _uu);
    COUT << "adding module : " << topname << '\n';
    modu->setBBox(boundary);
    std::map<std::string, Placement::Instance*> instLUT;
    for (auto& kv : it->items()) {
      auto mname = kv.key();
      auto& m = kv.value();
      int oX, oY, W, H;
      auto itx = m.find("x");
      auto ity = m.find("y");
      auto itw = m.find("w");
      auto ith = m.find("h");
      if (itx != m.end() && ity != m.end() && itw != m.end() && ith != m.end()) {
        oX = *itx;
        oY = *ity;
        W = *itw;
        H = *ith;
      }
      Geom::Transform tr;
      auto tritr = m.find("orientation");
      if (tritr != m.end()) {
        switch (int(*tritr)) {
          case 0:
          default:
            tr = Geom::Transform(oX, oY, 0);
            break;
          case 1:
            tr = Geom::Transform(oX, oY + H, -90);
            break;
          case 2:
            tr = Geom::Transform(oX + W, oY + H, -180);
            break;
          case 3:
            tr = Geom::Transform(oX + W, oY, -270);
            break;
        }
      }
      auto aname = m.find("gds_file");
      std::string primName(mname);
      if (aname != m.end()) {
        primName = getPrimitiveName(aname->dump());
      }
      instLUT[mname] = modu->addInstance(mname, primName, tr);
    }
    it = oj.find("nets");
    if (it != oj.end()) {
      for (auto& kv : it->items()) {
        auto netName = kv.key();
        auto& netData = kv.value();
        const Net* n = &(modu->addNet(netName));
        auto epit = netData.find("endpoints");
        std::cout << "adding net : " << netName << std::endl;
        if (epit != netData.end()) {
          for (auto& pins : *epit) {
            std::cout << "adding pin : " << pins["module"] << ' ' << instLUT[pins["module"]] << " " << pins["pin_name"] << std::endl;
            modu->addTmpPin(n, instLUT[pins["module"]], pins["pin_name"]);
            auto master = _modules.find(instLUT[pins["module"]]->moduleName());
            if (master != _modules.end()) {
              std::string pinName = pins["pin_name"];
              auto p = master->second->addPin(pinName);
              master->second->addNet(pinName);
              master->second->net(pinName)->addPin(p);
            }
          }
        }
      }
    } else {
      COUT << "instptr nullptr\n";
    }
    _modules[modu->name()] = modu;
  }
  if (!ildir.empty()) {
    for (auto& it : _modules) {
      std::string modlef{ildir + it.first + "_interim_hier.lef"};
      std::ifstream ifs(modlef);
      if (ifs.good()) {
        ifs.close();
        loadLEF(modlef, lf);
        if (_loadedMacros.find(it.first) != _loadedMacros.end()) {
          it.second->setLeaf();
        }
      }
    }
  }
  loadLEF(leffile, lf);
  _loadedMacros.clear();
  build();
  readNDR(ndrfile, lf);
}


Netlist::~Netlist()
{
  for (auto& m : _modules) delete m.second;
  _modules.clear();
}


void Netlist::print() const
{
  for (const auto& m : _modules) {
    COUT << "module : " << m.second->name() << '\n';
    m.second->print();
  }
}


void Netlist::build()
{
  for (auto& m : _modules) {
    for (auto& inst : m.second->instances()) {
      auto it = _modules.find(inst->moduleName());
      if (it != _modules.end()) {
        inst->setModule(it->second);
      }
    }
  }
  for (auto& m : _modules) m.second->build();
}


void Netlist::loadLEF(const std::string& leffile, const DRC::LayerInfo& lf)
{
  if (leffile.empty()) {
    CERR<< "missing leffile" <<std::endl;
    _valid = 0;
    return;
  }
  std::ifstream ifs(leffile);
  if (!ifs) {
    CERR << "unable to open leffile " << leffile <<std::endl;
    _valid = 0;
    return;
  }
  COUT << "Reading LEF file " << leffile << '\n';
  std::string line;
  bool inMacro{false}, inPin{false}, inObs{false}, inPort{false}, inUnits{false};
  Module* curr_module{nullptr};
  Pin* curr_pin{nullptr};
  Port* curr_port{nullptr};
  std::string macroName, pinName;
  int layer{-1};
  double macroUnits{1.};
  int units = _uu;
  while (std::getline(ifs, line)) {
    std::string str;
    std::stringstream ss(line);
    if (line.find("MACRO") != npos) {
      ss >> str >> macroName;
      COUT << "macro " << macroName << '\n';
      if (_loadedMacros.find(macroName) != _loadedMacros.end()) {
        while (std::getline(ifs, line)) {
          if (line.find("END") != npos && line.find(macroName) != npos) break;
        }
      }
      auto it = _modules.find(macroName);
      if (it != _modules.end()) {
        curr_module =  it->second;
        COUT << "loading macro " << macroName << '\n';
        _loadedMacros.insert(macroName);
      }
      inMacro = true;
      continue;
    }
    if (line.find("FOREIGN ") != npos) continue;
    if (line.find("END") != npos) {
      if (inUnits) {
        if (line.find("UNITS") != npos) {
          inUnits = false;
        }
      }
      if (inPort) {
        inPort = false;
        if (curr_port) curr_pin->addPort(curr_port);
        curr_port = nullptr;
      } else if (inPin) {
        if (line.find(pinName) != npos) {
          inPin = false;
          curr_pin = nullptr;
          pinName.clear();
        }
      } else if (inMacro) {
        if (line.find(macroName) != npos) {
          inMacro = false;
          curr_module = nullptr;
          macroName.clear();
        }
      } else if (inObs) {
        inObs = false;
        layer = -1;
      }
      continue;
    }
    if (inMacro && curr_module) {
      if (line.find("SIZE") != npos) {
        double w{0.}, h{0.};
        ss >> str >> w >> str >> h;
        curr_module->setBBox(Geom::Rect(0, 0, w * units, h * units));
      }
      if (line.find("PIN") != npos) {
        ss >> str >> pinName;
        curr_pin = curr_module->getPin(pinName);
        inPin = true;
        continue;
      }
    }
    if (inUnits && line.find("DATABASE") != npos) {
      ss >> str >> str >> str >> macroUnits;
      units /= macroUnits;
    }
    if (inPin && curr_pin && ((line.find("DIRECTION") != npos) || (line.find("USE") != npos))) {
      continue;
    }
    if (inPin && curr_pin && line.find("PORT") != npos) {
      inPort = true;
      curr_port = new Port();
      layer = -1;
      continue;
    }
    if (line.find("OBS") != npos) {
      inObs = true;
      continue;
    }
    if (inPort && curr_port) {
      if (line.find("LAYER") != npos) {
        ss >> str >> str;
        layer = lf.getLayerIndex(str);
        continue;
      }
      if (line.find("RECT") != npos) {
        double llx{0}, lly{0}, urx{0}, ury{0};
        ss >> str >> llx >> lly >> urx >> ury;
        if (layer >= 0) {
          curr_port->addRect(layer, Geom::Rect(round(llx * units), round(lly * units), round(urx * units), round(ury * units)));
        }
        continue;
      }
    }
    if (inObs && curr_module) {
      if (line.find("LAYER") != npos) {
        ss >> str >> str;
        layer = lf.getLayerIndex(str);
        if (str[0] != 'M' && str[0] != 'V') layer = -1;
        continue;
      }
      if (line.find("RECT") != npos) {
        double llx{0}, lly{0}, urx{0}, ury{0};
        ss >> str >> llx >> lly >> urx >> ury;
        if (layer >= 0) {
//          std::cout << layer << ' ' << str << ' ' << llx << ' ' << lly << ' ' << urx << ' ' << ury << ' ' << units << std::endl;
          curr_module->addObstacle(layer, Geom::Rect(round(llx * units), round(lly * units), round(urx * units), round(ury * units)));
        }
        continue;
      }
    }
  }
  ifs.close();
}

void Netlist::readNDR(const std::string& ndrfile, const DRC::LayerInfo& lf)
{
  if (!ndrfile.empty()) {
    std::ifstream ifs(ndrfile);
    if (!ifs) {
      CERR << "unable to open NDR file " << ndrfile <<std::endl;
      _valid = 0;
      return;
    }
    ordered_json oj = json::parse(ifs);
    for (auto& m : oj) {
      auto it = m.find("module");
      if (it != m.end()) {
        auto modit = _modules.find(*it);
        if (modit != _modules.end()) {
          const std::vector<std::string> wsd = {"widths", "spaces", "directions", "preferred_layers", "vias"};
          for (unsigned iwsd = 0; iwsd < wsd.size(); ++iwsd) {
            auto itwsd = m.find(wsd[iwsd]);
            if (itwsd != m.end()) {
              if (iwsd < 3) {
                for (auto& el : (*itwsd).items()) {
                  auto layer = lf.getLayerIndex(el.key());
                  if (layer >= 0) {
                    switch (iwsd) {
                      default:
                      case 0: modit->second->addNDRWidth(layer, std::round(static_cast<double>(el.value()) * _uu));
                              break;
                      case 1: modit->second->addNDRSpace(layer, std::round(static_cast<double>(el.value()) * _uu));
                              break;
                      case 2: modit->second->addNDRDir(layer, el.value());
                              break;
                    }
                  }
                }
              } else if (iwsd == 3) {
                for (auto& el : (*itwsd)) {
                  auto layer = lf.getLayerIndex(el);
                  modit->second->addPrefLayer(layer);
                }
              } else if (iwsd == 4) {
                for (auto& el : (*itwsd).items()) {
                  auto layer = lf.getLayerIndex(el.key());
                  auto &via = el.value();
                  if (layer >= 0) {
                    int wx{0}, wy{0}, sx{0}, sy{0}, nx{0}, ny{0};
                    auto itvia = via.find("WidthX");
                    if (itvia != via.end()) wx = *itvia;
                    itvia = via.find("WidthY");
                    if (itvia != via.end()) wy = *itvia;
                    itvia = via.find("SpaceX");
                    if (itvia != via.end()) sx = *itvia;
                    itvia = via.find("SpaceY");
                    if (itvia != via.end()) sy = *itvia;
                    itvia = via.find("NumX");
                    if (itvia != via.end()) nx = *itvia;
                    itvia = via.find("NumY");
                    if (itvia != via.end()) ny = *itvia;
                    modit->second->addNDRVia(layer, DRC::ViaArray(wx, wy, sx, sy, nx, ny));
                  }
                }
              }
            }
          }
          it = m.find("nets");
          if (it != m.end()) {
            for (auto& netiter : *it) {
              auto itnetname = netiter.find("name");
              if (itnetname != netiter.end()) {
                auto itdetour = netiter.find("large_detour");
                if (itdetour != netiter.end() && *itdetour == "allowed") {
                  modit->second->allowDetour(*itnetname);
                }
                for (unsigned iwsd = 0; iwsd < wsd.size(); ++iwsd) {
                  auto itwsd = netiter.find(wsd[iwsd]);
                  if (itwsd != netiter.end()) {
                    if (iwsd < 3) {
                      for (auto& el : (*itwsd).items()) {
                        auto layer = lf.getLayerIndex(el.key());
                        if (layer >= 0) {
                          switch (iwsd) {
                            default:
                            case 0: modit->second->addNDRWidth(layer, std::round(static_cast<double>(el.value()) * _uu), *itnetname);
                                    break;
                            case 1: modit->second->addNDRSpace(layer, std::round(static_cast<double>(el.value()) * _uu), *itnetname);
                                    break;
                            case 2: modit->second->addNDRDir(layer, el.value(), *itnetname);
                                    break;
                          }
                        }
                      }
                    } else if (iwsd == 3) {
                      modit->second->clearPrefLayer(*itnetname);
                      for (auto& el : (*itwsd)) {
                        auto layer = lf.getLayerIndex(el);
                        modit->second->addPrefLayer(layer, *itnetname);
                      }
                    } else if (iwsd == 4) {
                      for (auto& el : (*itwsd).items()) {
                        auto layer = lf.getLayerIndex(el.key());
                        auto &via = el.value();
                        if (layer >= 0) {
                          int wx{0}, wy{0}, sx{0}, sy{0}, nx{0}, ny{0};
                          auto itvia = via.find("WidthX");
                          if (itvia != via.end()) wx = *itvia;
                          itvia = via.find("WidthY");
                          if (itvia != via.end()) wy = *itvia;
                          itvia = via.find("SpaceX");
                          if (itvia != via.end()) sx = *itvia;
                          itvia = via.find("SpaceY");
                          if (itvia != via.end()) sy = *itvia;
                          itvia = via.find("NumX");
                          if (itvia != via.end()) nx = *itvia;
                          itvia = via.find("NumY");
                          if (itvia != via.end()) ny = *itvia;
                          modit->second->addNDRVia(layer, DRC::ViaArray(wx, wy, sx, sy, nx, ny), *itnetname);
                        }
                      }
                    }
                  }
                }
              }
              auto itvpin = netiter.find("virtual_pins");
              if (itvpin != netiter.end()) {
                for (auto& vp : *itvpin) {
                  Geom::LayerRects lr;
                  for (auto& l : vp.items()) {
                    auto layer = lf.getLayerIndex(l.key());
                    if (layer >= 0) {
                      for (auto& r : l.value()) {
                        if (r.size() == 4) lr[layer].emplace_back(std::round(static_cast<double>(r[0]) * _uu), std::round(static_cast<double>(r[1]) * _uu),
                            std::round(static_cast<double>(r[2]) * _uu), std::round(static_cast<double>(r[3]) * _uu));
                      }
                    }
                  }
                  if (!lr.empty()) {
                    modit->second->addVirtualPin(*itnetname, lr);
                  }
                }
              }
            }
          }
          it = m.find("do_not_route");
          if (it != m.end()) {
            for (auto& netiter : *it) {
              modit->second->excludeNet(netiter);
            }
          }
          it = m.find("clock_nets");
          if (it != m.end()) {
            for (auto& netiter : *it) {
              auto itnetname = netiter.find("name");
              auto itdriver = netiter.find("driver");
              if (itnetname != netiter.end() && itdriver != netiter.end()) {
                modit->second->setClockDriver(*itnetname, *itdriver);
              }
            }
          }
          it = m.find("routing_order");
          if (it != m.end()) {
            for (auto& netiter : *it) {
              modit->second->addNetToOrder(netiter);
            }
          }
          it = m.find("obstacles");
          if (it != m.end()) {
            for (auto& obsiter : *it) {
              auto itnets = obsiter.find("nets");
              auto itshapes = obsiter.find("shapes");
              if (itshapes != obsiter.end()) {
                if (itnets == obsiter.end()) {
                  for (auto& l : (*itshapes).items()) {
                    auto layer = lf.getLayerIndex(l.key());
                    if (layer >= 0) {
                      for (auto& r : l.value()) {
                        if (r.size() == 4) {
                          COUT << "Adding obstacle to module " << modit->second->name() << " layer : " << l.key() << " : [" << r[0] << ' ' << r[1] << ' ' << r[2] << ' ' << r[3] << "]\n";
                          modit->second->addObstacle(layer, Geom::Rect(std::round(static_cast<double>(r[0]) * _uu), std::round(static_cast<double>(r[1]) * _uu),
                                std::round(static_cast<double>(r[2]) * _uu), std::round(static_cast<double>(r[3]) * _uu))); 
                        }
                      }
                    }
                  }
                } else {
                  for (auto& n : *itnets) {
                    for (auto& l : (*itshapes).items()) {
                      auto layer = lf.getLayerIndex(l.key());
                      if (layer >= 0) {
                        for (auto& r : l.value()) {
                          if (r.size() == 4) modit->second->addNetObstacle(n, layer, Geom::Rect(std::round(static_cast<double>(r[0]) * _uu), std::round(static_cast<double>(r[1]) * _uu),
                                std::round(static_cast<double>(r[2]) * _uu), std::round(static_cast<double>(r[3]) * _uu)));
                        }
                      }
                    }
                  }
                }
              }
            }
          }
          it = m.find("use_pin_width");
          if (it != m.end()) {
            modit->second->setusepinwidth(static_cast<int>(*it));
          }
        }
      }
    }
  }
}

}
