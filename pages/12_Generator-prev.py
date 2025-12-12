import streamlit as st
import geopandas as gpd
import pandas as pd
import requests
import os
import json
import math
from datetime import datetime
from shapely.geometry import Polygon

from src.geojson_tools import (
    load_config,
    save_config,
    load_geodataframe_raw,
    select_file_dialog,
    select_folder_dialog,
)

# --- KONFIGURATION ---
st.set_page_config(page_title="Einsatzzonen Generator (Step 1)", layout="wide")
GLOBAL_CONFIG_FILE = "general_config.json"
st.title("🚒 Einsatzzonen Generator (Step 1)")
st.markdown("Erstellt Hexagon-Gitter (Outbound-Logik) mit **erweitertem Nachbarschafts-Pool**.")

# --- HELPER ---
def load_station_tags_df(filepath):
    try:
        gdf = load_geodataframe_raw(filepath)
        cols = [c for c in gdf.columns if c != "geometry"]
        sel = st.session_state.get("selected_tags", [])
        data = [{"selected": c in sel, "name": c, "count": gdf[c].count()} for c in cols]
        return pd.DataFrame(data).sort_values(by=["selected", "count"], ascending=[False, False])
    except Exception:
        return pd.DataFrame()

# --- STATE ---
cfg = load_config(GLOBAL_CONFIG_FILE)
defaults = {
    "ors_base_url": "http://127.0.0.1:8082/ors/v2",
    "available_profiles": ["driving-car", "driving-emergency"],
    "selected_profile": "driving-car",
    "hex_edge_length": 500,
    "n_neighbors": 10,
    "matrix_limit": 2500,
    "run_name": "Run_01",
    "output_folder_path": os.getcwd(),
    "area_file_path": "",
    "stations_file_path": "",
    "sequential_processing": False,
    "store_candidates": False,
    "candidate_count": 5,
    "save_single_zones": True,
    "selected_tags": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = cfg.get(k, v)


def autosave():
    save_config(GLOBAL_CONFIG_FILE, {k: st.session_state.get(k, defaults[k]) for k in defaults.keys()})

# --- UI ---
with st.sidebar:
    st.header("1. Setup")
    st.session_state["ors_base_url"] = st.text_input("ORS URL", st.session_state["ors_base_url"])
    if st.button("Check Verb."):
        try:
            r = requests.get(f"{st.session_state['ors_base_url']}/status", timeout=2)
            if r.status_code==200 and "profiles" in r.json(): 
                st.session_state["available_profiles"] = list(r.json()["profiles"].keys()); st.success("OK")
        except: st.error("Fehler")
    st.session_state["selected_profile"] = st.selectbox("Profil", st.session_state["available_profiles"])

    st.markdown("---")
    c1,c2 = st.columns([3,1])
    with c2: 
        if st.button("📂", key="b1"): 
            f = select_file_dialog("Gebiet")
            if f: st.session_state["area_file_path"]=f; autosave(); st.rerun()
    with c1: st.session_state["area_file_path"] = st.text_input("Gebiet", st.session_state["area_file_path"])

    c3,c4 = st.columns([3,1])
    with c4:
        if st.button("📂", key="b2"): 
            f = select_file_dialog("DS")
            if f: st.session_state["stations_file_path"]=f; autosave(); st.rerun()
    with c3: st.session_state["stations_file_path"] = st.text_input("Dienststellen", st.session_state["stations_file_path"])

    st.markdown("---")
    st.session_state["run_name"] = st.text_input("Lauf-Name", st.session_state["run_name"])
    c5,c6 = st.columns([3,1])
    with c6:
        if st.button("📂", key="b3"):
            d = select_folder_dialog("Output");
            if d: st.session_state["output_folder_path"]=d; autosave(); st.rerun()
    with c5: st.session_state["output_folder_path"] = st.text_input("Output", st.session_state["output_folder_path"])

if st.session_state["stations_file_path"] and os.path.exists(st.session_state["stations_file_path"]):
    st.markdown("---")
    with st.expander("Datenfelder wählen (Tags)"):
        tags_df = load_station_tags_df(st.session_state["stations_file_path"])
        if not tags_df.empty:
            with st.form("tag_form"):
                sel = []
                st.write("Wähle Spalten, die in das Ergebnis übernommen werden sollen:")
                for _, row in tags_df.iterrows():
                    label = f"{row['name']} ({row['count']})"
                    if st.checkbox(label, value=row['selected'], key=f"tag_{row['name']}"):
                        sel.append(row['name'])
                if st.form_submit_button("💾 Auswahl Speichern"):
                    st.session_state["selected_tags"] = sel
                    autosave()
                    st.rerun()

with st.expander("⚙️ Erweitert", expanded=False):
    c1,c2 = st.columns(2)
    with c1:
        st.session_state["hex_edge_length"] = st.number_input("Kantenlänge (m)", 50, value=st.session_state["hex_edge_length"])
        st.session_state["store_candidates"] = st.checkbox("Kandidaten speichern (für Step 2)", st.session_state["store_candidates"])
        if st.session_state["store_candidates"]:
            st.session_state["candidate_count"] = st.number_input("Top N", 1, 20, st.session_state["candidate_count"])
    with c2:
        st.session_state["n_neighbors"] = st.number_input("N Nachbarn (pro interner Wache)", 1, value=st.session_state["n_neighbors"])
        st.session_state["matrix_limit"] = st.number_input("Limit", 100, value=st.session_state["matrix_limit"])
        st.session_state["sequential_processing"] = st.checkbox("Sequentiell (Smart Batch)", st.session_state["sequential_processing"])
        if st.session_state["sequential_processing"]:
            st.info("ℹ️ Erzeugt autom. 'parts/' Ordner mit Hex-Dateien für Step 2.")
            st.session_state["save_single_zones"] = st.checkbox("Auch aufgelöste Zonen einzeln speichern", st.session_state["save_single_zones"])

# --- LOGIC ---
def create_hex_grid(gdf_area, edge):
    gdf_proj = gdf_area.to_crs(epsg=3857)
    min_x, min_y, max_x, max_y = gdf_proj.total_bounds
    buff = edge*2; min_x-=buff; min_y-=buff; max_x+=buff; max_y+=buff
    h_dist = math.sqrt(3)*edge; v_dist = 1.5*edge
    hexs = []
    curr_y = min_y; row = 0
    while curr_y < max_y:
        curr_x = min_x + (h_dist/2 if row%2==1 else 0)
        while curr_x < max_x:
            pts = []
            for i in range(6):
                ang = math.pi/180*(60*i-30)
                pts.append((curr_x+edge*math.cos(ang), curr_y+edge*math.sin(ang)))
            hexs.append(Polygon(pts))
            curr_x += h_dist
        curr_y += v_dist; row += 1
    g = gpd.GeoDataFrame({'geometry': hexs}, crs="EPSG:3857")
    return g[g.intersects(gdf_proj.geometry.unary_union)].copy().to_crs(epsg=4326)

def filter_stations_smart(area, stations, n):
    """
    NEUE LOGIK:
    1. Finde alle Wachen IM Gebiet.
    2. Für JEDE dieser Wachen: Finde die N nächsten Nachbarn.
    3. FALLBACK: Wenn KEINE Wache im Gebiet ist -> Finde N nächste vom Zentrum.
    """
    if area.crs != stations.crs: stations = stations.to_crs(area.crs)
    
    # Temporär metrisch für korrekte Distanzen
    stations_metric = stations.to_crs(epsg=3857)
    
    # 1. Wachen im Gebiet finden (ohne zusätzlichen Buffer)
    inside = gpd.sjoin(stations, area, how="inner", predicate="intersects")
    
    relevant_ids = set()
    
    if not inside.empty:
        # STRATEGIE A: Gebiet hat Wachen
        # Iteriere durch jede Wache im Gebiet und hole deren N Nachbarn
        # Da wir 'stations_metric' nutzen, können wir Indizes von 'inside' nutzen
        for idx, row in inside.iterrows():
            # Hole Geometrie dieser Wache in metrisch
            if idx in stations_metric.index:
                origin_geom = stations_metric.loc[idx].geometry
                # Berechne Distanz zu ALLEN Stationen
                dists = stations_metric.geometry.distance(origin_geom)
                # Nimm die N+1 nächsten (inklusive sich selbst)
                nearest = dists.nsmallest(n + 1).index.tolist()
                relevant_ids.update(nearest)
    else:
        # STRATEGIE B: Gebiet ist leer (Fallback)
        # Nimm Zentroid des Gebiets und suche N Nachbarn
        centroid = area.to_crs(epsg=3857).geometry.unary_union.centroid
        dists = stations_metric.geometry.distance(centroid)
        nearest = dists.nsmallest(n).index.tolist()
        relevant_ids.update(nearest)
    
    return stations.loc[list(relevant_ids)].copy()

def get_matrix_outbound(hex_gdf, stat_gdf, url, prof, limit, top_n, pbar, batch_txt):
    h_coords = [[p.x,p.y] for p in hex_gdf.geometry.centroid]
    # FIX: Ensure centroids for stations (works with Polygons too)
    s_coords = [[p.x,p.y] for p in stat_gdf.geometry.centroid]
    
    if not h_coords: return None
    batch = max(1, int(limit/len(s_coords))); res = []
    s_ids = stat_gdf.index.tolist(); total = math.ceil(len(h_coords)/batch)
    
    for i in range(0, len(h_coords), batch):
        cur_b = (i//batch)+1
        if batch_txt: batch_txt.text(f"📡 Routing: Batch {cur_b} / {total} (Outbound)")
        
        chunk = h_coords[i:i+batch]
        locs = chunk + s_coords
        try:
            r = requests.post(f"{url}/matrix/{prof}", json={"locations":locs,"metrics":["duration"],"sources":list(range(len(chunk),len(chunk)+len(s_coords))),"destinations":list(range(len(chunk)))}, headers={'Content-Type':'application/json'})
            if r.status_code==200:
                durs = r.json()['durations']
                for h_idx in range(len(chunk)):
                    cands = []
                    for s_idx in range(len(s_coords)):
                        val = durs[s_idx][h_idx]
                        if val is not None: cands.append((val, s_idx))
                    cands.sort(key=lambda x:x[0])
                    res.append([s_ids[x[1]] for x in cands[:top_n]])
            else: 
                for _ in chunk: res.append([])
        except: 
            for _ in chunk: res.append([])
        if pbar: pbar.progress(min(cur_b/total, 1.0))
    return res

def process_step(sub, stat, cfg, status_ph, batch_ph, name):
    # 1. Filter
    status_ph.markdown(f"**{name}**: 📍 Suche relevante Wachen...")
    rel = filter_stations_smart(sub, stat, cfg["n_neighbors"])
    
    # VORSCHAU EXPANDER
    with st.expander(f"👁️ Vorschau: {len(rel)} Wachen für '{name}'", expanded=False):
        c_map, c_list = st.columns([1,1])
        with c_list: st.dataframe(rel[['final_label']].astype(str), height=200)
        with c_map:
            # Map braucht Lat/Lon Spalten
            map_df = pd.DataFrame({'lat': rel.geometry.centroid.y, 'lon': rel.geometry.centroid.x})
            st.map(map_df, size=40, color='#ff0000', zoom=8)

    batch_ph.info(f"Pool: {len(rel)} Wachen")
    
    # 2. Grid
    status_ph.markdown(f"**{name}**: 🕸️ Grid ({cfg['hex_edge_length']}m)...")
    gr = create_hex_grid(sub, cfg["hex_edge_length"])
    if gr.empty: return None, None
    
    # 3. Route
    status_ph.markdown(f"**{name}**: 📡 Matrix Routing ({len(gr)} Hex)...")
    pb = st.progress(0)
    need = cfg["candidate_count"] if cfg["store_candidates"] else 1
    res = get_matrix_outbound(gr, rel, cfg["url"], cfg["profile"], cfg["limit"], need, pb, batch_ph)
    pb.empty(); batch_ph.empty()
    
    # 4. Merge
    status_ph.markdown(f"**{name}**: 🧬 Merge...")
    lkp = stat['final_label'].to_dict()
    gr['zone_label'] = [lkp.get(r[0]) if r else None for r in res]
    if cfg["store_candidates"]:
        for i in range(cfg["candidate_count"]): gr[f"cand_{i+1}_name"] = [lkp.get(r[i]) if len(r)>i else None for r in res]
    
    gr = gr.dropna(subset=['zone_label'])
    
    # 5. Dissolve
    status_ph.markdown(f"**{name}**: ✂️ Dissolve & Clip...")
    try:
        zones = gr[['zone_label','geometry']].copy(); zones['geometry']=zones.geometry.buffer(0)
        zones = zones.dissolve(by='zone_label', as_index=False)

        valid_tags = []
        if cfg.get("selected_tags"):
            valid = [t for t in cfg["selected_tags"] if t in stat.columns]
            if valid:
                valid_tags = valid
                meta = stat[['final_label'] + valid].drop_duplicates('final_label')
                zones = zones.merge(meta, left_on='zone_label', right_on='final_label', how='left')
                if 'final_label' in zones.columns and 'final_label' != 'zone_label':
                    zones = zones.drop(columns=['final_label'])

        cl = sub.copy(); cl['geometry'] = cl.geometry.buffer(0)
        keep_cols = ['zone_label', 'geometry'] + valid_tags
        keep_cols = [c for c in keep_cols if c in zones.columns]
        zones_clip = gpd.overlay(zones, cl, how='intersection')[keep_cols]
    except: zones_clip = zones
    return gr, zones_clip

# --- RUN ---
if st.button("🚀 Start", type="primary"):
    autosave()
    if not os.path.exists(st.session_state["area_file_path"]) or not os.path.exists(st.session_state["stations_file_path"]):
        st.error("Pfade prüfen"); st.stop()

    with st.spinner("Lade Daten..."):
        ga = load_geodataframe_raw(st.session_state["area_file_path"])
        if ga.crs and ga.crs.to_string() != "EPSG:4326":
            ga = ga.to_crs(epsg=4326)
        gs = load_geodataframe_raw(st.session_state["stations_file_path"])
        if gs.crs and gs.crs.to_string() != "EPSG:4326":
            gs = gs.to_crs(epsg=4326)
        if 'alt_name' not in gs: gs['alt_name'] = None
        if 'name' not in gs: gs['name'] = gs.index.astype(str)
        gs['final_label'] = gs['alt_name'].fillna(gs['name'])

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    cn = "".join([c for c in st.session_state["run_name"] if c.isalnum() or c in ('_','-')]).strip()
    out = os.path.join(st.session_state["output_folder_path"], f"{ts}_{cn}"); os.makedirs(out, exist_ok=True)
    
    conf = {"url":st.session_state["ors_base_url"],"profile":st.session_state["selected_profile"],
            "limit":st.session_state["matrix_limit"],"hex_edge_length":st.session_state["hex_edge_length"],
            "n_neighbors":st.session_state["n_neighbors"],"store_candidates":st.session_state["store_candidates"],
            "candidate_count":st.session_state["candidate_count"], "selected_tags": st.session_state.get("selected_tags", [])}
    
    all_z = []; batches = []; 
    main_status = st.empty(); sub_status = st.empty()

    index_filename = f"{cn}_index.json" if cn else "batch_index.json"

    if st.session_state["sequential_processing"]:
        tot = len(ga); pr = st.progress(0)
        for idx, row in ga.iterrows():
            nm = f"Feat_{idx}"
            for c in ['name','NAME','GEN','bezirk']: 
                if c in row and row[c]: nm=str(row[c]); break
            sub = gpd.GeoDataFrame([row], crs=ga.crs)
            
            h_res, z_res = process_step(sub, gs, conf, main_status, sub_status, nm)
            
            if h_res is not None and not h_res.empty:
                pd_dir = os.path.join(out, "parts"); os.makedirs(pd_dir, exist_ok=True)
                hp = os.path.join(pd_dir, f"hex_{nm}.geojson")
                h_res.to_file(hp, driver='GeoJSON')
                
                batches.append({"feature": nm, "path": hp, "original_area_index": idx})
            
            if z_res is not None:
                all_z.append(z_res)
                if st.session_state["save_single_zones"]:
                    zd_dir = os.path.join(out, "single_zones"); os.makedirs(zd_dir, exist_ok=True)
                    z_res.to_file(os.path.join(zd_dir, f"zones_{nm}.geojson"), driver='GeoJSON')

            pr.progress((idx+1)/tot)
            
        with open(os.path.join(out, index_filename), 'w', encoding='utf-8') as f:
            json.dump({
                "meta": {
                    "area_path": st.session_state["area_file_path"], 
                    "stations_path": st.session_state["stations_file_path"],
                    "run_name": st.session_state["run_name"]
                }, 
                "batches": batches
            }, f, indent=4)
            
    else:
        h_res, z_res = process_step(ga, gs, conf, main_status, sub_status, "Gesamt")
        if z_res is not None:
            all_z.append(z_res)
            hp = os.path.join(out, "hexagons_global.geojson")
            h_res.to_file(hp, driver='GeoJSON')
            with open(os.path.join(out, index_filename), 'w', encoding='utf-8') as f:
                json.dump({
                    "meta": {
                        "area_path": st.session_state["area_file_path"], 
                        "stations_path": st.session_state["stations_file_path"],
                        "run_name": st.session_state["run_name"]
                    }, 
                    "batches": [{"feature": "Global", "path": hp, "original_area_index": None}]
                }, f, indent=4)

    main_status.text("Finalisiere...")
    if all_z:
        fin = pd.concat(all_z, ignore_index=True)
        fin.to_file(os.path.join(out, f"{cn}_zones_combined.geojson"), driver='GeoJSON')
        st.balloons()
        st.success(f"Fertig! Index: `{index_filename}` in {out}")
    else: st.error("Leer")
