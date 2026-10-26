# Kailarin mark — working brand kit

Status: the owner selected the luminous raster concept for the current application logo. The vector studies below remain optional and are not the selected mark.

## Core idea

The mark combines a readable `K` silhouette with a black-hole center and one orbital ring. Its left arc carries electric cyan; the two right arms carry violet. The black-hole opening and the ring remain visible in small sizes.

The selected cinematic raster concept is `kailarin-minimal-k-logo-v3.jpg`. Its padded, circle-safe export is `kailarin-v3-profile-safe.jpg`; a 512 px PNG export now occupies `src/kyrin/app/qt/assets/kyrin-logo.png`. The vector files here are a simplified alternative that was explored but not selected. They are not an automatic or pixel-perfect trace of the raster concept.

## Files

| File | Intended use |
| --- | --- |
| `kailarin-minimal-k-logo-v3.jpg` | Selected luminous artwork |
| `kailarin-v3-profile-safe.jpg` | Selected artwork with safe margins for a circular profile crop |
| `kailarin-mark.svg` | Transparent master mark for scalable layouts |
| `kailarin-avatar-dark.svg` | Circular-crop-safe mark on midnight navy |
| `kailarin-avatar-dark.png` | Upload-ready raster export of the dark avatar |
| `kailarin-avatar-light.svg` | Mark on a light surface |
| `kailarin-avatar-light.png` | Raster export of the light avatar |
| `kailarin-mark-mono-dark.svg` | One-color mark on light surfaces |
| `kailarin-mark-mono-light.svg` | One-color mark on dark surfaces |
| `generate_kailarin_logo.py` | Dependency-free source for the vector variants |

## Color and spacing

- Midnight background: `#050B1B`.
- Electric cyan accent: `#05E6F1`.
- Electric violet accent: `#ED53E9`.
- Keep a clear area of at least 10% of the canvas width around the mark.
- Use the avatar files where a platform crops the image into a circle; their mark is scaled inward to protect the tips.
- Use the compact avatar at 48 px and above. Below that, consider a still simpler one-color mark after visual review.
- Avoid stars, dense nebula textures, extra rings, and strong bloom in icon-sized uses.

## Current checks

- Rendered both avatar variants at 1254 × 1254 px.
- Inspected the dark avatar after reduction to 48 × 48 px.
- Verified that the avatar exports are each below 1 MB.
- The application asset has been replaced with the selected luminous logo. The circle-safe export was uploaded as the GitHub profile picture for `mohammadhosseinzakeri10`; GitHub confirmed the update.

Regenerate the SVG files with `python3 assets/brand/generate_kailarin_logo.py` from the repository root. The PNG exports can be rendered from their matching SVG files with FFmpeg's `librsvg` decoder.
