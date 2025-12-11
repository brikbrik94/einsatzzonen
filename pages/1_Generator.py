import streamlit as st
import geopandas as gpd
import pandas as pd
import requests
import os
import math
import sys
import json 
from datetime import datetime
from shapely.geometry import Polygon

# --- SETUP: SHARED TOOLS ---
# Nur für Config & Dialoge, NICHT für Daten-Loading
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

try:
    from src.geojson_tools import (
        load_config, save_config, select_file_dialog, select_folder_dialog
    )
except ImportError:
    st.error("Fehler: 'src/geojson_tools.py' nicht gefunden.")
    st.stop()

# --- HELPER: LOKALER RAW LOADER (SICHERHEIT) ---
def load_data_local(filepath):
    """
    Lädt Geodaten 1:1 ohne Veränderungen an den Koordinaten.
    """
    if not os.path.exists(filepath): return None
    try:
        gdf = gpd.read_file(filepath)
        # Entferne technisch leere Zeilen
        if 'geometry' in gdf.columns:
            gdf = gdf[gdf.geometry.notna()]
        # Setze CRS Tag falls fehlend (Standard GeoJSON = 4326)
        if gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True)
        return gdf
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")
        return None

# --- HELPER: TAG ANALYSE ---
def get_station_tags_df(filepath):
    try:
        gdf = load_data_local(filepath)
        if gdf is None: return pd.DataFrame()
        cols = [c for c in gdf.columns if c != 'geometry']
        sel = st.session_state.get("selected_tags", [])
        data = [{"selected": c in sel, "name": c, "count": gdf[c].count()} for c in cols]
        return pd.DataFrame(data).sort_values(by=["selected", "count"], ascending=[False, False])
    except: return pd.DataFrame()

# --- CONFIG ---
st.set_page_config(page_title="Einsatzzonen Generator", layout="wide")
GLOBAL_CONFIG_FILE = "general_config.json"
st.title("🚒 Einsatzzonen Generator (Robust Iterativ)")

cfg = load_config(GLOBAL_CONFIG_FILE)
defaults = {
    "area_file_path": "", "stations_file_path": "", "output_folder_path": os.getcwd(),
    "run_name": "Run_01", "ors_base_url": "http://127.0.0.1:8082/ors/v2", 
    "available_profiles": ["driving-car"], "selected_profile": "driving-car", 
    "hex_edge_length": 500, "n_neighbors": 10, "matrix_limit": 2500,
    "sequential_processing": False, "save_single_zones": True,
    "store_candidates": False, "candidate_count": 5, "selected_tags": [] 
}
# Pfad Migration
if "area_path_loaded" in cfg and not cfg.get("area_file_path"): cfg["area_file_path"] = cfg["area_path_loaded"]
if "out_path" in cfg and not cfg.get("output_folder_path"): cfg["output_folder_path"] = cfg["out_path"]
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = cfg.get(k, v)

def autosave():
    save_config(GLOBAL_CONFIG_FILE, {k: st.session_state[k] for k in defaults.keys() if k in st.session_state})

# --- UI SIDEBAR ---
with st.sidebar:
    st.header("Setup")
    st.text_input("ORS URL", key="ors_base_url")
    if st.button("Verb. Prüfen"):
        try: 
            requests.get(f"{st.session_state['ors_base_url']}/status", timeout=1)
            st.success("OK")
        except: st.error("Fehler")
    st.selectbox("Profil", st.session_state["available_profiles"], key="selected_profile")
    st.divider()
    
    if st.button("📂 Gebiet"): 
        f = select_file_dialog("Gebiet"); 
        if f: st.session_state["area_file_path"] = f; autosave(); st.rerun()
    st.text_input("Gebiet", key="area_file_path")

    if st.button("📂 DS"): 
        f = select_file_dialog("DS"); 
        if f: st.session_state["stations_file_path"] = f; autosave(); st.rerun()
    st.text_input("DS", key="stations_file_path")
    
    st.divider()
    st.text_input("Run Name", key="run_name")
    if st.button("📂 Output"):
        d = select_folder_dialog("Output"); 
        if d: st.session_state["output_folder_path"] = d; autosave(); st.rerun()
    st.text_input("Output", key="output_folder_path")

# Tag Auswahl Formular
if st.session_state["stations_file_path"] and os.path.exists(st.session_state["stations_file_path"]):
    st.divider()
    with st.expander("Datenfelder wählen (Tags)"):
        tags_df = get_station_tags_df(st.session_state["stations_file_path"])
        if not tags_df.empty:
            with st.form("tag_form"):
                sel = []
                st.write("Wähle Spalten, die in das Ergebnis übernommen werden sollen:")
                for _, r in tags_df.iterrows():
                    if st.checkbox(f"{r['name']} ({r['count']})", value=r['selected'], key=f"chk_{r['name']}"):
                        sel.append(r['name'])
                if st.form_submit_button("💾 Auswahl Speichern"):
                    st.session_state["selected_tags"] = sel; autosave(); st.rerun()

st.divider()
with st.expander("Parameter", expanded=True):
    c1,c2 = st.columns(2)
    with c1:
        st.number_input("Grid (m)", min_value=10, value=500, key="hex_edge_length")
        st.number_input("Nachbarn (Top N)", min_value=1, value=10, key="n_neighbors", help="Pro Wache in der Zone werden N Nachbarn geladen.")
    with c2:
        st.number_input("Matrix Limit", value=2500, key="matrix_limit")
        st.checkbox("Sequentiell", key="sequential_processing")
        st.checkbox("Zonen einzeln speichern", key="save_single_zones")
    st.checkbox("Kandidaten speichern (in Grid)", key="store_candidates")
    if st.session_state["store_candidates"]:
        st.number_input("Anzahl Kandidaten Spalten", 1, 50, 5, key="candidate_count")

# --- KERN-LOGIK: ITERATIV ---

def get_candidates_iterative(area, stations, n, cfg, ui_callback=None):
    if area.crs != stations.crs:
        if stations.crs: area = area.to_crs(stations.crs)

    inside = gpd.sjoin(stations, area, how="inner", predicate="intersects")
    has_inside_stations = not inside.empty
    
    anchors = []
    if has_inside_stations:
        inside_wgs = inside.to_crs(epsg=4326)
        for idx, row in inside_wgs.iterrows():
            name = str(row.get('final_label', idx))
            geom = [row.geometry.centroid.x, row.geometry.centroid.y]
            anchors.append({'name': name, 'coords': geom})
    else:
        try: c = area.to_crs(epsg=4326).geometry.union_all().centroid
        except: c = area.to_crs(epsg=4326).geometry.unary_union.centroid
        anchors.append({'name': 'Zentroid', 'coords': [c.x, c.y]})

    stations_wgs = stations.to_crs(epsg=4326)
    all_coords = [[p.x, p.y] for p in stations_wgs.geometry.centroid]
    all_ids = stations_wgs.index.tolist()
    
    pool_indices = set()
    error_log = []
    
    for i, anchor in enumerate(anchors):
        # Update UI Message via Callback
        if ui_callback:
            ui_callback(f"Analysiere Wache {i+1} von {len(anchors)}: {anchor['name']}")

        locs = all_coords + [anchor['coords']]
        src_idx = list(range(len(all_coords)))
        dst_idx = [len(all_coords)]
        
        try:
            payload = {"locations": locs, "metrics": ["duration"], "sources": src_idx, "destinations": dst_idx}
            # Timeout entfernt
            r = requests.post(f"{cfg['url']}/matrix/{cfg['profile']}", json=payload, headers={'Content-Type':'application/json'}, timeout=None)
            
            if r.status_code == 200:
                durs = r.json().get('durations')
                results = []
                for s_idx in range(len(all_coords)):
                    if durs and durs[s_idx] and durs[s_idx][0] is not None:
                        results.append((durs[s_idx][0], all_ids[s_idx]))
                
                results.sort(key=lambda x: x[0])
                
                # --- FIX: EXAKT N+1 (Selbst + N Nachbarn) ---
                # Index 0 ist die Wache selbst (Zeit ~0), Index 1 bis N sind die Nachbarn
                top_selection = [res[1] for res in results[:n+1]]
                pool_indices.update(top_selection)
            else:
                error_log.append({"Anker": anchor['name'], "Fehler": f"HTTP {r.status_code}"})
                
        except Exception as e:
            error_log.append({"Anker": anchor['name'], "Fehler": str(e)})
            
    return stations.loc[list(pool_indices)].copy(), has_inside_stations, error_log

def create_hex_grid(area, edge):
    am = area.to_crs(epsg=3857)
    minx, miny, maxx, maxy = am.total_bounds
    hexs = []
    y = miny; row=0
    h=math.sqrt(3)*edge; v=1.5*edge
    while y < maxy+edge:
        x = minx + (h/2 if row%2==1 else 0)
        while x < maxx+edge:
            pts = []
            for i in range(6):
                ang = math.pi/180*(60*i-30)
                pts.append((x+edge*math.cos(ang), y+edge*math.sin(ang)))
            hexs.append(Polygon(pts))
            x += h
        y += v; row+=1
    g = gpd.GeoDataFrame({'geometry':hexs}, crs=3857)
    try: u = am.geometry.union_all()
    except: u = am.geometry.unary_union
    return g[g.intersects(u)].copy().to_crs(epsg=4326)

def run_routing_batch(hex_gdf, station_gdf, cfg, ui_callback):
    h_c = [[p.x,p.y] for p in hex_gdf.geometry.centroid]
    s_c = [[p.x,p.y] for p in station_gdf.geometry.centroid]
    s_ids = station_gdf.index.tolist()
    res = []
    batch = max(1, int(cfg['matrix_limit']/len(s_c)))
    total_batches = math.ceil(len(h_c)/batch)
    
    for i in range(0, len(h_c), batch):
        batch_num = (i // batch) + 1
        
        # Fortschrittsbalken auf maximal 1.0 begrenzen
        current_progress = min((i+batch)/len(h_c), 1.0)
        
        if ui_callback: 
            ui_callback(f"Batch {batch_num}/{total_batches}", current_progress)
            
        chunk = h_c[i:i+batch]
        locs = chunk + s_c
        src = list(range(len(chunk), len(locs)))
        dst = list(range(len(chunk)))
        try:
            pl = {"locations":locs, "metrics":["duration"], "sources":src, "destinations":dst}
            r = requests.post(f"{cfg['url']}/matrix/{cfg['profile']}", json=pl, headers={'Content-Type':'application/json'}, timeout=None)
            if r.status_code==200:
                d = r.json()['durations']
                for hi in range(len(chunk)):
                    v = []
                    for si in range(len(s_c)):
                        if d[si][hi] is not None: v.append((d[si][hi], s_ids[si]))
                    v.sort(key=lambda x:x[0])
                    # Top N speichern
                    top_n = cfg['candidate_count'] if cfg['store_candidates'] else 1
                    res.append([x[1] for x in v[:top_n]])
            else: 
                for _ in chunk: res.append([])
        except:
            for _ in chunk: res.append([])
    return res

# --- UI HELPER: STATUS ANZEIGE ---
def render_step_status(placeholder, steps_status, current_detail=""):
    icons = {0: "⬜", 1: "🔄", 2: "✅", 3: "❌"}
    md = ""
    for name, status in steps_status:
        icon = icons.get(status, "⬜")
        style = "**" if status == 1 else ""
        line = f"{icon} {style}{name}{style}"
        if status == 1 and current_detail:
            line += f"  — *{current_detail}*"
        md += f"{line}  \n"
    placeholder.markdown(md)

# --- PROZESS STEUERUNG ---

def process_single_area(sub_area, all_stations, cfg, status_ph, prog_bar, area_name, selected_tags):
    
    # Initiale Steps
    steps = [
        ("1. Kandidaten finden", 1), 
        ("2. Hex-Gitter erstellen", 0),
        ("3. Matrix Routing", 0),
        ("4. Daten zusammenführen", 0),
        ("5. Auflösen & Speichern", 0)
    ]
    render_step_status(status_ph, steps, "Initialisiere...")
    
    # --- 1. KANDIDATEN ---
    def cand_ui_cb(msg): 
        render_step_status(status_ph, steps, msg)
        
    rel, has_inside, error_log = get_candidates_iterative(sub_area, all_stations, cfg["n_neighbors"], cfg, cand_ui_cb)
    
    if rel.empty:
        steps[0] = ("1. Kandidaten finden", 3)
        render_step_status(status_ph, steps, "Keine Wachen gefunden!")
        return None, None

    steps[0] = ("1. Kandidaten finden", 2)
    steps[1] = ("2. Hex-Gitter erstellen", 1)
    render_step_status(status_ph, steps, f"Gefunden: {len(rel)} Wachen")
    
    # --- UI: VORSCHAU ---
    with st.expander(f"🗺️ Vorschau: {len(rel)} Wachen für '{area_name}'", expanded=False):
        c_map, c_list = st.columns([2,1])
        with c_list: st.dataframe(rel[['final_label']].astype(str), height=200)
        with c_map:
            rel_wgs = rel.to_crs(epsg=4326)
            st.map(pd.DataFrame({'lat': rel_wgs.geometry.y, 'lon': rel_wgs.geometry.x}))
        if error_log:
            st.error(f"⚠️ Probleme bei {len(error_log)} Ankern:")
            st.dataframe(pd.DataFrame(error_log), hide_index=True)

    # --- 2. GRID ---
    grid = create_hex_grid(sub_area, cfg["hex_edge_length"])
    if grid.empty:
        steps[1] = ("2. Hex-Gitter erstellen", 3)
        render_step_status(status_ph, steps, "Grid leer")
        return None, None
        
    steps[1] = ("2. Hex-Gitter erstellen", 2)
    steps[2] = ("3. Matrix Routing", 1)
    render_step_status(status_ph, steps, f"{len(grid)} Hexagone")
    
    # --- 3. ROUTING ---
    def route_ui_cb(msg, progress):
        render_step_status(status_ph, steps, msg)
        prog_bar.progress(progress)
        
    matrix_res = run_routing_batch(grid, rel, cfg, route_ui_cb)
    
    steps[2] = ("3. Matrix Routing", 2)
    steps[3] = ("4. Daten zusammenführen", 1)
    render_step_status(status_ph, steps)
    prog_bar.empty()
    
    # --- 4. MERGE ---
    lkp = all_stations['final_label'].to_dict()
    grid['zone_label'] = [lkp.get(r[0]) if r else None for r in matrix_res]
    
    if cfg["store_candidates"]:
        for i in range(cfg["candidate_count"]):
            grid[f"cand_{i+1}_name"] = [lkp.get(r[i]) if r and len(r)>i else None for r in matrix_res]

    grid = grid.dropna(subset=['zone_label'])
    
    steps[3] = ("4. Daten zusammenführen", 2)
    steps[4] = ("5. Auflösen & Speichern", 1)
    render_step_status(status_ph, steps)
    
    # --- 5. DISSOLVE ---
    try:
        zones = grid[['zone_label','geometry']].copy()
        zones['geometry'] = zones.geometry.buffer(0)
        zones = zones.dissolve(by='zone_label', as_index=False)
        
        if selected_tags:
            valid = [t for t in selected_tags if t in all_stations.columns]
            meta = all_stations[['final_label'] + valid].drop_duplicates('final_label')
            zones = zones.merge(meta, left_on='zone_label', right_on='final_label', how='left')
            if 'final_label' in zones.columns and 'final_label' != 'zone_label':
                zones = zones.drop(columns=['final_label'])
                
        cl = sub_area.copy()
        cl['geometry'] = cl.geometry.buffer(0)
        zones_clip = gpd.overlay(zones, cl, how='intersection')
        
        steps[4] = ("5. Auflösen & Speichern", 2)
        render_step_status(status_ph, steps, "Fertig")
        
    except Exception as e: 
        steps[4] = ("5. Auflösen & Speichern", 3)
        render_step_status(status_ph, steps, f"Fehler: {e}")
        zones_clip = zones
        
    return grid, zones_clip

# --- MAIN RUN ---
if st.button("🚀 Start", type="primary"):
    autosave()
    if not (st.session_state["area_file_path"] and st.session_state["stations_file_path"]):
        st.error("Pfade fehlen!")
        st.stop()

    with st.spinner("Lade Geodaten (Raw)..."):
        ga = load_data_local(st.session_state["area_file_path"])
        gs = load_data_local(st.session_state["stations_file_path"])
        if 'alt_name' not in gs: gs['alt_name'] = None
        if 'name' not in gs: gs['name'] = gs.index.astype(str)
        gs['final_label'] = gs['alt_name'].fillna(gs['name'])

    out_dir = os.path.join(st.session_state["output_folder_path"], f"{st.session_state['run_name']}")
    os.makedirs(out_dir, exist_ok=True)
    
    cfg_run = {
        "url": st.session_state["ors_base_url"],
        "profile": st.session_state["selected_profile"],
        "matrix_limit": st.session_state["matrix_limit"],
        "hex_edge_length": st.session_state["hex_edge_length"],
        "n_neighbors": st.session_state["n_neighbors"],
        "store_candidates": st.session_state["store_candidates"],
        "candidate_count": st.session_state["candidate_count"]
    }
    
    # UI Container
    status_header = st.empty()
    status_list = st.empty()
    progress_bar = st.empty()
    
    all_z = []; batches = []
    tags_to_keep = st.session_state.get("selected_tags", [])

    items = [ga] if not st.session_state["sequential_processing"] else [gpd.GeoDataFrame([r], crs=ga.crs) for _,r in ga.iterrows()]
    
    for idx, sub_area in enumerate(items):
        # Name ermitteln
        nm = f"Zone_{idx}"
        if st.session_state["sequential_processing"]:
            for c in ['name','NAME','GEN','bezirk']: 
                if c in sub_area.iloc[0] and sub_area.iloc[0][c]: nm=str(sub_area.iloc[0][c]); break
        
        # Header Update
        status_header.markdown(f"### 📍 Verarbeite: **{nm}** ({idx+1}/{len(items)})")
        
        # Processing
        h_res, z_res = process_single_area(sub_area, gs, cfg_run, status_list, progress_bar, nm, tags_to_keep)
        
        # Speichern Grid (Kandidaten)
        if st.session_state["store_candidates"] and h_res is not None:
            cand_dir = os.path.join(out_dir, "candidates_grid")
            os.makedirs(cand_dir, exist_ok=True)
            h_res.to_file(os.path.join(cand_dir, f"hex_{nm}.geojson"), driver='GeoJSON')
        
        # Speichern Zone
        if z_res is not None:
            all_z.append(z_res)
            if st.session_state["save_single_zones"]:
                z_res.to_file(os.path.join(out_dir, f"zones_{nm}.geojson"), driver='GeoJSON')
            batches.append({"feature": nm, "path": f"zones_{nm}.geojson"})

    status_header.markdown("### ✅ Verarbeitung abgeschlossen")
    status_list.empty()
    progress_bar.empty()
    
    if all_z:
        fin = pd.concat(all_z, ignore_index=True)
        fin_path = os.path.join(out_dir, "zones_combined.geojson")
        fin.to_file(fin_path, driver='GeoJSON')
        
        # JSON Index
        with open(os.path.join(out_dir, "index.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "meta": {
                    "run_name": st.session_state["run_name"],
                    "selected_tags": tags_to_keep,
                    "date": datetime.now().isoformat()
                },
                "batches": batches
            }, f, indent=4)
            
        st.balloons()
        st.success(f"Fertig! Ergebnis gespeichert in: {fin_path}")
    else: 
        st.error("Keine Zonen generiert.")