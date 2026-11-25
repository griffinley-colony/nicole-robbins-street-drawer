#!/usr/bin/env python3
"""draw_streets.py: draw a US city's streets as plain black lines from Census Bureau road data.

Usage:
    python draw_streets.py --lat 42.3601 --lon -71.0589 --km 12 --out boston.png
    python draw_streets.py --lat 42.3601 --lon -71.0589 --km 12 --out boston.png --from-files a.json b.json c.json

The roads come from the U.S. Census Bureau's TIGERweb map service. Three layers are asked for
(primary roads, secondary roads, local roads), one request at a time, each on the same square
box centred on your point. With --from-files the script reads query results you saved earlier
and asks the server for nothing.

Needs Python 3 and matplotlib. Everything else is the standard library.
"""
import argparse
import json
import math
import sys
import time
import urllib.request

SERVICE = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer"
LAYERS = [(2, "primary roads"), (6, "secondary roads"), (8, "local roads")]
USER_AGENT = ("draw_streets.py/1.0 (draws one city's roads; "
              "https://github.com/griffinley-colony/nicole-robbins-street-drawer)")
KM_PER_DEGREE_LAT = 110.9

# Line width in points for each Census road class (MTFCC). Heavier roads draw a little thicker.
WIDTH = {
    "S1100": 1.4,   # primary road: interstates and other limited-access highways
    "S1200": 1.1,   # secondary road: US and state highways
    "S1630": 0.6,   # ramp
    "S1400": 0.45,  # local street
    "S1640": 0.25,  # service drive
    "S1730": 0.25,  # alley
    "S1740": 0.25,  # private road for service vehicles
    "S1500": 0.25,  # vehicular trail
}
LOCAL_WIDTH = WIDTH["S1400"]  # a road with no class, or a class not listed, draws as a local street
SKIP = {"S1710", "S1720", "S1750", "S1780", "S1820", "S1830"}  # walkways, stairs, parking lots, bike and bridle paths


def box(lat, lon, km):
    """A square box km wide around the point, as (lon_min, lat_min, lon_max, lat_max)."""
    dlat = km / 2 / KM_PER_DEGREE_LAT
    dlon = dlat / math.cos(math.radians(lat))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def query_url(layer, bbox):
    """The TIGERweb query for every road of one layer that touches the box, as GeoJSON."""
    geometry = "%.4f,%.4f,%.4f,%.4f" % bbox
    return ("%s/%d/query?where=1%%3D1&geometry=%s&geometryType=esriGeometryEnvelope&inSR=4326"
            "&spatialRel=esriSpatialRelIntersects&outFields=MTFCC,NAME&outSR=4326"
            "&geometryPrecision=5&f=geojson" % (SERVICE, layer, geometry))


def download(bbox):
    """Asks for the three layers one after another, with a pause between requests."""
    results = []
    for i, (layer, name) in enumerate(LAYERS):
        if i:
            time.sleep(2)
        url = query_url(layer, bbox)
        print("downloading %s ..." % name)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=180) as response:
            results.append((name, json.loads(response.read().decode("utf-8"))))
    return results


def read_files(paths):
    results = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            results.append((path, json.load(f)))
    return results


def collect_roads(results):
    """Every drawable road as (width, [(lon, lat), ...]). A line that comes twice is drawn once."""
    roads, seen = [], set()
    for name, data in results:
        if not isinstance(data, dict):
            sys.exit("%s: not a query result" % name)
        if "error" in data:
            sys.exit("%s: the server answered with an error: %s" % (name, json.dumps(data["error"])))
        if data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"):
            print("warning: %s came back cut short by the server's record limit; try a smaller --km" % name,
                  file=sys.stderr)
        for feature in data.get("features", []):
            geometry = feature.get("geometry") or {}
            if geometry.get("type") == "LineString":
                parts = [geometry.get("coordinates") or []]
            elif geometry.get("type") == "MultiLineString":
                parts = geometry.get("coordinates") or []
            else:
                continue
            code = str((feature.get("properties") or {}).get("MTFCC") or "").strip().upper()
            if code in SKIP:
                continue
            width = WIDTH.get(code, LOCAL_WIDTH)
            for part in parts:
                points = tuple((float(p[0]), float(p[1])) for p in part)
                if len(points) < 2 or points in seen:
                    continue
                seen.add(points)
                roads.append((width, points))
    return roads


def draw(roads, lat, lon, km, out, size):
    """Black lines on white, square, no labels. North is up and a kilometre is the same length both ways."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    km_x = math.cos(math.radians(lat)) * 111.32
    km_y = KM_PER_DEGREE_LAT
    lines = [[((x - lon) * km_x, (y - lat) * km_y) for x, y in points] for _, points in roads]
    widths = [width for width, _ in roads]

    figure = plt.figure(figsize=(10, 10))
    axes = figure.add_axes([0, 0, 1, 1])
    axes.add_collection(LineCollection(lines, linewidths=widths, colors="black",
                                       capstyle="round", joinstyle="round"))
    axes.set_xlim(-km / 2, km / 2)
    axes.set_ylim(-km / 2, km / 2)
    axes.set_aspect("equal")
    axes.axis("off")
    figure.savefig(out, dpi=size / 10, facecolor="white")
    plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Draw a US city's streets as plain black lines.")
    parser.add_argument("--lat", type=float, required=True, help="latitude of the centre, like 42.3601")
    parser.add_argument("--lon", type=float, required=True, help="longitude of the centre, like -71.0589")
    parser.add_argument("--km", type=float, default=12, help="width of the square in kilometres (default 12)")
    parser.add_argument("--out", required=True, help="the PNG to write, like boston.png")
    parser.add_argument("--size", type=int, default=2000, help="picture width and height in pixels (default 2000)")
    parser.add_argument("--from-files", nargs="+", metavar="FILE",
                        help="draw from saved query results instead of downloading")
    args = parser.parse_args(argv)
    if not 0 < args.km <= 50:
        parser.error("--km should be more than 0 and at most 50")

    bbox = box(args.lat, args.lon, args.km)
    results = read_files(args.from_files) if args.from_files else download(bbox)
    roads = collect_roads(results)
    if not roads:
        sys.exit("no roads found in that box")
    draw(roads, args.lat, args.lon, args.km, args.out, args.size)
    print("drew %d road lines, wrote %s" % (len(roads), args.out))


if __name__ == "__main__":
    main()
