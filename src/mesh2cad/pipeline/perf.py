from __future__ import annotations


def effective_sample_count(
    requested: int,
    *,
    face_count: int,
    vertex_count: int,
    auto_tune: bool = True,
) -> int:
    """Clamp sampling to reduce pathological runtime on huge meshes."""
    if not auto_tune:
        return max(100, min(requested, 200_000))

    # Soft budget: more faces -> allow more samples, but cap.
    budget = 4_000 + int(face_count**0.5) * 80
    budget = min(budget, 50_000)
    budget = max(budget, 1_500)

    vertex_budget = 3_000 + vertex_count // 200
    vertex_budget = min(vertex_budget, 50_000)

    cap = int(min(budget, vertex_budget))
    out = max(500, min(requested, cap))
    return min(out, 200_000)


def suggest_simplify_target_faces(face_count: int, *, max_faces: int = 80_000) -> int | None:
    """If the mesh is very large, suggest decimation target; otherwise None."""
    if face_count <= max_faces:
        return None
    return max(20_000, min(max_faces, face_count // 3))
