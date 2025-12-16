import streamlit as st
import geopandas as gpd
import pandas as pd
import os
import sys
import re
import json

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import (
    load_config,
    select_file_dialog,
    select_folder_dialog,
    load_geodataframe_raw
)

# --- SETUP ---
st.set_page_config(page_title="Zonen Splitter", layout="wide", page_icon="🔀")
st.title("🔀 Zonen Splitter (Matrix-Zuweisung)")
st.markdown("Automatische Zuordnung via **Funkkennung** ODER **Gemeinde/Bundesland** (mit intelligenter Namensbereinigung).")

CODE_CONFIG_FILE = "leitstellen_config.json"
STATE_CONFIG_FILE = "bundesland_config.json"

# --- STATE ---
if "split_gdf" not in st.session_state: st.session_state["split_gdf"] = None
if "split_filename" not in st.session_state: st.session_state["split_filename"] = ""
if "split_mapping_df" not in st.session_state: st.session_state["split_mapping_df"] = None
if "municipality_lookup" not in st.session_state: st.session_state["municipality_lookup"] = {} 

# --- HELPER ---
def load_configs():
    return load_config(CODE_CONFIG_FILE), load_config(STATE_CONFIG_FILE)

def load_municipality_csv(filepath):
    """Lädt CSV: Code;Name;Bundesland"""
    try:
        df = pd.read_csv(filepath, sep=';', header=None, names=['code', 'name', 'bundesland'], dtype=str)
        # Lookup: Name -> Bundesland (Wir strippen Whitespaces)
        lookup = pd.Series(df.bundesland.values, index=df.name.str.strip()).to_dict()
        return lookup
    except Exception as e:
        st.error(f"Fehler beim Laden der CSV: {e}")
        return {}

def find_district_code(row):
    """Sucht 4-stellige Zahl."""
    text = ""
    if 'name' in row and pd.notna(row['name']): text += str(row['name']) + " "
    if 'alt_name' in row and pd.notna(row['alt_name']): text += str(row['alt_name'])
    
    match = re.search(r'\b(\d{4})\b', text)
    if match:
        full_code = match.group(1)
        return full_code[:2], full_code 
    return None, None

def clean_zone_name(raw_name):
    """Entfernt typische Rotes Kreuz Präfixe für besseres Matching."""
    if not raw_name or not isinstance(raw_name, str):
        return ""
    
    # WICHTIG: Längere Phrasen zuerst, damit sie komplett entfernt werden
    noise_words = [
        "Rotes Kreuz Bezirksstelle", "Rotes Kreuz Ortsstelle", "Rotes Kreuz Dienststelle",
        "Rotkreuz-Bezirksstelle", "Rotkreuz-Ortsstelle", "Rotkreuz-Dienststelle",
        "Rotes Kreuz", "Rotkreuz", "ÖRK", "RK", 
        "Bezirksstelle", "Ortsstelle", "Dienststelle", 
        "Ausgabestelle", "Stützpunkt"
    ]
    
    cleaned = raw_name
    for word in noise_words:
        # Ersetze Wort (ignoriere Groß/Kleinschreibung) durch nichts
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        cleaned = pattern.sub("", cleaned)
    
    # Sonderzeichen wie Bindestriche/Slashes entfernen oder durch Leerzeichen ersetzen
    cleaned = cleaned.replace("-", " ").replace("_", " ").replace("/", " ")
    
    # Doppelte Leerzeichen entfernen und trimmen
    return re.sub(r'\s+', ' ', cleaned).strip()

def auto_assign_leitstelle(row, code_conf, state_conf, muni_lookup):
    """
    Logik:
    1. Suche Funkkennung (Bezirks-Code) -> Priorität A
    2. Suche Name in CSV (mit Bereinigung) -> Priorität B
    """
    
    # 1. Funkkennung Check
    bezirk, full_code = find_district_code(row)
    
    if bezirk:
        for ls_name, codes in code_conf.items():
            if bezirk in codes:
                return ls_name, f"Code ({full_code})", bezirk
    
    # 2. Namens-Check (Fallback)
    # Hole Roh-Namen
    raw_name = str(row['name']) if 'name' in row and pd.notna(row['name']) else ""
    
    # A) Versuch: Bereinigter Name (z.B. "Ortsstelle Bad Ischl" -> "Bad Ischl")
    clean_name = clean_zone_name(raw_name)
    
    match_bundesland = None
    
    # Direkter Treffer im Lookup?
    if clean_name in muni_lookup:
        match_bundesland = muni_lookup[clean_name]
    else:
        # B) Versuch: "Enthält"-Suche (Ist eine bekannte Gemeinde Teil des Namens?)
        if muni_lookup:
            for muni_name, bundesland in muni_lookup.items():
                # Prüfen ob Gemeinde im bereinigten Namen steckt (als ganzes Wort)
                if re.search(r'\b' + re.escape(muni_name) + r'\b', clean_name, re.IGNORECASE):
                    match_bundesland = bundesland
                    break 

    if match_bundesland:
        if match_bundesland in state_conf:
            return state_conf[match_bundesland], f"Ort ({clean_name})", "-"
            
    return None, None, (bezirk if bezirk else "-")

def prepare_data(gdf, code_conf, state_conf, muni_lookup):
    assigned_rows = []
    unassigned_rows = []
    
    all_ls = set(code_conf.keys()) | set(state_conf.values())
    ls_cols = sorted(list(all_ls))
    
    for idx, row in gdf.iterrows():
        ls_match, method, bezirk_display = auto_assign_leitstelle(row, code_conf, state_conf, muni_lookup)
        
        name_val = row['name'] if 'name' in row and pd.notna(row['name']) else f"Feature {idx}"
        
        base_data = {
            "orig_index": idx,
            "Name": name_val,
            "Info": method if method else "-", 
            "Bezirk": bezirk_display
        }
        
        if ls_match:
            base_data["Zuweisung"] = ls_match
            assigned_rows.append(base_data)
        else:
            for ls in ls_cols: base_data[ls] = False
            unassigned_rows.append(base_data)
            
    return pd.DataFrame(assigned_rows), pd.DataFrame(unassigned_rows), ls_cols

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Input")
    
    # A) GeoJSON
    if st.button("📂 GeoJSON laden", type="primary"):
        f = select_file_dialog()
        if f:
            st.session_state["split_gdf"] = load_geodataframe_raw(f)
            st.session_state["split_filename"] = os.path.basename(f)
            st.rerun()

    if st.session_state["split_gdf"] is not None:
        st.success(f"GeoJSON: `{st.session_state['split_filename']}`")

    st.markdown("---")
    
    # B) CSV Referenz
    st.write("**Referenzdaten (Gemeinden)**")
    if st.button("📂 CSV laden"):
        csv_path = select_file_dialog("Gemeinde CSV wählen", [("CSV", "*.csv"), ("Text", "*.txt")])
        if csv_path:
            st.session_state["municipality_lookup"] = load_municipality_csv(csv_path)
            st.success("CSV geladen!")
            st.rerun()

    if st.session_state["municipality_lookup"]:
        st.caption(f"CSV aktiv: {len(st.session_state['municipality_lookup'])} Gemeinden")
    else:
        st.warning("Keine CSV geladen. Namenserkennung eingeschränkt.")

    st.markdown("---")
    st.header("2. Output")
    if "split_out_dir" not in st.session_state: st.session_state["split_out_dir"] = os.getcwd()
    
    if st.button("📂 Zielordner"):
        d = select_folder_dialog()
        if d: 
            st.session_state["split_out_dir"] = d
            st.rerun()
    st.text_input("Pfad", st.session_state["split_out_dir"], disabled=True)


# --- MAIN AREA ---
if st.session_state["split_gdf"] is not None:
    
    code_conf, state_conf = load_configs()
    muni_lookup = st.session_state.get("municipality_lookup", {})
    
    if not code_conf and not state_conf:
        st.error("Keine Konfiguration gefunden! Bitte Seite 7 nutzen.")
    else:
        ass_df, unass_df, ls_cols = prepare_data(st.session_state["split_gdf"], code_conf, state_conf, muni_lookup)
        
        # 1. Info Metriken
        c1, c2, c3 = st.columns(3)
        c1.metric("Gesamt Zonen", len(st.session_state["split_gdf"]))
        c2.metric("Automatisch zugeordnet", len(ass_df))
        c3.metric("Offen / Manuell", len(unass_df), delta_color="inverse")
        
        st.divider()

        # 2. MATRIX EDITOR
        edited_unass_df = pd.DataFrame() 
        
        if not unass_df.empty:
            st.subheader("⚠️ Manuelle Zuweisung erforderlich")
            st.info("Bitte hake für jede Zone die zuständige Leitstelle an.")
            
            col_config = {
                "orig_index": None, 
                "Name": st.column_config.TextColumn("Zone", disabled=True),
                "Info": st.column_config.TextColumn("Info", disabled=True, width="small"),
                "Bezirk": st.column_config.TextColumn("Bez.", disabled=True, width="small"),
            }
            for ls in ls_cols:
                col_config[ls] = st.column_config.CheckboxColumn(ls, default=False)

        edited_unass_df = st.data_editor(
            unass_df,
            column_config=col_config,
            hide_index=True,
            width="stretch",
            height=500
        )
        else:
            st.success("🎉 Alles erledigt! Keine offenen Zonen.")

        st.divider()
        st.subheader("🚀 Export starten")
        
        col_l, col_r = st.columns([3,1])
        with col_l:
            with st.expander("Bereits zugeordnete Zonen ansehen"):
                st.dataframe(ass_df[["Name", "Info", "Zuweisung"]], width="stretch")

        with col_r:
            if st.button("Dateien splitten & speichern", type="primary"):
                try:
                    gdf_source = st.session_state["split_gdf"]
                    out_dir = st.session_state["split_out_dir"]
                    
                    final_mapping = []
                    if not ass_df.empty:
                        final_mapping = ass_df[["orig_index", "Zuweisung"]].to_dict('records')
                    
                    if not edited_unass_df.empty:
                        for idx, row in edited_unass_df.iterrows():
                            found_ls = None
                            for ls in ls_cols:
                                if row[ls] == True:
                                    found_ls = ls
                                    break 
                            orig_idx = row["orig_index"]
                            if found_ls:
                                final_mapping.append({"orig_index": orig_idx, "Zuweisung": found_ls})
                            else:
                                final_mapping.append({"orig_index": orig_idx, "Zuweisung": "Unzugewiesen_Rest"})

                    map_df = pd.DataFrame(final_mapping)
                    
                    if map_df.empty:
                        st.warning("Nichts zu exportieren.")
                    else:
                        files_created = []
                        groups = map_df.groupby("Zuweisung")
                        
                        bar = st.progress(0); current_i = 0; total_g = len(groups)
                        
                        for ls_name, group_data in groups:
                            current_i += 1
                            bar.progress(current_i / total_g)
                            
                            indices = group_data["orig_index"].tolist()
                            sub_gdf = gdf_source.iloc[indices].copy()
                            
                            safe_name = "".join([c for c in ls_name if c.isalnum() or c in (' ', '_', '-')]).strip().replace(" ", "_")
                            filename = f"Export_{safe_name}.geojson"
                            
                            out_path = os.path.join(out_dir, filename)
                            sub_gdf.to_file(out_path, driver='GeoJSON')
                            files_created.append(f"{filename} ({len(sub_gdf)} Zonen)")
                        
                        bar.progress(1.0)
                        st.balloons()
                        st.success("Export abgeschlossen!")
                        for f in files_created: st.write(f"- ✅ {f}")

                except Exception as e:
                    st.error(f"Fehler beim Export: {e}")

else:
    st.info("👈 Bitte lade zuerst eine GeoJSON-Datei.")