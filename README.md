# 🚑 Einsatzzonen Suite

Eine Streamlit-basierte Tool-Suite zur Berechnung, Verfeinerung und Zusammenführung von **Einsatzzonen** auf Basis von Fahrzeiten (ORS).

## Voraussetzungen

- Python **3.11** (empfohlen)
- laufender OpenRouteService-Endpunkt (lokal oder remote)
- Linux VPS für Produktivbetrieb

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Start lokal

```bash
streamlit run Home.py
```

Die Module liegen in `pages/`:
- Step 1: `pages/1_Generator.py`
- Step 2: `pages/2_Refiner.py`
- Step 3: `pages/3_Resolver.py`

## ORS Konfiguration

Standardmäßig wird `ORS_BASE_URL` verwendet (falls gesetzt), sonst:

```text
http://127.0.0.1:8082/ors/v2
```

Beispiel:

```bash
export ORS_BASE_URL="http://10.0.0.5:8082/ors/v2"
streamlit run Home.py
```

## VPS Betrieb (empfohlen)

1. Systemd-Service nutzen (`deploy/einsatzzonen.service`).
2. Nginx als Reverse Proxy verwenden (`deploy/nginx-einsatzzonen.conf`).
3. TLS mit Let's Encrypt aktivieren.
4. Streamlit-Defaults über `deploy/streamlit-config.toml` bereitstellen.

### Service installieren

```bash
sudo cp deploy/einsatzzonen.service /etc/systemd/system/einsatzzonen.service
sudo systemctl daemon-reload
sudo systemctl enable --now einsatzzonen.service
sudo systemctl status einsatzzonen.service
```

### Nginx aktivieren

```bash
sudo cp deploy/nginx-einsatzzonen.conf /etc/nginx/sites-available/einsatzzonen
sudo ln -s /etc/nginx/sites-available/einsatzzonen /etc/nginx/sites-enabled/einsatzzonen
sudo nginx -t
sudo systemctl reload nginx
```

## Hinweise für Headless-Server

- Dateidialoge sind headless-fähig abgesichert. Wenn kein Desktop verfügbar ist, nutzt die App weiterhin die manuellen Pfadfelder.
- Für produktive Nutzung sollten Ein-/Ausgabepfade serverseitig klar definiert werden (z. B. `/srv/einsatzzonen/data`).

