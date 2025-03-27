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
echo "   ____    __    ___    ____   _       _     _   ____    "
echo "  |___ /  / /_  / _ \\  | __ ) | |     | |   | | |  _ \\   "
echo "    |_ \\ | '_ \\| | | | |  _ \\ | |     | |   | | | |_) |  "
echo "   ___) || (_) | |_| | | |_) || |___  | |___| | |  _ <   "
echo "  |____/  \\___/ \\___/  |____/ |_____| |_____|_| |_| \\_\\  "
echo -e "${NC}"
echo -e "${CYAN}         Video Processing for 360° Privacy${NC}"
echo -e "${CYAN}        https://github.com/rpaasch/360blur-mp${NC}"
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

# Tjek om destinationen kan oprettes/bruges
if [[ "$INSTALL_DIR" == /* ]]; then
    # Absolut sti - tjek skriverettigheder
    if [[ ! -d $(dirname "$INSTALL_DIR") ]]; then
        echo -e "${YELLOW}Warning: Parent directory $(dirname "$INSTALL_DIR") does not exist${NC}"
    fi
    
    if [[ ! -w $(dirname "$INSTALL_DIR") ]]; then
        echo -e "${RED}Error: No write permission to create directory at $INSTALL_DIR${NC}"
        echo -e "${YELLOW}Please choose a directory in your home folder like ~/360blur or ./360blur${NC}"
        read -p "New installation directory: " INSTALL_DIR
        INSTALL_DIR=${INSTALL_DIR:-"./360blur"}
        INSTALL_DIR=$(eval echo "$INSTALL_DIR")
    fi
fi

# Create directory and change to it
if mkdir -p "$INSTALL_DIR"; then
    cd "$INSTALL_DIR" || {
        echo -e "${RED}Error: Could not change to $INSTALL_DIR${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Installation directory: $INSTALL_DIR${NC}"
else
    echo -e "${RED}Error: Could not create $INSTALL_DIR${NC}"
    echo -e "${YELLOW}Installing to current directory instead${NC}"
    INSTALL_DIR=$(pwd)
    echo -e "${GREEN}✓ Using current directory: $INSTALL_DIR${NC}"
fi

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

# Installer YOLO (valgfrit) - tjek først om det allerede er installeret
echo -e "\n${BLUE}${BOLD}Checking for YOLO (Ultralytics)...${NC}"
if python -c "import ultralytics" &>/dev/null; then
    echo -e "${GREEN}✓ YOLO (Ultralytics) is already installed${NC}"
    YOLO_INSTALLED=true
else
    echo -e "\n${BLUE}${BOLD}Do you want to install YOLO for improved detection? (y/n) [y]:${NC} "
    read -p "" INSTALL_YOLO
    INSTALL_YOLO=${INSTALL_YOLO:-"y"}

    if [[ $INSTALL_YOLO =~ ^[Yy]$ ]]; then
        echo "Installing YOLO..."
        if pip install ultralytics>=8.0.0; then
            echo -e "${GREEN}✓ YOLO installed${NC}"
            YOLO_INSTALLED=true
        else
            echo -e "${YELLOW}⚠ Failed to install YOLO, will use OpenCV DNN instead${NC}"
            YOLO_INSTALLED=false
        fi
    else
        echo "Skipping YOLO installation, will use OpenCV DNN only."
        YOLO_INSTALLED=false
    fi
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
echo -e "\n${BLUE}${BOLD}Creating startup and uninstall scripts...${NC}"
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
    
    # Create a symlink to the actual uninstall script
    if [ -f uninstall.sh ]; then
        chmod +x uninstall.sh
        echo -e "${GREEN}✓ Uninstall script is ready${NC}"
    else
        echo -e "${YELLOW}Warning: Uninstall script was not found${NC}"
        # Create a minimal uninstall script that gives instructions
        cat > uninstall.sh << 'EOL'
#!/bin/bash
# Script til at afinstallere 360blur
# For at bruge det, kør ./uninstall.sh

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BLUE}${BOLD}"
echo "   ____    __    ___    ____   _       _     _   ____    "
echo "  |___ /  / /_  / _ \\  | __ ) | |     | |   | | |  _ \\   "
echo "    |_ \\ | '_ \\| | | | |  _ \\ | |     | |   | | | |_) |  "
echo "   ___) || (_) | |_| | | |_) || |___  | |___| | |  _ <   "
echo "  |____/  \\___/ \\___/  |____/ |_____| |_____|_| |_| \\_\\  "
echo -e "${NC}"
echo -e "${RED}         Uninstaller for 360blur${NC}"

# Get current directory
INSTALL_DIR=$(pwd)

# Ask for confirmation
echo -e "${YELLOW}${BOLD}WARNING: This will uninstall 360blur and remove all related files from:${NC}"
echo -e "${BLUE}$INSTALL_DIR${NC}"
read -p "Are you sure you want to continue? (y/n) [n]: " CONFIRM
CONFIRM=${CONFIRM:-"n"}

if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Uninstallation cancelled${NC}"
    exit 0
fi

# Perform basic uninstallation
echo -e "\n${BLUE}${BOLD}Uninstalling 360blur...${NC}"

# Remove virtual environment
if [ -d "$INSTALL_DIR/venv" ]; then
    echo "Removing virtual environment..."
    rm -rf "$INSTALL_DIR/venv"
fi

# Remove data directories
for dir in "uploads" "processed" "status" "models" "cloudflare" "systemd"; do
    if [ -d "$INSTALL_DIR/$dir" ]; then
        echo "Removing $dir directory..."
        rm -rf "$INSTALL_DIR/$dir"
    fi
done

echo -e "${GREEN}${BOLD}Basic uninstallation completed!${NC}"
echo -e "You may want to manually check for any remaining files in: $INSTALL_DIR"
echo -e "${YELLOW}To fully remove the application, check for systemd services:${NC}"
echo -e "  sudo systemctl disable 360blur.service (if installed)"
echo -e "  sudo systemctl disable cloudflared-360blur.service (if installed)"
EOL
        chmod +x uninstall.sh
        echo -e "${GREEN}✓ Created basic uninstall.sh${NC}"
    fi
fi

# Tilbyd avanceret konfiguration
echo -e "\n${BLUE}${BOLD}Do you want to configure advanced options? (y/n) [n]:${NC} "
read -p "" CONFIGURE_ADVANCED
CONFIGURE_ADVANCED=${CONFIGURE_ADVANCED:-"n"}

if [[ $CONFIGURE_ADVANCED =~ ^[Yy]$ ]]; then
    echo -e "\n${BLUE}Server Configuration${NC}"
    
    # Konfigurer IP og port
    echo -e "Which interface should the server bind to?"
    echo -e "  1) localhost only (127.0.0.1) - Most secure, accessible only from this computer"
    echo -e "  2) All interfaces (0.0.0.0) - Accessible from other devices on your network"
    echo -e "  3) Specific IP address - Bind to a specific network interface"
    echo -e "Enter your choice [1]: "
    read -p "" BIND_CHOICE
    BIND_CHOICE=${BIND_CHOICE:-"1"}
    
    case $BIND_CHOICE in
        1) HOST="127.0.0.1" ;;
        2) HOST="0.0.0.0" ;;
        3) 
            echo -e "Enter the IP address to bind to: "
            read -p "" HOST
            HOST=${HOST:-"127.0.0.1"}
            ;;
        *) HOST="127.0.0.1" ;;
    esac
    
    echo -e "Enter the port number for the server [5000]: "
    read -p "" PORT
    PORT=${PORT:-"5000"}
    
    # Opdater config.ini
    CONFIG_FILE="$INSTALL_DIR/config.ini"
    if [[ -f "$CONFIG_FILE" ]]; then
        # Update existing config
        sed -i.bak "s/host = .*/host = $HOST/g" "$CONFIG_FILE"
        sed -i.bak "s/port = .*/port = $PORT/g" "$CONFIG_FILE"
        rm -f "${CONFIG_FILE}.bak"
    else
        # Create new config
        cat > "$CONFIG_FILE" << EOL
[server]
# Host setting: 
# - Use 127.0.0.1 for local access only
# - Use 0.0.0.0 to allow access from other computers on your network
# - Use a specific IP to bind to that address
host = $HOST

# Port number
port = $PORT

# Debug mode (True/False)
debug = False

[processing]
# Maximum number of parallel processes for video processing
# Default: Set to number of CPU cores - 1
# max_workers = 3

# Default language
language = da

# Enable detailed logging
verbose_logging = False

[cloudflare]
# Set to True to enable CloudFlare Tunnel integration
enabled = False

# CloudFlare Tunnel token (if using token authentication)
# token = your_cloudflare_token

# CloudFlare hostname (e.g. your-tunnel.domain.com)
# hostname = your-tunnel.domain.com
EOL
    fi
    
    # Offer systemd service setup on Linux
    if [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl &> /dev/null; then
        echo -e "\n${BLUE}Would you like to set up 360blur as a systemd service? (y/n) [n]:${NC} "
        read -p "" SETUP_SERVICE
        SETUP_SERVICE=${SETUP_SERVICE:-"n"}
        
        if [[ $SETUP_SERVICE =~ ^[Yy]$ ]]; then
            # Create systemd directory if it doesn't exist
            if [[ ! -d "$INSTALL_DIR/systemd" ]]; then
                mkdir -p "$INSTALL_DIR/systemd"
            fi
            
            # Create service file
            cat > "$INSTALL_DIR/systemd/360blur.service" << EOL
[Unit]
Description=360blur Video Processing Service
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/blur360_webapp.py
Restart=on-failure
RestartSec=5s
Environment=PYTHONUNBUFFERED=1

# Security options
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOL
            
            # Create setup script
            cat > "$INSTALL_DIR/systemd/setup_service.sh" << 'EOL'
#!/bin/bash
#
# Setup script for 360blur systemd service
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the installation directory from the first argument or use current directory
INSTALLDIR=${1:-$(pwd)}
USER=$(whoami)

echo -e "${BLUE}Setting up 360blur systemd service${NC}"
echo -e "Installation directory: ${INSTALLDIR}"
echo -e "Service will run as user: ${USER}"

# Check if systemd is available
if ! command -v systemctl &> /dev/null; then
    echo -e "${RED}Error: systemd is not available on this system${NC}"
    echo -e "This script only works on systems using systemd (most modern Linux distributions)"
    exit 1
fi

# Check if user has sudo privileges
if ! sudo -v &> /dev/null; then
    echo -e "${RED}Error: You need sudo privileges to install a systemd service${NC}"
    exit 1
fi

# Create a copy of the service file with proper paths
SERVICE_FILE="${INSTALLDIR}/systemd/360blur.service"
TMP_SERVICE_FILE="/tmp/360blur.service"

if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}Error: Service template file not found at ${SERVICE_FILE}${NC}"
    exit 1
fi

# Replace placeholders in the service file
cat "$SERVICE_FILE" | sed "s|%INSTALLDIR%|${INSTALLDIR}|g" | sed "s|%USER%|${USER}|g" > "$TMP_SERVICE_FILE"

# Install the service
echo -e "${BLUE}Installing systemd service...${NC}"
sudo cp "$TMP_SERVICE_FILE" /etc/systemd/system/360blur.service
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to install service file${NC}"
    exit 1
fi

# Reload systemd configuration
echo -e "${BLUE}Reloading systemd configuration...${NC}"
sudo systemctl daemon-reload
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to reload systemd configuration${NC}"
    exit 1
fi

# Enable the service
echo -e "${BLUE}Enabling 360blur service...${NC}"
sudo systemctl enable 360blur.service
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to enable service${NC}"
    exit 1
fi

echo -e "${GREEN}360blur service has been successfully installed and enabled!${NC}"
echo -e "You can now manage the service using the following commands:"
echo -e "  ${YELLOW}sudo systemctl start 360blur${NC} - Start the service"
echo -e "  ${YELLOW}sudo systemctl stop 360blur${NC} - Stop the service"
echo -e "  ${YELLOW}sudo systemctl restart 360blur${NC} - Restart the service"
echo -e "  ${YELLOW}sudo systemctl status 360blur${NC} - Check service status"
echo -e "  ${YELLOW}sudo journalctl -u 360blur${NC} - View service logs"

echo -e "\nDo you want to start the service now? (y/n) [y]: "
read -r START_SERVICE
START_SERVICE=${START_SERVICE:-"y"}

if [[ $START_SERVICE =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Starting 360blur service...${NC}"
    sudo systemctl start 360blur.service
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Service started successfully!${NC}"
        echo -e "You can access 360blur at http://localhost:5000"
    else
        echo -e "${RED}Failed to start service${NC}"
        echo -e "Please check the service status with: sudo systemctl status 360blur.service"
    fi
fi

# Clean up
rm -f "$TMP_SERVICE_FILE"
EOL
            
            chmod +x "$INSTALL_DIR/systemd/setup_service.sh"
            
            echo -e "\n${GREEN}Systemd service files have been created${NC}"
            echo -e "To install the service, run:"
            echo -e "${CYAN}  cd $INSTALL_DIR/systemd && ./setup_service.sh $INSTALL_DIR${NC}"
        fi
    fi
    
    # Offer CloudFlare tunnel setup
    echo -e "\n${BLUE}${BOLD}Would you like to set up CloudFlare Tunnel for remote access? (y/n) [n]:${NC} "
    read -p "" SETUP_CLOUDFLARE
    SETUP_CLOUDFLARE=${SETUP_CLOUDFLARE:-"n"}
    
    if [[ $SETUP_CLOUDFLARE =~ ^[Yy]$ ]]; then
        echo -e "\n${YELLOW}=== CloudFlare Tunnel Information ===${NC}"
        echo -e "CloudFlare Tunnels allow secure remote access to your 360blur instance from anywhere"
        echo -e "without port forwarding or exposing your IP address."
        echo -e "\n${YELLOW}Prerequisites:${NC}"
        echo -e "1. A CloudFlare account (free)"
        echo -e "2. A domain registered with CloudFlare (or a subdomain of your existing domain)"
        echo -e "3. A CloudFlare Tunnel token that you'll create in the CloudFlare dashboard\n"
        echo -e "${YELLOW}Steps to get your CloudFlare Tunnel token (2025):${NC}"
        echo -e "1. Go to ${CYAN}https://one.dash.cloudflare.com/${NC} and log in"
        echo -e "2. Click on 'Tunnels' in the left sidebar"
        echo -e "3. Click 'Create a tunnel' and give it a name"
        echo -e "4. Select the 'Manual' installation method"
        echo -e "5. Copy your tunnel token when shown"
        echo -e "6. Use this token during the 360blur CloudFlare setup\n"
        
        # Create cloudflare directory if it doesn't exist
        if [[ ! -d "$INSTALL_DIR/cloudflare" ]]; then
            mkdir -p "$INSTALL_DIR/cloudflare"
        fi
        
        # Create setup script
        cat > "$INSTALL_DIR/cloudflare/setup_cloudflare.sh" << 'EOL'
#!/bin/bash
#
# Setup script for 360blur CloudFlare Tunnel
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the installation directory from the first argument or use current directory
INSTALLDIR=${1:-$(pwd)}
CONFIG_FILE="${INSTALLDIR}/config.ini"
CLOUDFLARED_CONFIG="${INSTALLDIR}/cloudflare/cloudflared_config.yaml"

echo -e "${BLUE}Setting up 360blur CloudFlare Tunnel${NC}"
echo -e "Installation directory: ${INSTALLDIR}"

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo -e "${YELLOW}CloudFlare Tunnel client (cloudflared) is not installed${NC}"
    echo -e "Would you like to install it now? (y/n) [y]: "
    read -r INSTALL_CLOUDFLARED
    INSTALL_CLOUDFLARED=${INSTALL_CLOUDFLARED:-"y"}
    
    if [[ $INSTALL_CLOUDFLARED =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Installing CloudFlare Tunnel client...${NC}"
        
        # Detect OS and install cloudflared
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            if command -v apt-get &> /dev/null; then
                # Debian/Ubuntu
                echo -e "Detected Debian/Ubuntu system"
                curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
                sudo apt-get update && sudo apt-get install -y ./cloudflared.deb
                rm cloudflared.deb
            elif command -v yum &> /dev/null; then
                # RHEL/CentOS/Fedora
                echo -e "Detected RHEL/CentOS/Fedora system"
                curl -L --output cloudflared.rpm https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-x86_64.rpm
                sudo yum install -y ./cloudflared.rpm
                rm cloudflared.rpm
            else
                echo -e "${RED}Unsupported Linux distribution${NC}"
                echo -e "Please install cloudflared manually from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation"
                exit 1
            fi
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            echo -e "Detected macOS system"
            if command -v brew &> /dev/null; then
                brew install cloudflare/cloudflare/cloudflared
            else
                echo -e "${RED}Homebrew is not installed${NC}"
                echo -e "Please install Homebrew first (https://brew.sh/) or install cloudflared manually"
                exit 1
            fi
        else
            echo -e "${RED}Unsupported operating system: $OSTYPE${NC}"
            echo -e "Please install cloudflared manually from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation"
            exit 1
        fi
        
        # Check if installation was successful
        if ! command -v cloudflared &> /dev/null; then
            echo -e "${RED}Failed to install cloudflared${NC}"
            exit 1
        else
            echo -e "${GREEN}CloudFlare Tunnel client installed successfully${NC}"
        fi
    else
        echo -e "${RED}CloudFlare Tunnel client is required for this setup${NC}"
        exit 1
    fi
fi

# Create directory for CloudFlare configuration
mkdir -p "${INSTALLDIR}/cloudflare"

# Ask for CloudFlare tunnel details
echo -e "\n${BLUE}CloudFlare Tunnel Configuration${NC}"
echo -e "Do you have an existing CloudFlare Tunnel token? (y/n) [n]: "
read -r HAS_TOKEN
HAS_TOKEN=${HAS_TOKEN:-"n"}

if [[ $HAS_TOKEN =~ ^[Yy]$ ]]; then
    echo -e "Please enter your CloudFlare Tunnel token: "
    read -r TUNNEL_TOKEN
    
    # Create cloudflared config
    cat > "$CLOUDFLARED_CONFIG" << EOY
tunnel: ${TUNNEL_TOKEN}
credentials-file: ${HOME}/.cloudflared/${TUNNEL_TOKEN}.json
logfile: ${INSTALLDIR}/cloudflare/cloudflared.log

ingress:
  - hostname: 360blur.example.com
    service: http://localhost:5000
  - service: http_status:404
EOY

    echo -e "${BLUE}Enter your CloudFlare hostname (e.g., 360blur.example.com):${NC} "
    read -r HOSTNAME
    
    # Update hostname in config
    sed -i.bak "s/360blur.example.com/$HOSTNAME/g" "$CLOUDFLARED_CONFIG"
    rm -f "${CLOUDFLARED_CONFIG}.bak"
    
    # Update config.ini
    sed -i.bak "s/enabled = False/enabled = True/g" "$CONFIG_FILE"
    sed -i.bak "s/# token = your_cloudflare_token/token = $TUNNEL_TOKEN/g" "$CONFIG_FILE"
    sed -i.bak "s/# hostname = your-tunnel.domain.com/hostname = $HOSTNAME/g" "$CONFIG_FILE"
    rm -f "${CONFIG_FILE}.bak"
    
    echo -e "${GREEN}CloudFlare Tunnel configuration completed!${NC}"
    echo -e "Configuration files:"
    echo -e "  - CloudFlare config: ${CLOUDFLARED_CONFIG}"
    echo -e "  - 360blur config: ${CONFIG_FILE}"
    
    # Create systemd service for cloudflared
    if [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl &> /dev/null; then
        echo -e "\nDo you want to set up a systemd service for CloudFlare Tunnel? (y/n) [y]: "
        read -r SETUP_SERVICE
        SETUP_SERVICE=${SETUP_SERVICE:-"y"}
        
        if [[ $SETUP_SERVICE =~ ^[Yy]$ ]]; then
            CLOUDFLARE_SERVICE_FILE="${INSTALLDIR}/cloudflare/cloudflared.service"
            
            # Create service file
            cat > "$CLOUDFLARE_SERVICE_FILE" << EOT
[Unit]
Description=CloudFlare Tunnel for 360blur
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${INSTALLDIR}/cloudflare
ExecStart=/usr/bin/cloudflared tunnel --config ${CLOUDFLARED_CONFIG} run
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOT
            
            # Install service
            sudo cp "$CLOUDFLARE_SERVICE_FILE" /etc/systemd/system/cloudflared-360blur.service
            sudo systemctl daemon-reload
            sudo systemctl enable cloudflared-360blur.service
            
            echo -e "${GREEN}CloudFlare Tunnel systemd service has been set up${NC}"
            echo -e "You can now manage the service using the following commands:"
            echo -e "  ${YELLOW}sudo systemctl start cloudflared-360blur${NC} - Start the tunnel"
            echo -e "  ${YELLOW}sudo systemctl stop cloudflared-360blur${NC} - Stop the tunnel"
            echo -e "  ${YELLOW}sudo systemctl status cloudflared-360blur${NC} - Check tunnel status"
            
            echo -e "\nDo you want to start the CloudFlare Tunnel now? (y/n) [y]: "
            read -r START_TUNNEL
            START_TUNNEL=${START_TUNNEL:-"y"}
            
            if [[ $START_TUNNEL =~ ^[Yy]$ ]]; then
                sudo systemctl start cloudflared-360blur.service
                echo -e "${GREEN}CloudFlare Tunnel started!${NC}"
                echo -e "Your 360blur instance should now be accessible at https://${HOSTNAME}"
            fi
        fi
    else
        echo -e "\n${BLUE}To start the CloudFlare Tunnel, run:${NC}"
        echo -e "  ${YELLOW}cloudflared tunnel --config ${CLOUDFLARED_CONFIG} run${NC}"
    fi
else
    echo -e "${YELLOW}CloudFlare Tunnel setup requires a token${NC}"
    echo -e "To create a tunnel and get a token, visit https://dash.cloudflare.com/ and follow these steps:"
    echo -e "1. Go to Zero Trust > Access > Tunnels"
    echo -e "2. Click 'Create a tunnel'"
    echo -e "3. Follow the instructions to create a tunnel and get a token"
    echo -e "4. Run this script again with your token"
fi
EOL
        
        chmod +x "$INSTALL_DIR/cloudflare/setup_cloudflare.sh"
        
        echo -e "\n${GREEN}CloudFlare Tunnel setup script has been created${NC}"
        echo -e "To set up CloudFlare Tunnel, run:"
        echo -e "${CYAN}  cd $INSTALL_DIR/cloudflare && ./setup_cloudflare.sh $INSTALL_DIR${NC}"
    fi
fi

# Færdig!
echo -e "\n${GREEN}${BOLD}Installation complete!${NC}"
echo -e "To start 360blur, navigate to the installation directory and run:"

if [[ "$OSTYPE" == "win"* ]]; then
    echo -e "${CYAN}  cd $INSTALL_DIR${NC}"
    echo -e "${CYAN}  start_blur360.bat${NC}"
else
    echo -e "${CYAN}  cd $INSTALL_DIR${NC}"
    echo -e "${CYAN}  ./start_blur360.sh${NC}"
fi

echo -e "\nOr for convenience, use this one-line command:"
if [[ "$OSTYPE" == "win"* ]]; then
    echo -e "${CYAN}  cd $INSTALL_DIR && start_blur360.bat${NC}"
else
    echo -e "${CYAN}  cd $INSTALL_DIR && ./start_blur360.sh${NC}"
fi

# Vis korrekt URL baseret på host/port konfiguration
if [[ -f "$CONFIG_FILE" ]]; then
    # Try to extract configuration values safely
    HOST=$(grep "^host" "$CONFIG_FILE" | head -n 1 | cut -d'=' -f2 | tr -d ' ' 2>/dev/null)
    PORT=$(grep "^port" "$CONFIG_FILE" | head -n 1 | cut -d'=' -f2 | tr -d ' ' 2>/dev/null)
    
    # Set defaults if not found
    HOST=${HOST:-"127.0.0.1"}
    PORT=${PORT:-"5000"}
    
    # Check if CloudFlare is enabled (properly)
    CLOUDFLARE_ENABLED=$(grep "^enabled = True" "$CONFIG_FILE" 2>/dev/null)
    
    # Extract hostname only if not commented
    CLOUDFLARE_HOSTNAME=""
    if grep "^hostname = " "$CONFIG_FILE" | grep -v "^#" &>/dev/null; then
        CLOUDFLARE_HOSTNAME=$(grep "^hostname = " "$CONFIG_FILE" | grep -v "^#" | head -n 1 | cut -d'=' -f2 | tr -d ' ' 2>/dev/null)
    fi
    
    # Handle CloudFlare separately from regular access
    echo -e "\n${GREEN}${BOLD}== Access Information ==${NC}"
    
    # Always show local access information
    echo -e "${BOLD}Local access:${NC}"
    if [[ "$HOST" == "0.0.0.0" ]]; then
        # Try to get IP address safely
        IP=$(hostname -I 2>/dev/null | awk '{print $1}' 2>/dev/null)
        if [[ -n "$IP" ]]; then
            echo -e "${CYAN}  http://$IP:$PORT${NC} (from any device on your network)"
        fi
        echo -e "${CYAN}  http://localhost:$PORT${NC} (from this computer)"
    elif [[ "$HOST" == "127.0.0.1" ]]; then
        echo -e "${CYAN}  http://localhost:$PORT${NC} (from this computer only)"
    else
        echo -e "${CYAN}  http://$HOST:$PORT${NC}"
    fi
    
    # Show CloudFlare information if enabled and configured
    if [[ -n "$CLOUDFLARE_ENABLED" && -n "$CLOUDFLARE_HOSTNAME" ]]; then
        echo -e "\n${BOLD}CloudFlare tunnel:${NC}"
        echo -e "${YELLOW}To complete CloudFlare setup, run:${NC}"
        echo -e "${CYAN}  cd $INSTALL_DIR/cloudflare && ./setup_cloudflare.sh $INSTALL_DIR${NC}"
        echo -e "\n${YELLOW}After configuration, your instance will be accessible at:${NC}"
        echo -e "${CYAN}  https://$CLOUDFLARE_HOSTNAME${NC}"
    elif [[ -n "$CLOUDFLARE_ENABLED" ]]; then
        echo -e "\n${BOLD}CloudFlare tunnel:${NC}"
        echo -e "${YELLOW}To complete CloudFlare setup, run:${NC}"
        echo -e "${CYAN}  cd $INSTALL_DIR/cloudflare && ./setup_cloudflare.sh $INSTALL_DIR${NC}"
    fi
else
    echo -e "\nOpen http://localhost:5000 in your browser after starting."
fi

echo -e "\n${PURPLE}Thank you for installing 360blur!${NC}"
echo -e "${CYAN}For updates and documentation, visit https://github.com/rpaasch/360blur-mp${NC}"