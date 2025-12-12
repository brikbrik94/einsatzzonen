import os
import sys

import geopandas as gpd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.geojson_tools import process_coloring


def test_process_coloring_handles_empty_geodataframe():
    empty = gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")

    colored, color_map, stats = process_coloring(empty, "zone")

    assert colored.empty
    assert color_map == {}
    assert stats == {
        "num_features": 0,
        "num_colors": 0,
        "components": 0,
        "isolates": [],
    }
