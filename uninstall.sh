#!/bin/bash
#
# 360blur Uninstaller Script
# Dette script fjerner 360blur og relaterede filer
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
echo -e "${RED}${BOLD}"
echo "   ____    __    ___    ____   _       _     _   ____    "
echo "  |___ /  / /_  / _ \\  | __ ) | |     | |   | | |  _ \\   "
echo "    |_ \\ | '_ \\| | | | |  _ \\ | |     | |   | | | |_) |  "
echo "   ___) || (_) | |_| | | |_) || |___  | |___| | |  _ <   "
echo "  |____/  \\___/ \\___/  |____/ |_____| |_____|_| |_| \\_\\  "
echo -e "${NC}"
echo -e "${RED}         Uninstaller for 360blur${NC}"
echo -e "${CYAN}        https://github.com/rpaasch/360blur-mp${NC}"
echo ""

# Bestem installationssti
current_dir=$(pwd)
read -p "Enter the path where 360blur is installed [$current_dir]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-"$current_dir"}

# Konverter relativ sti til absolut
INSTALL_DIR=$(eval echo "$INSTALL_DIR")

if [ ! -f "$INSTALL_DIR/blur360_webapp.py" ]; then
    echo -e "${YELLOW}Warning: 360blur webapp not found at $INSTALL_DIR/blur360_webapp.py${NC}"
    read -p "Continue with uninstallation? (y/n) [n]: " CONTINUE
    CONTINUE=${CONTINUE:-"n"}
    if [[ ! $CONTINUE =~ ^[Yy]$ ]]; then
        echo -e "${RED}Uninstallation cancelled${NC}"
        exit 1
    fi
fi

echo -e "${YELLOW}${BOLD}WARNING: This will uninstall 360blur and remove all related files${NC}"
read -p "Are you sure you want to continue? (y/n) [n]: " CONFIRM
CONFIRM=${CONFIRM:-"n"}

if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Uninstallation cancelled${NC}"
    exit 0
fi

echo -e "\n${BLUE}${BOLD}Uninstalling 360blur...${NC}"

# Fjern systemd services hvis de er installeret
if [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl &> /dev/null; then
    echo -e "${BLUE}Checking for systemd services...${NC}"
    
    # Fjern 360blur service
    if sudo systemctl is-active --quiet 360blur.service; then
        echo -e "Stopping 360blur service..."
        sudo systemctl stop 360blur.service
    fi
    
    if sudo systemctl is-enabled --quiet 360blur.service 2>/dev/null; then
        echo -e "Disabling 360blur service..."
        sudo systemctl disable 360blur.service
    fi
    
    if [ -f "/etc/systemd/system/360blur.service" ]; then
        echo -e "Removing 360blur systemd service..."
        sudo rm -f /etc/systemd/system/360blur.service
    fi
    
    # Fjern CloudFlare service
    if sudo systemctl is-active --quiet cloudflared-360blur.service; then
        echo -e "Stopping CloudFlare tunnel service..."
        sudo systemctl stop cloudflared-360blur.service
    fi
    
    if sudo systemctl is-enabled --quiet cloudflared-360blur.service 2>/dev/null; then
        echo -e "Disabling CloudFlare tunnel service..."
        sudo systemctl disable cloudflared-360blur.service
    fi
    
    if [ -f "/etc/systemd/system/cloudflared-360blur.service" ]; then
        echo -e "Removing CloudFlare tunnel systemd service..."
        sudo rm -f /etc/systemd/system/cloudflared-360blur.service
    fi
    
    # Reload systemd
    echo -e "Reloading systemd configuration..."
    sudo systemctl daemon-reload
    
    echo -e "${GREEN}✓ Systemd services removed${NC}"
fi

# Spørg om alle filer skal fjernes
echo -e "\n${BLUE}Do you want to remove all 360blur files? (y/n) [y]:${NC} "
read -p "" REMOVE_FILES
REMOVE_FILES=${REMOVE_FILES:-"y"}

if [[ $REMOVE_FILES =~ ^[Yy]$ ]]; then
    # Check om brugeren har skriverettigheder i mappen
    if [ ! -w "$INSTALL_DIR" ]; then
        echo -e "${RED}Error: You don't have write permissions for $INSTALL_DIR${NC}"
        echo -e "Please run this script with appropriate permissions"
        exit 1
    fi
    
    echo -e "${BLUE}Removing 360blur files...${NC}"
    
    # Lav en backup af brugerdata før sletning hvis ønsket
    echo -e "Do you want to keep a backup of your processed videos? (y/n) [y]: "
    read -p "" KEEP_BACKUP
    KEEP_BACKUP=${KEEP_BACKUP:-"y"}
    
    if [[ $KEEP_BACKUP =~ ^[Yy]$ ]]; then
        BACKUP_DIR="$HOME/360blur_backup_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$BACKUP_DIR"
        
        # Kopier processerede videoer til backup
        if [ -d "$INSTALL_DIR/processed" ]; then
            echo -e "Backing up processed videos to $BACKUP_DIR/processed/"
            cp -r "$INSTALL_DIR/processed" "$BACKUP_DIR/"
        fi
        
        echo -e "${GREEN}✓ Backup created at $BACKUP_DIR${NC}"
    fi
    
    # Liste over filer og mapper der skal slettes
    echo -e "Removing 360blur files and directories..."
    
    # Slet virtuel miljø hvis det findes
    if [ -d "$INSTALL_DIR/venv" ]; then
        rm -rf "$INSTALL_DIR/venv"
        echo -e "- Removed virtual environment"
    fi
    
    # Slet midlertidige filer
    if [ -d "$INSTALL_DIR/uploads" ]; then
        rm -rf "$INSTALL_DIR/uploads"
        echo -e "- Removed uploaded files"
    fi
    
    if [ -d "$INSTALL_DIR/processed" ]; then
        rm -rf "$INSTALL_DIR/processed"
        echo -e "- Removed processed files"
    fi
    
    if [ -d "$INSTALL_DIR/status" ]; then
        rm -rf "$INSTALL_DIR/status"
        echo -e "- Removed status files"
    fi
    
    # Slet modeller
    if [ -d "$INSTALL_DIR/models" ]; then
        rm -rf "$INSTALL_DIR/models"
        echo -e "- Removed model files"
    fi
    
    # Slet konfigurationsfiler
    if [ -f "$INSTALL_DIR/config.ini" ]; then
        rm -f "$INSTALL_DIR/config.ini"
        echo -e "- Removed configuration file"
    fi
    
    # Slet CloudFlare konfiguration
    if [ -d "$INSTALL_DIR/cloudflare" ]; then
        rm -rf "$INSTALL_DIR/cloudflare"
        echo -e "- Removed CloudFlare configuration"
    fi
    
    # Slet systemd konfiguration
    if [ -d "$INSTALL_DIR/systemd" ]; then
        rm -rf "$INSTALL_DIR/systemd"
        echo -e "- Removed systemd configuration"
    fi
    
    # Slet translations
    if [ -d "$INSTALL_DIR/translations" ]; then
        rm -rf "$INSTALL_DIR/translations"
        echo -e "- Removed translations"
    fi
    
    # Spørg om alle Python-filer skal fjernes
    echo -e "\nDo you want to remove all Python source files? (y/n) [y]: "
    read -p "" REMOVE_SOURCE
    REMOVE_SOURCE=${REMOVE_SOURCE:-"y"}
    
    if [[ $REMOVE_SOURCE =~ ^[Yy]$ ]]; then
        # Slet Python-filer
        find "$INSTALL_DIR" -maxdepth 1 -name "*.py" -delete
        echo -e "- Removed Python source files"
        
        # Slet øvrige filer
        rm -f "$INSTALL_DIR/babel.cfg"
        rm -f "$INSTALL_DIR/messages.pot"
        rm -f "$INSTALL_DIR/README.md"
        rm -f "$INSTALL_DIR/CLAUDE.md"
        rm -f "$INSTALL_DIR/install.sh"
        rm -f "$INSTALL_DIR/install-remote.sh"
        rm -f "$INSTALL_DIR/uninstall.sh"
        rm -f "$INSTALL_DIR/start_blur360.sh"
        rm -f "$INSTALL_DIR/start_blur360.bat"
        echo -e "- Removed other source files"
    fi
    
    echo -e "${GREEN}✓ 360blur files removed${NC}"
    
    # Spørg om hele mappen skal fjernes hvis tom
    if [ "$(ls -A "$INSTALL_DIR")" ]; then
        echo -e "${YELLOW}The installation directory is not empty.${NC}"
        echo -e "You may want to check for remaining files at $INSTALL_DIR"
    else
        echo -e "\nThe installation directory is now empty."
        echo -e "Do you want to remove the directory as well? (y/n) [n]: "
        read -p "" REMOVE_DIR
        REMOVE_DIR=${REMOVE_DIR:-"n"}
        
        if [[ $REMOVE_DIR =~ ^[Yy]$ ]]; then
            # Sikrer at vi ikke er i mappen før vi sletter den
            cd "$HOME"
            if rm -rf "$INSTALL_DIR"; then
                echo -e "${GREEN}✓ Installation directory removed${NC}"
            else
                echo -e "${RED}Failed to remove directory${NC}"
            fi
        fi
    fi
fi

echo -e "\n${GREEN}${BOLD}360blur uninstallation completed!${NC}"

if [[ $KEEP_BACKUP =~ ^[Yy]$ ]] && [[ -d "$BACKUP_DIR" ]]; then
    echo -e "Your processed videos have been backed up to: $BACKUP_DIR"
fi

echo -e "${CYAN}Thank you for using 360blur!${NC}"