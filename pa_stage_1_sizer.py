#!/usr/bin/env python3
import argparse
import json
import math
import numpy as np
from PRIMITIVE_OPTIMIZERS import optimize_inductor as my_L_optimizer
import sys

def load_config(config_path):
    with open(config_path, "r") as f:
        return json.load(f)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Python replacement for PA sizing and matching flow using config.json"
    )
    parser.add_argument("--config", required=True, help="Path to config.json")
    parser.add_argument(
        "--out-json",
        default="best_pa_design.json",
        help="Path to output best design JSON file"
    )

    parser.add_argument(
        "--out-csv",
        default="pa_designs.csv",
        help="Path to output all design csv file"
    )

    return parser.parse_args()


def classA_PA(gen_cfg, output_json):
    dataset_path = gen_cfg["datasets"]["spiral_inductor"]
    output_json_path = output_json
    cfg = load_config(gen_cfg["stage_1_config"])
    emx_estimator_rf_model, knn_model, knn_geom_train = my_L_optimizer.setup_all_models(dataset_path)

    print("--Class A PA--")

    # ==== Bias and device parameters ====
    cgs = cfg["cgs"]
    cd = cfg["cd"]
    gm = cfg["gm"]
    rgate = cfg["rgate"]
    rs_fixed = cfg["rs_fixed"]
    power_unit = cfg["power_unit"]
    vdsat = cfg["vdsat"]
    ft = cfg["ft"]

    # ==== User inputs ====
    freq = gen_cfg["design_requirements"]["freq_ghz"] * 1000000000
    psat_req = gen_cfg["design_requirements"]["p_sat_db"]
    gain_req = gen_cfg["design_requirements"]["gain_req_db"]
    print(freq, psat_req, gain_req)
    em_l_border = cfg["em_l_border"]

    # ==== Fixed constants moved to config ====
    stage_gain_factor = cfg["stage_gain_factor"]
    size_last_coeff = cfg["size_last_coeff"]
    size_last_round_base = cfg["size_last_round_base"]
    size_last_search_start = cfg["size_last_search_start"]
    size_last_search_stop = cfg["size_last_search_stop"]
    size_last_search_step = cfg["size_last_search_step"]
    error_threshold = cfg["error_threshold"]

    load_cap_offset = cfg["load_cap_offset"]
    omega_approx = cfg["omega_approx"]
    drain_res_base = cfg["drain_res_base"]
    check_target_real = cfg["check_target_real"]

    size_last_vdsat_override = cfg["size_last_vdsat_override"]
    z1_coeff = cfg["z1_coeff"]
    tan_numerator = cfg["tan_numerator"]
    theta1_coeff = cfg["theta1_coeff"]
    default_cap_mod = cfg["default_cap_mod"]
    default_cload_mod = cfg["default_cload_mod"]
    matching0_col1_value = cfg["matching0_col1_value"]
    shunt_ind2_scale = cfg["shunt_ind2_scale"]
    optimizer_four_variants = cfg["optimizer_four_variants"]

    # ==== Stage calculation ====
    stages = int(np.ceil(gain_req / (10 * np.log10(stage_gain_factor * (ft / freq) ** 2))))
    print(f"Calculated stages: {stages}")

    # ==== Estimate size_last by minimizing error (matches MATLAB flow) ====
    size_last = size_last_round_base * round(size_last_coeff * 10 ** (psat_req / 10) / size_last_round_base)

    if stages > 1:
        stage_step = (size_last / 8) ** (1 / (stages - 1))
        if stage_step > 2:
            stage_step = 2
    else:
        stage_step = 1

    for n in range(size_last_search_start, size_last_search_stop + 1, size_last_search_step):
        ssum = 0.0
        for i_mat in range(1, stages + 1):
            term_inner = (
                (1.0 / stage_step)
                * (ft / freq) ** 2
                * (1250 * vdsat)
                * (1.0 / (rgate + 6.0 * n * (stage_step ** (1 - i_mat))))
            )
            term = (0.1 * n * (term_inner ** (i_mat - 1))) ** -1
            ssum += term

        error = (psat_req - 10.0 * np.log10(1.0 / (ssum))) ** 2
        if error < error_threshold:
            size_last = n

    print(f"Final size_last: {size_last}")

    # ==== Check ====
    check_factor = -1
    while check_factor <= 0:
        load_imag = (cd * size_last + load_cap_offset) * freq * omega_approx
        z_load = 1.0 / (size_last / (drain_res_base * vdsat) + 1j * load_imag)
        check_factor = np.imag(z_load) ** 2 + np.real(z_load) ** 2 - check_target_real * np.real(z_load)
        if check_factor <= 0:
            size_last -= size_last_search_step
        else:
            break

    # ==== Determine stage sizes (MATLAB indexing preserved) ====
    sizes = np.zeros(stages)
    for i_mat in range(1, stages + 1):
        if i_mat == 1:
            sizes[0] = size_last
        else:
            sizes[i_mat - 1] = size_last_round_base * round(sizes[i_mat - 2] * 0.5 / stage_step)

    print(f"Stage sizes: {sizes}")

    # ==== Matching network calculation with MATLABs decreasing index trick ====
    matching = np.zeros((stages + 1, 4))
    size_prev = None

    i = stages
    for size in sizes:
        if size == size_last:
            load_imag = (cd * size + load_cap_offset) * freq * omega_approx
            z_load = 1.0 / (size / (drain_res_base * size_last_vdsat_override) + 1j * load_imag)

            shunt_final = 1.0 / (
                omega_approx * freq
                * (
                    -np.imag(z_load)
                    + (np.real(z_load) / check_target_real) ** 0.5
                    * (
                        np.imag(z_load) ** 2
                        + np.real(z_load) ** 2
                        - check_target_real * np.real(z_load)
                    ) ** 0.5
                )
                / (abs(z_load) ** 2)
            )

            series_final = -1.0 / (
                (
                    (-(shunt_final * freq * omega_approx))
                    + np.imag(z_load) * check_target_real / np.real(z_load)
                    + check_target_real * (shunt_final * freq * omega_approx) / np.real(z_load)
                )
                * omega_approx
                * freq
            )

            matching[i, 0] = shunt_final * 1e12
            matching[i, 1] = series_final * 1e15

            if float(matching[i, 0]) > em_l_border:
                results_drain = my_L_optimizer.optimize_specs_multi_variant(
                    target_specs=[float(matching[i, 0]), None, None, None],
                    emx_estimator_model=emx_estimator_rf_model,
                    knn_model=knn_model,
                    knn_train_data=knn_geom_train,
                    four_variants=optimizer_four_variants,
                )
                srf_drain = results_drain["variants"]["x.1"]["pred_spec"][3]
                print(f"SRF of inductor {float(matching[i, 0])} is {srf_drain}")
                z1 = z1_coeff * omega_approx * matching[i, 0] / (1000 * math.tan(tan_numerator / srf_drain))
                theta1 = theta1_coeff * freq * 1e-9 / srf_drain
                z_load = 1 / (
                    size / (drain_res_base * vdsat)
                    + 1j * (cd * size) * omega_approx * freq
                    - 1j / (z1 * math.tan(omega_approx * theta1))
                )
                cap_mod = -1e15 * (
                    (
                        -np.imag(z_load)
                        + (np.real(z_load) / check_target_real) ** 0.5
                        * (
                            np.imag(z_load) ** 2
                            + np.real(z_load) ** 2
                            - check_target_real * np.real(z_load)
                        ) ** 0.5
                    )
                    / (abs(z_load) ** 2)
                ) / (omega_approx * freq)
            else:
                cap_mod = default_cap_mod

            matching[i, 3] = cap_mod

        else:
            load_imag = (cd * size + load_cap_offset) * freq * omega_approx
            z_load = 1.0 / (size / (drain_res_base * vdsat) + 1j * load_imag)

            source_imag = -1.0 / (cgs * size_prev * omega_approx * freq)
            source_real = rgate / size_prev + rs_fixed
            z_source = source_real + 1j * source_imag
            source_shunt = 1 / np.real(1 / z_source)
            load_shunt = drain_res_base * vdsat / size

            if source_shunt < load_shunt:
                matching[i, 2] = 1e12 / (np.imag(1 / z_source) * omega_approx * freq)

                shunt_element = 1.0 / (
                    omega_approx * freq
                    * (
                        -np.imag(z_load)
                        + ((np.real(z_load) / source_shunt) ** 0.5)
                        * (
                            np.imag(z_load) ** 2
                            + np.real(z_load) ** 2
                            - source_shunt * np.real(z_load)
                        ) ** 0.5
                    )
                    / (abs(z_load) ** 2)
                )

                series_element = -1.0 / (
                    (
                        (-(shunt_element * freq * omega_approx))
                        + np.imag(z_load) * source_shunt / np.real(z_load)
                        + source_shunt * (shunt_element * freq * omega_approx) / np.real(z_load)
                    )
                    * omega_approx
                    * freq
                )

                matching[i, 0] = shunt_element * 1e12
                matching[i, 1] = series_element * 1e15

                if float(matching[i, 0]) > em_l_border:
                    results_drain = my_L_optimizer.optimize_specs_multi_variant(
                        target_specs=[float(matching[i, 0]), None, None, None],
                        emx_estimator_model=emx_estimator_rf_model,
                        knn_model=knn_model,
                        knn_train_data=knn_geom_train,
                        four_variants=optimizer_four_variants,
                    )
                    srf_drain = results_drain["variants"]["x.1"]["pred_spec"][3]
                    print(f"SRF of inductor {float(matching[i, 0])} is {srf_drain}")
                    z1 = z1_coeff * omega_approx * matching[i, 0] / (1000 * math.tan(tan_numerator / srf_drain))
                    theta1 = theta1_coeff * freq * 1e-9 / srf_drain
                    z_load = 1 / (
                        size / (drain_res_base * vdsat)
                        + 1j * (cd * size) * omega_approx * freq
                        - 1j / (z1 * math.tan(omega_approx * theta1))
                    )
                    cap_mod = -1e15 * (
                        (
                            -np.imag(z_load)
                            + (np.real(z_load) / source_shunt) ** 0.5
                            * (
                                np.imag(z_load) ** 2
                                + np.real(z_load) ** 2
                                - source_shunt * np.real(z_load)
                            ) ** 0.5
                        )
                        / (abs(z_load) ** 2)
                    ) / (omega_approx * freq)
                else:
                    cap_mod = default_cap_mod

                matching[i, 3] = cap_mod

            else:
                matching[i, 0] = 1e12 / ((cd * size + load_cap_offset) * (omega_approx * freq) ** 2)

                if float(matching[i, 0]) > em_l_border:
                    results_drain = my_L_optimizer.optimize_specs_multi_variant(
                        target_specs=[float(matching[i, 0]), None, None, None],
                        emx_estimator_model=emx_estimator_rf_model,
                        knn_model=knn_model,
                        knn_train_data=knn_geom_train,
                        four_variants=optimizer_four_variants,
                    )
                    srf_drain = results_drain["variants"]["x.1"]["pred_spec"][3]
                    print(f"SRF of inductor {float(matching[i, 0])} is {srf_drain}")
                    z1 = z1_coeff * omega_approx * matching[i, 0] / (1000 * math.tan(tan_numerator / srf_drain))
                    theta1 = theta1_coeff * freq * 1e-9 / srf_drain
                    cload_mod = ((1 / (omega_approx * freq * z1 * math.tan(omega_approx * theta1))) * 1e15) - cd * size * 1e15
                else:
                    cload_mod = default_cload_mod

                shunt_element = 1.0 / (
                    omega_approx * freq
                    * (
                        -np.imag(z_source)
                        + (np.real(z_source) / load_shunt) ** 0.5
                        * (
                            np.imag(z_source) ** 2
                            + np.real(z_source) ** 2
                            - load_shunt * np.real(z_source)
                        ) ** 0.5
                    )
                    / (abs(z_source) ** 2)
                )

                series_element = -1.0 / (
                    (
                        (-(shunt_element * freq * omega_approx))
                        + np.imag(z_source) * load_shunt / np.real(z_source)
                        + load_shunt * (shunt_element * freq * omega_approx) / np.real(z_source)
                    )
                    * omega_approx
                    * freq
                )

                matching[i, 2] = shunt_element * 1e12
                matching[i, 1] = series_element * 1e15
                matching[i, 3] = cload_mod

        if i == 1:
            source_imag = -1.0 / (cgs * size * omega_approx * freq)
            source_real = rgate / size + rs_fixed
            z_first = source_real + 1j * source_imag
            matching[0, 0] = 1 / np.real(1 / z_first)
            matching[0, 1] = matching0_col1_value
            matching[0, 2] = 1e12 / (np.imag(1 / z_first) * omega_approx * freq)

        i -= 1
        size_prev = size

    print("\nMatching matrix [pF / fF / etc.]:")
    print(matching)

    stage_size_entries = {
        f"Stage_{idx + 1}_Size": f"{int(round(size))}*1um/60nm"
        for idx, size in enumerate(sizes[::-1])
    }

    matching_entries = {}
    for idx, row in enumerate(matching):
        matching_entries[f"Matching_Stage_{idx}_Shunt_Ind_1_pH"] = float(row[0])

        series_cap_F = float(row[1]) * 1e-15
        shunt_cap_F  = float(row[3]) * 1e-15

        matching_entries[f"Matching_Stage_{idx}_Series_Cap"] = f"{series_cap_F:.18e}"
        matching_entries[f"Matching_Stage_{idx}_Shunt_Ind_2_pH"] = float(row[2]) * shunt_ind2_scale
        matching_entries[f"Matching_Stage_{idx}_Shunt_Cap"] = f"{shunt_cap_F:.18e}"

    export_data = {
        "Best_ClassA_PA_Design": {
            "Spec_Targets": {
                "freq_Hz": float(freq),
                "psat_req_dBm": float(psat_req),
                "gain_req_dB": float(gain_req),
            },
            "Design_Parameters": {
                "Design_ID": "_",
                "Stages": int(stages),
                "Size_Last": float(size_last),
                "Stage_Step": float(stage_step),
                "gm": float(gm),
                "Power_Unit_mW": float(power_unit),
                **stage_size_entries,
                **matching_entries,
            },
        }
    }

    with open(output_json_path, "w") as f:
        json.dump(export_data, f, indent=4)

    print(f"\nExported results {output_json_path}")


def main():
    args = parse_args()
    cfg = load_config(args.config)
    print("Estimating Class A PA design from config")
    classA_PA(cfg, args.out_json)


if __name__ == "__main__":
    main()
