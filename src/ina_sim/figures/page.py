"""Assemble the reference figures into one self-contained page.

Offline like everything else: inline SVG, inline CSS, no fonts or scripts
fetched from anywhere. The page is generated on request so it can never be
stale relative to the registry it is drawn from.
"""

from __future__ import annotations

from typing import Any

from ina_sim import __version__
from ina_sim.physics.dose import slider_sensitivity
from ina_sim.physics.ns import registry_summary
from ina_sim.validation.runner import run_validation

_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0 16px 64px;
  background: #c0c0c0;
  font-family: Georgia, 'Times New Roman', serif;
  color: #111;
}
.wrap { max-width: 860px; margin: 0 auto; }
header {
  background: #000080; color: #fff; padding: 8px 12px; margin: 0 -16px 20px;
  font-family: 'MS Sans Serif', Tahoma, sans-serif; font-size: 13px;
  display: flex; justify-content: space-between; align-items: baseline;
  flex-wrap: wrap; gap: 8px;
}
header b { font-weight: 700; }
header .meta { font-size: 11px; opacity: .85; }
.panel {
  background: #fff; border: 2px solid #fff;
  border-right-color: #808080; border-bottom-color: #808080;
  padding: 16px 18px; margin: 0 0 18px;
}
h1 { font-size: 20px; margin: 0 0 6px; }
h2 { font-size: 15px; margin: 22px 0 8px; }
p, li { font-size: 14px; line-height: 1.55; }
figure { margin: 0 0 22px; }
figure svg { display: block; border: 1px solid #b0b0b0; background: #fff; }
figcaption { font-size: 13px; line-height: 1.5; color: #333; padding: 8px 2px 0; }
.src { font-size: 12px; color: #666; font-family: monospace; padding-top: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #ddd;
         vertical-align: top; }
th { font-family: 'MS Sans Serif', Tahoma, sans-serif; font-size: 12px; }
code { font-family: monospace; font-size: 12px; background: #f0f0f0; padding: 1px 4px; }
.note { font-size: 13px; color: #444; border-left: 3px solid #000080;
        padding-left: 10px; margin: 12px 0; }
.overflow { overflow-x: auto; }
a { color: #000080; }
@media (max-width: 640px) { header { font-size: 12px; } .panel { padding: 12px; } }
"""


def render_page(figures: list[dict[str, Any]]) -> str:
    registry = registry_summary()
    try:
        validation = run_validation().as_dict()["summary"]
        val_text = (
            f"{validation['pass']} passed / {validation['fail']} failed"
        )
    except Exception:  # a broken self-check must not break the page
        val_text = "unavailable"

    rows = "".join(
        f"<tr><td><code>{name}</code></td><td>{body['effect']}</td>"
        f"<td>{body['why']}</td></tr>"
        for name, body in slider_sensitivity().items()
    )

    blocks = []
    for fig in figures:
        src = (
            f'<div class="src">source: {fig["sources"]}</div>' if fig.get("sources") else ""
        )
        blocks.append(
            "<figure>"
            f'<div class="overflow">{fig["svg"]}</div>'
            f'<figcaption>{fig["caption"]}{src}</figcaption>'
            "</figure>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>INA-sim — reference figures</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <span><b>INA-sim</b> · reference figures</span>
  <span class="meta">v{__version__} · {registry['count']} parameterizations
  ({registry['published']} published, {registry['derived']} derived) ·
  validation {val_text}</span>
</header>
<div class="wrap">

<div class="panel">
<h1>What the literature says</h1>
<p>
These figures are static on purpose. They do not respond to the screening
sliders, because they are not about one parcel of air — they are the evidence
the tool is built on, drawn directly from
<code>library/parameterizations.yaml</code> every time this page is generated.
Change a coefficient and every figure here changes with it.
</p>
<p class="note">
Each curve is drawn only over the temperature range its source actually fitted.
Where a line stops, the evidence stops. Nothing here is extrapolated.
</p>
</div>

<div class="panel">
{"".join(blocks)}
</div>

<div class="panel">
<h2>What the screening inputs do</h2>
<p>
A control that changes nothing is not automatically a defect. Pressure genuinely
does not decide whether a droplet freezes, and neither does humidity once the
particle is already immersed in one. The two that <em>should</em> have mattered
and did not — particle size and dose — now do.
</p>
<div class="overflow">
<table>
<thead><tr><th>input</th><th>effect</th><th>why</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</div>
<p class="note">
Overseeding — where too many ice crystals compete for the same vapour and none
grows to precipitation size — is real, and is <b>not</b> modelled. Dose here
increases ice nucleating particles without limit, which is true of nucleation
and false of seeding outcomes.
</p>
</div>

</div>
</body>
</html>
"""
