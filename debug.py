from shapely.geometry import Point, Polygon
from patrol_center.tracker.lot_polygons import LOT_22

coords = LOT_22


# Build with the fix
poly = Polygon([(lng, lat) for lat, lng in coords])
print("Centroid:", poly.centroid)
print("Bounds:", poly.bounds)

# Test the point
test_point = (40.2530008557265, -111.64931697954968)  # This point is inside Lot 22
p = Point(test_point[1], test_point[0])  # Point(lng, lat)
print("Contains:", poly.contains(p), "for lot 22")