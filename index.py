import os
import subprocess
import time
import json
import requests  # Biblioteca oficial de requisições HTTP
from dotenv import load_dotenv
import keyboard
import qrcode  

# Carrega as variáveis do arquivo .env local
load_dotenv()

# Configurações essenciais do ecossistema vinda do .env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TOKEN_DISPOSITIVO = os.getenv("TOKEN_DISPOSITIVO") # Chave mestra de ativação da quadra
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000") # Link oficial do app (Vercel ou local)

ARQUIVO_FILA = "queue.json"
TRAVA_TEMPO_SEGUNDOS = 15  
ultimo_clique_timestamp = 0

# Variável global que será preenchida dinamicamente via API no boot do sistema
QUADRA_ID = None

# 🚀 DEFINE O EXECUTÁVEL CORRETO DO FFMPEG BASEADO NO SISTEMA OPERACIONAL
FFMPEG_EXEC = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'

# 🚀 CRIA AS PASTAS AUTOMATICAMENTE SE ELAS NÃO EXISTIREM NO RASPBERRY
os.makedirs(os.getenv('PASTA_SEGMENTOS', './segmentos'), exist_ok=True)
os.makedirs(os.getenv('PASTA_REPLAYS', './replays'), exist_ok=True)

print("=== SISTEMA DE REPLAY VIA HTTP — TOQUE EXCLUSIVO DE ELITE ===")

def autenticar_e_ativar_totem():
    """Bate na tabela dispositivos do Supabase e descobre o ID da quadra dinamicamente usando o Token."""
    global QUADRA_ID
    print("🔑 Autenticando dispositivo nos servidores FOX REPLAY...")
    
    if not TOKEN_DISPOSITIVO:
        print("❌ CRÍTICO: TOKEN_DISPOSITIVO não configurado no arquivo .env!")
        return False

    # Endpoint rest do Supabase para filtrar pelo token secreto gerado na dashboard
    endpoint = f"{SUPABASE_URL}/rest/v1/dispositivos?token_autenticacao=eq.{TOKEN_DISPOSITIVO}&select=quadra_id"
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }

    try:
        resposta = requests.get(endpoint, headers=headers)
        if resposta.status_code == 200:
            dados = resposta.json()
            if dados and len(dados) > 0:
                QUADRA_ID = dados[0]['quadra_id']
                print(f"✅ CONEXÃO ESTABELECIDA COM SUCESSO!")
                print(f"📌 ID da Quadra Ativado em Memória: {QUADRA_ID}\n")
                return True
            else:
                print("❌ ERRO: Token do Totem inválido ou não encontrado no painel!")
                return False
        else:
            print(f"❌ ERRO DE CONEXÃO COM O BANCO: {resposta.status_code}")
            return False
    except Exception as e:
        print(f"❌ FALHA SÉRIA DE REDE AO AUTENTICAR: {e}")
        return False

def iniciar_buffer_circular():
    """Inicia o FFmpeg em segundo plano adaptando-se para Windows ou Raspberry Pi (Linux)."""
    if os.name == 'nt':  # Windows
        camera_input = f"video={os.getenv('CAMERA_NOME', 'Logi C270 HD WebCam')}"
        formato_input = 'dshow'
        cmd_input = ['-f', formato_input, '-i', camera_input]
    else:  # 🍓 Raspberry Pi / Linux
        # No Raspberry Pi, o dispositivo padrão da primeira câmera USB conectada é '/dev/video0'
        camera_input = os.getenv('CAMERA_NOME', '/dev/video0')
        formato_input = 'v4l2' # Driver oficial de vídeo do Linux
        cmd_input = ['-f', formato_input, '-i', camera_input]

    comando = [
        FFMPEG_EXEC, *cmd_input, # Utiliza a variável dinâmica sem o .exe no Linux
        '-s', os.getenv('RESOLUCAO'), '-r', os.getenv('FPS'),
        '-c:v', 'libx264', '-f', 'segment',
        '-segment_time', os.getenv('TEMPO_SEGMENTO'),
        '-segment_wrap', os.getenv('QUANTIDADE_SEGMENTOS'),
        '-reset_timestamps', '1', '-y',
        f"{os.getenv('PASTA_SEGMENTOS')}/video_%03d.mp4"
    ]
    return subprocess.Popen(comando, shell=True)

def adicionar_a_fila():
    """Adiciona um novo pedido de replay no arquivo queue.json."""
    global ultimo_clique_timestamp
    tempo_atual = time.time()

    if tempo_atual - ultimo_clique_timestamp < TRAVA_TEMPO_SEGUNDOS:
        tempo_restante = int(TRAVA_TEMPO_SEGUNDOS - (tempo_atual - ultimo_clique_timestamp))
        print(f"⚠️ [TRAVA] Botão bloqueado! Aguarde mais {tempo_restante}s.")
        return

    ultimo_clique_timestamp = tempo_atual
    timestamp_id = int(tempo_atual)
    print(f"\n🔘 [BOTÃO] Clique registrado! Adicionando lance {timestamp_id} à fila...")

    fila = []
    if os.path.exists(ARQUIVO_FILA):
        try:
            with open(ARQUIVO_FILA, "r") as f: fila = json.load(f)
        except json.JSONDecodeError: fila = []

    nova_tarefa = {
        "id": timestamp_id,
        "status_video": "pendente",
        "status_upload": "pendente",
        "caminho_arquivo": "",
        "criado_em": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(tempo_atual))
    }
    fila.append(nova_tarefa)

    with open(ARQUIVO_FILA, "w") as f: json.dump(fila, f, indent=4)

def processar_fila_de_replays():
    """Busca tarefas pendentes e costura os vídeos locally."""
    if not os.path.exists(ARQUIVO_FILA): return

    try:
        with open(ARQUIVO_FILA, "r") as f: fila = json.load(f)
    except (json.JSONDecodeError, PermissionError): return

    tarefas_pendentes = [t for t in fila if t["status_video"] == "pendente"]
    if not tarefas_pendentes: return

    tarefa = tarefas_pendentes[0]
    tarefa["status_video"] = "processando"
    with open(ARQUIVO_FILA, "w") as f: json.dump(fila, f, indent=4)

    pasta_seg = os.getenv('PASTA_SEGMENTOS')
    arquivo_final = f"{os.getenv('PASTA_REPLAYS')}/replay_{tarefa['id']}.mp4"
    lista_txt_path = f"lista_{tarefa['id']}.txt"

    try:
        arquivos = [f for f in os.listdir(pasta_seg) if f.endswith('.mp4')]
        if len(arquivos) >= 3:
            arquivos_ordenados = sorted(arquivos, key=lambda x: os.path.getmtime(os.path.join(pasta_seg, x)))
            ultimos_segmentos = arquivos_ordenados[-8:-1] if len(arquivos_ordenados) >= 8 else arquivos_ordenados[:-1]

            with open(lista_txt_path, "w") as f:
                for seg in ultimos_segmentos:
                    f.write(f"file '{os.path.join(pasta_seg, seg).replace('\\', '/')}'\n")

            # 🚀 AJUSTADO AQUI TAMBÉM O PROCESSO DE CONCATENAÇÃO DO LINUX
            comando_concat = [FFMPEG_EXEC, '-f', 'concat', '-safe', '0', '-i', lista_txt_path, '-c', 'copy', '-y', arquivo_final]
            subprocess.run(comando_concat, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if os.path.exists(lista_txt_path): os.remove(lista_txt_path)

            print(f"🎉 [VÍDEO] Replay {tarefa['id']} costurado com sucesso!")
            tarefa["status_video"] = "concluido"
            tarefa["caminho_arquivo"] = arquivo_final
        else:
            print("[AVISO] Poucos segmentos para gerar o vídeo. Cancelando tarefa.")
            tarefa["status_video"] = "erro_pouco_segmento"

    except Exception as e:
        print(f"[ERRO] Falha ao gerar vídeo {tarefa['id']}: {e}")
        return

    with open(ARQUIVO_FILA, "w") as f: json.dump(fila, f, indent=4)

def executar_upload_da_fila():
    """Pega os vídeos concluídos, faz o upload para o Storage e registra na tabela do banco."""
    global QUADRA_ID
    if not os.path.exists(ARQUIVO_FILA): return

    try:
        with open(ARQUIVO_FILA, "r") as f: fila = json.load(f)
    except (json.JSONDecodeError, PermissionError): return

    tarefas_para_upload = [t for t in fila if t["status_video"] == "concluido" and t["status_upload"] in ["pendente", "erro_rede"]]
    if not tarefas_para_upload: return

    tarefa = tarefas_para_upload[0]
    tarefa["status_upload"] = "enviando"
    with open(ARQUIVO_FILA, "w") as f: json.dump(fila, f, indent=4)

    print(f"☁️  [NUVEM] Iniciando upload via HTTP do replay_{tarefa['id']}.mp4...")

    try:
        nome_arquivo_nuvem = f"replay_{tarefa['id']}.mp4"
        
        # 1. FAZ O UPLOAD DO VÍDEO PARA O STORAGE
        endpoint_storage = f"{SUPABASE_URL}/storage/v1/object/replays/{nome_arquivo_nuvem}"
        headers_storage = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Content-Type": "video/mp4"
        }

        with open(tarefa["caminho_arquivo"], "rb") as f_video:
            resposta_storage = requests.post(endpoint_storage, headers=headers_storage, data=f_video)
        
        if resposta_storage.status_code == 200:
            print("💾 [STORAGE] Arquivo saved no bucket com sucesso!")
            
            # URL pública definitiva do vídeo mp4
            url_publica_video = f"{SUPABASE_URL}/storage/v1/object/public/replays/{nome_arquivo_nuvem}"
            
            # 2. INSERE O REGISTRO USANDO O ID RESOLVIDO DINAMICAMENTE
            print("📝 [BANCO DE DADOS] Registrando jogada na tabela...")
            endpoint_banco = f"{SUPABASE_URL}/rest/v1/replays"
            
            headers_banco = {
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "apikey": SUPABASE_KEY,
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
            
            payload_banco = {
                "quadra_id": QUADRA_ID, 
                "video_url": url_publica_video
            }
            
            resposta_banco = requests.post(endpoint_banco, headers=headers_banco, json=payload_banco)
            
            if resposta_banco.status_code == 201:
                dados_replay_criado = resposta_banco.json()
                id_do_replay = dados_replay_criado[0]['id']
                
                # Link montado dinamicamente com base na URL do seu front da Vercel ou Local
                link_front_jogador = f"{FRONTEND_URL}/jogada?id={id_do_replay}"
                
                print(f"🚀 [SUCESSO TOTAL] Replay disponível na nuvem!")
                print(f"👉 Link do Jogador: {link_front_jogador}\n")
                
                # GERAÇÃO DO QR CODE
                print("🖼️  [QR CODE] Gerando imagem direcionada ao app...")
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(link_front_jogador)
                qr.make(fit=True)
                
                img_qr = qr.make_image(fill_color="black", back_color="white")
                caminho_qr = "qr_replay_atual.png"
                img_qr.save(caminho_qr)
                
                if os.name == 'nt':
                    os.startfile(caminho_qr)
                else:
                    # Executa o visualizador de imagens padrão do Linux
                    subprocess.Popen(['xdg-open', caminho_qr])
                
                print("📺 [QR CODE] Exibido na tela com sucesso!\n")
                fila = [t for t in fila if t["id"] != tarefa["id"]]
            else:
                print(f"❌ [ERRO BANCO] Falha ao registrar na tabela: {resposta_banco.status_code}")
                tarefa["status_upload"] = "erro_rede"
        else:
            print(f"❌ [ERRO STORAGE] Falha no upload do arquivo: {resposta_storage.status_code}")
            tarefa["status_upload"] = "erro_rede"

    except Exception as e:
        print(f"📡 [REDE] Erro crítico no processo: {e}")
        tarefa["status_upload"] = "erro_rede"

    with open(ARQUIVO_FILA, "w") as f: json.dump(fila, f, indent=4)

# ==============================================================================
# FLUXO PRINCIPAL DE INICIALIZAÇÃO (BOOT)
# ==============================================================================
if autenticar_e_ativar_totem():
    print("Pressione [ESPAÇO] para salvar uma jogada. Pressione [ESC] para sair.\n")
    
    # Inicia a gravação contínua em pedaços secundários
    processo_ffmpeg = iniciar_buffer_circular()

    try:
        while True:
            if keyboard.is_pressed('space'):
                adicionar_a_fila()
                time.sleep(0.3)
                
            processar_fila_de_replays()  
            executar_upload_da_fila()    

            if keyboard.is_pressed('esc'):
                print("\nEncerrando o sistema de forma limpa...")
                break
                
            time.sleep(0.1)

    finally:
        if 'processo_ffmpeg' in locals():
            if os.name == 'nt':
                subprocess.run(f"taskkill /F /T /PID {processo_ffmpeg.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                processo_ffmpeg.terminate()
                
        if os.path.exists(ARQUIVO_FILA): os.remove(ARQUIVO_FILA)
        print("Sistema finalizado.")
else:
    print("❌ BOOT ABORTADO: Não foi possível sincronizar o Totem com os servidores.")