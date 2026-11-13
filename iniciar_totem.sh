#!/bin/bash
# ==============================================================================
# FOX REPLAY — SCRIPT DE INICIALIZAÇÃO E AUTO-UPDATE (OTA VIA GITHUB)
# Executado automaticamente pelo serviço systemd no boot do Raspberry Pi
# ==============================================================================

DIR_APP="/home/pi/Raspberry-Beach-tenis"

# Garante que está no diretório correto
if [ -d "$DIR_APP" ]; then
    cd "$DIR_APP" || exit 1
fi

echo "================================================================="
echo "🦊 FOX REPLAY — INICIANDO TOTEM NA QUADRA"
echo "================================================================="

# 1. Verifica se há conexão com a internet (timeout de 3s)
if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1 || ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1; then
    echo "🌐 Conexão com a internet confirmada via cabo/rede."
    echo "🔍 Verificando atualizações no repositório oficial do GitHub..."

    # Garante que o git confie no diretório do usuário pi
    git config --global --add safe.directory "$DIR_APP" >/dev/null 2>&1

    # Busca novidades no branch main sem travar
    if git fetch origin main --quiet 2>/dev/null; then
        LOCAL_HASH=$(git rev-parse HEAD 2>/dev/null)
        REMOTE_HASH=$(git rev-parse origin/main 2>/dev/null)

        if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
            echo "🚀 [NOVA VERSÃO DETECTADA] Baixando atualização do GitHub..."

            # Verifica se requirements.txt mudou antes de atualizar
            REQ_DIFF=$(git diff HEAD origin/main -- requirements.txt 2>/dev/null)

            # Aplica a versão mais recente com segurança (preserva o .env pois está no .gitignore)
            git reset --hard origin/main --quiet

            # Se houve novas bibliotecas, instala automaticamente
            if [ -n "$REQ_DIFF" ]; then
                echo "📦 Instalando novas dependências Python..."
                pip3 install -r requirements.txt --break-system-packages --quiet 2>/dev/null
            fi

            echo "✅ Totem atualizado para a versão mais recente com sucesso!"
        else
            echo "✅ Totem já está rodando a versão mais recente do GitHub."
        fi
    else
        echo "⚠️ Não foi possível verificar novidades no GitHub agora. Continuando..."
    fi
else
    echo "⚠️ Sem internet no momento. Iniciando gravação com a versão local..."
fi

echo "🎾 Disparando Fox Replay Core..."
exec /usr/bin/python3 index.py
