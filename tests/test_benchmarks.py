from __future__ import annotations

import pytest

from mesh2cad.benchmarks.runner import assert_case_expectations, load_cases, run_case


def test_benchmark_catalog_loads():
    cases = load_cases()
    assert len(cases) >= 1
    assert all("name" in case and "generator" in case for case in cases)


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"])
def test_benchmark_cases_meet_expectations(tmp_path, case: dict):
    result = run_case(case, tmp_dir=tmp_path, auto_tune=False)
    assert_case_expectations(case, result)
