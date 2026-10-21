#!/usr/bin/env bash
# Instala o CineLocal para o usuário atual (Linux Mint / Ubuntu / Debian).
# Cria um ambiente virtual, um comando `cinelocal` e uma entrada no menu de aplicativos.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.local/opt/cinelocal"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"

echo "==> Verificando dependências do sistema"
PKGS=(python3 python3-venv python3-pip xdg-utils libegl1 libgl1 libxkbcommon-x11-0
      libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0
      libxcb-shape0 libxcb-xinerama0 vlc)
missing=()
for pkg in "${PKGS[@]}"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if ((${#missing[@]})); then
    echo "    Instalando: ${missing[*]} (pode pedir sua senha)"
    # Repositórios de terceiros com chave inválida (ex.: Spotify) fazem o update falhar;
    # isso não impede a instalação dos pacotes a partir das listas já existentes.
    sudo apt-get update -qq || echo "    aviso: apt-get update reportou erros (provavelmente um repositório de terceiros); continuando"
    for pkg in "${missing[@]}"; do
        sudo apt-get install -y "$pkg" || echo "    aviso: não foi possível instalar $pkg"
    done
fi

echo "==> Copiando arquivos para $PREFIX"
mkdir -p "$PREFIX" "$BIN" "$APPS" "$ICONS"
rm -rf "$PREFIX/cinelocal" "$PREFIX/assets"
cp -r "$SRC/cinelocal" "$SRC/assets" "$SRC/main.py" "$SRC/requirements.txt" "$PREFIX/"
find "$PREFIX" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "==> Criando ambiente virtual e instalando PySide6 (precisa de internet, ~200 MB)"
[ -x "$PREFIX/venv/bin/python" ] || python3 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --upgrade pip >/dev/null
"$PREFIX/venv/bin/pip" install -r "$PREFIX/requirements.txt"

echo "==> Criando atalhos"
cat > "$BIN/cinelocal" <<LAUNCHER
#!/usr/bin/env bash
exec "$PREFIX/venv/bin/python" "$PREFIX/main.py" "\$@"
LAUNCHER
chmod +x "$BIN/cinelocal"

cp "$SRC/assets/cinelocal.svg" "$ICONS/cinelocal.svg"
cat > "$APPS/cinelocal.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=CineLocal
Comment=Navegue pelos filmes da sua pasta local
Exec=$BIN/cinelocal
Icon=cinelocal
Terminal=false
Categories=AudioVideo;Video;Player;
StartupWMClass=CineLocal
DESKTOP

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" || true

echo
echo "Pronto! Abra o CineLocal pelo menu de aplicativos (categoria Som e Vídeo)"
echo "ou digite: cinelocal   (se o comando não for encontrado, faça logout/login)."
