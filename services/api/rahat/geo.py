import math


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def circle(lat: float, lon: float, radius_km: float, n: int = 72) -> dict:
    """GeoJSON polygon approximating a circle (good enough at city scale)."""
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        pts.append([
            lon + radius_km / (111.32 * math.cos(math.radians(lat))) * math.cos(a),
            lat + radius_km / 110.57 * math.sin(a),
        ])
    return {"type": "Polygon", "coordinates": [pts]}


def line_length_m(coords: list[list[float]]) -> float:
    return sum(km(a[1], a[0], b[1], b[0]) for a, b in zip(coords, coords[1:])) * 1000


def in_india(lat: float, lon: float) -> bool:
    # Coarse bounding box for India incl. islands; used only to reject obvious out-of-scope points.
    return 6.0 <= lat <= 37.5 and 68.0 <= lon <= 97.5
