import streamlit as st
import os
import sys
import pandas as pd
import re

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import select_folder_dialog

# --- SETUP ---
st.set_page_config(page_title="File Renamer", layout="wide", page_icon="🏷️")
st.title("🏷️ Massen-Umbenenner")
st.markdown("""
Benenne viele Dateien gleichzeitig um. Ideal um den Output des **General Splitters** zu bereinigen.
* **Suchen & Ersetzen:** Entfernt lästige Präfixe.
* **Nummerierung:** Bereinigt Zähler.
""")

# --- STATE ---
if "renamer_dir" not in st.session_state: st.session_state["renamer_dir"] = ""
if "renamer_files" not in st.session_state: st.session_state["renamer_files"] = []

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Ordner wählen")
    if st.button("📂 Ordner öffnen", type="primary"):
        d = select_folder_dialog()
        if d:
            st.session_state["renamer_dir"] = d
            st.rerun()

    if st.session_state["renamer_dir"]:
        st.success(f"Ordner: `{os.path.basename(st.session_state['renamer_dir'])}`")
        st.caption(st.session_state['renamer_dir'])
        
        # Filter
        st.markdown("---")
        st.write("**Filter**")
        only_geojson = st.checkbox("Nur .geojson", value=True)
        
        # Dateien laden
        all_files = sorted([f for f in os.listdir(st.session_state["renamer_dir"]) if os.path.isfile(os.path.join(st.session_state["renamer_dir"], f))])
        
        if only_geojson:
            st.session_state["renamer_files"] = [f for f in all_files if f.lower().endswith(".geojson")]
        else:
            st.session_state["renamer_files"] = all_files
            
        st.info(f"{len(st.session_state['renamer_files'])} Dateien gefunden.")
    else:
        st.info("Bitte Ordner wählen.")

# --- MAIN ---
if st.session_state["renamer_dir"] and st.session_state["renamer_files"]:
    
    files = st.session_state["renamer_files"]
    
    st.subheader("2. Regeln definieren")
    
    col1, col2 = st.columns(2)
    
    with col1:
        mode = st.radio("Modus", ["Einfaches Suchen & Ersetzen", "Regex (Fortgeschritten)"], horizontal=True)
        
        search_pattern = st.text_input("Suche nach (Text/Pattern)", placeholder="z.B. Fahrweg_Linie_WGS84_converted__")
        replace_pattern = st.text_input("Ersetze durch", placeholder="z.B. Linie-")
    
    with col2:
        st.info("💡 **Tipp für Splitter-Output:**")
        st.markdown("""
        Um aus `...converted__LINIE__2.geojson` -> `Linie-2.geojson` zu machen:
        1. Kopiere den fixen Teil: `Fahrweg_Linie_WGS84_converted__LINIE__`
        2. Füge ihn links bei "Suche nach" ein.
        3. Schreibe rechts bei "Ersetze durch": `Linie-`
        """)

    # --- PREVIEW LOGIC ---
    preview_data = []
    has_changes = False
    has_conflicts = False
    new_names_set = set()
    
    for filename in files:
        new_name = filename
        
        if search_pattern:
            try:
                if mode == "Einfaches Suchen & Ersetzen":
                    new_name = filename.replace(search_pattern, replace_pattern)
                else:
                    # Regex
                    new_name = re.sub(search_pattern, replace_pattern, filename)
            except Exception as e:
                new_name = f"ERROR: {e}"

        status = "Bleibt gleich"
        if new_name != filename:
            status = "Änderung"
            has_changes = True
        
        # Konflikt Check
        if new_name in new_names_set:
            status = "⚠️ DUPLIKAT"
            has_conflicts = True
        new_names_set.add(new_name)
        
        preview_data.append({
            "Original": filename,
            "Neu": new_name,
            "Status": status
        })
    
    df = pd.DataFrame(preview_data)

    # --- ANZEIGE ---
    st.divider()
    st.subheader("3. Vorschau")
    
    # Highlighting helper
    def highlight_rows(row):
        if row["Status"] == "Änderung":
            return ['background-color: #d4edda'] * len(row) # Light Green
        elif "DUPLIKAT" in row["Status"]:
            return ['background-color: #f8d7da'] * len(row) # Light Red
        return [''] * len(row)

    st.dataframe(df.style.apply(highlight_rows, axis=1), width="stretch", height=400)
    
    # --- ACTION ---
    st.divider()
    
    c_btn, c_msg = st.columns([1, 3])
    
    with c_btn:
        btn_disabled = not has_changes or has_conflicts or not search_pattern
        if st.button("🚀 Alle umbenennen", type="primary", disabled=btn_disabled, width="stretch"):
            
            success_count = 0
            fail_count = 0
            
            base_dir = st.session_state["renamer_dir"]
            
            # Progress bar
            prog_bar = st.progress(0)
            
            for i, row in df.iterrows():
                if row["Status"] == "Änderung":
                    old_p = os.path.join(base_dir, row["Original"])
                    new_p = os.path.join(base_dir, row["Neu"])
                    
                    try:
                        os.rename(old_p, new_p)
                        success_count += 1
                    except Exception as e:
                        fail_count += 1
                        print(e)
                prog_bar.progress((i + 1) / len(df))
            
            st.balloons()
            st.success(f"Fertig! {success_count} Dateien umbenannt.")
            if fail_count > 0:
                st.error(f"{fail_count} Fehler aufgetreten.")
            
            # Refresh File List
            st.session_state["renamer_files"] = []
            st.rerun()

    with c_msg:
        if has_conflicts:
            st.error("⚠️ Achtung: Es entstehen doppelte Dateinamen! Bitte Suchmuster anpassen.")
        elif not has_changes and search_pattern:
            st.warning("Keine Treffer für das Suchmuster.")
        elif not search_pattern:
            st.info("Gib oben ein Suchmuster ein.")
        else:
            st.success("Bereit zum Umbenennen.")

else:
    st.info("👈 Wähle links einen Ordner mit Dateien aus.")