#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_inventory.py

Make SC3ML safe for ObsPy by ensuring every <station> element has numeric
attribute values for latitude/longitude/elevation (namespace- and case-insensitive).

Also optionally normalizes <stream> azimuth/dip/sampleRate.

Usage:
  python check_inventory.py --in seiscomp_inventory.xml --out fixed_sc3ml.xml [--fix-channels]
"""

import argparse
import gzip
import io
import xml.etree.ElementTree as ET
from pathlib import Path

def local(tag: str) -> str:
    """Return local (namespace-stripped) tag name in lowercase."""
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    return tag.lower()

def get_child(elem, name_lc: str):
    """Find first child by local name (case-insensitive)."""
    for c in list(elem):
        if local(c.tag) == name_lc:
            return c
    return None

def get_child_text(elem, name_lc: str) -> str:
    c = get_child(elem, name_lc)
    return (c.text or "").strip() if c is not None else ""

def ensure_child(elem, name_lc: str):
    c = get_child(elem, name_lc)
    if c is None:
        # Reuse parent's namespace if any
        ns = ""
        if "}" in elem.tag:
            ns = elem.tag.split("}", 1)[0] + "}"
        c = ET.SubElement(elem, ns + name_lc)
    return c

def is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception:
        return False

def norm_num_or_default(s: str, default: str = "0.0") -> str:
    return s if is_float(s) else default

def read_xml_maybe_gz(path: Path) -> ET.ElementTree:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rb") as fh:
            data = fh.read()
        return ET.parse(io.BytesIO(data))
    return ET.parse(path)

def write_xml(path: Path, tree: ET.ElementTree):
    if path.suffix.lower() == ".gz":
        buf = io.BytesIO()
        tree.write(buf, encoding="UTF-8", xml_declaration=True)
        with gzip.open(path, "wb") as gz:
            gz.write(buf.getvalue())
    else:
        tree.write(path, encoding="UTF-8", xml_declaration=True)

def force_station_numeric_attrs(sta) -> bool:
    """
    Ensure <station> has numeric attributes latitude/longitude/elevation.
    Returns True if changed / ensured.
    """
    # Pull from attribute or child, then coerce to numeric string
    lat = (sta.attrib.get("latitude", "") or get_child_text(sta, "latitude")).strip()
    lon = (sta.attrib.get("longitude", "") or get_child_text(sta, "longitude")).strip()
    ele = (sta.attrib.get("elevation", "") or get_child_text(sta, "elevation")).strip()

    lat = norm_num_or_default(lat, "0.0")
    lon = norm_num_or_default(lon, "0.0")
    ele = norm_num_or_default(ele, "0.0")

    # Set attributes (ObsPy reads attributes)
    changed = False
    if sta.attrib.get("latitude") != lat:
        sta.set("latitude", lat); changed = True
    if sta.attrib.get("longitude") != lon:
        sta.set("longitude", lon); changed = True
    if sta.attrib.get("elevation") != ele:
        sta.set("elevation", ele); changed = True

    # Mirror into child elements (defensive)
    ensure_child(sta, "latitude").text = lat
    ensure_child(sta, "longitude").text = lon
    ensure_child(sta, "elevation").text = ele

    # Ensure station code attribute if only present as child
    if "code" not in sta.attrib or not sta.attrib["code"]:
        sc = get_child_text(sta, "code")
        if sc:
            sta.set("code", sc)
            changed = True

    return changed

def fix_stream(stream):
    # azimuth / dip defaults
    for nm in ("azimuth", "dip"):
        e = ensure_child(stream, nm)
        if not is_float((e.text or "").strip()):
            e.text = "0.0"
    # sampleRate: from sampleRate or numerator/denominator
    sr = get_child(stream, "samplerate")
    if sr is None or not is_float((sr.text or "").strip()):
        num = get_child_text(stream, "sampleratenumerator")
        den = get_child_text(stream, "sampleratedenominator")
        try:
            fnum = float(num) if is_float(num) else 1.0
            fden = float(den) if is_float(den) and float(den) != 0.0 else 1.0
            val = fnum / fden
        except Exception:
            val = 1.0
        if sr is None:
            sr = ensure_child(stream, "samplerate")
        sr.text = f"{val:.6f}"
    # ensure code attribute
    if "code" not in stream.attrib or not stream.attrib["code"]:
        cc = get_child_text(stream, "code")
        if cc:
            stream.set("code", cc)

def main():
    ap = argparse.ArgumentParser(description="Force numeric station attrs in SC3ML (namespace/case-insensitive).")
    ap.add_argument("--in", dest="infile", required=True, help="Input SC3ML (.xml or .xml.gz)")
    ap.add_argument("--out", dest="outfile", required=True, help="Output SC3ML (.xml or .xml.gz)")
    ap.add_argument("--fix-channels", action="store_true", help="Also normalize stream azimuth/dip/sampleRate")
    args = ap.parse_args()

    inp = Path(args.infile); outp = Path(args.outfile)
    if not inp.exists():
        raise SystemExit(f"Input not found: {inp}")

    tree = read_xml_maybe_gz(inp)
    root = tree.getroot()

    stations_total = 0
    stations_fixed = 0
    streams_touched = 0

    # Walk networks/stations/sensorlocations/streams with namespace/case independence
    for net in root.iter():
        if local(net.tag) != "network":
            continue
        # Ensure network code attr from child if missing
        if "code" not in net.attrib or not net.attrib["code"]:
            nc = get_child_text(net, "code")
            if nc:
                net.set("code", nc)
        for sta in list(net):
            if local(sta.tag) != "station":
                continue
            stations_total += 1
            if force_station_numeric_attrs(sta):
                stations_fixed += 1
            if args.fix_channels:
                for sl in list(sta):
                    if local(sl.tag) != "sensorlocation":
                        continue
                    if "code" not in sl.attrib or not sl.attrib["code"]:
                        lc = get_child_text(sl, "code")
                        if lc: sl.set("code", lc)
                    for stream in list(sl):
                        if local(stream.tag) != "stream":
                            continue
                        fix_stream(stream); streams_touched += 1

    write_xml(outp, tree)

    # Verify result file contains stations with numeric attrs
    tree2 = read_xml_maybe_gz(outp)
    root2 = tree2.getroot()
    bad = 0
    example = None
    for net in root2.iter():
        if local(net.tag) != "network":
            continue
        for sta in list(net):
            if local(sta.tag) != "station":
                continue
            lat = (sta.attrib.get("latitude") or "").strip()
            lon = (sta.attrib.get("longitude") or "").strip()
            ele = (sta.attrib.get("elevation") or "").strip()
            if not (is_float(lat) and is_float(lon) and is_float(ele)):
                bad += 1
            elif example is None:
                example = (net.attrib.get("code",""), sta.attrib.get("code",""), lat, lon, ele)

    print(f"Stations found: {stations_total}, stations fixed: {stations_fixed}, streams touched: {streams_touched}")
    if example:
        n, s, la, lo, el = example
        print(f"Example station OK: Network={n} Station={s} lat={la} lon={lo} elev={el}")
    if bad:
        print(f"WARNING: {bad} station(s) still missing numeric attrs.")

if __name__ == "__main__":
    main()

