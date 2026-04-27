from __future__ import annotations

import importlib.util

import pytest

from mesh2cad.benchmarks.runner import assert_case_expectations, load_cases, run_case


def test_benchmark_catalog_loads():
    cases = load_cases()
    assert len(cases) >= 1
    assert all("name" in case and "generator" in case for case in cases)


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"])
def test_benchmark_cases_meet_expectations(tmp_path, case: dict):
    if case.get("build_export") and importlib.util.find_spec("build123d") is None:
        pytest.skip("Catalog case with build_export requires build123d")
    result = run_case(case, tmp_dir=tmp_path, auto_tune=False)
    assert_case_expectations(case, result)
