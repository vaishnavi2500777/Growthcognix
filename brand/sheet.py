"""GrowthCognix brand sheet (outlined text, renders anywhere). Run after build.py."""
import os, cairosvg
from build import text_path, mark_paths, lockup_svg, C, OUT, HERE

S4, S5, S6 = "InstrumentSans-400.ttf", "InstrumentSans-500.ttf", "InstrumentSans-600.ttf"
SERIF_I = "InstrumentSerif-Italic.ttf"

def T(x, y, s, size, fill, font=S4, track=0):
    d, w = text_path(s, font, size, track)
    return f'<g transform="translate({x} {y})"><path d="{d}" fill="{fill}"/></g>', w

def page(theme):
    L = theme == "light"
    bg, fg = (C["paper"], C["ink"]) if L else (C["ink"], C["paper"])
    muted = C["slate"] if L else "#9AA39E"
    line = C["mist"] if L else "#232C28"
    surf = "#FFFFFF" if L else C["night"]
    prim = C["growth"] if L else C["signal"]
    W, H = 1600, 2000
    o = [f'<rect width="{W}" height="{H}" fill="{bg}"/>']
    add = lambda t: o.append(t[0])
    # header
    add(T(96, 120, "GROWTHCOGNIX  /  BRAND SYSTEM  /  V1.0  /  " + ("LIGHT" if L else "DARK"), 14, muted, S5, 1.6))
    o.append(f'<line x1="96" y1="148" x2="{W-96}" y2="148" stroke="{line}"/>')
    # lockup
    lk = lockup_svg(fg, prim, prim).split(">", 1)[1].rsplit("</svg>", 1)[0]
    o.append(f'<g transform="translate(78 200) scale(3.1)">{lk}</g>')
    add(T(96, 580, "Marketing that thinks.", 64, fg, S5, -1.2))
    add(T(96, 652, "Growth you approve.", 64, prim, SERIF_I, -0.4))
    add(T(96, 712, "An AI marketing department for every industry, supervised by you.", 22, muted))
    o.append(f'<line x1="96" y1="780" x2="{W-96}" y2="780" stroke="{line}"/>')
    # palette
    add(T(96, 836, "COLOUR", 13, muted, S5, 1.6))
    sw = [("Ink", C["ink"], "Text, dark surface"), ("Paper", C["paper"], "Light surface"),
          ("Growth", C["growth"], "Primary on light"), ("Signal", C["signal"], "Primary on dark"),
          ("Slate", C["slate"], "Secondary text"), ("Mist", C["mist"], "Borders, light")]
    for i, (n, hx, use) in enumerate(sw):
        x = 96 + i * 238
        o.append(f'<rect x="{x}" y="870" width="214" height="180" rx="14" fill="{hx}" stroke="{line}"/>')
        add(T(x, 1086, n, 20, fg, S6))
        add(T(x, 1112, hx, 15, muted, S4, 0.4))
        add(T(x, 1136, use, 15, muted))
    o.append(f'<line x1="96" y1="1190" x2="{W-96}" y2="1190" stroke="{line}"/>')
    # type
    add(T(96, 1246, "TYPE", 13, muted, S5, 1.6))
    add(T(96, 1340, "Aa", 96, fg, S6, -2))
    add(T(260, 1300, "Instrument Sans", 28, fg, S6))
    add(T(260, 1336, "Interface, headings, body. 400 / 500 / 600.", 18, muted))
    add(T(860, 1340, "Aa", 96, prim, SERIF_I))
    add(T(1010, 1300, "Instrument Serif Italic", 28, fg, S6))
    add(T(1010, 1336, "One accent phrase per page. Never body.", 18, muted))
    o.append(f'<line x1="96" y1="1400" x2="{W-96}" y2="1400" stroke="{line}"/>')
    # UI sample
    add(T(96, 1456, "INTERFACE", 13, muted, S5, 1.6))
    o.append(f'<rect x="96" y="1490" width="680" height="300" rx="16" fill="{surf}" stroke="{line}"/>')
    add(T(136, 1550, "Market Research Agent", 24, fg, S6))
    add(T(136, 1582, "Waiting for your approval before it runs.", 17, muted))
    o.append(f'<rect x="136" y="1620" width="150" height="48" rx="10" fill="{prim}"/>')
    add(T(168, 1652, "Approve", 18, C["ink"] if not L else "#FFFFFF", S5))
    o.append(f'<rect x="300" y="1620" width="130" height="48" rx="10" fill="none" stroke="{line}"/>')
    add(T(334, 1652, "Review", 18, fg, S5))
    add(T(136, 1740, "Radius 10  ·  8 px grid  ·  1 px hairlines  ·  no gradients", 15, muted))
    # icons
    for i, (b, s, n) in enumerate([(C["ink"], C["paper"], C["signal"]), (C["paper"], C["ink"], C["growth"])]):
        x = 836 + i * 200
        o.append(f'<rect x="{x}" y="1490" width="168" height="168" rx="38" fill="{b}" stroke="{line}"/>')
        o.append(f'<g transform="translate({x+22} {y if (y:=1512) else 0}) scale(1.94)">{mark_paths(s, n)}</g>')
    add(T(836, 1700, "App icon, dark and light", 15, muted))
    add(T(836, 1740, "Clear space = the node's diameter on every side.", 15, muted))
    # footer
    o.append(f'<line x1="96" y1="1870" x2="{W-96}" y2="1870" stroke="{line}"/>')
    add(T(96, 1914, "GrowthCognix  ·  Bengaluru 560064  ·  +91 90190 88160", 15, muted))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{"".join(o)}</svg>'

if __name__ == "__main__":
    import subprocess
    for t in ("light", "dark"):
        svg = page(t)
        cairosvg.svg2pdf(bytestring=svg.encode(), write_to=f"/tmp/sheet-{t}.pdf")
        cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(OUT, f"brand-sheet-{t}.png"))
    subprocess.run(["pdfunite", "/tmp/sheet-light.pdf", "/tmp/sheet-dark.pdf",
                    os.path.join(OUT, "GrowthCognix-Brand-System.pdf")], check=True)
    print("ok")
