#!/bin/bash
set -euo pipefail

SECONDS=0
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

CONFIG="config.json"

step_names=()
step_times=()
step_logs=()

current_step=""
current_log=""

format_time() {
    local total_seconds="$1"
    local hours=$((total_seconds / 3600))
    local minutes=$(((total_seconds % 3600) / 60))
    local seconds=$((total_seconds % 60))
    printf "%02d:%02d:%02d" "$hours" "$minutes" "$seconds"
}

usage() {
    echo "Usage:"
    echo "  ./composer.sh"
    echo "  ./composer.sh <config.json>"
    echo "  ./composer.sh <step>"
    echo "  ./composer.sh <config.json> <step>"
    echo "  ./composer.sh only <step>"
    echo "  ./composer.sh <config.json> only <step>"
    echo
    echo "Available steps:"
    echo "  sizing"
    echo "  parse"
    echo "  placement"
    echo "  routing_inputs"
    echo "  routing"
    echo
    echo "Examples:"
    echo "  ./composer.sh"
    echo "  ./composer.sh config.json"
    echo "  ./composer.sh placement"
    echo "  ./composer.sh config.json placement"
    echo "  ./composer.sh only routing"
    echo "  ./composer.sh config.json only routing"
    exit 1
}

normalize_step() {
    local step="$1"
    case "$step" in
        sizing|initial|initial_sizing|perform_initial_sizing)
            echo "sizing"
            ;;
        parse|netlist|parse_netlist)
            echo "parse"
            ;;
        placement|place|perform_placement)
            echo "placement"
            ;;
        routing_inputs|route_inputs|generate_routing_inputs)
            echo "routing_inputs"
            ;;
        routing|route|perform_routing)
            echo "routing"
            ;;
        *)
            return 1
            ;;
    esac
}

step_index() {
    local step="$1"
    case "$step" in
        sizing) echo 0 ;;
        parse) echo 1 ;;
        placement) echo 2 ;;
        routing_inputs) echo 3 ;;
        routing) echo 4 ;;
        *) return 1 ;;
    esac
}

on_error() {
    local exit_code=$?
    echo
    echo "=================================================="
    echo "ERROR: Step failed -> $current_step"
    echo "Log file: $current_log"
    echo "Elapsed time before failure: $(format_time "$SECONDS")"
    echo "=================================================="
    exit "$exit_code"
}

trap on_error ERR

run_step() {
    local step_name="$1"
    shift

    local log_file="$LOG_DIR/${step_name}.log"
    local start_time=$SECONDS

    current_step="$step_name"
    current_log="$log_file"

    echo "=================================================="
    echo "Starting: $step_name"
    echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Config    : $CONFIG"
    echo "Log file  : $log_file"
    echo "=================================================="

    "$@" > "$log_file" 2>&1

    local elapsed=$((SECONDS - start_time))

    step_names+=("$step_name")
    step_times+=("$elapsed")
    step_logs+=("$log_file")

    echo "Finished: $step_name"
    echo "Duration: $(format_time "$elapsed")"
    echo "Log file: $log_file"
    echo

    current_step=""
    current_log=""
}

run_selected_step() {
    local step="$1"
    case "$step" in
        sizing)
            run_step "perform_initial_sizing" \
                python3 perform_initial_sizing.py --config "$CONFIG"
            ;;
        parse)
            run_step "parse_netlist" \
                python3 parse_netlist.py --config "$CONFIG"
            ;;
        placement)
            run_step "perform_placement" \
                python3 perform_placement.py --config "$CONFIG"
            ;;
        routing_inputs)
            run_step "generate_routing_inputs" \
                python3 generate_routing_inputs.py --config "$CONFIG"
            ;;
        routing)
            local config_dir
            local pdn_config
            config_dir=1000 1000 1428 11457 15072 15075 15078 15080 77930 416806 531052 531210 531555 587763 1057471 1524748 1657909 2250686 38693426 43551672 59626750 79559656 96653542 118763438 162302374 451107875 483001641 512194978 582172737 588876012 816048422 853562094 867857153 901489026 933993915 994288581 1000179966 1055030236 1130212420 1138336024 1156764875 1212420267 1315188223 1806512976 1808947410 1853926220 1864340183 1962015000 2021385396 2033742384 2079082141dirname "")
            pdn_config="/config_pdn.json"

            if [ -f "" ]; then
                run_step "perform_routing_with_pdn" \
                    python3 perform_routing_with_pdn.py --config ""
            else
                run_step "perform_routing" \
                    python3 perform_routing.py --config ""
            fi
            ;;
        *)
            echo "Unknown step: $step"
            usage
            ;;
    esac
}

MODE="all"
TARGET_STEP=""

if [ "$#" -eq 0 ]; then
    MODE="all"

elif [ "$#" -eq 1 ]; then
    if [[ "$1" == *.json ]]; then
        CONFIG="$1"
        MODE="all"
    else
        TARGET_STEP=$(normalize_step "$1") || usage
        MODE="from"
    fi

elif [ "$#" -eq 2 ]; then
    if [[ "$1" == *.json ]]; then
        CONFIG="$1"
        TARGET_STEP=$(normalize_step "$2") || usage
        MODE="from"
    elif [ "$1" = "only" ]; then
        TARGET_STEP=$(normalize_step "$2") || usage
        MODE="only"
    else
        usage
    fi

elif [ "$#" -eq 3 ]; then
    if [[ "$1" != *.json ]]; then
        usage
    fi
    CONFIG="$1"
    if [ "$2" != "only" ]; then
        usage
    fi
    TARGET_STEP=$(normalize_step "$3") || usage
    MODE="only"

else
    usage
fi

echo "=================================================="
echo "Flow execution mode: $MODE"
echo "Config file        : $CONFIG"
if [ -n "$TARGET_STEP" ]; then
    echo "Target step        : $TARGET_STEP"
fi
echo "=================================================="
echo

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: Config file not found: $CONFIG"
    exit 1
fi

if [ "$MODE" = "all" ]; then
    run_selected_step "sizing"
    run_selected_step "parse"
    run_selected_step "placement"
    run_selected_step "routing_inputs"
    run_selected_step "routing"

elif [ "$MODE" = "from" ]; then
    start_idx=$(step_index "$TARGET_STEP")

    for idx in 0 1 2 3 4; do
        if [ "$idx" -lt "$start_idx" ]; then
            continue
        fi

        case "$idx" in
            0) run_selected_step "sizing" ;;
            1) run_selected_step "parse" ;;
            2) run_selected_step "placement" ;;
            3) run_selected_step "routing_inputs" ;;
            4) run_selected_step "routing" ;;
        esac
    done

elif [ "$MODE" = "only" ]; then
    run_selected_step "$TARGET_STEP"
fi

echo "=================================================="
echo "FULL RUN SUMMARY"
echo "=================================================="
printf "%-28s %-12s %s\n" "Process" "Time" "Log file"
printf "%-28s %-12s %s\n" "----------------------------" "------------" "------------------------------"

for ((i=0; i<${#step_names[@]}; i++)); do
    printf "%-28s %-12s %s\n" \
        "${step_names[$i]}" \
        "$(format_time "${step_times[$i]}")" \
        "${step_logs[$i]}"
done

echo
echo "Total runtime: $(format_time "$SECONDS")"
echo "Completed at : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=================================================="
