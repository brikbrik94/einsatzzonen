import streamlit as st
import pandas as pd
import os
import sys
import json

# --- IMPORT SHARED TOOLS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.geojson_tools import (
    load_config, 
    save_config
)

# --- SETUP ---
st.set_page_config(page_title="Leitstellen Config", layout="wide", page_icon="🏢")
st.title("🏢 Leitstellen Konfiguration")
st.markdown("Verwalte hier die Zuordnungen von **Bezirks-Codes** und **Bundesländern** zu deinen Leitstellen.")

CODE_CONFIG_FILE = "leitstellen_config.json"
STATE_CONFIG_FILE = "bundesland_config.json"
BUNDESLAENDER = [
    "Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", 
    "Salzburg", "Steiermark", "Tirol", "Vorarlberg", "Wien"
]

# --- HELPER ---
def load_code_conf(): return load_config(CODE_CONFIG_FILE)
def save_code_conf(data): save_config(CODE_CONFIG_FILE, data)

def load_state_conf(): return load_config(STATE_CONFIG_FILE)
def save_state_conf(data): save_config(STATE_CONFIG_FILE, data)

# --- STATE ---
if "ls_data" not in st.session_state: st.session_state["ls_data"] = load_code_conf()
if "state_data" not in st.session_state: st.session_state["state_data"] = load_state_conf()

# Init Dicts if empty
if not isinstance(st.session_state["ls_data"], dict): st.session_state["ls_data"] = {}
if not isinstance(st.session_state["state_data"], dict): st.session_state["state_data"] = {}

# Verfügbare Leitstellen Namen holen
available_leitstellen = sorted(list(st.session_state["ls_data"].keys()))


# --- UI STRUKTUR ---
tab_codes, tab_states = st.tabs(["🔢 Bezirks-Codes", "🇦🇹 Bundesländer"])

# ==========================================
# TAB 1: BEZIRKS CODES (Bisherige Logik)
# ==========================================
with tab_codes:
    col_new, col_info = st.columns([1, 2])
    with col_new:
        st.subheader("Neue Leitstelle anlegen")
        new_name = st.text_input("Name der Leitstelle", placeholder="z.B. Leitstelle Tirol")
        if st.button("➕ Hinzufügen", type="primary"):
            if new_name and new_name not in st.session_state["ls_data"]:
                st.session_state["ls_data"][new_name] = [] 
                save_code_conf(st.session_state["ls_data"])
                st.success(f"'{new_name}' angelegt!")
                st.rerun()
            elif new_name in st.session_state["ls_data"]:
                st.error("Name existiert bereits.")

    st.divider()
    
    if not st.session_state["ls_data"]:
        st.info("Noch keine Leitstellen vorhanden.")
    else:
        # Grid Layout
        cols = st.columns(2)
        for idx, (ls_name, codes) in enumerate(list(st.session_state["ls_data"].items())):
            with cols[idx % 2]:
                with st.container(border=True):
                    c_head, c_del = st.columns([4, 1])
                    with c_head: st.markdown(f"### {ls_name}")
                    with c_del:
                        if st.button("🗑️", key=f"del_{ls_name}"):
                            del st.session_state["ls_data"][ls_name]
                            save_code_conf(st.session_state["ls_data"])
                            st.rerun()

                    current_codes_str = ", ".join(codes)
                    new_codes_str = st.text_area(
                        f"Bezirks-Codes (2-stellig) für {ls_name}",
                        value=current_codes_str,
                        key=f"input_{ls_name}"
                    )
                    
                    if st.button(f"💾 Speichern ({ls_name})", key=f"save_{ls_name}"):
                        raw_list = [x.strip() for x in new_codes_str.split(",") if x.strip()]
                        clean_list = sorted(list(set(raw_list)))
                        st.session_state["ls_data"][ls_name] = clean_list
                        save_code_conf(st.session_state["ls_data"])
                        st.success("Gespeichert!")
                        st.rerun()

# ==========================================
# TAB 2: BUNDESLÄNDER (Neue Logik)
# ==========================================
with tab_states:
    st.subheader("Bundesland Zuweisung")
    st.info("Wenn keine Funkkennung gefunden wird, wird der Gemeindename geprüft. Ordne hier den Bundesländern die zuständige Leitstelle zu.")
    
    if not available_leitstellen:
        st.warning("Bitte erstelle zuerst im Tab 'Bezirks-Codes' mindestens eine Leitstelle.")
    else:
        # Formular für die 9 Bundesländer
        with st.form("state_mapping_form"):
            cols = st.columns(3)
            temp_config = st.session_state["state_data"].copy()
            
            # Option "Nicht zugewiesen" hinzufügen
            options = ["-"] + available_leitstellen
            
            for i, land in enumerate(BUNDESLAENDER):
                with cols[i % 3]:
                    # Aktueller Wert
                    current_val = temp_config.get(land, "-")
                    if current_val not in options: current_val = "-"
                    
                    selected = st.selectbox(
                        f"Leitstelle für **{land}**",
                        options=options,
                        index=options.index(current_val),
                        key=f"sel_{land}"
                    )
                    
                    # Im Temp Dict speichern
                    if selected == "-":
                        if land in temp_config: del temp_config[land]
                    else:
                        temp_config[land] = selected
            
            st.markdown("---")
            if st.form_submit_button("💾 Bundesland-Zuweisung speichern", type="primary"):
                st.session_state["state_data"] = temp_config
                save_state_conf(temp_config)
                st.success("Konfiguration gespeichert!")