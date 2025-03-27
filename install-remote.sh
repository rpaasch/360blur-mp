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
echo "  ____    __    _____  ____  _     _     ____    "
echo " |___ \  / /_  | ____|/ ___|| |   | |   |  _ \   "
echo "   __) || '_ \ |  _|  \___ \| |   | |   | |_) |  "
echo "  / __/ | (_) || |___  ___) | |___| |___|  _ <   "
echo " |_____| \___/ |_____||____/|_____|_____|_| \_\  "
echo -e "${NC}"
echo -e "${CYAN}Remote Installer for 360blur Video Processing Tool${NC}"
echo -e "${CYAN}         https://github.com/rpaasch/360blur-mp${NC}"
echo ""

# Opret en midlertidig mappe
TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"

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

# Ryd op efter os selv
cd - > /dev/null
rm -rf "$TMP_DIR"