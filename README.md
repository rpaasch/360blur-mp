# 360° Video Blur Tool

En webapplikation til automatisk detektering og sløring af ansigter og nummerplader i 360° panoramiske videoer.

[![Installation](https://img.shields.io/badge/Installation-One%20Line-green.svg)](https://github.com/rpaasch/360blur-mp#installation)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-blue.svg)](https://github.com/rpaasch/360blur-mp#installation)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Funktioner

- Upload og behandling af 360° videoer (MP4-format)
- Robust detektion af ansigter - både front, profil og delvist synlige
- Automatisk nummerpladedetektering med YOLO
- Intelligent sløring af detekterede objekter med avanceret algoritme
- Håndtering af 360° videokanter med wrap-around detektion
- Realtids-fremskridtsopdateringer via Socket.IO
- Download af færdigbehandlede videoer
- Paralleliseret baggrundsbehandling på flere CPU-kerner
- Understøtter forskellige sprog: Dansk, Engelsk, Tysk, Spansk, Italiensk, Bulgarsk

## Teknologier

- **Backend**: Flask, Socket.IO, OpenCV, YOLO (Ultralytics)
- **Multiprocessing**: Parallel videobehandling på tværs af CPU-kerner
- **Frontend**: HTML, JavaScript, Bootstrap
- **Internationalisering**: Flask-Babel

## Arkitektur

Applikationen bruger en skalerbar arkitektur:

1. **Flask Web App** (blur360_webapp.py):
   - Håndterer brugerinteraktion og filupload
   - Starter baggrundsprocesser til videobehandling
   - Viser fremskridt og resultater via Socket.IO

2. **Worker Process** (blur360_worker.py):
   - Kører som en separat proces via subprocess.Popen()
   - Behandler videoen parallelt via Python multiprocessing
   - Sender status og fremgangsoplysninger tilbage til webappen

3. **Detektion og Sløring**:
   - Anvender state-of-the-art YOLOv8-modeller til objekt detektion
   - DNN-baseret ansigtsdetektion som fallback
   - Ekstra wrap-around teknik til at håndtere 360° videoer
   - Optimeret sløring baseret på detekteringsstørrelse

## Installation

### Hurtig installation (Linux/macOS)

Kør denne kommando i din terminal for at installere 360blur automatisk:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rpaasch/360blur-mp/main/install-remote.sh)"
```

Alternativt med wget:

```bash
/bin/bash -c "$(wget -qO- https://raw.githubusercontent.com/rpaasch/360blur-mp/main/install-remote.sh)"
```

Installationsscriptet giver mulighed for avancerede indstillinger, herunder:
- Konfiguration af værtsnavn og port
- Opsætning som systemd-service (Linux)
- Integration med CloudFlare Tunnel for fjernbetjening

### Manuel installation

1. Clone eller download repository:
```
git clone https://github.com/rpaasch/360blur-mp.git
cd 360blur-mp
```

2. Opret et virtuel Python-miljø (anbefalet):
```
python -m venv venv
source venv/bin/activate  # På Windows: venv\Scripts\activate
```

3. Installer afhængigheder:
```
pip install -r requirements.txt
```

4. (Valgfrit) Installer YOLO for bedre detektion:
```
pip install ultralytics
```

5. Download nødvendige modeller:
```
python download_models.py
```

Dette vil automatisk hente de nødvendige modelfilet til mappen `models`.

6. Start applikationen:
```
python blur360_webapp.py
```

7. Åbn i browser: `http://localhost:5000`

### Afinstallation

Hvis du vil fjerne 360blur, kan du bruge det medfølgende afinstallationsscript:

```bash
cd /sti/til/360blur
./uninstall.sh
```

Afinstallationsscriptet vil fjerne alle programfiler, systemd-services, og konfiguration. Du vil blive spurgt om du vil beholde en backup af dine processerede videoer.

## Brug

1. Vælg en videofil (MP4-format) ved at klikke på "Vælg fil"
2. (Valgfrit) Aktiver debug mode for at se detekteringer
3. (Anbefalet) Behold DNN aktiveret for bedre detektion
4. Klik på "Upload og behandl"
5. Følg fremskridtet i realtid via progressbaren
6. Download den færdige video, når behandlingen er fuldført

## Fejlfinding

Hvis ansigter eller nummerplader ikke detekteres korrekt:

1. Kontroller at DNN-modellerne er korrekt installeret via download_models.py
2. Aktiver debug mode for at se hvilke områder der detekteres
3. For bedre nummerpladedetektering, installer ultralytics (YOLO)
4. Tjek logfilen for eventuelle fejlmeddelelser

## Begrænsninger

- Behandling af store 360° videoer kan være tidskrævende
- Ansigtsgenkendelse i 360° videoer er udfordrende på grund af forvrængning
- Meget små objekter kan være svære at detektere pålideligt