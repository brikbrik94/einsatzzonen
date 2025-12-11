import streamlit as st
import os
import sys

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import (
    select_file_dialog, 
    select_folder_dialog, 
    convert_gml_to_geojson
)

# --- SETUP ---
st.set_page_config(page_title="GML Konverter", layout="wide", page_icon="🔄")
st.title("🔄 GML zu GeoJSON Konverter (Austria Edition)")
st.markdown("""
Konvertiert GML-Dateien in **GeoJSON (WGS84)**.
* **Auto-Repair:** Erkennt, ob Koordinaten vertauscht sind (Jemen vs. Österreich).
* **Flatten:** Entfernt automatisch Höheninformationen (3D -> 2D) für bessere Kompatibilität.
""")

# --- STATE ---
if "gml_input_path" not in st.session_state: st.session_state["gml_input_path"] = ""
if "gml_output_dir" not in st.session_state: st.session_state["gml_output_dir"] = os.getcwd()

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Input (GML)")
    if st.button("📂 GML öffnen", type="primary"):
        f = select_file_dialog("GML Datei wählen", [("GML", "*.gml"), ("XML", "*.xml"), ("Alle", "*.*")])
        if f:
            st.session_state["gml_input_path"] = f
            st.rerun()
            
    if st.session_state["gml_input_path"]:
        st.success(f"Datei: `{os.path.basename(st.session_state['gml_input_path'])}`")
    else:
        st.info("Bitte GML Datei wählen.")

    st.markdown("---")
    
    st.header("2. Output")
    if st.button("📂 Zielordner"):
        d = select_folder_dialog()
        if d:
            st.session_state["gml_output_dir"] = d
            st.rerun()
            
    st.text_input("Pfad", st.session_state["gml_output_dir"], disabled=True)


# --- MAIN ---
if st.session_state["gml_input_path"]:
    
    st.subheader("Konvertierung")
    
    c1, c2 = st.columns([1, 1])
    
    with c1:
        base_name = os.path.splitext(os.path.basename(st.session_state["gml_input_path"]))[0]
        out_filename = st.text_input("Dateiname für GeoJSON", value=f"{base_name}_converted.geojson")
        
        swap_option = st.radio(
            "Koordinaten-Logik",
            options=["Automatisch (Prüfung auf AT)", "Erzwingen (Swap)", "Deaktivieren"],
            index=0,
            horizontal=True,
            help="Prüft, ob die Koordinaten im Bereich von Österreich liegen. Falls nicht (z.B. Jemen), werden sie gedreht."
        )
        
        mode_map = {"Automatisch (Prüfung auf AT)": "auto", "Erzwingen (Swap)": "yes", "Deaktivieren": "no"}
    
    with c2:
        st.write("##") # Spacer
        if st.button("🚀 Jetzt Konvertieren", type="primary", use_container_width=True):
            
            target_path = os.path.join(st.session_state["gml_output_dir"], out_filename)
            
            with st.spinner("Analysiere Geometrie und konvertiere..."):
                success, msg = convert_gml_to_geojson(
                    st.session_state["gml_input_path"], 
                    target_path,
                    swap_mode=mode_map[swap_option]
                )
                
            if success:
                st.balloons()
                st.success(msg)
                st.info(f"Gespeichert unter: `{target_path}`")
            else:
                st.error(msg)

else:
    st.info("👈 Wähle links eine GML-Datei aus.")