"""Build the self-contained animated README banner using the standard library."""

import base64
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets" / "brand"


def build_banner() -> None:
    artwork = base64.b64encode((ASSETS / "hero-still.webp").read_bytes()).decode("ascii")
    stars = "\n".join(
        f'<circle class="star s{i % 3}" cx="{x}" cy="{y}" r="{r}" fill="#d9faff"/>'
        for i, (x, y, r) in enumerate(
            [(121, 34, 1.2), (234, 151, 1.7), (751, 98, 1.4), (924, 554, 1.8),
             (264, 540, 1.9), (832, 639, 1.3), (1810, 607, 1.8), (2048, 150, 1.4)]
        )
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="2172" height="724" viewBox="0 0 2172 724" role="img" aria-labelledby="title desc">
<title id="title">KYRIN by Kailarin</title>
<desc id="desc">A cinematic intelligence core in deep space, with slowly traveling orbital light and a soft blue pulse. Open-source AI desktop agent. The animation respects reduced-motion preferences.</desc>
<defs>
  <radialGradient id="energy"><stop stop-color="#a9efff" stop-opacity=".65"/><stop offset=".35" stop-color="#42c8ff" stop-opacity=".22"/><stop offset="1" stop-color="#188fff" stop-opacity="0"/></radialGradient>
  <filter id="glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="4"/></filter>
  <path id="orbit" pathLength="1000" d="M 2052 518 C 2164 440 1816 227 1517 131 C 1263 48 1000 43 1031 153 C 1064 272 1592 479 1876 531 C 1964 547 2024 538 2052 518 Z"/>
</defs>
<style>
  .pulse {{animation: breathe 7s ease-in-out infinite; opacity:.12;}}
  .stream {{stroke-dasharray:26 974; animation: orbit 16s linear infinite;}}
  .stream.second {{stroke-dasharray:9 991; animation-delay:-8s; opacity:.55;}}
  .star {{animation: twinkle 6s ease-in-out infinite; opacity:.4;}}
  .s1 {{animation-delay:-2s;}} .s2 {{animation-delay:-4s;}}
  @keyframes orbit {{to {{stroke-dashoffset:-1000;}}}}
  @keyframes breathe {{0%,100% {{opacity:.07;}} 50% {{opacity:.35;}}}}
  @keyframes twinkle {{0%,100% {{opacity:.15;}} 50% {{opacity:.85;}}}}
  @media (prefers-reduced-motion: reduce) {{.pulse,.stream,.star {{animation:none;}} .stream {{display:none;}}}}
</style>
<image width="2172" height="724" href="data:image/webp;base64,{artwork}"/>
<ellipse class="pulse" cx="1511" cy="340" rx="147" ry="196" fill="url(#energy)"/>
<g fill="none" stroke="#6fddff" stroke-linecap="round">
  <use class="stream" xlink:href="#orbit" stroke-width="8" filter="url(#glow)" opacity=".48"/>
  <use class="stream" xlink:href="#orbit" stroke-width="1.8" opacity=".75"/>
  <use class="stream second" xlink:href="#orbit" stroke-width="2"/>
</g>
{stars}
</svg>
'''
    (ASSETS / "hero-animated.svg").write_text(svg, encoding="utf-8")
    print("Built assets/brand/hero-animated.svg")


if __name__ == "__main__":
    build_banner()
