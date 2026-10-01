# KYRIN visual identity

KYRIN is the project name. Kailarin is the parent brand. All public copy is in English.

## Artwork

- `hero-still.webp`: the still banner with the Kailarin endorsement.
- `hero-animated.svg`: a self-contained version with moving orbital light, a slow energy pulse, and subtle stars. It contains the still artwork and requires no scripts, external fonts, trackers, or image services.
- `horizons.svg`: the three planned product directions, with English text alternatives in the project README.

The hero is concept artwork, not a screenshot of working product functionality. The still image was created with the built-in image-generation tool and compressed to WebP. The SVG motion layer is authored separately and does not rotate the rendered sphere itself.

The original image brief was a panoramic deep-space banner with a graphite and titanium intelligence core, ice-blue orbital lighting, restrained violet nebulae, the exact title `KYRIN`, and the subtitle `OPEN-SOURCE AI DESKTOP AGENT`. The final edit preserved that composition and added the exact parent-brand signature `by Kailarin` beneath the subtitle.

## Rebuild

From the repository root:

```sh
python3 tools/brand/build_banner.py
```

Only the Python standard library is required. Edit the motion and lighting in that script, then rebuild the SVG. Keep typography in the still artwork unchanged unless intentionally revising the identity.

## Accessibility

The README selects the still artwork when the browser requests reduced motion. The SVG also disables its own animation for that preference. A direct still-artwork link remains available in the README footer.

The dark background is part of the artwork, so it remains legible in both light and dark GitHub themes. Essential project information is also available as normal text below the banner.
