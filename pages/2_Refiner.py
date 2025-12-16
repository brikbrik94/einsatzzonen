import streamlit as st
import geopandas as gpd
import pandas as pd
import requests
import os
import json
import concurrent.futures
import time
import sys
from datetime import datetime

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.geojson_tools import (
    load_config, save_config, select_files_dialog, select_folder_dialog, load_geodataframe_raw
)

st.set_page_config(page_title="Refiner (Smart)", layout="wide")
CONFIG_FILE = "step2_config.json"
st.title("🚑 Einsatzzonen Refiner (Step 2)")
st.markdown("Verfeinerung mit **Echtzeit-Routing** und **Attribut-Wiederherstellung**.")

# --- STATE & CONFIG ---
cfg = load_config(CONFIG_FILE)
defaults = {
    "ors_url": "http://127.0.0.1:8082/ors/v2", 
    "top_n": 3, 
    "threads": 4, 
    "profile": "driving-emergency", 
    "use_fallback": False, 
    "out_path": os.getcwd(), 
    "input_files": []
}

for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = cfg.get(k, v)

# --- HELPER ---
def build_lookup(gdf):
    """Baut Koordinaten-Lookup für Routing"""
    d = {}
    for _, r in gdf.iterrows():
        c = [r.geometry.x, r.geometry.y]
        if 'final_label' in r and r['final_label']: d[str(r['final_label'])] = c
        elif 'name' in r and r['name']: d[str(r['name'])] = c
    return d

def get_station_attributes_df(gdf, selected_tags):
    """Erstellt DF mit Tags für Merge nach Dissolve"""
    if not selected_tags or gdf is None: return None
    
    cols = ['final_label'] + [t for t in selected_tags if t in gdf.columns]
    # Drop geometry, drop duplicates
    df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
    if 'final_label' in df.columns:
        return df[cols].drop_duplicates(subset='final_label')
    return None

def route_hex(row, lookup, conf):
    try:
        hex_pt = [row.geometry.centroid.x, row.geometry.centroid.y]
        cands = []
        for i in range(1, conf["top_n"]+1):
            k = f"cand_{i}_name"
            if k in row and pd.notna(row[k]) and str(row[k]) in lookup: 
                cands.append((str(row[k]), lookup[str(row[k])]))
        
        if not cands: return row.get('zone_label'), row.get('duration', 9999)
        best_n, best_t = None, float('inf')
        
        if not conf["use_fallback"]:
            locs = [hex_pt] + [c[1] for c in cands]
            try:
                r = requests.post(f"{conf['url']}/matrix/{conf['profile']}", json={"locations":locs,"metrics":["duration"],"sources":list(range(1,len(cands)+1)),"destinations":[0]}, timeout=5)
                if r.status_code==200:
                    durs = r.json()['durations']
                    for idx, dl in enumerate(durs):
                        if dl[0] is not None and dl[0] < best_t: best_t = dl[0]; best_n = cands[idx][0]
            except: pass
            
        if conf["use_fallback"] or best_n is None:
            for n, coords in cands:
                try:
                    u = f"{conf['url']}/directions/{conf['profile']}?start={coords[0]},{coords[1]}&end={hex_pt[0]},{hex_pt[1]}"
                    r = requests.get(u, timeout=5)
                    if r.status_code==200:
                        t = r.json()['features'][0]['properties']['summary']['duration']
                        if t < best_t: best_t = t; best_n = n
                except: continue
        return (best_n, best_t) if best_n else (row.get('zone_label'), row.get('duration', 9999))
    except: return row.get('zone_label'), row.get('duration', 9999)

def process_file_and_clip(hex_path, st_lookup, conf, area_gdf, feat_idx, metrics_ph, prog_bar, station_attrs=None):
    gdf = load_geodataframe_raw(hex_path)
    
    # Prüfen ob Kandidaten vorhanden sind
    has_cands = "cand_1_name" in gdf.columns
    if not has_cands: 
        # Fallback: Wenn keine Kandidaten da sind, nehmen wir einfach das existierende Label
        # und machen nur den Dissolve/Tag-Merge Schritt
        pass
    
    if has_cands:
        tot = len(gdf); don = 0; res = []; stt = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=conf["threads"]) as exc:
            fut = {exc.submit(route_hex, r, st_lookup, conf): i for i, r in gdf.iterrows()}
            for f in concurrent.futures.as_completed(fut):
                don += 1
                if don % 20 == 0:
                    el = time.time()-stt; sp = don/el if el>0 else 0
                    prog_bar.progress(don/tot)
                    metrics_ph.markdown(f"⚡ Speed: `{sp:.1f}` Hex/s")
                try: res.append((fut[f], f.result()))
                except: pass
        
        prog_bar.progress(1.0)
        for i, (l, d) in res: 
            gdf.at[i, 'zone_label'] = l
            gdf.at[i, 'duration'] = d
            
    gdf = gdf.dropna(subset=['zone_label'])
    gdf['geometry'] = gdf.geometry.buffer(0)
    
    # Dissolve
    zones = gdf.dissolve(by='zone_label', as_index=False)
    
    # NEU: Tags wiederherstellen (Attribut Merge)
    if station_attrs is not None and not station_attrs.empty:
        # Left Join, um Tags an die Zone zu hängen
        zones = zones.merge(station_attrs, left_on='zone_label', right_on='final_label', how='left')
        if 'final_label' in zones.columns and 'final_label' != 'zone_label':
            zones = zones.drop(columns=['final_label'])

    # Clip mit Gebiet
    if area_gdf is not None:
        if feat_idx is not None: 
            try: cg = area_gdf.iloc[[feat_idx]] 
            except: cg = area_gdf
        else: cg = area_gdf
        cg = cg.copy(); cg['geometry'] = cg.geometry.buffer(0)
        try: zones = gpd.overlay(zones, cg, how='intersection')
        except: pass
        
    return zones

def render_queue(tasks, current_idx):
    md = ""
    for i, (path, _) in enumerate(tasks):
        fname = os.path.basename(path)
        if i < current_idx: icon = "✅"
        elif i == current_idx: icon = "🔄"
        else: icon = "⏳"
        if i == current_idx: md += f"**{icon} {fname}**\n\n"
        else: md += f"{icon} {fname}\n\n"
    return md

# --- UI SIDEBAR ---
with st.sidebar:
    st.header("Konfiguration")
    st.session_state["ors_url"] = st.text_input("ORS URL", st.session_state["ors_url"])
    st.session_state["profile"] = st.text_input("Profil", st.session_state["profile"])
    
    st.markdown("---")
    st.write("**Input (Batch Index JSON)**")
    c1,c2=st.columns([1,4])
    with c1: 
        if st.button("➕"): 
            fs = select_files_dialog()
            if fs: 
                for f in fs: 
                    if f not in st.session_state["input_files"]: st.session_state["input_files"].append(f)
                st.rerun()
    with c2:
        if st.button("🗑️"): st.session_state["input_files"]=[]; st.rerun()
    
    if st.session_state["input_files"]:
        st.info(f"{len(st.session_state['input_files'])} Dateien in Queue")
    else: st.warning("Leer")

    st.markdown("---")
    st.session_state["top_n"] = st.number_input("Top N", 1, 20, st.session_state["top_n"])
    st.session_state["threads"] = st.slider("Threads", 1, 32, st.session_state["threads"])
    st.session_state["use_fallback"] = st.checkbox("Fallback erzwingen", st.session_state["use_fallback"])
    
    c5,c6=st.columns([3,1])
    with c6:
        if st.button("📂", key="out"):
            d = select_folder_dialog(); 
            if d: st.session_state["out_path"] = d; st.rerun()
    with c5: st.session_state["out_path"] = st.text_input("Zielordner", st.session_state["out_path"])

# --- MAIN LOGIC ---
if st.button("🚀 Start Smart-Refiner", type="primary"):
    save_config(CONFIG_FILE, {k: st.session_state[k] for k in defaults if k in st.session_state})
    fps = st.session_state["input_files"]
    if not fps: st.error("Keine Dateien."); st.stop()
    
    conf = {"url":st.session_state["ors_url"],"profile":st.session_state["profile"],
            "top_n":st.session_state["top_n"],"use_fallback":st.session_state["use_fallback"],
            "threads":st.session_state["threads"]}
    
    col_main, col_queue = st.columns([2, 1])
    with col_queue:
        st.subheader("Warteschlange")
        queue_placeholder = st.empty()
    with col_main:
        st.subheader("Aktueller Job")
        current_job_title = st.empty()
        current_job_metrics = st.empty()
        current_job_prog = st.progress(0)
        global_status = st.info("Initialisiere...")

    # --- PROCESS FILES ---
    for f_idx, fpath in enumerate(fps):
        fname = os.path.basename(fpath)
        global_status.info(f"Lade Datei {f_idx+1}/{len(fps)}: {fname}")
        
        # 1. Prepare Meta & Data
        area_gdf = None; st_lookup = None; tasks = []; run_name = "Run"
        station_attrs = None # DF für Tags
        
        if fpath.endswith(".json"):
            try:
                js = json.load(open(fpath))
                if "meta" in js:
                    if "run_name" in js["meta"]: run_name = js["meta"]["run_name"]
                    ap = js["meta"]["area_path"]
                    sp = js["meta"]["stations_path"]
                    
                    # Tags aus Meta lesen
                    tags_to_load = js["meta"].get("selected_tags", [])

                    if os.path.exists(ap):
                        area_gdf = load_geodataframe_raw(ap).to_crs(epsg=4326)

                    if os.path.exists(sp):
                        # Lade DS komplett für Lookup UND Attribute
                        raw_st = load_geodataframe_raw(sp).to_crs(epsg=4326)
                        if 'alt_name' not in raw_st: raw_st['alt_name'] = None
                        if 'name' not in raw_st: raw_st['name'] = raw_st.index.astype(str)
                        raw_st['final_label'] = raw_st['alt_name'].fillna(raw_st['name'])
                        
                        # Lookup für Koordinaten
                        st_lookup = build_lookup(raw_st)
                        
                        # Attribute DF für Merge (falls Tags gewählt wurden)
                        if tags_to_load:
                            station_attrs = get_station_attributes_df(raw_st, tags_to_load)
                
                blist = js["batches"] if "batches" in js else js
                bd = os.path.dirname(fpath)
                for b in blist:
                    p = b["path"]
                    if not os.path.isabs(p): p = os.path.join(bd, p)
                    tasks.append((p, b.get("original_area_index")))
            except Exception as e:
                st.error(f"Fehler beim Lesen des Index: {e}")
                continue
        
        if not tasks: continue
        
        # 2. Output Dir
        ts = datetime.now().strftime("%H-%M-%S")
        final_dir = os.path.join(st.session_state["out_path"], f"Refined_{run_name}_{ts}")
        os.makedirs(final_dir, exist_ok=True)
        
        file_zones = []
        
        # --- PROCESS BATCHES ---
        for t_idx, (hexp, cidx) in enumerate(tasks):
            queue_placeholder.markdown(render_queue(tasks, t_idx))
            job_name = os.path.basename(hexp)
            current_job_title.markdown(f"### `{job_name}`")
            
            if os.path.exists(hexp):
                # Hier übergeben wir station_attrs
                z = process_file_and_clip(hexp, st_lookup, conf, area_gdf, cidx, current_job_metrics, current_job_prog, station_attrs)
                if z is not None: file_zones.append(z)
        
        queue_placeholder.markdown(render_queue(tasks, len(tasks)))
        
        if file_zones:
            global_status.text("Merge & Save...")
            fin = pd.concat(file_zones, ignore_index=True)
            fin.to_file(os.path.join(final_dir, f"Refined_{run_name}.geojson"), driver='GeoJSON')
            st.toast(f"✅ {fname} abgeschlossen!", icon="🎉")
            
    global_status.success("Alle Dateien erfolgreich verarbeitet!")
    current_job_title.empty()
    current_job_metrics.empty()
    st.balloons()