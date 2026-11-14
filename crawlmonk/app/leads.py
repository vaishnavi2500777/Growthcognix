"""Lead Finder: city-wise Indian business leads from OpenStreetMap (Nominatim + Overpass) and public web
search, verified and enriched by crawling each business's own website."""
import asyncio
import datetime as dt
import json
import re
import time
from urllib.parse import quote_plus, urlparse

import httpx

from . import ai, config, net, parse, search
from .net import FetchError

# maps.mail.ru answered fastest from Render Singapore; overpass-api.de refused connections from Render IPs.
OVERPASS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

# keyword -> OSM tag filters (key, regex or None for any value)
TAGMAP = [
    (r"clinic|doctor|hospital|medical|health|physio|diagnostic", [("amenity", "clinic|doctors|hospital"), ("healthcare", None)]),
    (r"dent", [("amenity", "dentist"), ("healthcare", "dentist")]),
    (r"pharma(cy)?$|chemist|medical store", [("amenity", "pharmacy")]),
    (r"restaurant|cafe|food|eatery|bakery|hotel food|dhaba", [("amenity", "restaurant|cafe|fast_food|food_court"), ("shop", "bakery|confectionery")]),
    (r"hotel|lodge|resort|guest ?house|homestay", [("tourism", "hotel|guest_house|hostel|motel|resort")]),
    (r"salon|beauty|spa|parlou?r", [("shop", "beauty|hairdresser|cosmetics"), ("leisure", "spa")]),
    (r"gym|fitness|yoga", [("leisure", "fitness_centre|sports_centre")]),
    (r"school|college|coaching|tuition|academy|institute|education|training", [("amenity", "school|college|university|kindergarten|training|language_school|music_school|driving_school"), ("office", "educational_institution|tutoring")]),
    (r"manufactur|factory|industr|plant|works|fabricat|engineering", [("man_made", "works"), ("industrial", None), ("craft", None), ("office", "company")]),
    (r"real ?estate|builder|propert", [("office", "estate_agent|construction_company|property_management")]),
    (r"lawyer|advocate|legal", [("office", "lawyer")]),
    (r"accountant|chartered|\bca\b|tax", [("office", "accountant|tax_advisor")]),
    (r"shop|store|retail|boutique|jewel", [("shop", None)]),
    (r"car|automobile|garage|auto service", [("shop", "car|car_repair|car_parts|motorcycle"), ("amenity", "car_wash")]),
    (r"interior|furniture", [("shop", "furniture|interior_decoration"), ("craft", "carpenter")]),
    (r"it company|software|tech", [("office", "it|company|telecommunication")]),
    (r"travel|tour", [("shop", "travel_agency"), ("office", "travel_agent")]),
    (r"vet|pet", [("amenity", "veterinary"), ("shop", "pet")]),
]
GENERIC = {"manufacturer", "manufacturers", "manufacturing", "company", "companies", "business", "businesses",
           "supplier", "suppliers", "dealer", "dealers", "shop", "shops", "store", "stores", "services", "service",
           "in", "and", "of", "the", "pvt", "ltd", "private", "limited", "industry", "industries", "factory",
           "clinic", "clinics", "restaurant", "restaurants", "hotel", "hotels"}
DIRECTORY_HOSTS = re.compile(r"(justdial|indiamart|sulekha|tradeindia|exportersindia|facebook|instagram|linkedin|"
                             r"twitter|x\.com|youtube|wikipedia|practo|zomato|swiggy|magicpin|lybrate|google\.|"
                             r"bing\.|yelp|tripadvisor|amazon|flipkart|quora|reddit|glassdoor|ambitionbox|naukri|"
                             r"zaubacorp|tofler|thecompanycheck|falconebiz|crunchbase|dnb\.com|yellowpages|"
                             r"grotal|asklaila|nearbuy|housing\.com|99acres|magicbricks|olx|quikr|medium\.com|"
                             r"pinterest|threads|wa\.me|blogspot|wordpress\.com|gov\.in|nic\.in|economictimes|"
                             r"timesofindia|thehindu|ndtv|hindustantimes|moneycontrol|alibaba|made-in-china|"
                             r"volza|zauba|seair|eximpedia|tradekey|go4worldbusiness|dial4trade|kompass|"
                             r"apollo247|1mg|healthians|credihealth|clinicspots|vaidam|sehat|docprime|"
                             r"eazydiner|dineout|burrp|urbanclap|urbancompany|nobroker)", re.I)

_nom_lock = asyncio.Lock()
_nom_last = 0.0
_geo_cache: dict[str, dict] = {}


class LeadError(Exception):
    code = "LEAD_ERROR"


async def geocode(city: str, state: str | None) -> dict:
    global _nom_last
    q = ", ".join(x for x in [city, state, "India"] if x)
    if q.lower() in _geo_cache:
        return _geo_cache[q.lower()]
    async with _nom_lock:  # Nominatim policy: max 1 request/second, identifying User-Agent
        wait = _nom_last + 1.1 - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _nom_last = time.monotonic()
        r = await net.fetch(f"https://nominatim.openstreetmap.org/search?q={quote_plus(q)}&format=jsonv2&limit=5"
                            f"&countrycodes=in&addressdetails=0", ua=config.BOT_UA, timeout=20)
    if r.status != 200:
        return await _photon(q)
    res = json.loads(r.text)
    res = [x for x in res if x.get("osm_type") == "relation"] or res
    if not res:
        raise LeadError(f"Could not find '{q}' on OpenStreetMap")
    g = res[0]
    out = {"name": g.get("display_name"), "lat": float(g["lat"]), "lon": float(g["lon"]),
           "osm_type": g.get("osm_type"), "osm_id": int(g["osm_id"])}
    if g.get("boundingbox"):
        s_, n_, w_, e_ = map(float, g["boundingbox"])
        out["bbox"] = _cap_bbox(s_, w_, n_, e_, out["lat"], out["lon"])
    _geo_cache[q.lower()] = out
    return out


def _cap_bbox(s, w, n, e, lat, lon, half=0.25):
    """Clamp to ~55 km square around the centre so district-sized results stay city-sized."""
    return (max(s, lat - half), max(w, lon - half), min(n, lat + half), min(e, lon + half))


async def _photon(q: str) -> dict:
    """Fallback geocoder (Komoot Photon, OSM data) when Nominatim rate-limits; returns a point (radius search)."""
    r = await net.fetch(f"https://photon.komoot.io/api/?q={quote_plus(q)}&limit=5&osm_tag=place", ua=config.BOT_UA,
                        timeout=20)
    if r.status != 200:
        raise LeadError(f"Geocoding failed (Nominatim and Photon unavailable, HTTP {r.status})")
    feats = [f for f in json.loads(r.text).get("features", []) if f["properties"].get("countrycode") == "IN"]
    if not feats:
        raise LeadError(f"Could not find '{q}' on OpenStreetMap")
    f = feats[0]
    lon, lat = f["geometry"]["coordinates"]
    out = {"name": ", ".join(x for x in [f["properties"].get("name"), f["properties"].get("state"), "India"] if x),
           "lat": lat, "lon": lon, "osm_type": "node", "osm_id": f["properties"]["osm_id"], "geocoder": "photon"}
    ext = f["properties"].get("extent")  # [minlon, maxlat, maxlon, minlat]
    if ext and len(ext) == 4:
        out["bbox"] = _cap_bbox(ext[3], ext[0], ext[1], ext[2], lat, lon)
    _geo_cache[q.lower()] = out
    return out


def keywords(category: str, extra: str | None) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9&+-]{2,}", f"{category} {extra or ''}")
    out = []
    for w in words:
        lw = w.lower()
        if lw in GENERIC:
            continue
        if len(lw) > 4 and lw.endswith("s") and not lw.endswith("ss"):
            lw = lw[:-1]
        out.append(lw)
    return list(dict.fromkeys(out))


def tag_filters(category: str) -> list[tuple[str, str | None]]:
    c = category.lower()
    out = []
    for rx, tags in TAGMAP:
        if re.search(rx, c):
            out += tags
    return out


def build_queries(geo: dict, category: str, kws: list[str], radius_km=15) -> list[str]:
    if geo.get("bbox"):  # bbox queries are far cheaper than area queries on public Overpass servers
        b = geo["bbox"]
        scope = f"({b[0]:.4f},{b[1]:.4f},{b[2]:.4f},{b[3]:.4f})"
    else:
        scope = f"(around:{radius_km * 1000},{geo['lat']},{geo['lon']})"
    tags = tag_filters(category)
    kre = "|".join(re.escape(k) for k in kws)
    stmts = []
    if not kws:  # pure category: every named place with the mapped tags
        for k, v in tags:
            sel = f'["{k}"~"^({v})$"]' if v else f'["{k}"]'
            stmts.append(f'nwr{sel}["name"]{scope};')
    else:  # keyword: match name / product / industrial tags anywhere in the city
        for key in ("name", "product", "industrial"):
            stmts.append(f'nwr["{key}"~"{kre}",i]{scope};')
    if not stmts:
        raise LeadError("Category too vague; add a keyword such as 'clinic' or 'PTFE'")
    # small single-statement queries: public Overpass servers time out on big unions
    return [f"[out:json][timeout:60];{st}out center tags 2000;" for st in stmts]


async def _overpass_one(ep: str, q: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), headers={"User-Agent": config.BOT_UA}) as c:
        r = await asyncio.wait_for(c.post(ep, data={"data": q}), 80)  # hard deadline (servers trickle keep-alives)
    if r.status_code != 200:
        raise LeadError(f"{urlparse(ep).hostname} HTTP {r.status_code}")
    return r.json().get("elements", [])


async def overpass(q: str) -> list[dict]:
    """Try the public Overpass servers with retries (they return 504/timeouts under load)."""
    errs = []
    for attempt in range(3):
        for ep in OVERPASS[:2] if attempt else OVERPASS:
            try:
                return await _overpass_one(ep, q)
            except Exception as e:
                errs.append(f"{urlparse(ep).hostname}: {type(e).__name__} {str(e)[:60]}")
        await asyncio.sleep(5 * (attempt + 1))
    raise LeadError("OpenStreetMap Overpass unavailable (" + "; ".join(errs[-4:]) + ")")


async def osm_elements(geo, category, kws, report) -> tuple[list[dict], list[str]]:
    qs = build_queries(geo, category, kws)
    seen, out, errs = set(), [], []
    for i, q in enumerate(qs):
        await report(stage=f"{geo['name'].split(',')[0]}: OpenStreetMap query {i + 1}/{len(qs)}")
        try:
            for e in await overpass(q):
                k = (e["type"], e["id"])
                if k not in seen:
                    seen.add(k)
                    out.append(e)
        except LeadError as e:
            errs.append(str(e))
    return out, errs


def from_osm(el: dict, city: str) -> dict | None:
    t = el.get("tags", {})
    name = t.get("name") or t.get("name:en")
    if not name:
        return None
    addr = ", ".join(x for x in [t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:suburb"),
                                 t.get("addr:city"), t.get("addr:postcode")] if x)
    cat = next((f"{k}={t[k]}" for k in ("amenity", "healthcare", "shop", "office", "industrial", "craft",
                                         "man_made", "tourism", "leisure") if k in t), "")
    web = t.get("website") or t.get("contact:website") or t.get("url")
    if web and not web.startswith("http"):
        web = "http://" + web
    phone = t.get("phone") or t.get("contact:phone") or t.get("contact:mobile") or t.get("mobile")
    socials = {k.split(":")[1]: v for k, v in t.items() if k in ("contact:facebook", "contact:instagram",
                                                                  "contact:linkedin", "contact:twitter")}
    c = el.get("center") or el
    return {"city": city, "name": name.strip(), "category": cat, "address": addr or t.get("addr:full", ""),
            "phone": phone, "website": web, "emails": [e for e in [t.get("email") or t.get("contact:email")] if e],
            "phones": [], "socials": socials, "signals": {}, "lat": c.get("lat"), "lon": c.get("lon"),
            "source": "openstreetmap", "source_ref": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            "_text": " ".join(str(v) for k, v in t.items() if k in ("name", "product", "industrial", "description",
                                                                    "craft", "cuisine", "healthcare:speciality")).lower(),
            "_tagmatch": True}


async def web_candidates(category: str, city: str, state: str | None, n=25) -> list[dict]:
    qs = [f"{category} in {city} {state or ''} contact".strip(), f"{category} {city} official website",
          f"{category} companies {city}"]
    out, seen = [], set()
    for q in qs:
        try:
            res, _ = await search.web(q, n)
        except Exception:
            continue
        for x in res:
            h = (urlparse(x["url"]).hostname or "").removeprefix("www.")
            if not h or DIRECTORY_HOSTS.search(h) or h in seen:
                continue
            seen.add(h)
            out.append({"city": city, "name": "", "category": "web:" + category, "address": "", "phone": None,
                        "website": f"{urlparse(x['url']).scheme}://{urlparse(x['url']).netloc}/",
                        "emails": [], "phones": [], "socials": {}, "signals": {}, "lat": None, "lon": None,
                        "source": "web_search", "source_ref": x["url"], "_text": (x["title"] + " " + x["description"]).lower(),
                        "_title": x["title"], "_tagmatch": False})
    return out


CONTACT_RX = re.compile(r"contact|about|reach|enquir|location|find-us", re.I)


async def enrich(lead: dict, city: str, state: str | None, kws: list[str]):
    url = lead["website"]
    sig = lead["signals"]
    try:
        if not await net.robots_allowed(url):
            sig["enrich"] = "blocked_by_robots"
            return
        r = await net.fetch(url, timeout=12, delay=0.3)
    except FetchError as e:
        sig["website_ok"] = False
        sig["enrich"] = e.code.lower()
        return
    if r.status >= 400 or "html" not in r.content_type:
        sig["website_ok"] = False
        sig["enrich"] = f"http_{r.status}"
        return
    sig["website_ok"] = True
    pages = [r]
    s = parse.soup_of(r.text)
    parse.absolutize(s, r.final_url)
    sig.update(parse.site_signals(s, r.text, r.final_url))
    if not lead["name"]:
        og = s.find("meta", property="og:site_name")
        t = (og.get("content") if og else None) or (s.title.string if s.title and s.title.string else "") or lead.get("_title", "")
        lead["name"] = re.split(r"\s[|\-–:]\s", t.strip())[0][:120] if t else urlparse(url).hostname
    sub = [a["href"] for a in s.find_all("a", href=True) if CONTACT_RX.search(a["href"]) and
           urlparse(a["href"]).hostname == urlparse(r.final_url).hostname][:2]
    if lead["source"] == "web_search" and lead.get("source_ref") and \
            (urlparse(lead["source_ref"]).hostname or "").removeprefix("www.") == (urlparse(r.final_url).hostname or "").removeprefix("www."):
        sub.insert(0, lead["source_ref"])
    for u in list(dict.fromkeys(sub))[:3]:
        try:
            if await net.robots_allowed(u):
                pr = await net.fetch(u, timeout=10, delay=0.3)
                if pr.status < 400 and "html" in pr.content_type:
                    pages.append(pr)
        except FetchError:
            pass
    text_all = ""
    for p in pages:
        ps = s if p is r else parse.soup_of(p.text)
        if p is not r:
            parse.absolutize(ps, p.final_url)
        txt = ps.get_text(" ", strip=True)
        text_all += " " + txt
        c = parse.contacts(ps, txt)
        lead["emails"] = list(dict.fromkeys(lead["emails"] + c["emails"]))[:8]
        lead["phones"] = list(dict.fromkeys(lead["phones"] + c["phones"]))[:6]
        for k, v in c["socials"].items():
            lead["socials"].setdefault(k, v)
    low = text_all.lower()
    sig["keyword_hits"] = {k: low.count(k) for k in kws} if kws else {}
    sig["mentions_city"] = city.lower() in low or (state or "~~").lower() in low
    lead["_text"] += " " + low[:6000]
    lead["_site_excerpt"] = re.sub(r"\s+", " ", text_all)[:1500]


def score(lead: dict, kws: list[str], goal: str) -> tuple[int, str]:
    sig, why = lead["signals"], []
    rel = 0
    if lead.get("_tagmatch"):
        rel += 25
        why.append("category match on OpenStreetMap")
    name_hits = [k for k in kws if k in lead["name"].lower()]
    if name_hits:
        rel += 10
        why.append("keyword in name: " + ", ".join(name_hits))
    site_hits = [k for k, n in (sig.get("keyword_hits") or {}).items() if n]
    if site_hits:
        rel += 15 if lead["source"] == "web_search" else 10
        why.append("website mentions " + ", ".join(site_hits))
    if lead["source"] == "web_search" and sig.get("mentions_city"):
        rel += 10
        why.append("website mentions the city")
    rel = min(rel, 40)
    con = 0
    if lead.get("phone") or lead["phones"]:
        con += 12
    if lead["emails"]:
        con += 13
        why.append("public email found")
    if sig.get("website_ok"):
        con += 10
    opp = 0
    if goal == "agency":
        if not lead.get("website"):
            opp += 10
            why.append("no website")
        elif sig.get("website_ok"):
            if "instagram" not in lead["socials"]:
                opp += 6
                why.append("no Instagram linked")
            if not sig.get("https"):
                opp += 5
                why.append("site not on HTTPS")
            if not sig.get("mobile_meta"):
                opp += 5
                why.append("site not mobile-friendly")
            y = sig.get("copyright_year")
            if y and y < dt.date.today().year - 2:
                opp += 5
                why.append(f"site footer dated {y}")
        opp = min(opp, 25)
        total = rel + con + opp
    else:  # buyer: relevance matters most
        total = round(rel * 1.6 + con)
    return min(100, total), "; ".join(why)


def dedupe_key(l: dict) -> list[str]:
    keys = []
    if l.get("website"):
        h = (urlparse(l["website"]).hostname or "").removeprefix("www.")
        if h and not DIRECTORY_HOSTS.search(h):
            keys.append("w:" + h)
    ph = re.sub(r"\D", "", l.get("phone") or "")[-10:]
    if len(ph) == 10:
        keys.append("p:" + ph)
    nm = re.sub(r"[^a-z0-9]", "", l["name"].lower())
    if nm:
        keys.append("n:" + nm + ":" + l["city"].lower())
    return keys


async def ai_reasons(leads: list[dict], category: str, offer: str | None):
    if not ai.enabled() or not leads:
        return
    items = [{"id": i, "name": l["name"], "category": l["category"], "website": l.get("website"),
              "signals": {k: v for k, v in l["signals"].items() if k in ("https", "mobile_meta", "copyright_year", "keyword_hits")},
              "socials": list(l["socials"]), "site_text": l.get("_site_excerpt", "")[:600]} for i, l in enumerate(leads)]
    prompt = (f"You qualify B2B sales leads in India. Target: '{category}'. "
              f"Seller's offer: {offer or 'not specified'}.\nFor each business, judge fit ONLY from the given data. "
              "Return JSON array of {id, fit: 'high'|'medium'|'low', reason: one sentence (<=25 words) citing the "
              "evidence}.\n" + json.dumps(items)[:50000])
    try:
        res = ai.parse_json(await ai.generate(prompt, json_mode=True, max_tokens=6000))
        for x in res if isinstance(res, list) else []:
            i = x.get("id")
            if isinstance(i, int) and 0 <= i < len(leads):
                leads[i]["ai_reason"] = f"{x.get('fit', '?')}: {x.get('reason', '')}"
    except Exception as e:  # AI is optional; heuristic score stays
        for l in leads:
            l.setdefault("ai_reason", None)
        leads[0]["_ai_error"] = str(e)


async def find_city(city: str, state: str | None, p: dict, report) -> tuple[list[dict], dict]:
    category = p["category"].strip()
    kws = keywords(category, p.get("keywords"))
    max_leads = max(5, min(int(p.get("max_leads", 60)), 300))
    goal = p.get("goal", "agency")
    stats = {"city": city}
    await report(stage=f"{city}: geocoding")
    geo = await geocode(city, state)
    stats["resolved"] = geo["name"]
    raw = []
    if "osm" in p.get("sources", ["osm", "web"]):
        await report(stage=f"{city}: querying OpenStreetMap")
        els, errs = await osm_elements(geo, category, kws, report)
        raw += [x for x in (from_osm(e, city) for e in els) if x]
        stats["osm_found"] = len(raw)
        if errs:
            stats["osm_error"] = f"{len(errs)} of the OpenStreetMap queries failed: {errs[0]}"
    if "web" in p.get("sources", ["osm", "web"]):
        await report(stage=f"{city}: searching the web")
        w = await web_candidates(category, city, state)
        stats["web_candidates"] = len(w)
        raw += w
    # dedupe
    merged, index = [], {}
    for l in raw:
        hit = next((index[k] for k in dedupe_key(l) if k in index), None)
        if hit is not None:
            m = merged[hit]
            for k in ("phone", "website", "address"):
                m[k] = m.get(k) or l.get(k)
            m["emails"] = list(dict.fromkeys(m["emails"] + l["emails"]))
            m["socials"] = {**l["socials"], **m["socials"]}
            m["_tagmatch"] = m["_tagmatch"] or l["_tagmatch"]
            continue
        for k in dedupe_key(l):
            index[k] = len(merged)
        merged.append(l)
    # prefer contactable OSM entries, cap before enrichment
    merged.sort(key=lambda l: (bool(l.get("website")), bool(l.get("phone")), l["source"] == "openstreetmap"), reverse=True)
    merged = merged[:max_leads + 20]
    stats["after_dedupe"] = len(merged)
    if p.get("enrich", True):
        todo = [l for l in merged if l.get("website")]
        sem = asyncio.Semaphore(6)
        done = 0

        async def go(l):
            nonlocal done
            async with sem:
                try:
                    await asyncio.wait_for(enrich(l, city, state, kws), 45)
                except asyncio.TimeoutError:
                    l["signals"]["enrich"] = "timeout"
                done += 1
                if done % 5 == 0:
                    await report(stage=f"{city}: checking websites {done}/{len(todo)}")
        await asyncio.gather(*(go(l) for l in todo))
    # web-search candidates must prove relevance on their own site
    keep = []
    for l in merged:
        if l["source"] == "web_search":
            hits = sum((l["signals"].get("keyword_hits") or {}).values())
            if not l["signals"].get("website_ok") or (kws and hits == 0) or not l["signals"].get("mentions_city"):
                continue
        if not l["name"]:
            continue
        l["score"], l["reason"] = score(l, kws, goal)
        keep.append(l)
    # second dedupe pass: names learned from websites
    final, seen = [], set()
    for l in sorted(keep, key=lambda x: x["score"], reverse=True):
        ks = dedupe_key(l)
        if any(k in seen for k in ks):
            continue
        seen.update(ks)
        final.append(l)
    final = final[:max_leads]
    if p.get("ai", True):
        await report(stage=f"{city}: AI fit reasons")
        await ai_reasons(final[:40], category, p.get("offer"))
        if final and final[0].get("_ai_error"):
            stats["ai_error"] = final[0]["_ai_error"]
    stats["leads"] = len(final)
    return final, stats
