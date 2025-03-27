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

# Show clear CloudFlare setup instructions 
echo -e "\n${BLUE}${BOLD}CloudFlare Tunnel Configuration${NC}"
echo -e "${YELLOW}=====================================================================${NC}"
echo -e "CloudFlare Tunnels provide secure remote access to your 360blur instance"
echo -e "without exposing your IP address or opening ports on your firewall."
echo -e "\n${YELLOW}Before proceeding, you'll need:${NC}"
echo -e "1. A CloudFlare account (free at cloudflare.com)"
echo -e "2. A domain registered with CloudFlare (or subdomain)"
echo -e "3. A CloudFlare Tunnel token from your CloudFlare dashboard"
echo -e "\n${BLUE}Do you have a CloudFlare account and domain already set up? (y/n) [n]:${NC} "
read -r HAS_ACCOUNT
HAS_ACCOUNT=${HAS_ACCOUNT:-"n"}

if [[ ! $HAS_ACCOUNT =~ ^[Yy]$ ]]; then
    echo -e "\n${YELLOW}Please create a CloudFlare account and add your domain first:${NC}"
    echo -e "1. Sign up at https://dash.cloudflare.com/sign-up"
    echo -e "2. Add your domain to CloudFlare (or use an existing one)"
    echo -e "3. Return to this setup script when finished"
    echo -e "\n${BLUE}Press Enter to continue when ready, or Ctrl+C to exit...${NC}"
    read
fi

echo -e "\n${BLUE}Do you have an existing CloudFlare Tunnel token? (y/n) [n]:${NC} "
read -r HAS_TOKEN
HAS_TOKEN=${HAS_TOKEN:-"n"}

if [[ $HAS_TOKEN =~ ^[Yy]$ ]]; then
    echo -e "\n${YELLOW}Please enter your CloudFlare Tunnel token:${NC} "
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

    echo -e "\n${YELLOW}Enter your CloudFlare hostname (e.g., 360blur.example.com):${NC} "
    read -r HOSTNAME
    
    # Extract port from config.ini if available
    PORT="5000"  # Default port
    if [[ -f "$CONFIG_FILE" ]]; then
        CONFIG_PORT=$(grep "port" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d ' ')
        if [[ -n "$CONFIG_PORT" ]]; then
            PORT="$CONFIG_PORT"
        fi
    fi
    
    # Update hostname in config and set service to use the correct port
    sed -i.bak "s/360blur.example.com/$HOSTNAME/g" "$CLOUDFLARED_CONFIG"
    sed -i.bak "s|service: http://localhost:5000|service: http://localhost:$PORT|g" "$CLOUDFLARED_CONFIG"
    rm -f "${CLOUDFLARED_CONFIG}.bak"
    
    # Update config.ini
    sed -i.bak "s/enabled = False/enabled = True/g" "$CONFIG_FILE"
    sed -i.bak "s/# token = your_cloudflare_token/token = $TUNNEL_TOKEN/g" "$CONFIG_FILE"
    sed -i.bak "s/# hostname = your-tunnel.domain.com/hostname = $HOSTNAME/g" "$CONFIG_FILE"
    rm -f "${CONFIG_FILE}.bak"
    
    echo -e "\n${GREEN}${BOLD}CloudFlare Tunnel configuration completed!${NC}"
    echo -e "${YELLOW}Configuration files:${NC}"
    echo -e "  - CloudFlare config: ${CLOUDFLARED_CONFIG}"
    echo -e "  - 360blur config: ${CONFIG_FILE}"
    echo -e "\n${YELLOW}Important:${NC} Your 360blur instance will be accessible at:"
    echo -e "${CYAN}  https://$HOSTNAME${NC}"
    echo -e "You may need to wait a few minutes for DNS propagation."
    
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
    echo -e "\n${YELLOW}${BOLD}CloudFlare Tunnel Setup Instructions${NC}"
    echo -e "${YELLOW}=====================================================================${NC}"
    echo -e "To create a tunnel and get a token, follow these detailed steps:"
    echo -e "\n${CYAN}1. Log in to your CloudFlare dashboard:${NC}"
    echo -e "   https://dash.cloudflare.com/"
    echo -e "\n${CYAN}2. Navigate to CloudFlare Zero Trust:${NC}"
    echo -e "   - Click on 'Zero Trust' in the sidebar or go to:"
    echo -e "   - https://one.dash.cloudflare.com/"
    echo -e "\n${CYAN}3. Create a new tunnel:${NC}"
    echo -e "   - Go to Access > Tunnels"
    echo -e "   - Click 'Create a tunnel'"
    echo -e "   - Give your tunnel a name (e.g., '360blur')"
    echo -e "\n${CYAN}4. Get your tunnel token:${NC}"
    echo -e "   - On the installation page, select 'Linux'"
    echo -e "   - Choose 'Install and run manually'"
    echo -e "   - Look for your tunnel token in the command"
    echo -e "   - It will look like: 'cloudflared service install YOUR_TOKEN_HERE'"
    echo -e "\n${CYAN}5. Configure your tunnel:${NC}"
    echo -e "   - Skip the CloudFlare installation steps (we handle this)"
    echo -e "   - In 'Public Hostname' section, set up your domain"
    echo -e "   - Enter a subdomain (e.g., '360blur')"
    echo -e "   - Choose your domain from the dropdown"
    echo -e "   - Set Type to 'HTTP'"
    echo -e "   - Set URL to 'localhost:5000' (or your custom port)"
    echo -e "   - Click Save"
    echo -e "\n${YELLOW}After completing these steps, run this script again and enter your token${NC}"
    
    # Ask if they want to open browser to CloudFlare
    echo -e "\n${BLUE}Would you like to open the CloudFlare dashboard in your browser now? (y/n) [y]:${NC} "
    read -r OPEN_BROWSER
    OPEN_BROWSER=${OPEN_BROWSER:-"y"}
    
    if [[ $OPEN_BROWSER =~ ^[Yy]$ ]]; then
        if command -v xdg-open &> /dev/null; then
            xdg-open "https://dash.cloudflare.com/" &
        elif command -v open &> /dev/null; then
            open "https://dash.cloudflare.com/"
        else
            echo -e "${YELLOW}Could not open browser automatically.${NC}"
            echo -e "Please visit: ${CYAN}https://dash.cloudflare.com/${NC}"
        fi
    fi
fi