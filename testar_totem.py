#!/usr/bin/env python3
import os
import sys
import time
import subprocess
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("🎾 FOX REPLAY — ASSISTENTE DE TESTE DO TOTEM NA QUADRA")
print("=" * 60)

# 1. TESTE DA CÂMERA IP
camera_url = os.getenv("CAMERA_NOME", "")
print(f"\n[1/3] Testando conexão com a câmera...")
print(f"URL: {camera_url}")

if camera_url:
    try:
        # Tenta ler 1 frame da câmera para validar
        cmd = ['ffmpeg', '-rtsp_transport', 'tcp', '-i', camera_url, '-vframes', '1', '-y', 'teste_camera.jpg']
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        if res.returncode == 0 and os.path.exists('teste_camera.jpg'):
            print("✅ CÂMERA CONECTADA COM SUCESSO! (Frame capturado em teste_camera.jpg)")
        else:
            print("❌ Falha ao conectar na câmera. Verifique o IP, usuário/senha e cabo de rede.")
    except Exception as e:
        print(f"⚠️ Erro ao testar câmera: {e}")
else:
    print("❌ CAMERA_NOME não configurada no .env")

# 2. TESTE DO BANCO DE DADOS E TOKEN
print(f"\n[2/3] Testando comunicação com os servidores Fox Replay...")
token = os.getenv("TOKEN_DISPOSITIVO")
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if token and supabase_url and supabase_key:
    import requests
    headers = {"Authorization": f"Bearer {supabase_key}", "apikey": supabase_key, "Content-Type": "application/json"}
    try:
        r = requests.post(f"{supabase_url}/rest/v1/rpc/validar_totem", headers=headers, json={"p_token": token}, timeout=6)
        if r.status_code == 200 and r.json().get('valido'):
            print(f"✅ SERVIDOR CONECTADO! Quadra ID: {r.json().get('quadra_id')}")
        else:
            # Fallback
            r2 = requests.get(f"{supabase_url}/rest/v1/dispositivos?token_autenticacao=eq.{token}&select=quadra_id", headers=headers, timeout=6)
            if r2.status_code == 200 and len(r2.json()) > 0:
                print(f"✅ SERVIDOR CONECTADO! Quadra ID: {r2.json()[0]['quadra_id']}")
            else:
                print("❌ Token do totem não reconhecido pelo painel.")
    except Exception as e:
        print(f"⚠️ Erro de rede ao conectar no servidor: {e}")

# 3. TESTE DO BOTÃO FÍSICO NA GRADE
pino_gpio = int(os.getenv("PINO_BOTAO_GPIO", "17"))
print(f"\n[3/3] Testando o botão físico na grade (Pino GPIO {pino_gpio} - Pino Físico 11)...")
print("👉 VÁ ATÉ A GRADE E APERTE O BOTÃO AGORA (aguardando por 20 segundos)...")

botao_clicado = False
try:
    from gpiozero import Button
    btn = Button(pino_gpio, bounce_time=0.2)
    def on_click():
        global botao_clicado
        botao_clicado = True
        print("\n🎉 BOTÃO ACIONADO COM SUCESSO! A fiação e o botão estão 100% funcionando! 🎾⚡\n")
    btn.when_pressed = on_click
    
    fim = time.time() + 20
    while time.time() < fim and not botao_clicado:
        time.sleep(0.1)
        
    if not botao_clicado:
        print("⏱️ Tempo esgotado sem detectar clique. Verifique se os fios estão nos pinos corretos (Pino 11 e Pino 9/GND).")
except Exception as e:
    print(f"Aviso GPIO: {e}")

print("=" * 60)
print("Fim do teste de diagnóstico.")
