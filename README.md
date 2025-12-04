# 🚑 Einsatzzonen Generator Toolset

Eine Sammlung von Python-Tools (mit Streamlit GUI) zur Berechnung, Verfeinerung und Zusammenführung von **Einsatzzonen** (Voronoi/Isochronen-Logik) basierend auf Fahrzeiten.

Das System nutzt **OpenRouteService (ORS)** für das Routing und arbeitet in einem 3-stufigen Prozess, um auch große Gebiete (z.B. Bundesländer) performant und präzise zu berechnen.

## 📋 Features

* **Raster-basiert:** Nutzt ein Hexagon-Gitter (konfigurierbare Auflösung) für die Flächenberechnung.
* **Outbound-Routing:** Berechnet Fahrzeiten korrekt von der **Wache ZUM Einsatzort** (berücksichtigt Einbahnstraßen bei der Ausfahrt).
* **Two-Stage Process:**
    * *Step 1:* Grobe Vorberechnung und Kandidaten-Auswahl (Top-N).
    * *Step 2:* Präzise Nachberechnung mit spezialisierten Profilen (z.B. `driving-emergency`).
* **Batch-Processing:** Automatische Verarbeitung von komplexen Gebieten (z.B. feature-weise nach Bezirken) mit automatischer Indexierung.
* **Robust:** Fallback-Mechanismen (Matrix -> Einzel-Routing), Multithreading und Smart-Filtering.

---

## 🛠️ Installation

1.  **Repository klonen:**
    ```bash
    git clone <dein-repo-url>
    cd einsatzzonen-generator
    ```

2.  **Virtuelle Umgebung erstellen (Empfohlen):**
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # Mac/Linux:
    source .venv/bin/activate
    ```

3.  **Abhängigkeiten installieren:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **OpenRouteService (ORS):**
    Das Tool benötigt eine laufende ORS-Instanz (empfohlen: lokal via Docker), da öffentliche APIs die Menge an Anfragen oft blockieren.
    * Standard-URL: `http://127.0.0.1:8082/ors/v2`

---

## 🚀 Workflow

Der Prozess ist in drei spezialisierte Skripte unterteilt:

### 1️⃣ Step 1: Generator (`app.py`)
Erstellt das Hexagon-Gitter und führt eine erste Berechnung durch, um potenzielle Kandidaten-Wachen pro Hexagon zu identifizieren.

* **Start:** `streamlit run app.py`
* **Input:** Gebiets-GeoJSON (z.B. Bezirksgrenzen), Dienststellen-GeoJSON.
* **Funktion:**
    * Erstellt Hexagone (z.B. 500m).
    * Filtert relevante Wachen (Drinnen + N nächste Nachbarn).
    * Führt schnelles Routing durch (z.B. `driving-car`).
* **Wichtig:** Aktiviere **"Sequentielle Verarbeitung"** für große Gebiete und **"Kandidaten speichern"**, damit Step 2 arbeiten kann.
* **Output:** Erzeugt einen Ordner mit `parts/` (Hex-Dateien) und einer `batch_index.json`.

### 2️⃣ Step 2: Refiner (`step2.py`)
Nimmt die Ergebnisse aus Step 1 und verfeinert sie mit präzisem Routing und Multithreading.

* **Start:** `streamlit run step2.py`
* **Input:** Die `batch_index.json` aus Step 1.
* **Funktion:**
    * Lädt automatisch alle Teil-Dateien.
    * Prüft die Top-N Kandidaten (z.B. Top 5) aus Step 1.
    * Nutzt das **Emergency-Profil** (z.B. Wendehammer ignorieren).
    * Nutzt `/directions` (Einzel-Routing) als Fallback, falls die Matrix fehlschlägt.
    * Schneidet (Clipping) die Ergebnisse exakt an den Gebietsgrenzen ab.
* **Output:** Hochpräzise `zones_final_clipped.geojson`.

### 3️⃣ Step 3: Resolver (`resolve.py`)
Fügt einzelne Ergebnisse (z.B. aus verschiedenen Bezirken) zu einer großen Karte zusammen.

* **Start:** `streamlit run resolve.py`
* **Input:** Mehrere GeoJSON-Dateien (z.B. `Refined_BezirkA.geojson`, `Refined_BezirkB.geojson`).
* **Funktion:**
    * Merged alle Dateien.
    * Erlaubt Auswahl des Namens-Tags (z.B. `alt_name` -> `name`).
    * **Dissolve:** Entfernt Grenzen zwischen gleichen Zonen (z.B. wenn eine Wache über eine Bezirksgrenze hinweg zuständig ist).
* **Output:** Finale `Zonen_Final_Merged.geojson`.

---

## ⚙️ Wichtige Einstellungen

| Einstellung | Empfehlung | Beschreibung |
| :--- | :--- | :--- |
| **Hexagon Kantenlänge** | 100m - 500m | Kleiner = genauere Grenzen, aber längere Rechenzeit (quadratischer Anstieg). |
| **N Nachbarn (Step 1)** | 10 - 20 | Wie viele Wachen sollen grob in Betracht gezogen werden? Bei Flüssen/Bergen höher setzen! |
| **Top N (Step 2)** | 3 - 5 | Wie viele der Kandidaten sollen präzise nachgerechnet werden? |
| **Profil (Step 2)** | `driving-emergency` | Sollte auf dem ORS Server konfiguriert sein für realistische Blaulicht-Fahrten. |

---

## 📂 Ordnerstruktur (Output)

```text
/Output_Folder
    /YYYY-MM-DD_LaufName
        batch_index.json       <-- Input für Step 2
        run_config.json        <-- Dokumentation der Einstellungen
        /parts                 <-- Rohe Hexagon-Teile
            hex_Feat_0.geojson
            hex_Feat_1.geojson
        /single_zones          <-- (Optional) Einzelne Zonen zur Vorschau
