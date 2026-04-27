from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from mesh2cad.domain.types import PartClass
from mesh2cad.mesh.sampling import SampledCloud


@dataclass(slots=True)
class SceneAnalysis:
    principal_axes: NDArray[np.float64]
    dominant_plane_normals: list[NDArray[np.float64]]
    symmetry_planes: list[dict[str, NDArray[np.float64]]]
    part_class: PartClass


def analyze_scene(cloud: SampledCloud) -> SceneAnalysis:
    """Extract coarse global structure cues from sampled points and normals."""
    centered = cloud.points - cloud.points.mean(axis=0, keepdims=True)
    covariance = np.cov(centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    principal_axes = eigenvectors[:, order]

    dominant_plane_normals: list[NDArray[np.float64]] = []
    if cloud.normals is not None and len(cloud.normals) > 0:
        rounded = np.round(cloud.normals, decimals=2)
        unique_normals, counts = np.unique(rounded, axis=0, return_counts=True)
        top_indices = np.argsort(counts)[::-1][:3]
        dominant_plane_normals = [
            unique_normals[index] / np.linalg.norm(unique_normals[index])
            for index in top_indices
            if np.linalg.norm(unique_normals[index]) > 0
        ]

    extents = centered.max(axis=0) - centered.min(axis=0)
    sorted_extents = np.sort(extents)[::-1]
    ex0 = float(sorted_extents[0])
    ex1 = float(sorted_extents[1]) if len(sorted_extents) > 1 else 0.0
    ex2 = float(sorted_extents[2]) if len(sorted_extents) > 2 else 0.0

    part_class = PartClass.UNKNOWN
    if ex0 > 1e-12:
        thin_plate = ex1 > 0.0 and (ex2 / ex1) < 0.15
        one_short_dim = (ex2 / ex0) < 0.35
        if thin_plate or one_short_dim:
            part_class = PartClass.PRISMATIC
        elif ex1 > 0.0 and (ex1 / ex0) < 0.55 and (ex2 / ex0) < 0.55 and (ex1 / ex0) > 0.08:
            part_class = PartClass.ROTATIONAL

    symmetry_planes = [
        {
            "origin": cloud.points.mean(axis=0),
            "normal": principal_axes[:, idx],
        }
        for idx in range(principal_axes.shape[1])
    ]

    return SceneAnalysis(
        principal_axes=principal_axes,
        dominant_plane_normals=dominant_plane_normals,
        symmetry_planes=symmetry_planes,
        part_class=part_class,
    )
