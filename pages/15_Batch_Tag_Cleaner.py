import os
import sys

import geopandas as gpd
import streamlit as st

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import (
    select_files_dialog,
    load_geodataframe_raw,
)

# --- SETUP ---
st.set_page_config(page_title="Batch Tag Cleaner", layout="wide", page_icon="🧹")
st.title("🧹 Batch GeoJSON Tag Cleaner")
st.markdown("Bereinigt mehrere GeoJSON-Dateien auf einmal anhand eines Presets.")

# --- STATE ---
if "batch_cleaner_files" not in st.session_state:
    st.session_state["batch_cleaner_files"] = []

# --- PRESETS ---
presets = {
    "Keine Voreinstellung": None,
    "Einsatzstellen (Rettungsdienst)": [
        "id",
        "addr:city",
        "addr:housenumber",
        "addr:postcode",
        "addr:street",
        "ambulance_station:emergency_doctor",
        "ambulance_station:patient_transport",
        "brand",
        "brand:short",
        "emergency",
        "name",
        "alt_name",
        "operator",
        "short_name",
    ],
}

# --- SIDEBAR ---
with st.sidebar:
    st.header("Dateien")
    if st.button("📂 Dateien auswählen", type="primary"):
        chosen = select_files_dialog()
        if chosen:
            st.session_state["batch_cleaner_files"] = list(chosen)

    if st.session_state["batch_cleaner_files"]:
        st.success(f"{len(st.session_state['batch_cleaner_files'])} Dateien ausgewählt")
        for f in st.session_state["batch_cleaner_files"]:
            st.caption(os.path.basename(f))
    else:
        st.info("Noch keine Dateien ausgewählt.")

# --- MAIN ---
if st.session_state["batch_cleaner_files"]:
    st.divider()

    col_left, col_right = st.columns([2, 1])

    with col_right:
        st.subheader("⚙️ Einstellungen")
        preset_choice = st.selectbox(
            "Preset",
            options=list(presets.keys()),
            index=0,
            help="Legt fest, welche Tags standardmäßig erhalten bleiben.",
        )

        save_mode = st.radio(
            "Speichermodus",
            ["In-Place (Original überschreiben)", "Kopie (_clean)"],
            index=1,
            key="batch_cleaner_save_mode",
        )

    with col_left:
        st.subheader("🧾 Preset-Übersicht")
        if preset_choice == "Keine Voreinstellung":
            st.info("Bitte ein Preset auswählen, um fortzufahren.")
        else:
            st.write("**Erhalten bleiben:**")
            st.success(", ".join(presets[preset_choice]))

    st.divider()
    st.subheader("🚀 Batch bereinigen & speichern")

    if preset_choice == "Keine Voreinstellung":
        st.warning("Bitte ein Preset auswählen.")
    elif st.button("Batch bereinigen", type="primary"):
        keep_tags = set(presets[preset_choice])
        in_place = "In-Place" in save_mode

        results = []
        progress = st.progress(0)

        for idx, path in enumerate(st.session_state["batch_cleaner_files"], start=1):
            try:
                gdf = load_geodataframe_raw(path)
                cols_to_delete = [
                    c for c in gdf.columns if c != "geometry" and c not in keep_tags
                ]

                clean_gdf = gdf.drop(columns=cols_to_delete)

                dir_name = os.path.dirname(path)
                base_name = os.path.splitext(os.path.basename(path))[0]
                new_path = os.path.join(dir_name, f"{base_name}_clean.geojson")
                if in_place:
                    new_path = path

                size_old = os.path.getsize(path) / 1024
                clean_gdf.to_file(new_path, driver="GeoJSON")
                size_new = os.path.getsize(new_path) / 1024

                results.append(
                    {
                        "Datei": os.path.basename(path),
                        "Gelöscht": len(cols_to_delete),
                        "Alte Größe (KB)": round(size_old, 1),
                        "Neue Größe (KB)": round(size_new, 1),
                        "Status": "OK",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "Datei": os.path.basename(path),
                        "Gelöscht": "-",
                        "Alte Größe (KB)": "-",
                        "Neue Größe (KB)": "-",
                        "Status": f"Fehler: {exc}",
                    }
                )

            progress.progress(idx / len(st.session_state["batch_cleaner_files"]))

        st.dataframe(results, hide_index=True, width="stretch")
        st.balloons()
else:
    st.info("👈 Bitte wähle GeoJSON-Dateien aus der Seitenleiste aus.")
