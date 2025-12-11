import streamlit as st
import geopandas as gpd
import pandas as pd
import os
import sys
import re

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import (
    select_file_dialog,
    select_folder_dialog,
    load_geodataframe_raw,
)

st.set_page_config(
    page_title="Universal Splitter",
    page_icon="🧩",
    layout="wide",
)

st.title("🧩 Universal GeoJSON Splitter")
st.caption("Teile eine GeoJSON-Datei nach einem beliebigen Attribut in mehrere Dateien auf.")

st.markdown(
    """
Diese Seite:
- Lädt eine GeoJSON-Datei
- Analysiert alle Spalten
- Wählt eine Spalte zum Splitten
- Optional: Explode für Listen / geteilte Strings
- Optional: Dissolve nach Zielspalte
"""
)

def analyze_columns(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    cols_info = {}
    for col in gdf.columns:
        if col == "geometry":
            continue
        series = gdf[col]
        dtype = str(series.dtype)
        n_missing = int(series.isna().sum())
        has_comma = series.dropna().astype(str).str.contains(",").any()
        example = series.iloc[0] if len(series) > 0 else "-"
        cols_info[col] = {
            "dtype": dtype,
            "non_null": int(series.notna().sum()),
            "missing": n_missing,
            "unique": int(series.nunique(dropna=True)),
            "has_comma": bool(has_comma),
            "example": example,
        }
    return pd.DataFrame(cols_info).T

def is_listlike(v) -> bool:
    return isinstance(v, (list, tuple, set))

# --- STATE ---
if "gen_split_gdf" not in st.session_state:
    st.session_state["gen_split_gdf"] = None
if "gen_split_file" not in st.session_state:
    st.session_state["gen_split_file"] = ""
if "gen_out_dir" not in st.session_state:
    st.session_state["gen_out_dir"] = ""

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Input")
    if st.button("📂 GeoJSON laden", type="primary"):
        f = select_file_dialog()
        if f:
            try:
                st.session_state["gen_split_gdf"] = load_geodataframe_raw(f)
                st.session_state["gen_split_file"] = os.path.basename(f)
                st.rerun()
            except Exception as e:
                st.error(f"Fehler beim Laden: {e}")

    if st.session_state["gen_split_gdf"] is not None:
        st.success(f"Geladen: `{st.session_state['gen_split_file']}`")
        st.caption(f"{len(st.session_state['gen_split_gdf'])} Features")

    st.markdown("---")
    st.header("2. Output")
    if st.button("📂 Zielordner wählen"):
        d = select_folder_dialog()
        if d:
            st.session_state["gen_out_dir"] = d
            st.rerun()

    if st.session_state["gen_out_dir"]:
        st.success(f"Ziel: `{st.session_state['gen_out_dir']}`")
    else:
        st.info("Kein Zielordner gewählt.")

# --- HAUPTBEREICH ---
gdf = st.session_state["gen_split_gdf"]

if gdf is not None:
    st.subheader("Datenvorschau")
    # Nur Attribute anzeigen, damit Arrow keinen Stress mit 'geometry' macht
    try:
        st.dataframe(gdf.drop(columns="geometry").head())
    except KeyError:
        st.dataframe(gdf.head())

    cols_info_df = analyze_columns(gdf)
    with st.expander("Spaltenanalyse"):
        st.dataframe(cols_info_df)

    st.markdown("### 3. Spalte zum Splitten wählen")
    possible_cols = [c for c in gdf.columns if c != "geometry"]
    target_col = st.selectbox("Attribut zum Splitten", options=possible_cols)

    if target_col:
        info = cols_info_df.loc[target_col]
        st.write(f"**Typ:** `{info['dtype']}`")
        st.write(f"**Unique:** {info['unique']} · **Missing:** {info['missing']}")
        st.write("Beispielwert:", info["example"])

        col_opt1, col_opt2 = st.columns(2)
        do_explode = False
        do_dissolve = False
        separator = r",\s*"  # Default: Komma + optionales Leerzeichen

        with col_opt1:
            st.markdown("##### Aufteilen")
            default_explode = bool(info["has_comma"])
            do_explode = st.checkbox("Werte trennen (Explode)?", value=default_explode)

            if do_explode:
                sep_mode = st.radio(
                    "Trennzeichen",
                    ["Komma (Standard)", "Benutzerdefiniert (Regex)"],
                    horizontal=True,
                )
                if sep_mode == "Benutzerdefiniert (Regex)":
                    separator = st.text_input("Regex", value=r"[,\s]+")

        with col_opt2:
            st.markdown("##### Geometrie")
            do_dissolve = st.checkbox(
                "Nach Zielspalte verschmelzen (Dissolve)?",
                value=False,
                help="Versucht nach dem Split die Geometrie pro Wert zu verschmelzen.",
            )

        st.markdown("---")
        st.markdown("### 4. Split ausführen")

        if st.button("🚀 Split starten", type="primary", disabled=not st.session_state["gen_out_dir"]):
            if not st.session_state["gen_out_dir"]:
                st.error("Bitte zuerst einen Zielordner wählen.")
            else:
                out_dir = st.session_state["gen_out_dir"]
                base_name = os.path.splitext(st.session_state["gen_split_file"])[0]

                try:
                    proc_gdf = gdf.copy()

                    # 1) Zielspalte vorbereiten: Listen loswerden / Strings splitten
                    if do_explode:
                        def make_token_list(v):
                            if v is None or (isinstance(v, float) and pd.isna(v)):
                                return []
                            if is_listlike(v):
                                return [t for t in v if t not in (None, "")]
                            s = str(v)
                            if re.search(separator, s):
                                return [t for t in re.split(separator, s) if t != ""]
                            return [s]

                        proc_gdf["__tokens__"] = proc_gdf[target_col].map(make_token_list)
                        # GeoPandas-explode auf der Token-Spalte, Geometrie bleibt erhalten
                        proc_gdf = proc_gdf.explode("__tokens__", ignore_index=True)
                        proc_gdf[target_col] = proc_gdf["__tokens__"]
                        proc_gdf = proc_gdf.drop(columns="__tokens__")
                    else:
                        # keine Explosion, aber Listen in Strings umwandeln, damit hashbar
                        def normalize_scalar(v):
                            if is_listlike(v):
                                return ",".join(map(str, v))
                            return v
                        proc_gdf[target_col] = proc_gdf[target_col].map(normalize_scalar)

                    # 2) Jetzt sollte target_col nur noch skalare, hashbare Werte haben
                    unique_vals = proc_gdf[target_col].dropna().unique()
                    total_vals = len(unique_vals)

                    if total_vals == 0:
                        st.warning("Keine gültigen Werte in der gewählten Spalte gefunden.")
                    else:
                        progress = st.progress(0.0)
                        created_files = []

                        for i, val in enumerate(unique_vals, start=1):
                            label = str(val)
                            if label == "":
                                label = "EMPTY"
                            safe_label = re.sub(r"[^0-9A-Za-z_\-]+", "_", label)[:80]
                            filename = f"{base_name}__{target_col}__{safe_label}.geojson"
                            out_path = os.path.join(out_dir, filename)

                            sub = proc_gdf[proc_gdf[target_col] == val].copy()
                            if sub.empty:
                                continue

                            final_gdf = sub.copy()

                            if do_dissolve:
                                try:
                                    final_gdf["geometry"] = final_gdf.geometry.buffer(0)
                                    final_gdf = final_gdf.dissolve(by=target_col, as_index=False)
                                except Exception:
                                    # Wenn dissolve knallt, speichern wir ohne
                                    pass

                            final_gdf.to_file(out_path, driver="GeoJSON")
                            created_files.append(filename)

                            progress.progress(i / total_vals)

                        progress.progress(1.0)
                        st.balloons()
                        st.success("Fertig!")

                        with st.expander("Ergebnis"):
                            st.write(created_files)

                except Exception as e:
                    st.error(f"Speicherfehler: {e}")
else:
    st.info("👈 Wähle eine Datei.")
