"""
Zentrale Werkzeugkiste für die Einsatzzonen-Suite.
Beinhaltet:
1. Färbe-Algorithmus (4-Farben-Problem)
2. Datei-Dialoge (Tkinter Wrapper)
3. Geometrie-Reparatur & IO
4. Config-Management
"""

import os
import json
import logging
import tkinter as tk
from tkinter import filedialog
from typing import Dict, Any, Tuple, List, Optional

import geopandas as gpd
import networkx as nx
import libpysal
import pandas as pd

# Logger
logger = logging.getLogger(__name__)

# --- 1. CONFIG MANAGEMENT ---
def load_config(filepath: str) -> Dict[str, Any]:
    """Lädt eine JSON Konfiguration sicher."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Config Error: {e}")
            return {}
    return {}

def save_config(filepath: str, data: Dict[str, Any]):
    """Speichert eine JSON Konfiguration."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Save Config Error: {e}")

# --- 2. GUI DIALOGE (TKINTER) ---
# Ersetzt die vielen Zeilen in deinen Pages
def select_file_dialog(title: str = "Datei wählen", filetypes: List[Tuple[str, str]] = None) -> str:
    if filetypes is None:
        filetypes = [("GeoJSON", "*.geojson"), ("JSON", "*.json")]
    root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1)
    f = filedialog.askopenfilename(title=title, filetypes=filetypes)
    root.destroy()
    return f

def select_files_dialog(title: str = "Dateien wählen") -> List[str]:
    root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1)
    files = filedialog.askopenfilenames(title=title, filetypes=[("GeoJSON", "*.geojson")])
    root.destroy()
    return list(files)

def select_folder_dialog(title: str = "Ordner wählen") -> str:
    root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1)
    d = filedialog.askdirectory(title=title)
    root.destroy()
    return d

# --- 3. GEOMETRIE & IO ---

def load_geodataframe_raw(path: str) -> gpd.GeoDataFrame:
    """
    Läd GeoJSON ohne Geometrie-Reparatur.
    Ideal für Tools, die nur Attribute bearbeiten (z.B. Streamlit-General-Splitter).
    """
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf.set_crs(epsg=4326, inplace=True)
    return gdf


def load_geodataframe(path: str) -> gpd.GeoDataFrame:
    """Lädt GeoJSON und führt IMMER eine Basis-Reparatur durch."""
    gdf = gpd.read_file(path)
    # Standardisiere CRS auf WGS84 wenn möglich, sonst lass es
    if gdf.crs is None:
        gdf.set_crs(epsg=4326, inplace=True)
    return repair_geometry(gdf)


def repair_geometry(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Führt buffer(0) aus und entfernt leere Geometrien."""
    if gdf is None or gdf.empty:
        return gdf
    gdf["geometry"] = gdf["geometry"].buffer(0)
    return gdf[~gdf.geometry.is_empty & gdf.geometry.is_valid].copy()

# --- 4. COLORING LOGIK (NEU) ---
def process_coloring(
    gdf: gpd.GeoDataFrame,
    property_name: str,
    existing_colors: Dict[str, int] = None
) -> Tuple[gpd.GeoDataFrame, Dict[str, int], Dict[str, Any]]:
    """
    Färbt Zonen basierend auf Nachbarschaft (Graph Coloring).
    """
    if gdf is None or gdf.empty:
        columns = list(getattr(gdf, "columns", []))
        if "geometry" not in columns:
            columns.append("geometry")

        empty_gdf = gpd.GeoDataFrame(columns=columns, geometry="geometry", crs=getattr(gdf, "crs", None))
        stats = {
            "num_features": 0,
            "num_colors": 0,
            "components": 0,
            "isolates": []
        }
        return empty_gdf, existing_colors or {}, stats

    # Sicherstellen, dass Geometrie sauber ist
    gdf = repair_geometry(gdf).reset_index(drop=True)

    # Nachbarschaftsgraph (Queen)
    try:
        w = libpysal.weights.Queen.from_dataframe(gdf, use_index=False)
    except Exception as e:
        logger.warning(f"Queen weights failed, fallback to KNN: {e}")
        w = libpysal.weights.KNN.from_dataframe(gdf, k=1)

    graph = w.to_networkx()

    # Färben (Greedy Strategy)
    coloring = nx.greedy_color(graph, strategy="largest_first")
    
    # +1 damit IDs bei 1 starten
    gdf["color_id"] = gdf.index.map(coloring) + 1
    
    # Mapping erstellen
    new_color_mapping = {}
    if property_name in gdf.columns:
        temp_df = gdf[[property_name, "color_id"]].drop_duplicates(subset=[property_name])
        new_color_mapping = dict(zip(temp_df[property_name], temp_df["color_id"]))

    stats = {
        "num_features": len(gdf),
        "num_colors": int(gdf["color_id"].max()),
        "components": nx.number_connected_components(graph),
        "isolates": list(nx.isolates(graph))
    }

    return gdf, new_color_mapping, stats

# --- 5. GML CONVERTER (AUSTRIA-SMART FIX) ---
def convert_gml_to_geojson(input_path: str, output_path: str, swap_mode: str = "auto") -> Tuple[bool, str]:
    """
    Konvertiert GML nach GeoJSON.
    Spezial-Feature: Prüft geographisch, ob die Daten in Österreich liegen.
    Falls sie im Jemen/Afrika liegen, werden die Achsen automatisch gedreht.
    """
    import fiona
    from shapely.ops import transform
    
    try:
        layers = fiona.listlayers(input_path)
        if not layers:
            return False, "Keine Layer in der GML-Datei gefunden."
        
        gdfs = []
        
        for layer in layers:
            try:
                # engine='fiona' ist wichtig für GML-Kurven
                gdf = gpd.read_file(input_path, layer=layer, engine="fiona")
                
                if gdf.empty:
                    continue

                # 1. CRS Fallback
                if gdf.crs is None:
                    # Annahme: OÖ Standard (MGI)
                    gdf.set_crs(epsg=31255, inplace=True)
                
                # 2. Nach WGS84 transformieren (falls nötig)
                if gdf.crs.to_string() != "EPSG:4326":
                    gdf = gdf.to_crs(epsg=4326)
                
                # 3. Geometrie bereinigen
                gdf = gdf[gdf.geometry.notnull()]
                gdf = gdf.explode(index_parts=False).reset_index(drop=True)
                
                # Z-Koordinaten entfernen (Flatten to 2D)
                # Das verhindert viele Fehler bei Web-Darstellung und Swap
                if not gdf.empty:
                    gdf.geometry = gdf.geometry.map(
                        lambda geom: transform(lambda x, y, z=None: (x, y), geom)
                    )

                if not gdf.empty:
                    gdf["source_layer"] = layer
                    gdfs.append(gdf)
                    
            except Exception as e:
                logger.warning(f"Warnung bei Layer '{layer}': {e}")

        if not gdfs:
            return False, "Konnte keine validen Geometrien extrahieren."

        full_gdf = pd.concat(gdfs, ignore_index=True)
        
        # --- AUSTRIA CHECK ---
        # Wir prüfen, ob die Daten "sinnvoll" in Österreich liegen.
        # Österreich Bounding Box ca: Lon (X) 9-17, Lat (Y) 46-49
        
        bounds = full_gdf.total_bounds # [minx, miny, maxx, maxy]
        mean_x = (bounds[0] + bounds[2]) / 2
        mean_y = (bounds[1] + bounds[3]) / 2
        
        perform_swap = False
        msg_suffix = ""

        if swap_mode == "yes":
            perform_swap = True
            msg_suffix = " (Manuell erzwungen)"
        
        elif swap_mode == "auto":
            # IST-Zustand Analyse:
            # Fall A: X ist ~48 (Breite), Y ist ~14 (Länge) -> DAS IST JEMEN -> SWAP NÖTIG
            if mean_x > 40 and mean_x < 55 and mean_y > 9 and mean_y < 20:
                perform_swap = True
                msg_suffix = " (Auto-Korrektur: Jemen-Problem erkannt & behoben)"
            
            # Fall B: X ist ~14, Y ist ~48 -> DAS IST ÖSTERREICH -> KEIN SWAP
            elif mean_x > 9 and mean_x < 20 and mean_y > 40 and mean_y < 55:
                perform_swap = False
                msg_suffix = " (Auto-Check: Daten liegen korrekt in Österreich)"
                
            # Fall C: Ganz woanders -> Wir vertrauen dem CRS, machen nichts.

        if perform_swap:
            full_gdf.geometry = full_gdf.geometry.map(
                lambda geom: transform(lambda x, y, z=None: (y, x), geom)
            )

        # Speichern
        full_gdf.to_file(output_path, driver='GeoJSON')
        
        return True, f"Erfolgreich konvertiert! ({len(full_gdf)} Features){msg_suffix}"

    except Exception as e:
        logger.error(f"GML Convert Error: {e}")
        return False, f"Fehler: {str(e)}"