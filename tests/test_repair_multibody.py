"""Multi-body repair: select N-th largest surface component."""

from __future__ import annotations

from pathlib import Path

import trimesh

from mesh2cad.mesh.cleanup import repair_mesh
from mesh2cad.mesh.geometry_input import load_geometry
from mesh2cad.pipeline.orchestrator import run_pipeline


def test_repair_mesh_selects_nth_largest_component(tmp_path) -> None:
    large = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    small = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    small.apply_translation([20.0, 0.0, 0.0])
    combo = trimesh.util.concatenate([large, small])
    combo.merge_vertices()
    path = tmp_path / "two.stl"
    combo.export(path)

    loaded = load_geometry(path)
    assert loaded.mesh is not None
    md0 = repair_mesh(loaded, component_index=0)
    md1 = repair_mesh(loaded, component_index=1)
    assert md0.mesh.volume > md1.mesh.volume * 2.0


def test_run_pipeline_respects_repair_component_index(tmp_path) -> None:
    large = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    small = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    small.apply_translation([25.0, 0.0, 0.0])
    combo = trimesh.util.concatenate([large, small])
    combo.merge_vertices()
    path = tmp_path / "pair.stl"
    combo.export(path)

    r0 = run_pipeline(path, output_dir=None, sample_count=800, auto_tune_sampling=False, repair_component_index=0)
    r1 = run_pipeline(path, output_dir=None, sample_count=800, auto_tune_sampling=False, repair_component_index=1)
    assert r0.debug["primitive_support_counts"] != r1.debug["primitive_support_counts"]


def test_run_pipeline_warns_when_input_has_multiple_bodies(tmp_path) -> None:
    large = trimesh.creation.box(extents=(4.0, 4.0, 1.0))
    small = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    small.apply_translation([12.0, 0.0, 0.0])
    combo = trimesh.util.concatenate([large, small])
    combo.merge_vertices()
    path = tmp_path / "multi.stl"
    combo.export(path)

    result = run_pipeline(path, output_dir=None, sample_count=600, auto_tune_sampling=False)
    assert any("disconnected components" in w for w in result.warnings)
    assert any("largest surface-area body" in w for w in result.warnings)
