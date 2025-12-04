import streamlit as st
import geopandas as gpd
import pandas as pd
import os
import tkinter as tk
from tkinter import filedialog

# --- SETUP ---
st.set_page_config(page_title="Geo List Editor V2", layout="wide", page_icon="📜")

# --- CSS FÜR KOMPAKTERES DESIGN ---
st.markdown("""
<style>
    .streamlit-expanderHeader {font-weight: bold; background-color: #f0f2f6;}
    div[data-testid="stForm"] {border: 2px solid #ddd; padding: 20px; border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

# --- STATE ---
if "gdf" not in st.session_state: st.session_state["gdf"] = None
if "filepath" not in st.session_state: st.session_state["filepath"] = None

# --- HELPER ---
def load_file():
    root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1)
    f = filedialog.askopenfilename(filetypes=[("GeoJSON", "*.geojson")])
    root.destroy()
    if f:
        try:
            st.session_state["gdf"] = gpd.read_file(f)
            st.session_state["filepath"] = f
        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")

def save_to_disk():
    if st.session_state["gdf"] is not None and st.session_state["filepath"]:
        try:
            st.session_state["gdf"].to_file(st.session_state["filepath"], driver='GeoJSON')
            st.toast(f"✅ Datei erfolgreich gespeichert!", icon="💾")
        except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")

# --- UI SIDEBAR ---
with st.sidebar:
    st.header("🗂️ Datei")
    if st.button("📂 Datei öffnen", type="primary"):
        load_file()
    
    if st.session_state["gdf"] is not None:
        st.success(f"Offen: {os.path.basename(st.session_state['filepath'])}")
        st.info(f"{len(st.session_state['gdf'])} Features")
        
        st.markdown("---")
        st.header("💾 Speichern")
        if st.button("Auf Festplatte schreiben"):
            save_to_disk()
            
        st.warning("⚠️ WICHTIG: Änderungen in der Liste rechts müssen erst mit dem Button 'Änderungen übernehmen' bestätigt werden, bevor du hier speicherst!")

# --- MAIN AREA ---
if st.session_state["gdf"] is not None:
    gdf = st.session_state["gdf"]
    cols = [c for c in gdf.columns if c != 'geometry']

    # TABS: HIER IST DIE TRENNUNG ZWISCHEN DATEN UND STRUKTUR
    tab_list, tab_struct = st.tabs(["📝 Werte bearbeiten (Liste)", "🔧 Tags verwalten (Spalten)"])

    # === TAB 1: LISTE (DIE SCROLLBARE ANSICHT) ===
    with tab_list:
        st.subheader("Features bearbeiten")
        
        # Start des Formulars (verhindert ständiges Neuladen)
        with st.form("bulk_edit_form"):
            
            for idx, row in gdf.iterrows():
                # Name für den Header bauen
                name_display = f"#{idx}"
                if 'name' in row and row['name']: name_display += f" | {row['name']}"
                elif 'alt_name' in row and row['alt_name']: name_display += f" | {row['alt_name']}"
                
                # Feature Block
                with st.expander(name_display, expanded=True):
                    # Grid Layout (3 Spalten pro Zeile)
                    c_cols = st.columns(3)
                    
                    for i, col in enumerate(cols):
                        val = row[col]
                        val_str = str(val) if pd.notna(val) else ""
                        
                        unique_key = f"cell_{idx}_{col}"
                        
                        with c_cols[i % 3]:
                            st.text_input(label=col, value=val_str, key=unique_key)
            
            st.markdown("---")
            # Submit Button am Ende der Liste
            if st.form_submit_button("✔️ Alle Änderungen in den Speicher übernehmen", type="primary"):
                updates_count = 0
                for idx in gdf.index:
                    for col in cols:
                        key = f"cell_{idx}_{col}"
                        if key in st.session_state:
                            new_val = st.session_state[key]
                            # Leere Strings zu None (optional, hält GeoJSON sauber)
                            final_val = new_val if new_val.strip() != "" else None
                            
                            current = gdf.at[idx, col]
                            # Nur schreiben wenn anders (Performance)
                            if str(current) != str(final_val) and not (pd.isna(current) and final_val is None):
                                gdf.at[idx, col] = final_val
                                updates_count += 1
                
                st.session_state["gdf"] = gdf
                st.success(f"{updates_count} Werte aktualisiert! Klicke jetzt links auf 'Auf Festplatte schreiben'.")
                st.rerun()

    # === TAB 2: STRUKTUR (HIER KANNST DU SPALTEN BEARBEITEN) ===
    with tab_struct:
        st.markdown("### 🔧 Tags Management")
        st.info("Hier kannst du Tags (Spalten) für die gesamte Datei hinzufügen, umbenennen oder löschen.")
        
        col1, col2, col3 = st.columns(3)
        
        # 1. Hinzufügen
        with col1:
            st.write("**Tag hinzufügen**")
            new_col_name = st.text_input("Name des neuen Tags")
            default_val = st.text_input("Standardwert (optional)")
            if st.button("Hinzufügen"):
                if new_col_name and new_col_name not in gdf.columns:
                    st.session_state["gdf"][new_col_name] = default_val if default_val else None
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
                    st.session_state["gdf"] = st.session_state["gdf"].rename(columns={rename_target: rename_new})
                    st.success(f"Umbenannt in '{rename_new}'.")
                    st.rerun()
                else:
                    st.error("Ungültiger Name.")

        # 3. Löschen
        with col3:
            st.write("**Tag löschen**")
            del_target = st.selectbox("Tag wählen", cols, key="sel_del")
            if st.button("🗑️ Löschen", type="secondary"):
                st.session_state["gdf"] = st.session_state["gdf"].drop(columns=[del_target])
                st.warning(f"Tag '{del_target}' gelöscht.")
                st.rerun()

else:
    st.info("Bitte öffne links eine Datei.")
