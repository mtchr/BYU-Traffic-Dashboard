from shapely.geometry import Point, Polygon
from .lot_polygons import CAMPUS_LOTS

# Build the polygons directly from the frontend's dictionary
POLYGONS = {
    name: Polygon([(lng, lat) for lat, lng in coords])
    for name, coords in CAMPUS_LOTS.items()
    if coords and len(coords) >= 3
}

def get_lot(lat, lng):
    point = Point(lng, lat)
    for lot_name, polygon in POLYGONS.items():
        if polygon.contains(point):
            return lot_name
    return None