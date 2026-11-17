from shapely.geometry import Point, Polygon
import tracker.lot_polygons as raw

LOT_POLYGONS_RAW = {
    "Lot 1":  raw.LOT_1,
    "Lot 2":  raw.LOT_2,
    "Lot 3":  raw.LOT_3,
    "Lot 4":  raw.LOT_4,
    "Lot 5":  raw.LOT_5,
    "Lot 6":  raw.LOT_6,
    "Lot 7":  raw.LOT_7,
    "Lot 8":  raw.LOT_8,
    "Lot 9":  raw.LOT_9,
    "Lot 10_11": raw.LOT_10_11,
    "Lot 12": raw.LOT_12,
    "Lot 13": raw.LOT_13,
    "Lot 14": raw.LOT_14,
    "Lot 15": raw.LOT_15,
    "Lot 16W": raw.LOT_16W,
    "Lot 16N": raw.LOT_16N,
    "Lot 18": raw.LOT_18,
    "Lot 19": raw.LOT_19,
    "Lot 20": raw.LOT_20,
    "Lot 22": raw.LOT_22,
    "Lot 23": raw.LOT_23,
    "Lot 24": raw.LOT_24,
    "Lot 26": raw.LOT_26,
    "Lot 29": raw.LOT_29,
    "Lot 30": raw.LOT_30,
    "Lot 31": raw.LOT_31,
    "Lot 32": raw.LOT_32,
    "Lot 33": raw.LOT_33,
    "Lot 34": raw.LOT_34,
    "Lot 36": raw.LOT_36,
    "Lot 40": raw.LOT_40,
    "Lot 40G": raw.LOT_40G,
    "Lot 41": raw.LOT_41,
    "Lot 42": raw.LOT_42,
    "Lot 43": raw.LOT_43,
    "Lot 44": raw.LOT_44,
    "Lot 45": raw.LOT_45,
    "Lot 46": raw.LOT_46,
    "Lot 47": raw.LOT_47,
    "Lot 48": raw.LOT_48,
    "Lot 49": raw.LOT_49,
    "Lot 50": raw.LOT_50,
    "Lot 52B": raw.LOT_52B,
    "Lot 52WM": raw.LOT_52WM,
    "Lot 53": raw.LOT_53,
    "Lot 54": raw.LOT_54,
    "Lot 55": raw.LOT_55,
    "Lot 56": raw.LOT_56,
    "Lot 57": raw.LOT_57,
    "Lot 59": raw.LOT_59,
    "Lot 61": raw.LOT_61,
    "B67": raw.LOT_B67,
    "CFA": raw.CFA,
    "MCD": raw.MCD,
    "CANES": raw.CANES
}

# Single build, coordinate flip applied here
POLYGONS = {
    name: Polygon([(lng, lat) for lat, lng in coords])
    for name, coords in LOT_POLYGONS_RAW.items()
    if coords
}

def get_lot(lat, lng):
    point = Point(lng, lat)
    for lot_name, polygon in POLYGONS.items():
        if polygon.contains(point):
            return lot_name
    return None