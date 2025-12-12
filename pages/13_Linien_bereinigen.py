import json
import math
import os
import sys
from typing import Any, Dict, List, Tuple

import streamlit as st

# Optional geometry tooling
try:
    from shapely.geometry import LineString, MultiLineString
    from shapely.geometry import mapping
    from shapely.ops import transform as shapely_transform
    from shapely.ops import unary_union

    SHAPELY_AVAILABLE = True
except Exception:
    SHAPELY_AVAILABLE = False

try:
    from pyproj import CRS, Transformer

    PYPROJ_AVAILABLE = True
except Exception:
    PYPROJ_AVAILABLE = False

# Allow imports from src if needed
def add_repo_to_path() -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.append(repo_root)


add_repo_to_path()

st.set_page_config(page_title="Linien bereinigen (PolylineOffset Fix)", layout="wide")
st.title("🚧 Linien bereinigen (PolylineOffset Fix)")
st.markdown(
    "Entfernt sehr kurze Segmente aus LineStrings/MultiLineStrings und bietet optional eine Douglas-Peucker-Vereinfachung."
)


def haversine_m(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Great-circle distance between two lon/lat points in meters."""
    lon1, lat1 = p1
    lon2, lat2 = p2
    R = 6371000  # mean Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def ensure_min_points(coords: List[List[float]]) -> List[List[float]]:
    if len(coords) >= 2:
        return coords
    if not coords:
        return []
    # Duplicate first point if only one remains to avoid degenerating
    return [coords[0], coords[-1]]


def clean_linestring(
    coords: List[List[float]], min_seg_m: float, keep_ends: bool = True
) -> Tuple[List[List[float]], int, int]:
    """Remove consecutive points closer than min_seg_m (meters). Returns cleaned coords and point counts."""
    if not coords:
        return [], 0, 0

    kept: List[List[float]] = [coords[0]]
    for idx, pt in enumerate(coords[1:], start=1):
        is_last = idx == len(coords) - 1
        dist = haversine_m((kept[-1][0], kept[-1][1]), (pt[0], pt[1]))
        if dist >= min_seg_m or (keep_ends and is_last):
            kept.append(pt)
    cleaned = ensure_min_points(kept)
    return cleaned, len(coords), len(cleaned)


def infer_utm_crs(lon: float, lat: float) -> CRS:
    zone = int((lon + 180) // 6) + 1
    north = lat >= 0
    epsg_code = 32600 + zone if north else 32700 + zone
    return CRS.from_epsg(epsg_code)


def simplify_geometry(geom, simplify_m: float):
    if not SHAPELY_AVAILABLE or not PYPROJ_AVAILABLE:
        return geom, False

    if simplify_m <= 0:
        return geom, False

    try:
        lon, lat = geom.coords[0]
        target_crs = infer_utm_crs(lon, lat)
        transformer_to = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
        transformer_back = Transformer.from_crs(target_crs, "EPSG:4326", always_xy=True)

        projected = shapely_transform(transformer_to.transform, geom)
        simplified = projected.simplify(simplify_m, preserve_topology=False)
        restored = shapely_transform(transformer_back.transform, simplified)

        if restored.geom_type == "LineString" and len(restored.coords) >= 2:
            return restored, True
        if restored.geom_type == "MultiLineString":
            parts = [ls for ls in restored.geoms if len(ls.coords) >= 2]
            if parts:
                return MultiLineString(parts), True
    except Exception:
        return geom, False
    return geom, False


def process_geometry(
    geometry: Dict[str, Any], min_seg_m: float, simplify_m: float, keep_ends: bool
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    stats = {
        "lines": 0,
        "points_in": 0,
        "points_out": 0,
        "changed": 0,
    }

    gtype = geometry.get("type")

    def handle_linestring(coords: List[List[float]]):
        cleaned, pin, pout = clean_linestring(coords, min_seg_m, keep_ends)
        stats["lines"] += 1
        stats["points_in"] += pin
        stats["points_out"] += pout
        geom_obj = None
        if SHAPELY_AVAILABLE:
            try:
                geom_obj = LineString(cleaned)
            except Exception:
                geom_obj = None
        simplified_geom = geom_obj
        simplified_used = False
        if simplify_m > 0 and geom_obj is not None:
            simplified_geom, simplified_used = simplify_geometry(geom_obj, simplify_m)
        if simplified_used and isinstance(simplified_geom, LineString):
            new_coords = [list(pt) for pt in simplified_geom.coords]
            stats["points_out"] -= pout
            stats["points_out"] += len(new_coords)
            return new_coords, pin != len(new_coords) or pin != pout
        return cleaned, pin != pout

    if gtype == "LineString":
        coords = geometry.get("coordinates", [])
        new_coords, changed = handle_linestring(coords)
        stats["changed"] += int(changed)
        return {"type": "LineString", "coordinates": new_coords}, stats

    if gtype == "MultiLineString":
        out_lines = []
        changed_any = False
        for coords in geometry.get("coordinates", []):
            new_coords, changed = handle_linestring(coords)
            out_lines.append(new_coords)
            changed_any = changed_any or changed
        stats["changed"] += int(changed_any)
        return {"type": "MultiLineString", "coordinates": out_lines}, stats

    return geometry, stats


uploaded = st.file_uploader("GeoJSON (FeatureCollection) hochladen", type=["geojson", "json"])

min_seg_m = st.number_input(
    "Minimale Segmentlänge (m) – Punkte mit kürzerem Abstand werden entfernt",
    min_value=0.0,
    max_value=10.0,
    value=2.0,
    step=0.1,
)
simplify_m = st.number_input(
    "Optional: Simplify (Douglas-Peucker, Meter)",
    min_value=0.0,
    max_value=20.0,
    value=0.0,
    step=0.5,
)
keep_ends = st.checkbox("Start- und Endpunkte beibehalten", value=True)
merge_features = st.checkbox("Linien-Features zusammenfassen (Union)", value=False)

if simplify_m > 0 and (not SHAPELY_AVAILABLE or not PYPROJ_AVAILABLE):
    st.warning(
        "Simplify benötigt shapely und pyproj; mindestens ein Paket fehlt. Der Schritt wird übersprungen."
    )

process_clicked = st.button("Bereinigen")

if process_clicked:
    if not uploaded:
        st.error("Bitte eine GeoJSON-Datei hochladen.")
    else:
        try:
            data = json.loads(uploaded.read().decode("utf-8"))
        except Exception as exc:
            st.error(f"GeoJSON konnte nicht gelesen werden: {exc}")
            data = None

        if data:
            if data.get("type") != "FeatureCollection" or "features" not in data:
                st.error("Die Datei muss eine GeoJSON FeatureCollection enthalten.")
            else:
                cleaned_features = []
                aggregate = {
                    "features_total": len(data["features"]),
                    "lines_total": 0,
                    "points_in_total": 0,
                    "points_out_total": 0,
                    "features_changed": 0,
                }

                for feature in data.get("features", []):
                    geom = feature.get("geometry")
                    if not geom:
                        cleaned_features.append(feature)
                        continue
                    new_geom, geom_stats = process_geometry(
                        geom, min_seg_m=min_seg_m, simplify_m=simplify_m, keep_ends=keep_ends
                    )
                    aggregate["lines_total"] += geom_stats["lines"]
                    aggregate["points_in_total"] += geom_stats["points_in"]
                    aggregate["points_out_total"] += geom_stats["points_out"]
                    aggregate["features_changed"] += geom_stats["changed"]

                    new_feature = feature.copy()
                    new_feature["geometry"] = new_geom
                    cleaned_features.append(new_feature)

                final_features = cleaned_features

                if merge_features:
                    if not SHAPELY_AVAILABLE:
                        st.warning("Shapely ist nicht verfügbar; Zusammenfassung wird übersprungen.")
                    else:
                        line_geoms = []
                        other_features = []
                        for feat in cleaned_features:
                            geom = feat.get("geometry") or {}
                            gtype = geom.get("type")
                            coords = geom.get("coordinates")
                            try:
                                if gtype == "LineString":
                                    line_geoms.append(LineString(coords))
                                elif gtype == "MultiLineString":
                                    line_geoms.append(MultiLineString(coords))
                                else:
                                    other_features.append(feat)
                            except Exception:
                                other_features.append(feat)

                        if line_geoms:
                            try:
                                merged = unary_union(line_geoms)
                                if merged.is_empty:
                                    st.warning("Union der Linien ist leer – übersprungen.")
                                else:
                                    merged_geom = merged
                                    if merged_geom.geom_type == "GeometryCollection":
                                        merged_parts = [g for g in merged_geom.geoms if g.geom_type in {"LineString", "MultiLineString"}]
                                        if merged_parts:
                                            merged_geom = unary_union(merged_parts)
                                    geojson_geom = mapping(merged_geom)
                                    merged_feature = {"type": "Feature", "properties": {}, "geometry": geojson_geom}
                                    final_features = other_features + [merged_feature]
                            except Exception as exc:
                                st.warning(f"Union der Linien fehlgeschlagen: {exc}")

                cleaned_geojson = {"type": "FeatureCollection", "features": final_features}

                st.success("Bereinigung abgeschlossen.")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Features gesamt", aggregate["features_total"])
                col2.metric("Linien gesamt", aggregate["lines_total"])
                col3.metric("Punkte vorher", aggregate["points_in_total"])
                col4.metric("Punkte nachher", aggregate["points_out_total"])
                col5.metric("Geänderte Features", aggregate["features_changed"])

                base_name = os.path.splitext(uploaded.name)[0]
                out_name = f"{base_name}.cleaned.geojson"
                st.download_button(
                    "Bereinigte GeoJSON herunterladen",
                    data=json.dumps(cleaned_geojson, ensure_ascii=False, indent=2),
                    file_name=out_name,
                    mime="application/geo+json",
                )

                with st.expander("Bereinigte GeoJSON Vorschau"):
                    st.json(cleaned_geojson)
