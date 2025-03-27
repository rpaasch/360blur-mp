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
- Integration med CloudFlare Tunnel for fjernbetjening og sikker adgang udefra

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

## CloudFlare Tunnel Integration

360blur understøtter integration med CloudFlare Tunnels, hvilket giver sikker fjernadgang til din 360blur-instans fra hvor som helst i verden uden behov for port forwarding eller at eksponere din IP-adresse.

### Forudsætninger for CloudFlare Tunnel:

1. En CloudFlare-konto (gratis)
2. Et domæne registreret hos CloudFlare (eller et subdomæne af dit eksisterende domæne)
3. Et CloudFlare Tunnel-token oprettet i CloudFlare-dashboardet

### Sådan opretter du en CloudFlare Tunnel (2025):

1. Gå direkte til [CloudFlare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Klik på "Tunnels" i venstremenuen
3. Klik på "Create a tunnel" og giv tunnelen et navn
4. Vælg "Manual" som installationsmetode
5. Kopiér det viste tunnel-token
6. Vend tilbage til din 360blur-installation og kør:
   ```
   cd /sti/til/360blur/cloudflare && ./setup_cloudflare.sh /sti/til/360blur
   ```
7. Følg anvisningerne for at indtaste dit token og domæne

### Adgang til din 360blur-instans via CloudFlare:

Efter konfiguration vil din 360blur-instans være tilgængelig på den URL, du har angivet under opsætningen (f.eks. `https://360blur.mitdomæne.com`).

## Fejlfinding

Hvis ansigter eller nummerplader ikke detekteres korrekt:

1. Kontroller at DNN-modellerne er korrekt installeret via download_models.py
2. Aktiver debug mode for at se hvilke områder der detekteres
3. For bedre nummerpladedetektering, installer ultralytics (YOLO)
4. Tjek logfilen for eventuelle fejlmeddelelser

### CloudFlare Tunnel fejlfinding:

1. Kontroller at CloudFlare-tunnelen kører med `sudo systemctl status cloudflared-360blur` (Linux)
2. Tjek tunnellogfilen i `/sti/til/360blur/cloudflare/cloudflared.log`
3. Verificer at dit domæne er korrekt konfigureret i CloudFlare Zero Trust dashboardet
4. Gå til [CloudFlare Zero Trust Dashboard](https://one.dash.cloudflare.com/) > Tunnels
5. Tjek at tunnelen er markeret som "Active" 
6. Klik på tunnelens navn og tjek "Public Hostnames" konfigurationen
7. Sørg for at porten i 360blur's config.ini matcher den port, der er angivet i CloudFlare-konfigurationen

## Begrænsninger

- Behandling af store 360° videoer kan være tidskrævende
- Ansigtsgenkendelse i 360° videoer er udfordrende på grund af forvrængning
- Meget små objekter kan være svære at detektere pålideligt
- CloudFlare Tunnel kræver et domæne, der er konfigureret med CloudFlare