import streamlit as st
import geopandas as gpd
import pandas as pd
import requests
import os
import json
import concurrent.futures
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
import time

# --- SETUP ---
st.set_page_config(page_title="Refiner (Smart)", layout="wide")
CONFIG_FILE = "step2_config.json"
st.title("🚑 Einsatzzonen Refiner (Dashboard)")
st.markdown("Verfeinerung mit **Echtzeit-Status** und detaillierter Queue.")

# --- HELPER ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        try: return json.load(open(CONFIG_FILE))
        except: return {}
    return {}

def save_config(data):
    try: json.dump(data, open(CONFIG_FILE,'w'), indent=4)
    except: pass

def select_input_file():
    root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1)
    f = filedialog.askopenfilenames(title="Wähle batch_index.json", filetypes=[("JSON / GeoJSON", "*.json *.geojson")])
    root.destroy(); return list(f)

def select_folder():
    root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1)
    d = filedialog.askdirectory(); root.destroy(); return d

# --- INIT ---
cfg = load_config()
state_keys = ["ors_url", "input_files", "out_path", "top_n", "threads", "profile", "use_fallback", "area_path_loaded", "stations_path_loaded"]
defaults = {"ors_url": "http://127.0.0.1:8082/ors/v2", "top_n": 3, "threads": 4, "profile": "driving-emergency", "use_fallback": False, "out_path": os.getcwd(), "input_files": []}

for k in state_keys:
    if k not in st.session_state: st.session_state[k] = cfg.get(k, defaults.get(k, ""))
if not isinstance(st.session_state["input_files"], list): st.session_state["input_files"] = []

# --- UI SIDEBAR ---
with st.sidebar:
    st.header("Konfiguration")
    st.session_state["ors_url"] = st.text_input("ORS URL", st.session_state["ors_url"])
    st.session_state["profile"] = st.text_input("Profil", st.session_state["profile"])
    
    st.markdown("---")
    st.write("**Input**")
    c1,c2=st.columns([1,4])
    with c1: 
        if st.button("➕"): 
            fs = select_input_file()
            if fs: 
                for f in fs: 
                    if f not in st.session_state["input_files"]: st.session_state["input_files"].append(f)
                
                # Auto-Load Meta vom letzten File
                if fs[-1].endswith(".json"):
                    try:
                        d = json.load(open(fs[-1]))
                        if "meta" in d:
                            st.session_state["area_path_loaded"] = d["meta"]["area_path"]
                            st.session_state["stations_path_loaded"] = d["meta"]["stations_path"]
                    except: pass
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
            d = select_folder(); 
            if d: st.session_state["out_path"] = d; st.rerun()
    with c5: st.session_state["out_path"] = st.text_input("Zielordner", st.session_state["out_path"])

# --- CORE LOGIC ---
def build_lookup(gdf):
    d = {}
    for _, r in gdf.iterrows():
        c = [r.geometry.x, r.geometry.y]
        if 'name' in r and r['name']: d[str(r['name'])] = c
        if 'alt_name' in r and r['alt_name']: d[str(r['alt_name'])] = c
    return d

def route_hex(row, lookup, conf):
    # Outbound Logic (Wache -> Hex)
    try:
        hex_pt = [row.geometry.centroid.x, row.geometry.centroid.y]
        cands = []
        for i in range(1, conf["top_n"]+1):
            k = f"cand_{i}_name"
            if k in row and pd.notna(row[k]) and str(row[k]) in lookup: cands.append((str(row[k]), lookup[str(row[k])]))
        
        if not cands: return row.get('zone_label'), row.get('duration', 9999)
        best_n, best_t = None, float('inf')
        
        if not conf["use_fallback"]:
            locs = [hex_pt] + [c[1] for c in cands]
            try:
                # Sources: 1..N (Stations), Dest: 0 (Hex)
                r = requests.post(f"{conf['url']}/matrix/{conf['profile']}", json={"locations":locs,"metrics":["duration"],"sources":list(range(1,len(cands)+1)),"destinations":[0]}, timeout=5)
                if r.status_code==200:
                    durs = r.json()['durations']
                    for idx, dl in enumerate(durs):
                        if dl[0] is not None and dl[0] < best_t: best_t = dl[0]; best_n = cands[idx][0]
            except: pass
            
        if conf["use_fallback"] or best_n is None:
            for n, coords in cands:
                try:
                    # Start: Wache, End: Hex
                    u = f"{conf['url']}/directions/{conf['profile']}?start={coords[0]},{coords[1]}&end={hex_pt[0]},{hex_pt[1]}"
                    r = requests.get(u, timeout=5)
                    if r.status_code==200:
                        t = r.json()['features'][0]['properties']['summary']['duration']
                        if t < best_t: best_t = t; best_n = n
                except: continue
        return (best_n, best_t) if best_n else (row.get('zone_label'), row.get('duration', 9999))
    except: return row.get('zone_label'), row.get('duration', 9999)

def process_file_and_clip(hex_path, st_lookup, conf, area_gdf, feat_idx, metrics_ph, prog_bar):
    gdf = gpd.read_file(hex_path).to_crs(epsg=4326)
    if "cand_1_name" not in gdf.columns: return None
    
    tot = len(gdf); don = 0; res = []; stt = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=conf["threads"]) as exc:
        fut = {exc.submit(route_hex, r, st_lookup, conf): i for i, r in gdf.iterrows()}
        for f in concurrent.futures.as_completed(fut):
            don += 1
            if don % 10 == 0: # Update UI every 10 hexes
                el = time.time()-stt; sp = don/el if el>0 else 0
                prog_bar.progress(don/tot)
                metrics_ph.markdown(f"**Fortschritt:** `{don}/{tot}` Hexagone | **Speed:** ⚡ `{sp:.1f}` Hex/s")
            
            try: res.append((fut[f], f.result()))
            except: pass
    
    # Finalize UI
    prog_bar.progress(1.0)
    
    for i, (l, d) in res: 
        gdf.at[i, 'zone_label'] = l
        gdf.at[i, 'duration'] = d
        
    gdf = gdf.dropna(subset=['zone_label'])
    gdf['geometry'] = gdf.geometry.buffer(0)
    zones = gdf.dissolve(by='zone_label', as_index=False)
    
    if area_gdf is not None:
        if feat_idx is not None: cg = area_gdf.iloc[[feat_idx]] 
        else: cg = area_gdf
        cg = cg.copy(); cg['geometry'] = cg.geometry.buffer(0)
        try: zones = gpd.overlay(zones, cg, how='intersection')
        except: pass
        
    return zones[['zone_label', 'geometry']]

def render_queue(tasks, current_idx):
    """Generates markdown for the queue list"""
    md = ""
    for i, (path, _) in enumerate(tasks):
        fname = os.path.basename(path)
        if i < current_idx: icon = "✅"
        elif i == current_idx: icon = "🔄" # Processing
        else: icon = "⏳" # Waiting
        
        # Highlight current
        if i == current_idx: md += f"**{icon} {fname}**\n\n"
        else: md += f"{icon} {fname}\n\n"
    return md

# --- RUN ---
if st.button("🚀 Start Smart-Refiner", type="primary"):
    save_config(st.session_state.to_dict())
    fps = st.session_state["input_files"]
    if not fps: st.error("Keine Dateien."); st.stop()
    
    conf = {"url":st.session_state["ors_url"],"profile":st.session_state["profile"],
            "top_n":st.session_state["top_n"],"use_fallback":st.session_state["use_fallback"],
            "threads":st.session_state["threads"]}
    
    # --- LAYOUT ---
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
        
        # 1. Prepare Meta
        area_gdf = None; st_lookup = None; tasks = []; run_name = "Run"
        if fpath.endswith(".json"):
            try:
                js = json.load(open(fpath))
                if "meta" in js:
                    if "run_name" in js["meta"]: run_name = js["meta"]["run_name"]
                    ap = js["meta"]["area_path"]; sp = js["meta"]["stations_path"]
                    if os.path.exists(ap) and os.path.exists(sp):
                        area_gdf = gpd.read_file(ap).to_crs(epsg=4326)
                        st_lookup = build_lookup(gpd.read_file(sp).to_crs(epsg=4326))
                
                blist = js["batches"] if "batches" in js else js
                bd = os.path.dirname(fpath)
                for b in blist:
                    p = b["path"]
                    if not os.path.isabs(p): p = os.path.join(bd, p)
                    tasks.append((p, b.get("original_area_index")))
            except: pass
        
        if not tasks: continue
        
        # 2. Output Dir
        ts = datetime.now().strftime("%H-%M-%S")
        final_dir = os.path.join(st.session_state["out_path"], f"Refined_{run_name}_{ts}")
        os.makedirs(final_dir, exist_ok=True)
        
        file_zones = []
        
        # --- PROCESS BATCHES IN FILE ---
        for t_idx, (hexp, cidx) in enumerate(tasks):
            # Update Queue View
            queue_placeholder.markdown(render_queue(tasks, t_idx))
            
            job_name = os.path.basename(hexp)
            current_job_title.markdown(f"### `{job_name}`")
            
            if os.path.exists(hexp):
                z = process_file_and_clip(hexp, st_lookup, conf, area_gdf, cidx, current_job_metrics, current_job_prog)
                if z is not None: file_zones.append(z)
        
        # File complete
        queue_placeholder.markdown(render_queue(tasks, len(tasks))) # All done
        
        if file_zones:
            global_status.text("Merge & Save...")
            fin = pd.concat(file_zones, ignore_index=True)
            fin.to_file(os.path.join(final_dir, f"Refined_{run_name}.geojson"), driver='GeoJSON')
            st.toast(f"✅ {fname} abgeschlossen!", icon="🎉")
            
    global_status.success("Alle Dateien erfolgreich verarbeitet!")
    current_job_title.empty()
    current_job_metrics.empty()
    st.balloons()
