import streamlit as st
import geopandas as gpd
import pandas as pd
import json
import os
import tkinter as tk
from tkinter import filedialog

# --- SETUP ---
st.set_page_config(page_title="Tag Cleaner", layout="wide")
st.title("🧹 GeoJSON Tag Cleaner")
st.markdown("Analysiert GeoJSON-Dateien und entfernt unerwünschte Eigenschaften (Tags), um die Dateigröße zu reduzieren.")

# --- STATE ---
if "cleaner_input_path" not in st.session_state: st.session_state["cleaner_input_path"] = ""
if "cleaner_gdf" not in st.session_state: st.session_state["cleaner_gdf"] = None
if "cleaner_tags_stats" not in st.session_state: st.session_state["cleaner_tags_stats"] = None

# --- HELPER ---
def select_file():
    root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1)
    f = filedialog.askopenfilename(title="Wähle GeoJSON", filetypes=[("GeoJSON", "*.geojson"), ("JSON", "*.json")])
    root.destroy()
    return f

def analyze_tags(gdf):
    """Erstellt eine Statistik über alle Spalten (Tags)"""
    total_rows = len(gdf)
    stats = []
    
    # Geometrie ignorieren wir bei Tags
    cols = [c for c in gdf.columns if c != 'geometry']
    
    for col in cols:
        # Zähle nicht-null Werte
        count = gdf[col].count()
        percent = (count / total_rows) * 100
        
        # Beispielwert finden (erster nicht-null)
        sample = gdf[col].dropna().iloc[0] if count > 0 else ""
        if len(str(sample)) > 50: sample = str(sample)[:47] + "..."
        
        stats.append({
            "Tag": col,
            "Count": count,
            "Percent": round(percent, 1),
            "Sample": str(sample)
        })
        
    return pd.DataFrame(stats).sort_values(by="Count", ascending=False)

# --- UI: DATEI LADEN ---
col1, col2 = st.columns([3, 1])
with col2:
    if st.button("📂 Datei öffnen"):
        f = select_file()
        if f:
            st.session_state["cleaner_input_path"] = f
            # Direkt laden
            try:
                gdf = gpd.read_file(f)
                st.session_state["cleaner_gdf"] = gdf
                st.session_state["cleaner_tags_stats"] = analyze_tags(gdf)
                st.rerun()
            except Exception as e:
                st.error(f"Fehler beim Laden: {e}")

with col1:
    st.text_input("Pfad", st.session_state["cleaner_input_path"], disabled=True)

# --- UI: ANALYSE & AUSWAHL ---
if st.session_state["cleaner_gdf"] is not None:
    gdf = st.session_state["cleaner_gdf"]
    stats_df = st.session_state["cleaner_tags_stats"]
    
    st.divider()
    st.subheader(f"📊 Analyse ({len(gdf)} Features)")
    
    col_l, col_r = st.columns([2, 1])
    
    with col_r:
        st.info("Wähle die Tags aus, die **GELÖSCHT** werden sollen.")
        mode = st.radio("Auswahl-Modus", ["Manuell wählen", "Alles auswählen", "Nichts auswählen"], horizontal=True)
        
        # Logik für Default-Werte der Checkboxen
        if mode == "Alles auswählen":
            default_selection = stats_df["Tag"].tolist()
        elif mode == "Nichts auswählen":
            default_selection = []
        else:
            # Smart Default: Behalte 'name', 'id', lösche Rest? 
            # Hier lieber manuell lassen, User soll entscheiden.
            default_selection = st.session_state.get("selected_tags_to_delete", [])

    with col_l:
        # Data Editor mit Checkboxen
        # Wir fügen eine Spalte 'Löschen' hinzu
        
        # Um den State zu erhalten, bauen wir ein temporäres DF für den Editor
        editor_df = stats_df.copy()
        editor_df.insert(0, "Löschen", False)
        
        if mode == "Alles auswählen": editor_df["Löschen"] = True
        if mode == "Nichts auswählen": editor_df["Löschen"] = False
        
        # Wichtige Spalten schützen (Vorschlag)
        # Man könnte Logik bauen: if col in ['name', 'id']: default false
        
        edited_df = st.data_editor(
            editor_df,
            column_config={
                "Löschen": st.column_config.CheckboxColumn(
                    "Löschen?",
                    help="Aktivieren, um diesen Tag zu entfernen",
                    default=False,
                ),
                "Percent": st.column_config.ProgressColumn(
                    "Abdeckung",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                ),
            },
            disabled=["Tag", "Count", "Percent", "Sample"],
            hide_index=True,
            height=500
        )

    # --- SPEICHERN ---
    st.divider()
    st.subheader("💾 Speichern")
    
    # Ermittle zu löschende Spalten
    cols_to_delete = edited_df[edited_df["Löschen"] == True]["Tag"].tolist()
    cols_to_keep = [c for c in gdf.columns if c not in cols_to_delete and c != 'geometry']
    
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Zu löschen ({len(cols_to_delete)}):**")
        st.caption(", ".join(cols_to_delete) if cols_to_delete else "Keine")
    
    with c2:
        st.write(f"**Bleiben erhalten ({len(cols_to_keep)}):**")
        st.caption(", ".join(cols_to_keep))

    if st.button("🚀 Bereinigen & Speichern", type="primary"):
        if not cols_to_delete:
            st.warning("Keine Tags zum Löschen ausgewählt.")
        else:
            try:
                # Kopie erstellen und Spalten droppen
                clean_gdf = gdf.drop(columns=cols_to_delete)
                
                # Pfad generieren
                orig_path = st.session_state["cleaner_input_path"]
                dir_name = os.path.dirname(orig_path)
                base_name = os.path.splitext(os.path.basename(orig_path))[0]
                new_path = os.path.join(dir_name, f"{base_name}_clean.geojson")
                
                clean_gdf.to_file(new_path, driver='GeoJSON')
                
                st.success(f"Datei erfolgreich gespeichert: `{new_path}`")
                
                # Dateigrößen Vergleich
                size_old = os.path.getsize(orig_path) / 1024
                size_new = os.path.getsize(new_path) / 1024
                diff = size_old - size_new
                st.metric("Dateigröße", f"{size_new:.1f} KB", delta=f"-{diff:.1f} KB (gespart)")
                
            except Exception as e:
                st.error(f"Fehler beim Speichern: {e}")

else:
    st.info("👈 Bitte wähle eine GeoJSON-Datei aus, um die Tags zu analysieren.")
