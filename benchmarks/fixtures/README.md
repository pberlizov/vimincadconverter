# Real-part style fixtures (pack v2)

Small on-disk meshes and point clouds used by the **benchmark catalog** (`benchmarks/cases.json`) so CI exercises **noisy / non-ideal** inputs without large binaries or LFS.

## Purpose

These fixtures represent real-world scanning scenarios and challenging geometries that test the robustness of the mesh-to-CAD conversion pipeline. They include:

- **Scan noise**: Simulates 3D scanner inaccuracies
- **Missing data**: Represents occluded areas in scans
- **Complex geometries**: Tests feature inference limits
- **Multi-material parts**: Challenges primitive fitting
- **Manufacturing artifacts**: Real production variations

## Fixture Categories

### Basic Mechanical Parts
| File | Description | Test Focus |
|------|-------------|------------|
| `noisy_plate.stl` | 10×6×2 mm plate with Gaussian vertex jitter | Scan noise robustness |
| `bracket_with_holes.stl` | L-bracket with 3 through-holes, light noise | Multi-hole inference |
| `spacer_cylinder.stl` | 15mm spacer with chamfered edges | Rotational part detection |
| `mounting_flange.stl` | Flange with 6 bolt holes, slight warping | Circular pattern detection |

### Complex Geometries
| File | Description | Test Focus |
|------|-------------|------------|
| `tapered_shaft.stl` | Shaft with 15° taper over 50mm length | Tapered revolve inference |
| `gear_blank.stl` | Gear profile before tooth cutting | Complex profile recovery |
| `pump_housing.stl` | Simplified pump housing with internal cavity | Concave feature detection |
| `control_knob.stl` | Knurled control knob with threaded bore | Surface texture handling |

### Challenging Cases
| File | Description | Test Focus |
|------|-------------|------------|
| `partial_scan_plate.stl` | Plate with 30% missing data (scan occlusion) | Incomplete data handling |
| **`noisy_multi_hole_plate.stl`** | Plate with 8 holes, heavy scan noise | Crowded hole detection |
| `thin_wall_bracket.stl` | 1mm thickness bracket with deformation | Thin geometry robustness |
| `corrupted_mesh.stl` | Mesh with some non-manifold edges | Error recovery |

### Point Cloud Examples
| File | Description | Test Focus |
|------|-------------|------------|
| `bearing_cloud.xyz` | Point cloud from laser scanner of bearing | Point cloud processing |
| `complex_assembly.pts` | Multiple parts in single point cloud | Multi-body separation |
| `noisy_surface.csv` | Surface scan with outlier points | Noise filtering |

## Guidelines for Adding Fixtures

### File Requirements
- **Size**: Keep under 100KB for CI efficiency
- **Format**: Prefer STL for meshes, XYZ/PTS for point clouds
- **Quality**: Representative of real scan data, not ideal CAD

### Naming Convention
```
{part_type}_{characteristic}_{variant}.ext

Examples:
- bracket_with_holes_clean.stl
- plate_noisy_heavy.stl
- shaft_tapered_15deg.stl
- assembly_multi_body.pts
```

### Metadata Requirements
Each fixture should include:
1. **Source**: Real scan, synthetic scan, or generated
2. **Scanner type** (if applicable): Laser, structured light, photogrammetry
3. **Noise level**: Light, moderate, heavy
4. **Intended test**: What specific capability this validates
5. **Expected features**: What the pipeline should recover

### Adding New Fixtures

1. **Create fixture file** in this directory
2. **Add metadata** to `fixtures_metadata.json`:
```json
{
  "filename": "new_fixture.stl",
  "description": "Brief description of the part",
  "source": "real_scan|synthetic_scan|cad_generated",
  "scanner_type": "laser|structured_light|photogrammetry|n/a",
  "noise_level": "light|moderate|heavy|none",
  "intended_test": "what this validates",
  "expected_features": ["base_extrude", "through_hole", "boss"],
  "difficulty": "easy|medium|hard",
  "file_size_kb": 45,
  "approximate_bounds": [10.0, 15.0, 5.0]
}
```

3. **Create benchmark case** in `benchmarks/cases.json`:
```json
{
  "name": "new_fixture_test",
  "generator": "fixture_file",
  "fixture": "new_fixture.stl",
  "expected_route_any_of": ["prismatic"],
  "min_feature_kind_counts_by_route": {
    "prismatic": {"base_extrude": 1, "through_hole": 2}
  },
  "build_export": false,
  "expect_warning_substr": ["noise"]
}
```

## Usage in Testing

### Running Specific Fixture Tests
```bash
# Test all fixture-based benchmarks
pytest tests/test_benchmarks.py -k "fixture"

# Test specific fixture
pytest tests/test_benchmarks.py -k "noisy_plate"

# Test by difficulty level
pytest tests/test_benchmarks.py -k "difficulty_hard"
```

### Performance Benchmarking
```bash
# Run with timing information
pytest tests/test_benchmarks.py --durations=10 -k "fixture"

# Generate performance report
python -m pytest tests/test_benchmarks.py --benchmark-only -k "fixture"
```

## Fixture Validation

### Quality Checks
Before adding a fixture, verify:
- [ ] File loads without errors
- [ ] Mesh is manifold (or expected non-manifold)
- [ ] Size is within limits
- [ ] Represents real-world scenario
- [ ] Has appropriate difficulty level

### Automated Validation
```bash
# Validate all fixtures
python scripts/validate_fixtures.py

# Check fixture metadata
python scripts/check_fixture_metadata.py
```

## Contributing

When adding new fixtures:

1. **Start from real data** when possible
2. **Document the source** and characteristics
3. **Test across different configurations** (sample counts, tolerances)
4. **Update documentation** with new fixture information
5. **Consider CI impact** - large files should be avoided

## Future Expansions

Planned additions for v3:
- **Material-specific fixtures**: Metal vs plastic scan characteristics
- **Industry-specific**: Automotive, aerospace, medical device parts
- **Failure cases**: Known challenging geometries for R&D
- **Scale variations**: Very small and very large parts
- **Assembly fixtures**: Multi-part assemblies with mating features

## Troubleshooting

### Common Issues
- **File too large**: Simplify mesh or reduce point density
- **Non-manifold**: Run mesh repair before adding
- **Too simple**: Add more realistic features or noise
- **Too complex**: Simplify while keeping essential characteristics

### Validation Failures
```bash
# Check specific fixture
python -c "
from mesh2cad.mesh.io import load_mesh
mesh = load_mesh('path/to/fixture.stl')
print(f'Vertices: {len(mesh.vertices)}')
print(f'Faces: {len(mesh.faces)}')
print(f'Manifold: {mesh.mesh.is_manifold}')
"
```

This fixture pack serves as the foundation for testing ViminCADConverter's robustness against real-world data quality issues and geometric complexity.
