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
    cat > "$CLOUDFLARED_CONFIG" << EOL
tunnel: ${TUNNEL_TOKEN}
credentials-file: ${HOME}/.cloudflared/${TUNNEL_TOKEN}.json
logfile: ${INSTALLDIR}/cloudflare/cloudflared.log

ingress:
  - hostname: 360blur.example.com
    service: http://localhost:5000
  - service: http_status:404
EOL

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
            cat > "$CLOUDFLARE_SERVICE_FILE" << EOL
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
EOL
            
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