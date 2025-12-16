import streamlit as st
import geopandas as gpd
import pandas as pd
import os
import sys

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import (
    select_file_dialog,
    load_geodataframe_raw
)

# --- SETUP ---
st.set_page_config(page_title="Geo List Editor V2", layout="wide", page_icon="📜")
st.title("📜 GeoJSON Tag Editor")
st.markdown("Bearbeite Attribute (Tags) direkt in einer Tabelle oder verwalte die Spaltenstruktur.")

# --- STATE ---
if "editor_gdf" not in st.session_state: st.session_state["editor_gdf"] = None
if "editor_filepath" not in st.session_state: st.session_state["editor_filepath"] = None
if "editor_unsaved_changes" not in st.session_state: st.session_state["editor_unsaved_changes"] = False

# --- HELPER ---
def save_to_disk():
    if st.session_state["editor_gdf"] is not None and st.session_state["editor_filepath"]:
        try:
            # Speichern
            st.session_state["editor_gdf"].to_file(st.session_state["editor_filepath"], driver='GeoJSON')
            st.session_state["editor_unsaved_changes"] = False
            st.toast(f"✅ Datei erfolgreich gespeichert!", icon="💾")
        except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")

# --- SIDEBAR ---
with st.sidebar:
    st.header("🗂️ Datei")
    if st.button("📂 Datei öffnen", type="primary"):
        f = select_file_dialog()
        if f:
            try:
                st.session_state["editor_gdf"] = load_geodataframe_raw(f)
                st.session_state["editor_filepath"] = f
                st.session_state["editor_unsaved_changes"] = False
                st.rerun()
            except Exception as e:
                st.error(f"Fehler: {e}")
    
    if st.session_state["editor_gdf"] is not None:
        fname = os.path.basename(st.session_state['editor_filepath'])
        st.success(f"Offen: `{fname}`")
        st.caption(f"{len(st.session_state['editor_gdf'])} Features")
        
        st.markdown("---")
        st.header("💾 Speichern")
        
        if st.session_state["editor_unsaved_changes"]:
            st.warning("⚠️ Ungespeicherte Änderungen!")
        
        if st.button("Auf Festplatte schreiben", type="primary" if st.session_state["editor_unsaved_changes"] else "secondary"):
            save_to_disk()


# --- MAIN AREA ---
if st.session_state["editor_gdf"] is not None:
    gdf = st.session_state["editor_gdf"]
    
    # Tabs für Daten und Struktur
    tab_data, tab_struct = st.tabs(["📝 Daten bearbeiten (Excel-Modus)", "🔧 Spalten verwalten"])

    # === TAB 1: DATEN (Data Editor) ===
    with tab_data:
        st.info("Du kannst Werte direkt in der Tabelle ändern. Geometrie-Spalten sind ausgeblendet.")
        
        # Wir trennen Geometrie ab, da DataEditor die nicht gut darstellen kann
        df_display = pd.DataFrame(gdf.drop(columns='geometry'))
        
        # Der Editor
        edited_df = st.data_editor(
            df_display,
            num_rows="fixed", # Keine Zeilen hinzufügen/löschen hier (Geometrie würde fehlen)
            width="stretch",
            height=600,
            key="data_editor_widget"
        )
        
        # Check auf Änderungen
        if not df_display.equals(edited_df):
            # Änderungen erkannt -> GDF updaten
            # Wir iterieren über die Spalten und updaten das GDF
            for col in edited_df.columns:
                gdf[col] = edited_df[col]
            
            st.session_state["editor_gdf"] = gdf
            st.session_state["editor_unsaved_changes"] = True
            st.rerun() # Refresh um Warnung in Sidebar anzuzeigen


    # === TAB 2: STRUKTUR (Spalten) ===
    with tab_struct:
        st.markdown("### 🔧 Tags Management")
        
        col1, col2, col3 = st.columns(3)
        cols = [c for c in gdf.columns if c != 'geometry']
        
        # 1. Hinzufügen
        with col1:
            st.write("**Tag hinzufügen**")
            new_col_name = st.text_input("Name des neuen Tags")
            default_val = st.text_input("Standardwert (optional)")
            if st.button("Hinzufügen"):
                if new_col_name and new_col_name not in gdf.columns:
                    st.session_state["editor_gdf"][new_col_name] = default_val if default_val else None
                    st.session_state["editor_unsaved_changes"] = True
                    st.success(f"Tag '{new_col_name}' hinzugefügt.")
                    st.rerun()
                elif new_col_name in gdf.columns:
                    st.error("Existiert bereits.")

        # 2. Umbenennen
        with col2:
            st.write("**Tag umbenennen**")
            rename_target = st.selectbox("Tag wählen", cols, key="sel_ren")
            rename_new = st.text_input("Neuer Name", value=rename_target)
            if st.button("Umbenennen"):
                if rename_new and rename_new not in gdf.columns:
                    st.session_state["editor_gdf"] = st.session_state["editor_gdf"].rename(columns={rename_target: rename_new})
                    st.session_state["editor_unsaved_changes"] = True
                    st.success(f"Umbenannt in '{rename_new}'.")
                    st.rerun()
                else:
                    st.error("Ungültiger Name.")

        # 3. Löschen
        with col3:
            st.write("**Tag löschen**")
            del_target = st.selectbox("Tag wählen", cols, key="sel_del")
            if st.button("🗑️ Löschen", type="secondary"):
                st.session_state["editor_gdf"] = st.session_state["editor_gdf"].drop(columns=[del_target])
                st.session_state["editor_unsaved_changes"] = True
                st.warning(f"Tag '{del_target}' gelöscht.")
                st.rerun()

else:
    st.info("👈 Bitte öffne links eine Datei.")