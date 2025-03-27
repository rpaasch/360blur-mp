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