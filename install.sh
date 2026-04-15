#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# GreenClaw One-Command Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/greench-ai/greenchclaw-cpu/HEAD/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -e

INSTALL_DIR="${HOME}/greenchclaw-cpu"
SPOOL_FILE="/tmp/greenchclaw_onboard_flag"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'
CYN='\033[0;36m'; DIM='\033[2m'; BOLD='\033[1m'; RESET='\033[0m'

banner() {
  echo -e "${GRN}"
  echo "  ╔══════════════════════════════════════════╗"
  echo "  ║       🦎  GreenClaw Installer  🦎        ║"
  echo "  ╚══════════════════════════════════════════╝"
  echo -e "${RESET}"
}

step() { echo -e "${CYN}[${BOLD}STEP${RESET}${CYN}]${RESET} $1"; }
info()  { echo -e "${DIM}[·] $1${RESET}"; }
ok()    { echo -e "${GRN}[✓] $1${RESET}"; }
warn()  { echo -e "${YEL}[!] $1${RESET}"; }
fail()  { echo -e "${RED}[✗] $1${RESET}"; }

# ── Detect OS ─────────────────────────────────────────────────────────────────
detect_os() {
  if [[ "$(uname)" == "Darwin" ]]; then echo "macos"
  elif command -v apt-get &> /dev/null; then echo "debian"
  elif command -v dnf &> /dev/null; then echo "fedora"
  elif command -v pacman &> /dev/null; then echo "arch"
  elif command -v brew &> /dev/null; then echo "brew"
  else echo "unknown"
  fi
}

# ── Check Python 3 ────────────────────────────────────────────────────────────
check_python() {
  step "Checking Python 3..."
  if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
    ok "Python $PY_VER found"
  else
    warn "Python3 not found. Installing..."
    OS=$(detect_os)
    case "$OS" in
      debian) sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv ;;
      fedora) sudo dnf install -y python3 python3-pip ;;
      arch)   sudo pacman -S --noconfirm python python-pip ;;
      macos)  command -v brew &> /dev/null && brew install python3 || true ;;
      *)      fail "Could not install Python automatically. Please install Python 3.10+ and try again."; exit 1 ;;
    esac
    PYTHON_CMD="python3"
  fi
}

# ── Check pip ─────────────────────────────────────────────────────────────────
check_pip() {
  step "Checking pip..."
  if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    OS=$(detect_os)
    warn "pip not found. Installing..."
    case "$OS" in
      debian) sudo apt-get install -y python3-pip ;;
      fedora) sudo dnf install -y python3-pip ;;
      arch)   sudo pacman -S --noconfirm python-pip ;;
      macos)  true ;;
    esac
  fi
  ok "pip ready"
}

# ── Install GreenClaw ────────────────────────────────────────────────────────
install_greenchlaw() {
  step "Installing GreenClaw..."
  info "Installing in editable mode: $INSTALL_DIR"

  # Clone or update repo
  if [ -d "$INSTALL_DIR/.git" ]; then
    info "GreenClaw already cloned — pulling latest..."
    git -C "$INSTALL_DIR" pull origin main 2>/dev/null || true
  else
    info "Cloning GreenClaw CPU..."
    git clone https://github.com/greench-ai/greenchclaw-cpu.git "$INSTALL_DIR"
  fi

  # Install in editable mode (includes web dependencies)
  $PYTHON_CMD -m pip install --upgrade pip --break-system-packages
  $PYTHON_CMD -m pip install -e "$INSTALL_DIR[all]" --quiet --break-system-packages
  ok "GreenClaw installed (with web UI)!"
}

# ── Check Ollama ─────────────────────────────────────────────────────────────
check_ollama() {
  step "Checking Ollama..."
  if command -v ollama &> /dev/null; then
    ok "Ollama is already installed"
    if ! curl -s http://localhost:11434/api/tags &> /dev/null; then
      warn "Ollama is installed but not running. Start it with: ollama serve"
    fi
  else
    echo ""
    warn "Ollama is not installed. GreenClaw works best with Ollama (runs AI locally, no API key needed)."
    echo ""
    echo -ne "${BOLD}Install Ollama now?${RESET} [Y/n]: "
    read -r response
    response=${response:-y}
    if [[ "$response" =~ ^[Yy]$ ]]; then
      echo -e "${DIM}Running Ollama installer...${RESET}"
      curl -fsSL https://ollama.ai/install.sh | sh
      ok "Ollama installed!"
    else
      info "Skipping Ollama. You can install it later at https://ollama.ai"
    fi
  fi
}

# ── Launch Onboarding ────────────────────────────────────────────────────────
launch_onboard() {
  step "Starting GreenClaw setup wizard..."
  echo ""
  # Touch flag so onboard knows this was a fresh install
  touch "$SPOOL_FILE"
  echo "$INSTALL_DIR" > "$SPOOL_FILE"
  echo ""
  greenchclaw --onboard
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
banner
echo ""
info "Welcome to GreenClaw — The Ultimate Body for a SOUL"
echo ""

check_python
check_pip
install_greenchlaw
check_ollama

echo ""
echo -e "${BOLD}${GRN}─────────────────────────────────────────${RESET}"
echo -e "${BOLD}${GRN}  All done! Launching setup wizard...${RESET}"
echo -e "${BOLD}${GRN}─────────────────────────────────────────${RESET}"
echo ""

launch_onboard
