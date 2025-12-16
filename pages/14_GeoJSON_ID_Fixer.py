import json
import os
import sys
from typing import Dict, Any, List, Tuple

import streamlit as st

# --- OPTIONAL TKINTER IMPORTS ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from src.geojson_tools import select_files_dialog

    GEO_TOOLS_AVAILABLE = True
except Exception:
    GEO_TOOLS_AVAILABLE = False


st.set_page_config(page_title="GeoJSON ID Repair", page_icon="🪪", layout="wide")
st.title("🪪 GeoJSON IDs ergänzen")
st.markdown(
    """
Lädt eine oder mehrere GeoJSON-Dateien, prüft die Features auf fehlende `id`-Felder
und ergänzt diese automatisch. Optional können die Dateien direkt überschrieben werden.
"""
)

# --- STATE ---
st.session_state.setdefault("id_repair_paths", [])


# --- HELPER ---
def ensure_feature_ids(data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Ensure every feature inside a FeatureCollection has an ``id`` value."""
    stats = {
        "features_total": 0,
        "ids_existing": 0,
        "ids_added": 0,
    }

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        return data, stats

    features: List[Dict[str, Any]] = data.get("features", []) or []
    stats["features_total"] = len(features)

    # Track existing IDs as strings to avoid duplicates when generating new ones
    existing_ids = {str(f.get("id")) for f in features if f.get("id") not in (None, "")}

    next_id = 1

    def generate_id() -> int:
        nonlocal next_id
        while str(next_id) in existing_ids:
            next_id += 1
        existing_ids.add(str(next_id))
        assigned = next_id
        next_id += 1
        return assigned

    updated_features = []
    for feature in features:
        fid = feature.get("id")
        if fid in (None, ""):
            fid = generate_id()
            stats["ids_added"] += 1
        else:
            stats["ids_existing"] += 1
        new_feat = feature.copy()
        new_feat["id"] = fid
        updated_features.append(new_feat)

    new_data = data.copy()
    new_data["features"] = updated_features
    return new_data, stats


def process_file(path: str) -> Tuple[Dict[str, Any], Dict[str, int]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ensure_feature_ids(data)


# --- SIDEBAR ---
st.sidebar.header("Dateiauswahl")
selection_mode = st.sidebar.radio(
    "Quelle", ["Upload (Browser)", "Lokale Auswahl (Tkinter)"]
)

selected_paths: List[str] = []
uploaded_files = []

if selection_mode == "Upload (Browser)":
    uploaded_files = st.sidebar.file_uploader(
        "GeoJSON-Dateien hochladen", type=["geojson", "json"], accept_multiple_files=True
    )
    inplace_write = False
    selected_paths = []
else:
    if not GEO_TOOLS_AVAILABLE:
        st.sidebar.warning(
            "Tkinter-Dateidialoge sind nicht verfügbar (src.geojson_tools fehlt). Bitte Upload nutzen."
        )
    else:
        if st.sidebar.button("Dateien wählen (Tk)"):
            chosen = select_files_dialog("GeoJSON-Dateien wählen")
            if chosen:
                st.session_state["id_repair_paths"] = chosen
        selected_paths = st.session_state.get("id_repair_paths", [])
    inplace_write = st.sidebar.checkbox(
        "Ausgewählte Dateien überschreiben (in-place)",
        value=bool(selected_paths),
        help="Schreibt die aktualisierten IDs direkt in die Dateien.",
    )


# --- MAIN LOGIC ---
st.divider()

if not uploaded_files and not selected_paths:
    st.info("👈 Wähle Dateien aus, um zu starten.")
else:
    results = []

    if uploaded_files:
        st.subheader("Upload-Verarbeitung")
        for up_file in uploaded_files:
            try:
                data = json.loads(up_file.getvalue().decode("utf-8"))
                new_data, stats = ensure_feature_ids(data)
                file_label = up_file.name
                results.append((file_label, stats, new_data, None))
            except Exception as e:
                st.error(f"Fehler beim Lesen von {up_file.name}: {e}")

    if selected_paths:
        st.subheader("Lokale Dateien")
        for path in selected_paths:
            try:
                new_data, stats = process_file(path)
                results.append((os.path.basename(path), stats, new_data, path))
            except Exception as e:
                st.error(f"Fehler beim Verarbeiten von {os.path.basename(path)}: {e}")

    if results:
        summary_rows = []
        for fname, stats, _, _ in results:
            summary_rows.append({
                "Datei": fname,
                "Features": stats["features_total"],
                "IDs vorhanden": stats["ids_existing"],
                "IDs ergänzt": stats["ids_added"],
            })

        st.markdown("### Ergebnis-Übersicht")
        st.dataframe(summary_rows, hide_index=True, width="stretch")

        st.markdown("---")
        st.markdown("### Ausgabe")

        for fname, stats, updated_data, path in results:
            st.write(f"**{fname}** – {stats['ids_added']} IDs ergänzt")
            payload = json.dumps(updated_data, ensure_ascii=False, indent=2)

            if path and inplace_write:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(payload)
                    st.success(f"{fname} wurde überschrieben.")
                except Exception as e:
                    st.error(f"Konnte {fname} nicht schreiben: {e}")
            else:
                st.download_button(
                    label=f"⬇️ {fname} herunterladen",
                    file_name=fname,
                    mime="application/geo+json",
                    data=payload,
                )

        if any(p for *_, p in results) and inplace_write:
            st.balloons()
