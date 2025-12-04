#!/bin/bash

# Farben
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}🚑 Starte Einsatzzonen Suite...${NC}"

# 1. VENV aktivieren
source .venv/bin/activate

# 2. Ordnerstruktur für Multi-Page App sicherstellen
if [ ! -d "pages" ]; then
    echo "Erstelle 'pages' Ordner für Navigation..."
    mkdir pages
fi

# 3. Dateien verschieben (falls sie noch im Hauptordner liegen)
# Wir benennen sie um, damit sie eine Nummerierung in der Sidebar haben (1_..., 2_...)

if [ -f "app.py" ]; then
    echo "Verschiebe app.py -> pages/1_Generator.py"
    mv app.py pages/1_Generator.py
fi

if [ -f "step2.py" ]; then
    echo "Verschiebe step2.py -> pages/2_Refiner.py"
    mv step2.py pages/2_Refiner.py
fi

if [ -f "resolve.py" ]; then
    echo "Verschiebe resolve.py -> pages/3_Resolver.py"
    mv resolve.py pages/3_Resolver.py
fi

# 4. Starten
echo -e "${GREEN}🚀 Starte Browser...${NC}"
streamlit run Home.py
