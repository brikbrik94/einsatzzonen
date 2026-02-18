# CI-Umsetzbarkeit in Streamlit (OE5ITH Design System)

Diese Notiz bewertet, wie weit sich das CI aus `corporate-identity.md` in einer Streamlit-App umsetzen lässt.

## Kurzfazit

- **Sehr gut umsetzbar (~80%)**: Farbpalette, Dark-Theme, typografische Basis, Card-Look, Statusfarben, einheitliche Abstände.
- **Teilweise umsetzbar (~50–60%)**: komplexe Topbar-Layouts mit linker/zentraler/rechter Zone, Sidebar-Drawer-Muster auf Mobile.
- **Eingeschränkt umsetzbar (~30–40%)**: pixelgenaue CSS-Architektur mit stabilen Selektoren über alle Streamlit-Versionen, vollständig eigene Interaktionslogik wie in maßgeschneiderten SPAs.

## 1) 1:1 in Streamlit abbildbar

1. **Farben & Dark-UI**
   - Streamlit-Theme (`primaryColor`, `backgroundColor`, `secondaryBackgroundColor`, `textColor`) deckt die CI-Basisfarben direkt ab.
   - Semantikfarben (z. B. Success) können per zusätzlichem CSS auf `.stAlert`, `.stMetric` und eigene Utility-Klassen angewendet werden.

2. **Typografie (Basis)**
   - Global via injected CSS (`st.markdown(..., unsafe_allow_html=True)`) umsetzbar.
   - `Segoe UI`, `system-ui`, `sans-serif` sind problemlos einstellbar.

3. **Card-/Button-Stil**
   - Container, Expander, Button und Eingabefelder lassen sich visuell konsistent an die CI annähern.
   - Hover-/Active-Zustände sind möglich, sofern Streamlit-Selektoren stabil bleiben.

4. **Sprache & Tonalität**
   - Bereits deutschsprachig; CI-konforme Textbausteine lassen sich zentralisieren.

## 2) Mit Workarounds umsetzbar

1. **Topbar-Standard (60px, 3 Zonen)**
   - Streamlit hat keine native App-weite Topbar mit freiem Slot-System.
   - Umsetzbar via Custom-HTML/CSS-Header in jeder Seite oder über ein gemeinsames Helper-Modul.

2. **Interne Sidebar-Muster**
   - Streamlit besitzt eine eigene Sidebar, die nicht wie ein vollständiger Off-Canvas-Drawer steuerbar ist.
   - Das CI-Verhalten ist näherungsweise umsetzbar (eigene HTML-Navigation im Body), allerdings mit höherem Wartungsaufwand.

3. **Responsive Spezialregeln**
   - Media Queries funktionieren mit injected CSS.
   - Fortgeschrittene Interaktionslogik (Escape/Fokus-Management/Backdrop) benötigt zusätzliches JS in Custom-Komponenten.

## 3) Schwierig in „purem“ Streamlit

1. **A11y-Feinlogik auf CI-Niveau**
   - Präzise Fokussteuerung und Drawer-Keyboard-UX wie im CI ist in Standard-Streamlit begrenzt.

2. **Komplexe Tool-Topbar mit einklappbaren Controls**
   - Ohne Custom Component nur eingeschränkt stabil; je Streamlit-Update können DOM-Selektoren brechen.

3. **Pixelperfekte Gleichheit zu einer klassischen Web-App**
   - Streamlit priorisiert Produktivität vor vollständiger DOM-Kontrolle.

## 4) Empfohlener Umsetzungsplan für dieses Repo

1. **Phase A – Schnellgewinn (1–2 Tage)**
   - Zentrales Theme in `.streamlit/config.toml` ergänzen.
   - `src/ui_theme.py` einführen (globale CSS-Utilities für Schrift, Cards, Buttons, Muted-Text, Status-Dot).
   - Auf allen Seiten über gemeinsame Funktion anwenden.

2. **Phase B – Konsistenz (2–4 Tage)**
   - Einheitliche Seitenkopf-Komponente (Brand + Icon + optionale Kontextlinks).
   - Wiederverwendbare „Card“-Hilfsfunktionen (Titel, Beschreibung, Status).

3. **Phase C – Erweitert (optional)**
   - Für komplexe Topbar/Drawer-Interaktionen gezielt eine kleine Custom-Component verwenden.
   - Nur dort einsetzen, wo das CI zwingend Interaktionsmuster fordert.

## 5) Konkretes Mapping (CI -> Streamlit)

- `--bg #1a1a1a` -> `backgroundColor`
- `--card-bg #252525` -> `secondaryBackgroundColor`
- `--text #e0e0e0` -> `textColor`
- `--accent #3b82f6` -> `primaryColor`
- `--accent-hover #2563eb` -> CSS für `button:hover`
- `--muted #888` -> Utility-Klasse `.ci-muted`
- `--border #333` -> Container/Inputs per CSS-Border
- `--success #22c55e` -> Status-Dot/Success-Hinweise

## Ergebnis

Das OE5ITH-CI ist für Streamlit **sehr gut als Look & Feel** umsetzbar. Für vollständig identisches Verhalten (Topbar-Interaktionen, Mobile-Drawer, A11y-Details) sollte man punktuell mit Custom-Komponenten ergänzen.
