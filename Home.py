import streamlit as st

st.set_page_config(
    page_title="Einsatzzonen Suite",
    page_icon="🚑",
    layout="wide"
)

st.title("🚑 Einsatzzonen Generator Suite")

st.markdown("""
### Willkommen im Control Center

Wähle links in der Seitenleiste das gewünschte Modul aus:

---

#### 1️⃣ **Generator (Step 1)**
* Erstellt das Hexagon-Raster.
* Filtert Dienststellen.
* Berechnet die ersten groben Zonen.
* *Output:* Batch-Index für Step 2.

#### 2️⃣ **Refiner (Step 2)**
* Liest den Batch-Index.
* Verfeinert die Zonen mit `driving-emergency` Profil.
* Nutzt Multithreading und Fallback-Routing.
* *Output:* Präzise, geschnittene Zonen pro Gebiet.

#### 3️⃣ **Resolver (Step 3)**
* Fügt die verfeinerten Teil-Gebiete zusammen.
* Löst Grenzen zwischen Bezirken auf (Dissolve).
* Finalisiert die Attribute.

---
""")

st.info("💡 Tipp: Die Einstellungen werden automatisch in `general_config.json` und `step2_config.json` gespeichert.")
