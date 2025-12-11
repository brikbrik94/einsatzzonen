import streamlit as st
import geopandas as gpd
import pandas as pd
import json
import matplotlib.pyplot as plt
import sys
import os

# Pfad-Fix für Importe aus src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.geojson_tools import process_coloring, load_geodataframe, select_file_dialog

st.set_page_config(page_title="Zonen Färbung", page_icon="🎨", layout="wide")

st.title("🎨 Zonen-Färbung")
st.markdown("Färbt Zonen so ein, dass keine Nachbarn die gleiche Farbe haben.")

# --- STATE ---
if "color_gdf" not in st.session_state: st.session_state["color_gdf"] = None
if "color_filename" not in st.session_state: st.session_state["color_filename"] = ""

# --- SIDEBAR ---
with st.sidebar:
    st.header("Input")
    if st.button("📂 GeoJSON laden"):
        f = select_file_dialog("Zonen Datei wählen")
        if f:
            try:
                st.session_state["color_gdf"] = load_geodataframe(f)
                st.session_state["color_filename"] = os.path.basename(f)
                st.rerun()
            except Exception as e:
                st.error(f"Fehler: {e}")
    
    if st.session_state["color_filename"]:
        st.success(f"Geladen: {st.session_state['color_filename']}")

# --- MAIN ---
if st.session_state["color_gdf"] is not None:
    gdf = st.session_state["color_gdf"]
    
    # Spaltenauswahl (ohne Geometrie)
    cols = [c for c in gdf.columns if c != "geometry"]
    
    c1, c2 = st.columns(2)
    with c1:
        # Versuche 'name' oder 'station_name' als Default zu treffen
        def_idx = 0
        if "name" in cols: def_idx = cols.index("name")
        elif "station_name" in cols: def_idx = cols.index("station_name")
        
        target_col = st.selectbox("Welche Spalte ist der Zonen-Name?", cols, index=def_idx)
    
    with c2:
        st.info(f"Anzahl Features: {len(gdf)}")

    if st.button("🎨 Farben berechnen", type="primary"):
        with st.spinner("Berechne Topologie..."):
            try:
                colored_gdf, mapping, stats = process_coloring(gdf, target_col)
                
                st.divider()
                # Metriken
                m1, m2, m3 = st.columns(3)
                m1.metric("Benötigte Farben", stats["num_colors"])
                m2.metric("Inseln", len(stats["isolates"]))
                m3.metric("Features", stats["num_features"])

                # Plot
                fig, ax = plt.subplots(figsize=(10, 8))
                colored_gdf.plot(column="color_id", ax=ax, cmap="tab10", edgecolor="white", linewidth=0.2)
                ax.set_axis_off()
                st.pyplot(fig)

                # Downloads
                res_json = colored_gdf.to_json()
                map_json = json.dumps(mapping, indent=2, ensure_ascii=False)
                
                d1, d2 = st.columns(2)
                d1.download_button("💾 GeoJSON speichern", res_json, "zones_colored.geojson", "application/geo+json")
                d2.download_button("💾 Farb-Mapping speichern", map_json, "color_mapping.json", "application/json")

            except Exception as e:
                st.error(f"Fehler bei der Berechnung: {e}")
else:
    st.info("Bitte lade eine Datei über die Seitenleiste.")