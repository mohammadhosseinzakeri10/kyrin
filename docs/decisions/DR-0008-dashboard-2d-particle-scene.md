# DR-0008: Dashboard uses the 2D particle scene; the 3D option was removed

- **Status:** Accepted. Supersedes an interactive 3D option.
- **Area:** Qt interface.

## Problem

An interactive 3D version of the logo scene was evaluated next to the 2D
particle scene. Prototypes either layered copies of the 2D artwork or changed
the logo silhouette, and a single image could not determine the hidden shape to
the required standard.

## Decision

Keep the approved **2D particle scene** with CPU and GPU renderers sharing the
same particle data and animation cycle. Remove all 3D geometry, interaction and
preference UI. A saved legacy 3D renderer preference is read as the GPU
renderer so locale and animation settings survive
([`translations.py`](../../src/kyrin/app/qt/translations.py)). Additional
GPU renderer levels have since been added within 2D.

## Alternatives considered

- *Ship an approximate 3D model:* rejected for visual fidelity.

## Consequences and limits

- Performance on other drivers and weaker systems is unmeasured.
- The recorded reason is fidelity to the approved logo.

## References

[Visual status](../desktop/VISUAL_STATUS.md)
