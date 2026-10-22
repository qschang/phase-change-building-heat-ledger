#!/usr/bin/env python3
"""Fail-closed validation of pytest's machine-readable group report."""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "dynamics": {
        "test_multinode_trajectory_and_outdoor_exchange_match_independent_integration",
        "test_node_renaming_and_permutation_preserve_physical_results",
        "test_disconnected_building_sections_do_not_exchange_heat",
        "test_fully_insulated_network_retains_energy_from_internal_sources",
        "test_thermal_balance_closes_independently_for_each_interval",
        "test_radiation_exchange_uses_kelvin_absolute_temperature",
        "test_phase_transition_crossing_reports_latent_state_not_only_temperature",
    },
    "heat_pump": {
        "test_nominal_operating_point_recovers_rated_cop_and_capacity",
        "test_cold_capacity_derating_and_temperature_lift_change_electricity",
        "test_zero_command_has_no_plant_energy_and_null_interval_cop",
        "test_extreme_cold_capacity_floor_does_not_create_negative_heat",
        "test_watt_seconds_and_seasonal_cop_use_energy_not_mean_interval_cop",
    },
    "state_accounting": {
        "test_output_schema_order_and_node_identity_follow_input",
        "test_zero_forcing_preserves_constitutive_energy_and_phase_fraction",
        "test_node_extrema_include_initial_state_and_each_reported_endpoint",
        "test_splitting_a_constant_operating_interval_preserves_final_state_and_totals",
        "test_summary_energy_fields_equal_interval_sums",
    },
    "invalid_input": {
        *(f"test_invalid_network_or_operating_record_rejects_without_file_side_effects[{i}]" for i in range(14)),
        "test_late_invalid_segment_does_not_publish_valid_prefix",
        "test_daily_horizon_limit_is_applied_to_complete_record",
    },
}


def main(argv):
    detail = {"valid": False, "reason": "invalid verifier invocation"}
    try:
        if len(argv) != 4:
            raise ValueError("expected report path, group, and pytest exit code")
        report, group, pytest_rc = Path(argv[1]), argv[2], int(argv[3])
        if group not in EXPECTED:
            raise ValueError("unknown score group")
        if pytest_rc != 0:
            raise ValueError(f"pytest exited with status {pytest_rc}")
        if not report.is_file() or report.stat().st_size == 0:
            raise ValueError("pytest report missing or empty")
        root = ET.parse(report).getroot()
        cases = root.findall(".//testcase")
        names = [case.attrib.get("name", "") for case in cases]
        expected = EXPECTED[group]
        if len(names) != len(expected) or set(names) != expected:
            raise ValueError("pytest testcase identities/count do not match the score-group manifest")
        if len(set(names)) != len(names):
            raise ValueError("duplicate pytest testcase identity")
        if any(case.find("failure") is not None or case.find("error") is not None or
               case.find("skipped") is not None for case in cases):
            raise ValueError("pytest report contains a failure, error, or skip")
        suites = root.findall(".//testsuite")
        if not suites or any(int(s.attrib.get("tests", "-1")) != len(expected) or
                             int(s.attrib.get("failures", "0")) != 0 or
                             int(s.attrib.get("errors", "0")) != 0 or
                             int(s.attrib.get("skipped", "0")) != 0 for s in suites):
            raise ValueError("pytest suite counters are missing or inconsistent")
        detail = {"valid": True, "group": group, "pytest_exit_code": pytest_rc,
                  "expected_test_count": len(expected), "observed_tests": sorted(names)}
    except Exception as exc:
        detail = {"valid": False, "reason": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(detail, sort_keys=True))
    return 0 if detail["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
