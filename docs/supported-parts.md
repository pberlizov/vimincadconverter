# Supported Geometry Classes

This document describes the geometry classes the current codebase handles well, handles partially, or does not yet target.

## Well supported

### Prismatic stock with through-holes

Examples:

- flat plates
- simple brackets
- spacer-like prismatic parts
- rectangular or polygonal stock with cylindrical cut features

Characteristics:

- dominant opposing planar faces
- one clear extrusion direction
- holes roughly aligned to that extrusion axis, including first-pass support for angled through-hole axes when cylinder inference finds an entry/exit through the top and bottom faces
- mechanical rather than organic surfaces

## Partially supported

### Prismatic parts with simple concave outlines

The pipeline now has first-pass concave boundary reconstruction, but support is still modest.

Current state:

- simple L-like or notched outlines can be preserved
- noisy real meshes are not yet strongly benchmarked for this path

### Noisy triangulated mesh variants of simple hole plates

Current state:

- scan-like mesh regression exists
- artifact matrix covers Gaussian noise, sparse outliers, quantization, and face dropout
- some cases are in a degraded tier where the base extrusion survives but hole recovery does not

### Rotational solids

Current state:

- revolve route exists
- route selection depends on global shape cues plus a strong cylinder primitive
- coverage is still lighter than the prismatic route

## Currently weak or unsupported

### Bosses and pockets

There is no robust verified boss or pocket inference yet.

### Non-parallel or angled hole systems

Current state:

- angled through-holes are now partially supported when the underlying cylinder primitive axis crosses the inferred stock faces and the hole fits the base profile.
- angled countersinks are supported when matched to angled through-holes, with the countersink axis aligned to the hole axis.
- angled blind holes are supported when the cylinder axis is not aligned with the extrusion axis.

### Organic or freeform surfaces

These are intentionally out of scope for the current pipeline.

### Assemblies

The pipeline reasons about single recovered parts, not assembly structure.

### Sheet-metal logic

There is no dedicated bend, flange, or sheet-thickness reasoning path.

## Reading test coverage

The current test corpus proves different confidence tiers:

- strong support: clean synthetic prismatic fixtures
- moderate support: noisy synthetic point clouds and scan-like triangulated meshes
- degraded support: severe quantization and mild face-dropout cases, where base extrusion may still recover while holes are expected to degrade
