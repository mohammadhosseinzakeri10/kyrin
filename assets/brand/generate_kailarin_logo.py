"""Generate standalone vector variants of the Kailarin black-hole K mark.

The original raster artwork remains the reference for large, cinematic uses.
This deliberately simpler companion is for small icons and consistent branding.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
VIEWBOX = "0 0 1254 1254"

LEFT = (
    "M 733 161 "
    "C 435 195 230 352 188 573 "
    "C 140 825 283 1028 777 1076 "
    "C 446 1046 282 917 271 730 "
    "C 257 499 416 254 733 161 Z"
)
UPPER = (
    "M 620 480 "
    "C 777 357 961 238 1142 198 "
    "C 996 326 902 440 821 558 "
    "C 762 522 697 494 620 480 Z"
)
LOWER = (
    "M 812 710 "
    "C 905 835 1016 989 1139 1070 "
    "C 965 1033 790 931 619 810 "
    "C 699 796 768 756 812 710 Z"
)
FRONT_RING = (
    "M 175 763 "
    "C 319 799 694 758 1055 555"
)


def svg_document(body: str, definitions: str = "") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1254" height="1254" '
        f'viewBox="{VIEWBOX}" role="img" '
        'aria-label="Kailarin black-hole K logo">\n'
        f"<defs>{definitions}</defs>\n{body}\n</svg>\n"
    )


def color_mark(light: bool = False, compact: bool = False) -> tuple[str, str]:
    cyan_outer = "#008dbc" if light else "#05e6f1"
    cyan_inner = "#073baf" if light else ("#136fdb" if compact else "#064bd2")
    violet_outer = "#9e24b7" if light else "#ed53e9"
    violet_inner = "#4b1fa8" if light else ("#4b22a8" if compact else "#2a146f")
    edge = "#075d91" if light else "#b4faff"
    hole = "#071425" if light else "#02050e"
    glow_opacity = "0.12" if light else "0.35"
    back_width = 22 if compact else 13
    horizon_width = 22 if compact else 8
    front_width = 38 if compact else 21
    highlight_width = 4 if compact else 3

    definitions = f"""
  <linearGradient id="cyan" x1="150" y1="600" x2="540" y2="650" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{cyan_outer}"/>
    <stop offset="0.44" stop-color="{cyan_inner}"/>
    <stop offset="1" stop-color="#071b68"/>
  </linearGradient>
  <linearGradient id="upper" x1="615" y1="530" x2="1050" y2="245" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{violet_inner}"/>
    <stop offset="0.68" stop-color="#5422c6"/>
    <stop offset="1" stop-color="{violet_outer}"/>
  </linearGradient>
  <linearGradient id="lower" x1="620" y1="800" x2="1110" y2="1050" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{violet_inner}"/>
    <stop offset="0.68" stop-color="#5720c4"/>
    <stop offset="1" stop-color="{violet_outer}"/>
  </linearGradient>
  <linearGradient id="orbit" x1="170" y1="790" x2="1080" y2="540" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{cyan_outer}"/>
    <stop offset="0.47" stop-color="#368cf9"/>
    <stop offset="1" stop-color="{violet_outer}"/>
  </linearGradient>
  <linearGradient id="horizon" x1="442" y1="650" x2="802" y2="650" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{cyan_outer}"/>
    <stop offset="0.52" stop-color="#586af2"/>
    <stop offset="1" stop-color="{violet_outer}"/>
  </linearGradient>
  <filter id="soft-glow" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="12"/>
  </filter>
"""

    body = f"""
  <g id="kailarin-mark">
    <path d="{LEFT}" fill="url(#cyan)"/>
    <path d="{UPPER}" fill="url(#upper)"/>
    <path d="{LOWER}" fill="url(#lower)"/>
    <path d="M 178 760 C 306 533 801 395 1062 542"
          fill="none" stroke="url(#orbit)" stroke-width="{back_width}" opacity="0.80"/>
    <circle cx="622" cy="650" r="179" fill="{hole}"/>
    <circle cx="622" cy="650" r="180" fill="none" stroke="url(#horizon)"
            stroke-width="15" opacity="{glow_opacity}" filter="url(#soft-glow)"/>
    <circle cx="622" cy="650" r="179" fill="none" stroke="url(#horizon)" stroke-width="{horizon_width}"/>
    <path d="{FRONT_RING}" fill="none" stroke="url(#orbit)"
          stroke-width="{front_width}" stroke-linecap="round"/>
    <path d="{FRONT_RING}" fill="none" stroke="{edge}"
          stroke-width="{highlight_width}" stroke-linecap="round" opacity="0.75"/>
  </g>
"""
    return definitions, body


def mono_mark(ink: str) -> str:
    return f"""
  <g id="kailarin-mark" fill="{ink}">
    <path d="{LEFT}"/>
    <path d="{UPPER}"/>
    <path d="{LOWER}"/>
    <path d="M 178 760 C 306 533 801 395 1062 542"
          fill="none" stroke="{ink}" stroke-width="17"/>
    <circle cx="622" cy="650" r="179" fill="none" stroke="{ink}" stroke-width="18"/>
    <path d="{FRONT_RING}" fill="none" stroke="{ink}"
          stroke-width="28" stroke-linecap="round"/>
  </g>
"""


def main() -> None:
    dark_defs, dark_mark = color_mark()
    dark_compact_defs, dark_compact_mark = color_mark(compact=True)
    light_defs, light_mark = color_mark(light=True, compact=True)
    variants = {
        "kailarin-mark.svg": svg_document(dark_mark, dark_defs),
        "kailarin-avatar-dark.svg": svg_document(
            '<rect width="1254" height="1254" fill="#050b1b"/>\n'
            + '<g transform="translate(113 113) scale(0.82)">'
            + dark_compact_mark + '</g>',
            dark_compact_defs,
        ),
        "kailarin-avatar-light.svg": svg_document(
            '<rect width="1254" height="1254" fill="#f7f9fd"/>\n'
            + '<g transform="translate(113 113) scale(0.82)">'
            + light_mark + '</g>',
            light_defs,
        ),
        "kailarin-mark-mono-dark.svg": svg_document(mono_mark("#101e39")),
        "kailarin-mark-mono-light.svg": svg_document(mono_mark("#ffffff")),
    }
    for name, content in variants.items():
        (ROOT / name).write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
