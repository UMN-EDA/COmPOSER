#!/usr/bin/env python3

import argparse
import math
import numpy as np
import pandas as pd
import sys
import os
import json
import numpy as np
from tqdm import tqdm




from PRIMITIVE_OPTIMIZERS import optimize_inductor as my_L_optimizer
from PRIMITIVE_OPTIMIZERS import optimize_tline as my_TL_optimizer
from PRIMITIVE_OPTIMIZERS import optimize_cpwd as my_CPWD_optimizer
from PRIMITIVE_OPTIMIZERS import emx_estimator as my_emx



def load_config(config_path):
    with open(config_path, "r") as f:
        return json.load(f)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Cascode LNA optimization with constants loaded from a config file."
    )
    parser.add_argument(
        "--config",
        default="lna_initial_config.json",
        help="Path to JSON config file"
    )
    parser.add_argument(
        "--out-json",
        default="best_lna_design.json",
        help="Path to output best design JSON file"
    )
    parser.add_argument(
        "--out-csv",
        default="all_lna_designs.csv",
        help="Path to output CSV file with all the LNA designs"
    )
    return parser


def real_roots_only(roots_arr, tol=1e-9):
    return [r.real for r in roots_arr if abs(r.imag) < tol]


def export_best_design_json(best_row, best_feasible, best_idx,
                            nf_target_max, gain_target_min, bw_target_min,
                            s11_target_max, pwr_target_max,
                            out_json="best_lna_design.json"):
    """
    Export best LNA designs (multi-objective) to a JSON file with clean custom keys.
    """

    KEY_MAP = {
        "Option": "Design_ID",
        "Rin": "Input_Resistance_Ohms",
        "Size": "CASMOS_Size",
        "NF": "Noise_Figure_dB",
        "Gain": "Gain_dB",
        "S11": "S11_dB",
        "BW": "Bandwidth_Hz",
        "_BW_GHz": "Bandwidth_GHz",
        "Input_TLine_Imp": "Input_TLine_Impedance_Ohms",
        "Input_TLine_Len": "Input_TLine_Length",
        "Input_L": "GATE_IND_L",
        "Input_L_Q": "GATE_IND_Q",
        "Input_L_SRF": "GATE_IND_SRF",
        "Input_L_Geom": "GATE_IND_GEOM",
        "Output_L": "DRAIN_IND_L",
        "Output_L_Q": "DRAIN_IND_Q",
        "Output_L_SRF": "DRAIN_IND_SRF",
        "Output_L_Geom": "DRAIN_IND_GEOM",
        "Degen_L": "SOURCE_IND_L",
        "Degen_L_Q": "SOURCE_IND_Q",
        "Degen_L_SRF": "SOURCE_IND_SRF",
        "Degen_L_Geom": "SOURCE_IND_GEOM",
        "DC_Power": "DC_Power_mW",
        "_PWR_mW": "DC_Power_numeric_mW",
        "Score": "Selection_Score",
        "CPWD_Length": "CPWD_Length",
        "CPWD_Width": "CPWD_Width",
        "CPWD_Gap": "CPWD_Gap",
        "CLoad": "CLoad",
        "Inter_ind_L": "Inter_ind_L",
        "Inter_ind_Q": "Inter_ind_Q",
        "Inter_ind_SRF": "Inter_ind_SRF",
        "Inter_cap": "Inter_cap"
    }

    def row_to_dict(row):
        out = {}
        for col, key in KEY_MAP.items():
            if col in row:
                val = row[col]
                if isinstance(val, (int, float, np.integer, np.floating)):
                    out[key] = round(float(val), 10)
                else:
                    out[key] = str(val)
        return out

    result_dict = {
        "Best_Cascode_LNA_Design": {
            "Selection_Score_LowerIsBetter": float(best_row["Score"]),
            "Spec_Targets": {
                "NF_max_dB": float(nf_target_max),
                "Gain_min_dB": float(gain_target_min),
                "BW_min_Hz": float(bw_target_min),
                "S11_max_dB": float(s11_target_max),
                "Power_max_mW": float(pwr_target_max)
            },
            "Design_Parameters": row_to_dict(best_row)
        }
    }

    if best_feasible is not None and best_feasible.name != best_idx:
        result_dict["Best_Strictly_Feasible_Design"] = row_to_dict(best_feasible)

    with open(out_json, "w") as f:
        json.dump(result_dict, f, indent=4)

    print(f"? Best design written to {out_json}")



def main():

    parser = build_parser()
    args = parser.parse_args()

    gen_cfg = load_config(args.config)
    cfg = load_config(gen_cfg["stage_1_config"])
    
    model_settings = cfg["model_settings"]
    debug_cfg = cfg["debug"]
    unit_conversions = cfg["unit_conversions"]
    formula_constants = cfg["formula_constants"]
    sweeps = cfg["sweeps"]
    thresholds = cfg["thresholds"]
    fallbacks = cfg["fallbacks"]
    interstage = cfg["interstage"]
    s11_reference = cfg["s11_reference"]
    scoring = cfg["scoring"]

    cpwd_knn_neighbors = model_settings["cpwd_knn_neighbors"]

    debug_check = False
    debug_L = None
    debug_emx_input_array = None

    ghz_to_hz = unit_conversions["ghz_to_hz"]
    h_to_ph = unit_conversions["h_to_ph"]

    nf_factor = formula_constants["nf_factor"]
    numerator_const = formula_constants["numerator_const"]
    q_formula_const = formula_constants["q_formula_const"]
    two_pi_approx = formula_constants["two_pi_approx"]
    degen_mid_const = formula_constants["degen_mid_const"]
    source_ind_scale = formula_constants["source_ind_scale"]
    input_match_loss_factor = formula_constants["input_match_loss_factor"]
    z1_scale = formula_constants["z1_scale"]
    z1_divisor = formula_constants["z1_divisor"]
    srf_angle_numerator = formula_constants["srf_angle_numerator"]
    theta1_scale = formula_constants["theta1_scale"]
    gamma_db_scale = formula_constants["gamma_db_scale"]
    rd_factor = formula_constants["rd_factor"]
    cpwd_penalty_prefactor = formula_constants["cpwd_penalty_prefactor"]
    gain_factor = formula_constants["gain_factor"]

    z2_start = sweeps["z2"]["start"]
    z2_stop = sweeps["z2"]["stop"]
    z2_num = sweeps["z2"]["num"]
    theta2_start = sweeps["theta2"]["start"]
    theta2_stop = sweeps["theta2"]["stop"]
    theta2_num = sweeps["theta2"]["num"]
    rin_start = sweeps["rin"]["start"]
    rin_stop = sweeps["rin"]["stop"]
    rin_step = sweeps["rin"]["step"]

    ind_src_opt_threshold = thresholds["ind_src_opt_threshold"]
    output_match_cload_threshold = thresholds["output_match_cload_threshold"]
    pad_input_imag_abs_max = thresholds["pad_input_imag_abs_max"]
    freq_interstage_threshold_hz = thresholds["freq_interstage_threshold_hz"]
    drain_ind_inter_threshold = thresholds["drain_ind_inter_threshold"]

    fallback_q_source = fallbacks["q_source"]

    interstage_series_cap = interstage["series_cap"]
    interstage_shunt_cap_1 = interstage["shunt_cap_1"]

    s11_numerator_ref = s11_reference["numerator_ref"]
    s11_denominator_ref = s11_reference["denominator_ref"]

    scoring_eps = scoring["eps"]
    scoring_weights = scoring["weights"]
    scoring_penalties = scoring["penalties"]

    dataset_path = gen_cfg["datasets"]["spiral_inductor"]
    cpwd_data = gen_cfg["datasets"]["cpwd"]
    cpwd_knn_model, _ = my_CPWD_optimizer.train_knn(
        cpwd_data,
        n_neighbors=cpwd_knn_neighbors
    )
    emx_estimator_rf_model, knn_model, knn_geom_train = my_L_optimizer.setup_all_models(dataset_path)

    check = debug_check
    if check:
        L = debug_L
        results = my_L_optimizer.optimize_specs(
            target_specs=[L, None, None, None],
            emx_estimator_model=emx_estimator_rf_model,
            knn_model=knn_model,
            knn_train_data=knn_geom_train
        )
        print("Input spec:     ", results['target_specs'])
        print("Predicted spec: ", results['pred_spec'])
        print("Best geometry:  ", results['geometry'])
        print(
            f"Emx of inductor is {my_emx.infer_emx_model(input_array=debug_emx_input_array, emx_estimator_model=emx_estimator_rf_model)}"
        )
        sys.exit()

    print("--Cascode LNA with inductor degeneration--")

    # %%%% bias = 0.6V
    cgs = cfg["device_constants"]["cgs"]
    cd = cfg["device_constants"]["cd"]
    gm = cfg["device_constants"]["gm"]
    rin = cfg["device_constants"]["rin"]
    rin2 = cfg["device_constants"]["rin2"]
    rgate = cfg["device_constants"]["rgate"]  # %240
    ft = cfg["device_constants"]["ft"]
    power_unit = cfg["device_constants"]["power_unit"]
    cload = cfg["device_constants"]["cload"]  # have to figure out

    #Global variable
    drain_q_srf = None
    gate_q_srf = None
    source_q_srf = None


    freq = gen_cfg["design_requirements"]["freq_ghz"]
    nf_req = gen_cfg["design_requirements"]["nf_req_db"]
    gain_req = gen_cfg["design_requirements"]["gain_req_db"]
    bw_req = gen_cfg["design_requirements"]["bw_req_ghz"]
    s11_req = gen_cfg["design_requirements"]["s11_req_db"]
    pwr_req = gen_cfg["design_requirements"]["pwr_req_mw"]

    freq = freq * ghz_to_hz
    bw_req = bw_req * ghz_to_hz
    design_freq = freq / ghz_to_hz

    outputq_req = freq / (bw_req)
    #output_req is the reqired Q of thr DRAIN inductor

    # Direct translations of formulas
    Nmin_nf_bw = (ft / (freq * rin)) * (
        (rgate) / (nf_factor * gm * (numerator_const / ((ft / freq) ** 2 + 1) + 1))
    ) ** 0.5

    soln_nf_bw = np.roots([
        (gm * rin * nf_factor * (numerator_const / ((ft / freq) ** 2 + 1) + 1) + (q_formula_const / outputq_req) * cd * rin * freq) * (freq / ft) ** 2,
        -10 ** (nf_req / 10) + 1 + (q_formula_const / outputq_req) * cload * rin * freq * (freq / ft) ** 2,
        rgate / rin
    ])

    soln_g_nf = np.roots([
        (gm * rin * nf_factor * (numerator_const / ((ft / freq) ** 2 + 1) + 1)) * (freq / ft) ** 2,
        -10 ** (nf_req / 10) + 1 + 10 ** (-gain_req / 10),
        rgate / rin
    ])

    soln_g_bw = (outputq_req / (10 ** (gain_req / 10) * (freq / ft) ** 2 * rin * q_formula_const * freq) - cload) / cd

    outputq_nf_g = 10 ** (gain_req / 10) * (freq / ft) ** 2 * rin * q_formula_const * freq * (Nmin_nf_bw * cd + cload)

    Nmin_nf_bw_100 = (ft / (freq * rin2)) * (
        (rgate) / (nf_factor * gm * (numerator_const / ((ft / freq) ** 2 + 1) + 1) + (q_formula_const / outputq_req) * freq * cd)
    ) ** 0.5

    soln_nf_bw_100 = np.roots([
        (gm * rin2 * nf_factor * (numerator_const / ((ft / freq) ** 2 + 1) + 1) + (q_formula_const / outputq_req) * cd * rin2 * freq) * (freq / ft) ** 2,
        -10 ** (nf_req / 10) + 1 + (q_formula_const / outputq_req) * cload * rin2 * freq * (freq / ft) ** 2,
        rgate / rin2
    ])

    soln_g_nf_100 = np.roots([
        (gm * rin2 * nf_factor * (numerator_const / ((ft / freq) ** 2 + 1) + 1)) * (freq / ft) ** 2,
        -10 ** (nf_req / 10) + 1 + 10 ** (-gain_req / 10),
        rgate / rin2
    ])

    soln_g_bw_100 = (outputq_req / (10 ** (gain_req / 10) * (freq / ft) ** 2 * rin2 * q_formula_const * freq) - cload) / cd

    outputq_nf_g_100 = 10 ** (gain_req / 10) * (freq / ft) ** 2 * rin2 * q_formula_const * freq * (Nmin_nf_bw * cd + cload)

    soln_pwr = math.floor(pwr_req / power_unit)

    # Emulate MATLAB behavior by using only real roots when picking maxima
    rr_g_nf = real_roots_only(soln_g_nf)
    rr_nf_bw = real_roots_only(soln_nf_bw)
    rr_nf_bw_100 = real_roots_only(soln_nf_bw_100)
    rr_g_nf_100 = real_roots_only(soln_g_nf_100)

    N1 = math.ceil(Nmin_nf_bw)
    N2 = math.ceil((N1 + math.ceil(Nmin_nf_bw_100)) / 2.0)
    N3 = math.floor((Nmin_nf_bw + (max(rr_g_nf) if rr_g_nf else N1)) / 2.0)
    N4 = math.floor((Nmin_nf_bw + (max(rr_nf_bw) if rr_nf_bw else N1)) / 2.0)
    N5 = math.floor(max(rr_nf_bw_100)) if rr_nf_bw_100 else N1
    N6 = math.floor(max(rr_g_nf_100)) if rr_g_nf_100 else N1

    sizes = [N1, N2, N3, N4, N5, N6]
    sizes = list(set(sizes))

    output_rows = []
    i = 0

    Z2_vals = np.linspace(
        z2_start,
        z2_stop,
        z2_num
    )         # characteristic impedances (ohms)
    theta2_vals = np.linspace(
        theta2_start,
        theta2_stop,
        theta2_num
    )  # electrical lengths (rad)
    rin_values = range(rin_start, rin_stop, rin_step)
    Z2_grid, theta2_grid = np.meshgrid(Z2_vals, theta2_vals)

    for size in sizes:

        #for rin in range(10, 100, 1):
        for rin in tqdm(rin_values):

            i += 1
            real_in = (rin - rgate / size)

            # degen = roots([...]) with the same coefficients and 6.28 used verbatim
            degen_coeffs = [
                real_in * (freq ** 2) * (size ** 2) * (two_pi_approx ** 2) * (gm ** 2),
                (- two_pi_approx * ft) * degen_mid_const,
                real_in * degen_mid_const
            ]
            degen_roots = np.roots(degen_coeffs)
            # ind_src follows MATLAB: min(abs(real(degen)))*1e12
            if degen_roots.size > 0:
                ind_src = min(abs(np.real(degen_roots))) * h_to_ph * source_ind_scale
            else:
                ind_src = float(0)
            if ind_src > ind_src_opt_threshold:  #TODO
                results_source = my_L_optimizer.optimize_specs_multi_variant(target_specs=[float(ind_src), None, None, None], emx_estimator_model=emx_estimator_rf_model, knn_model=knn_model, knn_train_data=knn_geom_train, four_variants=False)
                ind_src = results_source['variants']['x.1']['pred_spec'][0]
                q_source = results_source['variants']['x.1']['pred_spec'][1]
                source_q_srf = (results_source['variants']['x.1']['pred_spec'][1], results_source['variants']['x.1']['pred_spec'][3])
                source_ind_geom = results_source['variants']['x.1']['geometry']
            else:
                q_source = fallback_q_source
                source_q_srf = (q_source, 0)
                source_ind_geom = [0, 0, 0, 0]

            input_match = ((1 / ((cgs * size) * two_pi_approx * freq)) - (1 - input_match_loss_factor) * 1e-12 * ind_src * two_pi_approx * freq) / (two_pi_approx * freq * 1e-12) #input_match is the inductance value of the GATE inductor
            #Estimating GATE inductor geometry
            results_gate = my_L_optimizer.optimize_specs_multi_variant(target_specs=[float(input_match), None, None, None], emx_estimator_model=emx_estimator_rf_model, knn_model=knn_model, knn_train_data=knn_geom_train, four_variants=False)
            input_match = results_gate['variants']['x.1']['pred_spec'][0]
            gate_q_srf = (results_gate['variants']['x.1']['pred_spec'][1], results_gate['variants']['x.1']['pred_spec'][3])
            gate_ind_geom = results_gate['variants']['x.1']['geometry']

            PeakQf = results_gate['variants']['x.1']['pred_spec'][2]

            if design_freq > PeakQf:
                q_adj = gate_q_srf[0] * (PeakQf / design_freq)
            else:
                q_adj = gate_q_srf[0] * math.sqrt(design_freq / PeakQf)

            # create a new tuple with updated Q and the same SRF
            gate_q_srf = (q_adj, gate_q_srf[1])

            output_match = (1 / ((cd * size + cload) * two_pi_approx * freq)) / (two_pi_approx * freq * 1e-12)   #output_match is the drain INDUCTANCE

            #Estimating DRAIN inductor geometry
            results_drain = my_L_optimizer.optimize_specs_multi_variant(target_specs=[float(output_match), float(outputq_nf_g), None, None], emx_estimator_model=emx_estimator_rf_model, knn_model=knn_model, knn_train_data=knn_geom_train, four_variants=False)

            output_match = results_drain['variants']['x.1']['pred_spec'][0]
            drain_q_srf = (results_drain['variants']['x.1']['pred_spec'][1], results_drain['variants']['x.1']['pred_spec'][3])
            drain_ind_geom = results_drain['variants']['x.1']['geometry']

            PeakQf = results_drain['variants']['x.1']['pred_spec'][2]

            if design_freq > PeakQf:
                q_adj = drain_q_srf[0] * (PeakQf / design_freq)
            else:
                q_adj = drain_q_srf[0] * math.sqrt(design_freq / PeakQf)

            # create a new tuple with updated Q and the same SRF
            drain_q_srf = (q_adj, drain_q_srf[1])

            srf_drain = drain_q_srf[1] #results_gate['variants']['x.1']['pred_spec'][3]   #GATE inductor

            z1 = z1_scale * two_pi_approx * output_match / (z1_divisor * math.tan(srf_angle_numerator / (srf_drain)))
            theta1 = theta1_scale * freq * 1e-9 / srf_drain
            if output_match > output_match_cload_threshold:
                cload_mod = (1 / (two_pi_approx * freq * z1 * math.tan(two_pi_approx * theta1))) - (cd * size)
            else:
                cload_mod = 0
            # call the inductor functions here for srf and geometry and q
            srf_gate = gate_q_srf[1] #results_gate['variants']['x.1']['pred_spec'][3]   #GATE inductor

            z1 = z1_scale * two_pi_approx * input_match / (z1_divisor * math.tan(srf_angle_numerator / (srf_gate)))
            theta1 = theta1_scale * freq * 1e-9 / srf_gate

            zin = rin - 1j * input_match * two_pi_approx * freq * 1e-12
            impedance = z1 * (zin + 1j * z1 * math.tan(theta1 * two_pi_approx)) / (z1 + 1j * zin * math.tan(theta1 * two_pi_approx))

            pad_input = Z2_grid * (impedance + 1j * Z2_grid * np.tan(theta2_grid)) / (Z2_grid + 1j * impedance * np.tan(theta2_grid))
            gamma = gamma_db_scale * np.log10(np.abs((pad_input - s11_numerator_ref) / (pad_input + s11_denominator_ref)))
            valid_mask = (gamma < s11_req) & (np.abs(pad_input.imag) < pad_input_imag_abs_max)
            valid_gammas = gamma[valid_mask]
            valid_Z2s = Z2_grid[valid_mask]
            valid_theta2s = theta2_grid[valid_mask]
            solutions = np.stack((valid_gammas, valid_theta2s / (two_pi_approx * 2), valid_Z2s), axis=1)  #valid_theta2s is beta_l

            optimum_cpwd = None

            if len(solutions) == 0:
                # Preserve flow even if no feasible solution is found
                z2 = float("nan")
                theta2_val = float("nan")
                s11_val = float("nan")
                optimum_cpwd = [float("nan"), float("nan"), float("nan")]

            else:

                sols = solutions #np.array(solutions, dtype=float)
                cpwd_results = my_CPWD_optimizer.predict_CPWD_geometries(cpwd_knn_model, sols[:, 1:])
                idx = np.argmin(cpwd_results[:, 0])
                z2 = sols[idx, 2]
                # MATLAB does theta2 = solutions(idx,3)/6.28 which divides by 6.28 twice
                theta2_val = sols[idx, 1]
                s11_val = sols[idx, 0]
                optimum_cpwd = cpwd_results[idx, :]

            #30 is the Q of the drain inductor
            rd = drain_q_srf[0] * output_match * two_pi_approx * freq * 1e-12  # output q assumed 10
            r_loss_series = (input_match * two_pi_approx * freq * 1e-12) / gate_q_srf[0] + (ind_src * two_pi_approx * freq * 1e-12) / q_source #10 is the GATE q, and 15 is the SOURCE q
            nf = 1 + nf_factor * gm * size * rin * (freq / ft) ** 2 * (numerator_const / ((ft / freq) ** 2 + 1) + 1) \
                + (rd_factor * rin * (freq / ft) ** 2) / (rd) + rgate / (size * rin) + r_loss_series / rin + (cpwd_penalty_prefactor * optimum_cpwd[0] * z2) / rin
            gain = (gain_factor * rd / rin) * (freq / ft) ** -2
            bw = freq / drain_q_srf[0]  # output q assumed 10

            if freq > freq_interstage_threshold_hz:
                series_cap = interstage_series_cap
                shunt_cap_1 = interstage_shunt_cap_1
                rin_2nd = rgate / size - 1j / (cgs * size * two_pi_approx * freq)
                drain_ind_inter = 1e12 / ((np.imag(1 / rin_2nd) + shunt_cap_1 * two_pi_approx * freq + cd * size * two_pi_approx * freq) * two_pi_approx * freq)

                if drain_ind_inter > drain_ind_inter_threshold:
                    results_inter = my_L_optimizer.optimize_specs_multi_variant(target_specs=[float(drain_ind_inter), None, None, None], emx_estimator_model=emx_estimator_rf_model, knn_model=knn_model, knn_train_data=knn_geom_train, four_variants=False)
                    drain_ind_inter_SRF = results_inter['variants']['x.1']['pred_spec'][3]
                    z1 = z1_scale * two_pi_approx * drain_ind_inter / (z1_divisor * math.tan(srf_angle_numerator / (drain_ind_inter_SRF)))
                    theta1 = theta1_scale * freq * 1e-9 / drain_ind_inter_SRF
                    shunt_cap_1 = (1 / (two_pi_approx * freq * z1 * math.tan(two_pi_approx * theta1))) - (cd * size) - (np.imag(1 / rin_2nd) / (two_pi_approx * freq))
                    drain_ind_inter_Q = results_inter['variants']['x.1']['pred_spec'][1]
                else:
                    results_inter = my_L_optimizer.optimize_specs_multi_variant(target_specs=[float(drain_ind_inter), None, None, None], emx_estimator_model=emx_estimator_rf_model, knn_model=knn_model, knn_train_data=knn_geom_train, four_variants=False)
                    drain_ind_inter_SRF = results_inter['variants']['x.1']['pred_spec'][3]
                    drain_ind_inter_Q = results_inter['variants']['x.1']['pred_spec'][1]

            else:

                drain_ind_inter = 0
                drain_ind_inter_Q = 0
                drain_ind_inter_SRF = 0
                shunt_cap_1 = 0

            result = {
                "Option": chr(ord('A') + i - 1),
                "Rin": rin,
                "Size": f"{size}*1um/60nm",
                "NF": 10 * math.log10(nf),
                "Gain": 10 * math.log10(gain),
                "S11": s11_val,
                "BW": bw,
                "Input_TLine_Imp": z2,
                "Input_TLine_Len": theta2_val,
                "Input_L": input_match,
                "Input_L_Q": results_gate['variants']['x.1']['pred_spec'][1],
                "Input_L_SRF": gate_q_srf[1],
                "Input_L_Geom": gate_ind_geom,
                "Output_L": output_match,
                "Output_L_Q": results_drain['variants']['x.1']['pred_spec'][1],
                "Output_L_SRF": drain_q_srf[1],
                "Output_L_Geom": drain_ind_geom,
                "Degen_L": ind_src,
                "Degen_L_Q": source_q_srf[0],
                "Degen_L_SRF": source_q_srf[1],
                "Degen_L_Geom": source_ind_geom,
                "DC_Power": f"{power_unit * size}mW",
                "CPWD_Length": optimum_cpwd[0],
                "CPWD_Width": optimum_cpwd[1],
                "CPWD_Gap": optimum_cpwd[2],
                "CLoad": cload_mod * 1e15,
                "Inter_ind_L": drain_ind_inter,
                "Inter_ind_Q": drain_ind_inter_Q,
                "Inter_ind_SRF": drain_ind_inter_SRF,
                "Inter_cap": shunt_cap_1
            }
            output_rows.append(result)

    table = pd.DataFrame(output_rows, columns=[
        "Option", "Rin", "Size", "NF", "Gain", "S11", "BW",
        "Input_TLine_Imp", "Input_TLine_Len", "Input_L", "Input_L_Q", "Input_L_SRF", "Input_L_Geom", "Output_L", "Output_L_Q", "Output_L_SRF", "Output_L_Geom", "Degen_L", "Degen_L_Q", "Degen_L_SRF", "Degen_L_Geom", "DC_Power", "CPWD_Length", "CPWD_Width", "CPWD_Gap", "CLoad", "Inter_ind_L", "Inter_ind_Q", "Inter_ind_SRF", "Inter_cap"
    ])

    # =============================
    # Multi-objective selection for LNAs
    # Minimize: NF (dB), Power (mW)
    # Maximize: Gain (dB), BW (Hz), and make S11 more negative (dB)
    # Hard penalties for violating provided specs.
    # =============================

    # Parse DC power numeric in mW
    def _pwr_mw(x):
        if isinstance(x, str) and x.endswith("mW"):
            try:
                return float(x[:-2])
            except:
                return np.nan
        return float(x)

    table["_PWR_mW"] = table["DC_Power"].apply(_pwr_mw)
    table["_BW_GHz"] = table["BW"] / ghz_to_hz  # convert to GHz for human scale

    # Targets
    nf_target_max = nf_req           # dB, lower is better, must be <=
    gain_target_min = gain_req       # dB, higher is better, must be >=
    bw_target_min = bw_req           # GHz, higher is better, must be >=
    s11_target_max = s11_req         # dB, more negative is better, must be <= (s11_req is negative)
    pwr_target_max = pwr_req         # mW, lower is better, must be <=

    # Ranges for normalization with epsilon
    eps = scoring_eps
    nf_min, nf_max = float(table["NF"].min()), float(table["NF"].max())
    gn_min, gn_max = float(table["Gain"].min()), float(table["Gain"].max())
    bw_min, bw_max = float(table["_BW_GHz"].min()), float(table["_BW_GHz"].max())
    s11_min, s11_max = float(table["S11"].min()), float(table["S11"].max())  # remember: more negative is better
    pw_min, pw_max = float(table["_PWR_mW"].min()), float(table["_PWR_mW"].max())

    # Weights for tradeoffs among feasible designs
    w_nf = scoring_weights["w_nf"]
    w_gn = scoring_weights["w_gn"]
    w_bw = scoring_weights["w_bw"]
    w_s11 = scoring_weights["w_s11"]
    w_pwr = scoring_weights["w_pwr"]

    # Penalty weights for spec violations (large so infeasible lose)
    pen_nf = scoring_penalties["pen_nf"]
    pen_gn = scoring_penalties["pen_gn"]
    pen_bw = scoring_penalties["pen_bw"]
    pen_s11 = scoring_penalties["pen_s11"]
    pen_pwr = scoring_penalties["pen_pwr"]

    def _norm01(val, vmin, vmax):
        rng = max(vmax - vmin, eps)
        return (val - vmin) / rng

    def _score(row):
        """
        Improved hinge-penalty scoring.
        Lower score is better.
        """

        # Hard spec violations (hinge penalties)
        v_nf = max(0.0, row["NF"] - nf_target_max)   # NF must be <=
        v_gn = max(0.0, gain_target_min - row["Gain"])    # Gain must be >=
        v_bw = max(0.0, bw_target_min - row["_BW_GHz"]) # BW must be >=
        v_s11 = max(0.0, row["S11"] - s11_target_max) # S11 must be <= (target is negative)
        v_pwr = max(0.0, row["_PWR_mW"] - pwr_target_max) # Power must be <=

        # Penalty weights (large but not infinite)
        penalty = (1 * v_nf) + (1 * v_gn) + (1 * v_bw) + (1 * v_s11) + (1 * v_pwr)

        # Preference terms (normalized)
        nf_pref = (row["NF"] - nf_min) / (nf_max - nf_min + 1e-9)
        gn_pref = (row["Gain"] - gn_min) / (gn_max - gn_min + 1e-9)
        bw_pref = (row["_BW_GHz"] - bw_min) / (bw_max - bw_min + 1e-9)
        s11_pref = (abs(row["S11"]) - abs(s11_min)) / (abs(s11_max) - abs(s11_min) + 1e-9)
        pwr_pref = (row["_PWR_mW"] - pw_min) / (pw_max - pw_min + 1e-9)

        # Weighted preference sum (same as before, but normalized)
        pref = (3 * nf_pref) + 0 * (2 * pwr_pref) \
               - (3 * gn_pref) - 0 * (2 * bw_pref) \
               - (1 * s11_pref)

        return penalty + pref

    # =============================
    # Export DataFrame to CSV (with Score column)
    # =============================
    out_csv = args.out_csv
    table.to_csv(out_csv, index=False)
    print(f"\n? Results exported to {out_csv} with Score column")

    table["Score"] = table.apply(_score, axis=1)
    # Best overall design (lowest score)
    best_idx = table["Score"].idxmin()
    best_row = table.loc[best_idx]

    # Also compute a strictly feasible best if any exist
    feasible_mask = (
        (table["NF"] <= nf_target_max) &
        (table["Gain"] >= gain_target_min) &
        (table["_BW_GHz"] >= bw_target_min) &
        (table["S11"] <= s11_target_max) &
        (table["_PWR_mW"] <= pwr_target_max)
    )
    if feasible_mask.any():
        best_feasible = table.sort_values("Score", ascending=True).iloc[0]
    else:
        best_feasible = None

    # =============================
    # Save best design to JSON
    # =============================
    export_best_design_json(best_row, best_feasible, best_idx,
                            nf_target_max, gain_target_min, bw_target_min,
                            s11_target_max, pwr_target_max,
                            out_json=args.out_json)

    # Drop any rows with at least one NaN and report how many were removed
    total_rows = len(table)
    # Drop any rows with at least one NaN before final export
    table = table.dropna(how="any")
    removed_rows = total_rows - len(table)
    print(f"? Filtered out {removed_rows} rows with NaN values out of {total_rows} total rows")

    # =============================
    # Export DataFrame to CSV (with Score column)
    # =============================
    out_csv = args.out_csv
    table.to_csv(out_csv, index=False)
    print(f"\n? Results exported to {out_csv} with Score column")


if __name__ == "__main__":
    print(f"Estimating initial sizes from specs")
    main()
  


