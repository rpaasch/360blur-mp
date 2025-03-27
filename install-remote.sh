#!/bin/bash
#
# 360blur Remote Installer
# Denne fil downloades og køres via curl/wget
#

# Farve definitioner
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
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
echo -e "${CYAN}Remote Installer for 360blur Video Processing Tool${NC}"
echo -e "${CYAN}         https://github.com/rpaasch/360blur-mp${NC}"
echo ""

# Sikre at vi er i en læsbar mappe (brugeren's hjemmemappe)
cd "$HOME" || cd /tmp

# Download installer script
echo -e "${BLUE}${BOLD}Downloading installer script...${NC}"
if command -v curl >/dev/null 2>&1; then
    curl -L -o install.sh https://raw.githubusercontent.com/rpaasch/360blur-mp/main/install.sh
    DOWNLOAD_SUCCESS=$?
elif command -v wget >/dev/null 2>&1; then
    wget -O install.sh https://raw.githubusercontent.com/rpaasch/360blur-mp/main/install.sh
    DOWNLOAD_SUCCESS=$?
else
    echo -e "${RED}✗ Neither curl nor wget found. Cannot download installer.${NC}"
    exit 1
fi

if [ $DOWNLOAD_SUCCESS -ne 0 ]; then
    echo -e "${RED}✗ Failed to download installer script${NC}"
    exit 1
fi

# Gør installer scriptet eksekverbart
chmod +x install.sh

# Kør det faktiske installationsscript
echo -e "${GREEN}✓ Installer downloaded. Starting installation...${NC}"
echo ""
./install.sh

# Installation er færdig - ingen behov for yderligere oprydning
echo -e "${GREEN}Remote installation completed${NC}"