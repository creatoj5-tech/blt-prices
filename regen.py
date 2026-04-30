#!/usr/bin/env python3
"""Regenerate per-category BLT HTML files from the old prices.html.

Strategy: the old prices.html (commit d6193ed) already had real data in the
correct one-line-per-condition format. We just regroup those lines into
per-category files with conditions ordered Grade A first, HSO last.
"""
import os
import re
import sys
import datetime
from pathlib import Path
from collections import defaultdict

SOURCE = os.environ.get("BLT_PRICES_HTML", "/tmp/blt-extract/prices.html")
OUTDIR = Path(os.environ.get("BLT_OUTDIR", "/tmp/blt-extract"))
OUTDIR.mkdir(parents=True, exist_ok=True)

# Order matters: Grade A first, SWAP HSO last for USED. NEW conditions in their natural order.
USED_ORDER = ["Grade A", "Grade B", "Grade C", "Grade D", "DOA", "SWAP HSO"]
NEW_ORDER = ["Sealed", "Open Box", "Sealed (Activated)", "Sealed Activated"]

LINE_RE = re.compile(r"^<p>(NEW|USED)\s+(.+?),\s+([^:]+?):\s+\$([\d,]+(?:\.\d+)?)\.</p>\s*$")

def parse_lines(text):
    """Parse <p> price sentences into structured dicts."""
    out = []
    for raw in text.splitlines():
        m = LINE_RE.match(raw.strip())
        if not m:
            continue
        new_used, identifier, condition, price = m.groups()
        out.append({
            "new_used": new_used,
            "identifier": identifier.strip(),
            "condition": condition.strip(),
            "price": price.strip(),
            "raw": raw.strip(),
        })
    return out

def categorize(rec):
    """Return (category, model_key) for an entry."""
    ident = rec["identifier"]
    if ident.startswith("iPhone "):
        # Model = everything before the first storage marker (e.g. "128GB", "1TB").
        # Handles "iPhone 14 Pro Max 128GB Unlocked", "iPhone 17E 256GB Unlocked", "iPhone SE 64GB Unlocked".
        m = re.match(r"(iPhone\s+.+?)\s+\d+(?:GB|TB)\b", ident)
        cat = "iphone-new" if rec["new_used"] == "NEW" else "iphone-used"
        if m:
            return cat, m.group(1).strip()
        return cat, "iPhone (other)"
    if ident.startswith("iPad"):
        m = re.match(r"(iPad(?:\s+(?:Pro|Air|Mini))?(?:\s+\d+(?:\.\d+)?(?:\"|in)?)?)\s+", ident)
        model = m.group(1) if m else "iPad"
        return "ipad", model
    if ident.startswith("Galaxy") or ident.startswith("Samsung"):
        m = re.match(r"((?:Galaxy|Samsung)\s+\S+(?:\s+\S+)?(?:\s+(?:Ultra|Plus|FE))?)", ident)
        model = m.group(1) if m else ident.split(",")[0]
        return "samsung", model
    if "Apple Watch" in ident or ident.startswith("Watch"):
        m = re.match(r"(Apple Watch[^,]*?)(?:\s+\d+mm|\s+\(|\s+GPS|\s+Cellular|$)", ident)
        model = m.group(1).strip() if m else "Apple Watch"
        return "watch", model
    if "AirPods" in ident:
        m = re.match(r"(AirPods[^,]*?)(?:\s+\(|$)", ident)
        model = m.group(1).strip() if m else "AirPods"
        return "airpods", model
    if any(k in ident for k in ["PlayStation", "PS5", "PS4", "Xbox", "Nintendo", "Switch", "Steam Deck"]):
        return "gaming", ident.split(",")[0].strip()
    # Fallback
    return "other", ident.split(",")[0].strip()

def order_index(condition, ordering):
    for i, c in enumerate(ordering):
        if condition.lower() == c.lower():
            return i
    return 99

CONDITION_BLURBS = {
    "Grade A": ("Grade A Prices — DEFAULT for sellers who don't specify condition (no scratches, mint, like new)",
                "These are the DEFAULT buying prices. Quote a Grade A price whenever a seller names a phone without specifying condition. Trigger phrases that map here: \"no scratches\", \"mint\", \"like new\", silence on condition. NEVER pick a SWAP HSO price as the default — SWAP HSO is at the bottom of this page and only applies to \"brand new + no box\" descriptions."),
    "Grade B": ("Grade B Prices — for sellers who say \"light use, no cracks, fully functional\"",
                "Quote a Grade B price ONLY when the seller describes light wear with no cracks and full functionality."),
    "Grade C": ("Grade C Prices — for sellers describing cracked screens, hairline cracks, or heavy scratches",
                "Quote a Grade C price for: hairline cracks, small chips, cracked screens, shattered glass, heavy scratches, deep scratches."),
    "Grade D": ("Grade D Prices — for sellers describing bad LCD, dead pixels, or non-functional displays",
                "Quote a Grade D price for: bad LCD, dead pixels, lines on screen, screen black but powers on."),
    "DOA": ("DOA Prices — for sellers describing a dead device",
            "Quote a DOA price ONLY for: won't power on, water damage, completely dead device."),
    "SWAP HSO": ("SWAP HSO Prices — DO NOT QUOTE BY DEFAULT. ONLY for explicit \"brand new + no box\" descriptions",
                 "WARNING: SWAP HSO is NOT the default condition. Quote a SWAP HSO price ONLY when the seller explicitly says the device is brand new AND has no box. Trigger phrases: \"brand new without the box\", \"never used, no box\", \"factory new no box\", \"0 cycle, no box\", \"brand new in plastic, no box\". Vague \"brand new\" or \"sealed\" alone does NOT trigger HSO — those stay Grade A. The default ceiling for ANY used iPhone is Grade A, listed at the top of this page."),
}

def render_category_html(cat, title, records, page_blurb):
    """Render a per-category HTML file. USED iPhones group by CONDITION first, then model.
    Other categories group by model."""
    is_used_iphone = (cat == "iphone-used")
    today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = []
    html.append('<!DOCTYPE html>')
    html.append(f'<html lang="en"><head><meta charset="UTF-8"><title>{title}</title></head>')
    html.append('<body>')
    html.append(f'<h1>{title}</h1>')
    html.append(f'<p><strong>Last Updated:</strong> {today_utc}</p>')
    html.append(f'<p><strong>Category:</strong> {page_blurb} For other categories see welcome.html, iphone-new.html, iphone-used.html, ipad.html, samsung.html, watch.html, airpods.html, gaming.html on the same repo.</p>')
    html.append('')

    if is_used_iphone:
        # Group by CONDITION first. Each condition gets its own <h2> section
        # with a strong header that travels with retrieved chunks.
        by_cond = defaultdict(list)
        for r in records:
            by_cond[r["condition"]].append(r)
        for cond in USED_ORDER:
            entries = by_cond.get(cond, [])
            if not entries:
                continue
            heading, blurb = CONDITION_BLURBS.get(cond, (f"{cond} Prices", ""))
            html.append(f'<h2>{heading}</h2>')
            if blurb:
                html.append(f'<p>{blurb}</p>')
            # Group entries by model within this condition
            by_model = defaultdict(list)
            model_order = []
            for r in entries:
                _, m = categorize(r)
                if m not in by_model:
                    model_order.append(m)
                by_model[m].append(r)
            for model in model_order:
                html.append(f'<h3>{model} — {cond}</h3>')
                for e in by_model[model]:
                    html.append(f'<p>{e["new_used"]} {e["identifier"]}, {e["condition"]}: ${e["price"]}.</p>')
                html.append('')
    else:
        # Group by model in order of first appearance (NEW iPhones, iPad, Samsung, etc.)
        by_model = defaultdict(list)
        model_order = []
        for r in records:
            _, m = categorize(r)
            if m not in by_model:
                model_order.append(m)
            by_model[m].append(r)
        html.append('<h2>Quick Reference — Price Lookup</h2>')
        if cat == "iphone-new":
            html.append('<p>Every NEW price in this category as a single sentence. Conditions: Sealed, Open Box, Sealed (Activated).</p>')
        else:
            html.append('<p>Every price in this category as a single sentence.</p>')
        html.append('')
        for model in model_order:
            entries = by_model[model]
            html.append(f'<h3>{model}</h3>')
            by_variant = defaultdict(list)
            variant_order = []
            for e in entries:
                variant = e["identifier"]
                if variant not in by_variant:
                    variant_order.append(variant)
                by_variant[variant].append(e)
            for variant in variant_order:
                vlist = by_variant[variant]
                vlist_sorted = sorted(vlist, key=lambda x: order_index(x["condition"], USED_ORDER if x["new_used"] == "USED" else NEW_ORDER))
                for e in vlist_sorted:
                    html.append(f'<p>{e["new_used"]} {e["identifier"]}, {e["condition"]}: ${e["price"]}.</p>')
                html.append('')

    html.append('<p><strong>Contact:</strong> Yu (909) 664-5589 · Angelina (909) 631-1132 · Nick (628) 266-5678 weekends/after-hours text only. Mon–Fri 11AM–6PM CST, closed Thursdays.</p>')
    html.append('</body></html>')
    return "\n".join(html)

def render_welcome_html(text):
    """Build welcome.html with contact, hours, payment, policy, grading guide."""
    today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Try to extract grading guide and policies sections from the old prices.html
    # The old file has "Contact &amp; Policies" h2 section — pull everything from there to next h2
    contact_section = ""
    m = re.search(r"<h2>Contact[^<]*</h2>(.*?)<h2>", text, re.DOTALL)
    if m:
        contact_section = m.group(1).strip()

    html = []
    html.append('<!DOCTYPE html>')
    html.append('<html lang="en"><head><meta charset="UTF-8"><title>BLT Trading — Welcome, Policies &amp; Grading Guide</title></head>')
    html.append('<body>')
    html.append('<h1>BLT Trading — Welcome, Policies &amp; Grading Guide</h1>')
    html.append(f'<p><strong>Last Updated:</strong> {today_utc}</p>')
    html.append('<p>BLT Trading buys used and brand-new gadgets — phones, iPads, Apple Watches, AirPods, gaming consoles. We do NOT sell, trade-in, repair, unlock, or activate.</p>')
    html.append('')
    html.append('<h2>Contact Information</h2>')
    html.append('<p><strong>Yu</strong> — call or text (909) 664-5589 (default escalation)</p>')
    html.append('<p><strong>Angelina</strong> — call or text (909) 631-1132 (default escalation)</p>')
    html.append('<p><strong>Nick</strong> — text only (628) 266-5678 (weekends and after-hours only)</p>')
    html.append('<p><strong>Email:</strong> info@BLTtradings.com</p>')
    html.append('<p><strong>Hours:</strong> Mon–Fri 11AM–6PM CST. Closed every Thursday. Saturdays/Sundays handled by Nick by appointment.</p>')
    html.append('<p><strong>Shipping address:</strong> 2955 Congressman Ln, Dallas, TX 75220</p>')
    html.append('')
    html.append('<h2>Payment Methods</h2>')
    html.append('<p>Cash payment available in DFW Metropolitan area only. Outside DFW: wire transfer, ACH, or Zelle.</p>')
    html.append('<p>Apple Gift Cards purchased at 78% of face value.</p>')
    html.append('<p>Free FedEx shipping labels for sellers shipping 5+ devices.</p>')
    html.append('')
    html.append('<h2>General Policy</h2>')
    html.append('<p>Prices can change at any time at our discretion.</p>')
    html.append('<p>All quoted prices are buying prices — what BLT pays the seller.</p>')
    html.append('<p>Final price is confirmed only after in-person inspection or device test.</p>')
    html.append('<p>BLT does not sell devices to customers. BLT does not perform repairs, unlocks, or activations.</p>')
    html.append('')
    html.append('<h2>Specialist Routing</h2>')
    html.append('<p>Models not in the price list: text or call Yu (909) 664-5589 or Angelina (909) 631-1132 to confirm if BLT can still take them.</p>')
    html.append('<p>Bulk inquiries (5+ devices): same — Yu or Angelina.</p>')
    html.append('<p>Weekend or after-hours appointments: text Nick at (628) 266-5678 only. Do not contact Yu or Angelina outside business hours.</p>')
    html.append('')
    if contact_section:
        # Strip empty <p> tags and wrap into a guide section
        html.append('<h2>Device Grading &amp; Term Guide</h2>')
        # Embed the contact section content (it's a <p>-list of grading terms in the old file)
        html.append(contact_section)
    else:
        html.append('<h2>Device Grading &amp; Term Guide</h2>')
        html.append('<p><strong>NEW Sealed:</strong> Factory-sealed, brand new in box, never opened, never activated.</p>')
        html.append('<p><strong>NEW Open Box:</strong> Brand new but the seal is opened. Never used.</p>')
        html.append('<p><strong>Sealed (Activated):</strong> Sealed in box but Apple activation has occurred (clock started).</p>')
        html.append('<p><strong>SWAP / HSO:</strong> Factory-fresh device, zero battery cycles, but without the original box.</p>')
        html.append('<p><strong>Grade A:</strong> Used, no scratches at all, fully functional.</p>')
        html.append('<p><strong>Grade B:</strong> Used, light wear, no cracks, fully functional.</p>')
        html.append('<p><strong>Grade C:</strong> Used, visible scratches or hairline crack/chip, fully functional.</p>')
        html.append('<p><strong>Grade D:</strong> Used, cracked screen, bad LCD, dead pixels, or heavy damage but powers on.</p>')
        html.append('<p><strong>DOA:</strong> Dead on arrival — won\'t power on or has water damage.</p>')
    html.append('</body></html>')
    return "\n".join(html)

def render_aggregate(category_html_dict):
    """Build aggregate prices.html from per-category bodies."""
    today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = []
    html.append('<!DOCTYPE html>')
    html.append('<html lang="en"><head><meta charset="UTF-8"><title>BLT Trading — Mobile Device Price Sheet</title></head>')
    html.append('<body>')
    html.append('<h1>BLT Trading — Mobile Device Price Sheet (Aggregate)</h1>')
    html.append('<p><strong>Note:</strong> Per-category indices live at welcome.html, iphone-new.html, iphone-used.html, ipad.html, samsung.html, watch.html, airpods.html, gaming.html on the same repo.</p>')
    html.append(f'<p><strong>Last Updated:</strong> {today_utc}</p>')
    html.append('')
    for cat in ["welcome", "iphone-new", "iphone-used", "ipad", "samsung", "watch", "airpods", "gaming"]:
        body = category_html_dict.get(cat, "")
        # Extract <body>...</body> content from each
        m = re.search(r"<body>(.*)</body>", body, re.DOTALL)
        if m:
            html.append(f'<!-- {cat}.html body -->')
            html.append(m.group(1).strip())
    html.append('</body></html>')
    return "\n".join(html)

def main():
    src = Path(SOURCE).read_text()
    records = parse_lines(src)
    print(f"Parsed {len(records)} price records.")

    # Bucket by category
    by_cat = defaultdict(list)
    for r in records:
        cat, _ = categorize(r)
        by_cat[cat].append(r)

    for cat, items in by_cat.items():
        print(f"  {cat}: {len(items)} entries")

    # Render each category
    output = {}
    output["iphone-new"] = render_category_html(
        "iphone-new", "BLT Trading — iPhone Buying Prices (NEW Sealed)",
        by_cat.get("iphone-new", []),
        "NEW iPhones (Sealed, Open Box, Sealed Activated)."
    )
    output["iphone-used"] = render_category_html(
        "iphone-used", "BLT Trading — iPhone Buying Prices (USED)",
        by_cat.get("iphone-used", []),
        "USED iPhones (Grade A through DOA, plus SWAP HSO)."
    )
    output["ipad"] = render_category_html(
        "ipad", "BLT Trading — iPad Buying Prices",
        by_cat.get("ipad", []),
        "iPads (NEW Sealed and USED grades)."
    )
    output["samsung"] = render_category_html(
        "samsung", "BLT Trading — Samsung Buying Prices",
        by_cat.get("samsung", []),
        "Samsung Galaxy phones (NEW and USED)."
    )
    output["watch"] = render_category_html(
        "watch", "BLT Trading — Apple Watch Buying Prices",
        by_cat.get("watch", []),
        "Apple Watches (NEW and USED)."
    )
    output["airpods"] = render_category_html(
        "airpods", "BLT Trading — AirPods Buying Prices",
        by_cat.get("airpods", []),
        "AirPods (NEW and USED)."
    )
    output["gaming"] = render_category_html(
        "gaming", "BLT Trading — Gaming Console Buying Prices",
        by_cat.get("gaming", []),
        "Gaming consoles (NEW and USED)."
    )
    output["welcome"] = render_welcome_html(src)
    output["prices"] = render_aggregate(output)

    # Write all files
    for name, content in output.items():
        outpath = OUTDIR / f"{name}.html"
        outpath.write_text(content)
        size_kb = len(content) / 1024
        # Count <p> tags
        ptags = content.count("<p>")
        print(f"WROTE {outpath}  {size_kb:.1f}KB  {ptags} <p> tags")

if __name__ == "__main__":
    main()
