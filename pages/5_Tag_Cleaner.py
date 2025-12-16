import streamlit as st
import geopandas as gpd
import pandas as pd
import os
import sys

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import (
    select_file_dialog, 
    load_geodataframe
)

# --- SETUP ---
st.set_page_config(page_title="Tag Cleaner", layout="wide", page_icon="🧹")
st.title("🧹 GeoJSON Tag Cleaner")
st.markdown("Analysiert GeoJSON-Dateien und entfernt unerwünschte Eigenschaften (Tags), um die Dateigröße zu reduzieren.")

# --- STATE ---
if "cleaner_filepath" not in st.session_state: st.session_state["cleaner_filepath"] = ""
if "cleaner_gdf" not in st.session_state: st.session_state["cleaner_gdf"] = None
if "cleaner_stats" not in st.session_state: st.session_state["cleaner_stats"] = None

# --- HELPER ---
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
        try:
            sample = gdf[col].dropna().iloc[0] if count > 0 else ""
        except:
            sample = ""
            
        sample_str = str(sample)
        if len(sample_str) > 50: sample_str = sample_str[:47] + "..."
        
        stats.append({
            "Tag": col,
            "Count": count,
            "Percent": round(percent, 1),
            "Sample": sample_str
        })
        
    return pd.DataFrame(stats).sort_values(by="Count", ascending=False)

# --- SIDEBAR ---
with st.sidebar:
    st.header("Datei")
    if st.button("📂 Datei öffnen", type="primary"):
        f = select_file_dialog()
        if f:
            try:
                st.session_state["cleaner_filepath"] = f
                # Lade mit Repair-Funktion
                gdf = load_geodataframe(f)
                st.session_state["cleaner_gdf"] = gdf
                st.session_state["cleaner_stats"] = analyze_tags(gdf)
                st.rerun()
            except Exception as e:
                st.error(f"Fehler beim Laden: {e}")

    if st.session_state["cleaner_filepath"]:
        st.success(f"Geladen: `{os.path.basename(st.session_state['cleaner_filepath'])}`")
        if st.session_state["cleaner_gdf"] is not None:
             st.caption(f"{len(st.session_state['cleaner_gdf'])} Features")

# --- MAIN AREA ---
if st.session_state["cleaner_gdf"] is not None:
    gdf = st.session_state["cleaner_gdf"]
    stats_df = st.session_state["cleaner_stats"]
    
    st.divider()
    
    col_l, col_r = st.columns([2, 1])
    
    with col_r:
        st.subheader("⚙️ Auswahl")
        st.info("Wähle die Tags aus, die **GELÖSCHT** werden sollen.")
        
        # Auswahl-Modus
        mode = st.radio(
            "Schnell-Auswahl", 
            ["Manuell wählen", "Alles auswählen (Alles löschen)", "Nichts auswählen (Alles behalten)"], 
            horizontal=False
        )
        
    with col_l:
        st.subheader("📊 Tag-Analyse")
        
        # DataFrame für Editor vorbereiten
        editor_df = stats_df.copy()
        
        # Default Wert basierend auf Radio-Button setzen
        if "Alles auswählen" in mode:
            editor_df.insert(0, "Löschen", True)
        elif "Nichts auswählen" in mode:
            editor_df.insert(0, "Löschen", False)
        else:
            # Bei Manuell: Versuche State zu halten oder Default False
            editor_df.insert(0, "Löschen", False)

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
                "Tag": st.column_config.TextColumn("Tag Name", disabled=True),
                "Count": st.column_config.NumberColumn("Anzahl", disabled=True),
                "Sample": st.column_config.TextColumn("Beispiel", disabled=True),
            },
            hide_index=True,
            width="stretch",
            height=500
        )

    # --- SPEICHERN ---
    st.divider()
    st.subheader("💾 Bereinigen & Speichern")
    
    # Ermittle zu löschende Spalten
    cols_to_delete = edited_df[edited_df["Löschen"] == True]["Tag"].tolist()
    cols_to_keep = [c for c in gdf.columns if c not in cols_to_delete and c != 'geometry']
    
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Zu löschen ({len(cols_to_delete)}):**")
        if cols_to_delete:
            st.error(", ".join(cols_to_delete))
        else:
            st.caption("Keine")
    
    with c2:
        st.write(f"**Bleiben erhalten ({len(cols_to_keep)}):**")
        st.success(", ".join(cols_to_keep))

    if st.button("🚀 Datei bereinigen und speichern", type="primary"):
        if not cols_to_delete:
            st.warning("Keine Tags zum Löschen ausgewählt. Datei bleibt unverändert.")
        else:
            try:
                # Kopie erstellen und Spalten droppen
                clean_gdf = gdf.drop(columns=cols_to_delete)
                
                # Pfad generieren
                orig_path = st.session_state["cleaner_filepath"]
                dir_name = os.path.dirname(orig_path)
                base_name = os.path.splitext(os.path.basename(orig_path))[0]
                new_path = os.path.join(dir_name, f"{base_name}_clean.geojson")
                
                clean_gdf.to_file(new_path, driver='GeoJSON')
                
                # Dateigrößen Vergleich
                size_old = os.path.getsize(orig_path) / 1024
                size_new = os.path.getsize(new_path) / 1024
                diff = size_old - size_new
                
                st.balloons()
                st.success(f"Datei gespeichert unter: `{new_path}`")
                
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("Alte Größe", f"{size_old:.1f} KB")
                col_m2.metric("Neue Größe", f"{size_new:.1f} KB")
                col_m3.metric("Gespart", f"{diff:.1f} KB", delta_color="normal")
                
            except Exception as e:
                st.error(f"Fehler beim Speichern: {e}")

else:
    st.info("👈 Bitte wähle eine GeoJSON-Datei aus der Seitenleiste aus.")