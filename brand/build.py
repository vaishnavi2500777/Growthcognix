"""GrowthCognix brand asset generator. Run: python3 build.py"""
import math, os
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
import cairosvg

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets"); os.makedirs(OUT, exist_ok=True)

C = {
    "ink": "#0C1210", "paper": "#F5F4EF",
    "growth": "#0F7B5F", "signal": "#C8F169",
    "slate": "#5B635F", "mist": "#E4E3DC", "night": "#141B18",
}

# ---------- Mark: open G whose arc releases a rising signal node ----------
def mark_paths(stroke, node):
    cx, cy, r, w = 32, 34, 19, 7.2
    a0, a1 = -56, 0  # gap on upper right (screen coords, deg)
    def pt(a):
        t = math.radians(a); return cx + r * math.cos(t), cy + r * math.sin(t)
    x0, y0 = pt(a0); x1, y1 = pt(a1)
    arc = (f'<path d="M{x0:.2f} {y0:.2f} A{r} {r} 0 1 0 {x1:.2f} {y1:.2f} L{cx+3:.2f} {cy:.2f}" '
           f'fill="none" stroke="{stroke}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')
    dot = f'<circle cx="55.2" cy="16.6" r="4.6" fill="{node}"/>'
    return arc + dot

def mark_svg(stroke, node, bg=None, size=64, pad=0, radius=0):
    vb = 64 + 2 * pad
    bgs = f'<rect width="{vb}" height="{vb}" rx="{radius}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-pad} {-pad} {vb} {vb}" width="{size}" height="{size}">'
            f'{bgs.replace("<rect", f"<rect x=\"{-pad}\" y=\"{-pad}\"")}<g transform="translate(-2 -2)">{mark_paths(stroke, node)}</g></svg>')

# ---------- Wordmark as outlined paths ----------
def text_path(text, font_file, size, tracking=0):
    f = TTFont(os.path.join(HERE, "fonts", font_file))
    gs = f.getGlyphSet(); cmap = f.getBestCmap(); upm = f["head"].unitsPerEm
    s = size / upm; x = 0; parts = []
    hmtx = f["hmtx"]
    for ch in text:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        tp = TransformPen(pen, (s, 0, 0, -s, x, 0))
        gs[g].draw(tp)
        parts.append(pen.getCommands())
        x += hmtx[g][0] * s + tracking
    return " ".join(parts), x - tracking

def lockup_svg(fg, accent, node, bg=None):
    size = 31
    d1, w1 = text_path("Growth", "InstrumentSans-600.ttf", size, -0.6)
    d2, w2 = text_path("Cognix", "InstrumentSans-500.ttf", size, -0.6)
    pad = 18
    x_text = pad + 64 + 10
    base = pad + 45
    width = x_text + w1 + w2 + pad; h = 64 + 2 * pad
    bgs = f'<rect width="{width}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {h}" width="{width*3:.0f}" height="{h*3}">{bgs}'
            f'<g transform="translate({pad} {pad})">{mark_paths(fg, node)}</g>'
            f'<g transform="translate({x_text} {base})"><path d="{d1}" fill="{fg}"/></g>'
            f'<g transform="translate({x_text + w1:.2f} {base})"><path d="{d2}" fill="{accent}"/></g></svg>')

def save(name, svg, png_w=None):
    p = os.path.join(OUT, name + ".svg"); open(p, "w").write(svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(OUT, name + ".png"),
                     output_width=png_w)

if __name__ == "__main__":
    save("mark-light", mark_svg(C["ink"], C["growth"]), 512)
    save("mark-dark", mark_svg(C["paper"], C["signal"]), 512)
    save("app-icon", mark_svg(C["paper"], C["signal"], bg=C["ink"], pad=14, radius=22), 1024)
    save("app-icon-light", mark_svg(C["ink"], C["growth"], bg=C["paper"], pad=14, radius=22), 1024)
    save("favicon", mark_svg(C["ink"], C["growth"], bg=C["paper"], pad=6, radius=16), 64)
    save("logo-light", lockup_svg(C["ink"], C["growth"], C["growth"], bg=C["paper"]), 1600)
    save("logo-dark", lockup_svg(C["paper"], C["signal"], C["signal"], bg=C["ink"]), 1600)
    save("logo-light-transparent", lockup_svg(C["ink"], C["growth"], C["growth"]), 1600)
    save("logo-dark-transparent", lockup_svg(C["paper"], C["signal"], C["signal"]), 1600)
    print("ok")
