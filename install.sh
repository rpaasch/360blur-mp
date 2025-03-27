#!/bin/bash
#
# 360blur Installer Script
# Dette script installerer 360blur-mp video processing tool
#

# Farve definitioner
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Banner
echo -e "${BLUE}${BOLD}"
echo "  ____    __    _____  ____  _     _     ____    "
echo " |___ \  / /_  | ____|/ ___|| |   | |   |  _ \   "
echo "   __) || '_ \ |  _|  \___ \| |   | |   | |_) |  "
echo "  / __/ | (_) || |___  ___) | |___| |___|  _ <   "
echo " |_____| \___/ |_____||____/|_____|_____|_| \_\  "
echo -e "${NC}"
echo -e "${CYAN}       Video Processing for 360° Privacy${NC}"
echo -e "${CYAN}        https://github.com/360blur-mp${NC}"
echo ""

# Check for Python 3.9 eller højere
echo -e "${BLUE}${BOLD}Checking for Python 3.9+...${NC}"
if command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 9 ]; then
        echo -e "${GREEN}✓ Found Python $PYTHON_VERSION${NC}"
        PYTHON_CMD="python3"
    else
        echo -e "${YELLOW}⚠ Found Python $PYTHON_VERSION, but 3.9+ is recommended${NC}"
        echo -e "${YELLOW}  Will attempt to continue, but you might experience issues${NC}"
        PYTHON_CMD="python3"
    fi
else
    echo -e "${RED}✗ Python 3 not found. Please install Python 3.9 or higher.${NC}"
    echo "  Visit: https://www.python.org/downloads/"
    exit 1
fi

# Opret projektmappe
echo -e "\n${BLUE}${BOLD}Setting up installation directory...${NC}"
read -p "Where would you like to install 360blur? [./360blur]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-"./360blur"}

# Konverter relativ sti til absolut
INSTALL_DIR=$(eval echo "$INSTALL_DIR")
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
echo -e "${GREEN}✓ Installation directory: $INSTALL_DIR${NC}"

# Hent kildekode
echo -e "\n${BLUE}${BOLD}Downloading source code...${NC}"
if command -v git >/dev/null 2>&1; then
    echo "Using git to clone repository..."
    if git clone https://github.com/rpaasch/360blur-mp.git .; then
        echo -e "${GREEN}✓ Source code downloaded${NC}"
    else
        echo -e "${RED}✗ Failed to download source code with git${NC}"
        echo "  Falling back to manual download..."
        if command -v curl >/dev/null 2>&1; then
            curl -L -o 360blur.zip https://github.com/rpaasch/360blur-mp/archive/refs/heads/main.zip
            unzip 360blur.zip
            mv 360blur-mp-main/* .
            rm -rf 360blur-mp-main
            rm 360blur.zip
            echo -e "${GREEN}✓ Source code downloaded with curl${NC}"
        else
            echo -e "${RED}✗ Neither git nor curl available. Please install manually.${NC}"
            exit 1
        fi
    fi
else
    echo "Git not found, using direct download..."
    if command -v curl >/dev/null 2>&1; then
        curl -L -o 360blur.zip https://github.com/rpaasch/360blur-mp/archive/refs/heads/main.zip
        unzip 360blur.zip
        mv 360blur-mp-main/* .
        rm -rf 360blur-mp-main
        rm 360blur.zip
        echo -e "${GREEN}✓ Source code downloaded${NC}"
    else
        echo -e "${RED}✗ Neither git nor curl available. Please install manually.${NC}"
        exit 1
    fi
fi

# Opret virtuel miljø
echo -e "\n${BLUE}${BOLD}Creating virtual environment...${NC}"
if $PYTHON_CMD -m venv venv; then
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${RED}✗ Failed to create virtual environment${NC}"
    echo "  Please ensure 'venv' module is available"
    exit 1
fi

# Aktiver virtuelt miljø
if [[ "$OSTYPE" == "win"* ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Installer afhængigheder
echo -e "\n${BLUE}${BOLD}Installing dependencies...${NC}"
if pip install --upgrade pip; then
    echo -e "${GREEN}✓ Pip updated${NC}"
else
    echo -e "${YELLOW}⚠ Failed to update pip, continuing with existing version${NC}"
fi

echo "Installing required packages..."
if pip install -r requirements.txt; then
    echo -e "${GREEN}✓ Required packages installed${NC}"
else
    echo -e "${RED}✗ Failed to install required packages${NC}"
    exit 1
fi

# Installer YOLO (valgfrit)
echo -e "\n${BLUE}${BOLD}Do you want to install YOLO for improved detection? (y/n) [y]:${NC} "
read -p "" INSTALL_YOLO
INSTALL_YOLO=${INSTALL_YOLO:-"y"}

if [[ $INSTALL_YOLO =~ ^[Yy]$ ]]; then
    echo "Installing YOLO..."
    if pip install ultralytics>=8.0.0; then
        echo -e "${GREEN}✓ YOLO installed${NC}"
    else
        echo -e "${YELLOW}⚠ Failed to install YOLO, will use OpenCV DNN instead${NC}"
    fi
else
    echo "Skipping YOLO installation, will use OpenCV DNN only."
fi

# Download modeller
echo -e "\n${BLUE}${BOLD}Downloading detection models...${NC}"
if python download_models.py; then
    echo -e "${GREEN}✓ Detection models downloaded${NC}"
else
    echo -e "${RED}✗ Failed to download models${NC}"
    echo "  You can try again later by running: python download_models.py"
fi

# Kompiler oversættelser
echo -e "\n${BLUE}${BOLD}Compiling translations...${NC}"
if pybabel compile -d translations; then
    echo -e "${GREEN}✓ Translations compiled${NC}"
else
    echo -e "${YELLOW}⚠ Failed to compile translations, English will be used as fallback${NC}"
fi

# Opret startup script
echo -e "\n${BLUE}${BOLD}Creating startup script...${NC}"
if [[ "$OSTYPE" == "win"* ]]; then
    # Windows batch fil
    cat > start_blur360.bat << 'EOL'
@echo off
call venv\Scripts\activate
python blur360_webapp.py
EOL
    echo -e "${GREEN}✓ Created start_blur360.bat${NC}"
else
    # Unix shell script
    cat > start_blur360.sh << 'EOL'
#!/bin/bash
source venv/bin/activate
python blur360_webapp.py
EOL
    chmod +x start_blur360.sh
    echo -e "${GREEN}✓ Created start_blur360.sh${NC}"
fi

# Færdig!
echo -e "\n${GREEN}${BOLD}Installation complete!${NC}"
echo -e "To start 360blur, run:"

if [[ "$OSTYPE" == "win"* ]]; then
    echo -e "${CYAN}  start_blur360.bat${NC}"
else
    echo -e "${CYAN}  ./start_blur360.sh${NC}"
fi

echo -e "\nOpen http://localhost:5000 in your browser after starting."
echo -e "\n${PURPLE}Thank you for installing 360blur!${NC}"
echo -e "${CYAN}For updates and documentation, visit https://github.com/rpaasch/360blur-mp${NC}"