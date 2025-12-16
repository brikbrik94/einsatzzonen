import streamlit as st
import geopandas as gpd
import pandas as pd
import os
import sys
from datetime import datetime

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import (
    select_files_dialog,
    select_folder_dialog,
    load_geodataframe_raw
)

# --- SETUP ---
st.set_page_config(page_title="Resolver", layout="wide")
st.title("🧩 Einsatzzonen Resolver (Step 3)")
st.markdown("Fügt Teil-Dateien zusammen, standardisiert Namen und löst Grenzen auf.")

# --- STATE ---
if "res_input_files" not in st.session_state: st.session_state["res_input_files"] = []
if "res_output_folder" not in st.session_state: st.session_state["res_output_folder"] = os.getcwd()

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Input")
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("➕"):
            new = select_files_dialog()
            if new:
                # Duplikate vermeiden
                current_set = set(st.session_state["res_input_files"])
                for f in new:
                    if f not in current_set:
                        st.session_state["res_input_files"].append(f)
                st.rerun()
    with c2:
        if st.button("🗑️"): 
            st.session_state["res_input_files"] = []
            st.rerun()

    if st.session_state["res_input_files"]:
        st.info(f"{len(st.session_state['res_input_files'])} Dateien")
        with st.expander("Dateiliste"):
            for f in st.session_state["res_input_files"]:
                st.caption(os.path.basename(f))
    else:
        st.warning("Keine Dateien")

    st.markdown("---")
    st.header("2. Output")
    
    c3, c4 = st.columns([3, 1])
    with c4:
        if st.button("📂", key="out"):
            d = select_folder_dialog()
            if d: 
                st.session_state["res_output_folder"] = d
                st.rerun()
    with c3:
        st.text_input("Pfad", st.session_state["res_output_folder"], key="res_out_display")
        
    out_filename = st.text_input("Dateiname", "Final_Merged_Zones.geojson")

# --- MAIN LOGIC ---

if st.session_state["res_input_files"]:
    st.header("3. Konfiguration & Merge")
    
    # 1. ANALYSE (Erste Datei lesen um Spalten zu finden)
    first_file = st.session_state["res_input_files"][0]
    try:
        # Wir laden nur eine Zeile für die Spalten-Vorschau
        preview = gpd.read_file(first_file, rows=1)
        available_cols = [c for c in preview.columns if c != 'geometry']
    except Exception as e:
        st.error(f"Konnte Datei nicht lesen: {e}")
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🏷️ Tag Mapping")
        st.info("Welches Feld enthält den Namen der Wache (für das Zusammenfügen)?")
        
        # Smart Default Selection
        def_idx = 0
        preferred = ["zone_label", "alt_name", "station_name", "name"]
        for p in preferred:
            if p in available_cols:
                def_idx = available_cols.index(p)
                break
        
        target_col = st.selectbox("Quell-Spalte auswählen", available_cols, index=def_idx)
        st.caption(f"ℹ️ Der Inhalt von `{target_col}` wird in die Standard-Spalte `name` geschrieben.")

    with c2:
        st.subheader("⚙️ Optionen")
        do_dissolve = st.checkbox("Grenzen auflösen (Dissolve)", value=True, help="Entfernt Grenzen zwischen gleichen Zonen (z.B. über Bezirke hinweg).")
        keep_attrs = st.checkbox("Andere Attribute behalten", value=True, help="Wenn aktiv, werden Tags (Adresse, etc.) beibehalten (erster gefundener Wert pro Zone).")

    st.markdown("---")

    if st.button("🚀 Dateien fusionieren", type="primary"):
        prog = st.progress(0)
        status = st.empty()
        
        try:
            gdfs = []
            files = st.session_state["res_input_files"]
            
            # A. Lade Schleife
            for i, fpath in enumerate(files):
                status.text(f"Lade {i+1}/{len(files)}: {os.path.basename(fpath)}")
                
                # Ohne Geometrie-Reparatur laden
                tmp = load_geodataframe_raw(fpath)
                
                # Check ob Spalte existiert
                if target_col not in tmp.columns:
                    tmp[target_col] = "Unknown"
                
                gdfs.append(tmp)
                prog.progress((i+1) / (len(files)*2))
            
            # B. Concat
            status.text("Füge Geometrien zusammen...")
            full = pd.concat(gdfs, ignore_index=True)
            
            # C. Remap Name
            status.text(f"Setze 'name' = '{target_col}'...")
            full['name'] = full[target_col].fillna("Unknown")
            
            # D. Cleanup Columns
            if not keep_attrs:
                # Nur Name und Geometrie behalten
                full = full[['name', 'geometry']]
            
            # E. Dissolve
            if do_dissolve:
                status.text("Löse Grenzen auf (Dissolve)...")
                # Sicherstellen, dass Geometrie valide ist vor Dissolve
                full['geometry'] = full.geometry.buffer(0)
                
                # Dissolve by 'name'. 
                # as_index=False sorgt dafür, dass 'name' eine Spalte bleibt.
                # Andere Spalten werden per 'first' aggregiert (erster Wert wird behalten).
                final = full.dissolve(by='name', as_index=False)
            else:
                final = full

            # F. Save
            status.text("Speichere...")
            out_p = os.path.join(st.session_state["res_output_folder"], out_filename)
            final.to_file(out_p, driver='GeoJSON')
            
            prog.progress(1.0)
            status.empty()
            st.balloons()
            st.success(f"Erfolgreich gespeichert: `{out_p}`")
            
            with st.expander("Vorschau Ergebnisse"):
                # Geometrie nicht anzeigen in Tabelle, dauert zu lange
                st.dataframe(final.drop(columns='geometry', errors='ignore').head(20))

        except Exception as e:
            st.error(f"Fehler: {e}")
            # Optional: Stacktrace für Debugging
            # import traceback
            # st.text(traceback.format_exc())

else:
    st.info("👈 Bitte links Dateien auswählen.")