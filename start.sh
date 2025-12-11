#!/bin/bash

# Farben für schönere Ausgabe
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚑 Starte Einsatzzonen Suite...${NC}"

# 1. VENV aktivieren
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo -e "${RED}FEHLER: Ordner '.venv' nicht gefunden!${NC}"
    echo "Bitte erstelle zuerst eine virtuelle Umgebung (python -m venv .venv)"
    exit 1
fi

# 2. Abhängigkeiten automatisch abgleichen
# Wir nutzen pip install. Das prüft gegen requirements.txt.
# Wenn alles da ist, macht es nichts. Wenn etwas fehlt (wie fiona), installiert es nach.
if [ -f "requirements.txt" ]; then
    echo -e "Prüfe Abhängigkeiten aus requirements.txt..."
    
    # Wir führen pip install aus. Wenn Fehler auftreten, brechen wir ab.
    pip install -r requirements.txt
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Alle Abhängigkeiten sind aktuell.${NC}"
    else
        echo -e "${RED}Fehler bei der Installation der Abhängigkeiten.${NC}"
        echo "Bitte prüfe die Fehlermeldung oben."
        exit 1
    fi
else
    echo -e "${YELLOW}WARNUNG: Keine 'requirements.txt' gefunden.${NC}"
fi

# 3. Starten
if [ ! -f "Home.py" ]; then
    echo -e "${RED}FEHLER: 'Home.py' nicht gefunden! Bist du im richtigen Ordner?${NC}"
    exit 1
fi

echo -e "${GREEN}🚀 Starte Streamlit...${NC}"
streamlit run Home.py
