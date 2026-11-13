import os
import sys
import subprocess
import time
import json
import threading
import queue
import glob
import requests
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# ==============================================================================
# CONFIGURAÇÕES ESSENCIAIS
# ==============================================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TOKEN_DISPOSITIVO = os.getenv("TOKEN_DISPOSITIVO")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://fox-replay.vercel.app").rstrip("/")

ARQUIVO_FILA = "queue.json"
SEGUNDOS_REPLAY = int(os.getenv("SEGUNDOS_REPLAY", "30"))
TEMPO_SEGMENTO = int(os.getenv("TEMPO_SEGMENTO", "5"))
TRAVA_TEMPO_SEGUNDOS = int(os.getenv("TRAVA_TEMPO_SEGUNDOS", "20"))
RETENCAO_LOCAL_HORAS = int(os.getenv("RETENCAO_LOCAL_HORAS", "24"))
PINO_BOTAO_GPIO = int(os.getenv("PINO_BOTAO_GPIO", "17"))
PINO_FEEDBACK_GPIO = int(os.getenv("PINO_FEEDBACK_GPIO", "27")) # Pino Físico 13 (Buzzer/LED)

# Otimização de diretórios por SO
pasta_seg_env = os.getenv("PASTA_SEGMENTOS", "./segmentos")
if os.name == 'nt' and pasta_seg_env.startswith('/tmp'):
    PASTA_SEGMENTOS = "./segmentos"
else:
    PASTA_SEGMENTOS = pasta_seg_env

PASTA_REPLAYS = os.getenv("PASTA_REPLAYS", "./replays")

os.makedirs(PASTA_SEGMENTOS, exist_ok=True)
os.makedirs(PASTA_REPLAYS, exist_ok=True)

# Binário FFmpeg
if os.name == 'nt':
    FFMPEG_EXEC = 'ffmpeg.exe' if os.path.exists('ffmpeg.exe') else 'ffmpeg'
else:
    FFMPEG_EXEC = 'ffmpeg'

# Variáveis de controle de concorrência e estado
QUADRA_ID = None
ultimo_clique_timestamp = 0
trava_lock = threading.Lock()
fila_tarefas = queue.Queue()
processo_ffmpeg = None
feedback_dispositivo = None
executando = True

def acionar_feedback_confirmacao(duracao=1.0):
    """Aciona bip/LED de confirmação para os atletas saberem que o lance foi gravado."""
    global feedback_dispositivo
    if feedback_dispositivo:
        def _acionar():
            try:
                feedback_dispositivo.on()
                time.sleep(duracao)
                feedback_dispositivo.off()
            except Exception:
                pass
        threading.Thread(target=_acionar, daemon=True).start()

print("=" * 65)
print("🦊 FOX REPLAY — TOTEM EDGE CORE (ALTA DISPONIBILIDADE)")
try:
    _versao_git = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()
    print(f"📦 Versão Instalada: commit {_versao_git}")
except Exception:
    pass
print("=" * 65)

# ==============================================================================
# AUTENTICAÇÃO E ATIVAÇÃO DINÂMICA
# ==============================================================================
def autenticar_e_ativar_totem():
    """Conecta ao Supabase e obtém dinamicamente o ID da quadra através do Token seguro."""
    global QUADRA_ID
    print("🔑 Autenticando Totem nos servidores Fox Replay...")
    
    if not TOKEN_DISPOSITIVO:
        print("❌ CRÍTICO: TOKEN_DISPOSITIVO não configurado no .env!")
        return False

    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }

    # 1. Tenta primeiro a RPC segura (validar_totem) que não vaza a tabela
    endpoint_rpc = f"{SUPABASE_URL}/rest/v1/rpc/validar_totem"
    try:
        resposta_rpc = requests.post(endpoint_rpc, headers=headers, json={"p_token": TOKEN_DISPOSITIVO}, timeout=10)
        if resposta_rpc.status_code == 200:
            dados_rpc = resposta_rpc.json()
            if dados_rpc.get('valido') and dados_rpc.get('quadra_id'):
                QUADRA_ID = dados_rpc['quadra_id']
                print("✅ TOTEM ATIVADO COM SUCESSO VIA RPC SEGURA!")
                print(f"📌 Quadra ID Vinculada: {QUADRA_ID}\n")
                return True
            else:
                print("❌ ERRO: Token do Totem inválido ou não cadastrado no painel!")
                return False
    except Exception as e:
        print(f"⚠️ Aviso na RPC segura ({e}). Tentando endpoint de compatibilidade...")

    # 2. Fallback de compatibilidade (query direta) caso o script SQL ainda não tenha sido rodado
    endpoint = f"{SUPABASE_URL}/rest/v1/dispositivos?token_autenticacao=eq.{TOKEN_DISPOSITIVO}&select=quadra_id"
    try:
        resposta = requests.get(endpoint, headers=headers, timeout=10)
        if resposta.status_code == 200:
            dados = resposta.json()
            if dados and len(dados) > 0:
                QUADRA_ID = dados[0]['quadra_id']
                print("✅ TOTEM ATIVADO COM SUCESSO!")
                print(f"📌 Quadra ID Vinculada: {QUADRA_ID}\n")
                return True
            else:
                print("❌ ERRO: Token do Totem inválido ou não cadastrado no painel!")
                return False
        else:
            print(f"❌ ERRO HTTP BANCO: {resposta.status_code}")
            return False
    except Exception as e:
        print(f"❌ FALHA DE REDE AO AUTENTICAR: {e}")
        return False

# ==============================================================================
# WATCHDOG & BUFFER CIRCULAR DO FFMPEG
# ==============================================================================
def iniciar_buffer_circular():
    """Inicia o processo FFmpeg em modo contínuo de buffer circular."""
    global processo_ffmpeg
    camera_input = os.getenv('CAMERA_NOME', 'rtsp://admin:SuaSenhaAqui@XXXX:554/Streaming/Channels/101')
    tempo_seg = str(TEMPO_SEGMENTO)
    qtd_seg = os.getenv('QUANTIDADE_SEGMENTOS', '14')

    if camera_input.startswith('rtsp://'):
        print(f"📡 [CÂMERA IP] Conectando ao fluxo RTSP: {camera_input}")
        comando = [
            FFMPEG_EXEC,
            '-rtsp_transport', 'tcp',
            '-i', camera_input,
            '-c:v', 'copy',
            '-f', 'segment',
            '-segment_time', tempo_seg,
            '-segment_wrap', qtd_seg,
            '-reset_timestamps', '1',
            '-y',
            f"{PASTA_SEGMENTOS}/video_%03d.mp4"
        ]
    else:
        print(f"🔌 [WEBCAM USB] Conectando à câmera: {camera_input}")
        resolucao = os.getenv('RESOLUCAO', '1280x720')
        fps = os.getenv('FPS', '30')
        if os.name == 'nt':
            cmd_input = ['-f', 'dshow', '-i', f"video={camera_input}"]
        else:
            cmd_input = ['-f', 'v4l2', '-i', camera_input]

        comando = [
            FFMPEG_EXEC, *cmd_input,
            '-s', resolucao, '-r', fps,
            '-c:v', 'libx264',
            '-f', 'segment',
            '-segment_time', tempo_seg,
            '-segment_wrap', qtd_seg,
            '-reset_timestamps', '1',
            '-y',
            f"{PASTA_SEGMENTOS}/video_%03d.mp4"
        ]

    try:
        processo_ffmpeg = subprocess.Popen(
            comando,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return processo_ffmpeg
    except Exception as e:
        print(f"❌ Falha ao iniciar FFmpeg: {e}")
        return None

def supervisor_ffmpeg():
    """Watchdog que monitora o processo FFmpeg e reinicia automaticamente se cair."""
    global processo_ffmpeg, executando
    while executando:
        time.sleep(5)
        if processo_ffmpeg is not None:
            ret = processo_ffmpeg.poll()
            if ret is not None:
                print(f"⚠️ [WATCHDOG] O processo do FFmpeg parou com código {ret}! Reiniciando em 2s...")
                time.sleep(2)
                iniciar_buffer_circular()

# ==============================================================================
# FILA DE TAREFAS PERSISTENTE E ANTI-SPAM
# ==============================================================================
def registrar_lance_solicitado():
    """Registra uma solicitação de replay de forma não-bloqueante."""
    global ultimo_clique_timestamp
    tempo_atual = time.time()

    with trava_lock:
        if tempo_atual - ultimo_clique_timestamp < TRAVA_TEMPO_SEGUNDOS:
            restante = int(TRAVA_TEMPO_SEGUNDOS - (tempo_atual - ultimo_clique_timestamp))
            print(f"⚠️ [TRAVA] Botão em cooldown! Aguarde mais {restante}s.")
            return False

        ultimo_clique_timestamp = tempo_atual

    timestamp_id = int(tempo_atual)
    print(f"\n🔘 [BOTÃO ACIONADO] Lance {timestamp_id} agendado para processamento!")
    acionar_feedback_confirmacao(1.2)

    tarefa = {
        "id": timestamp_id,
        "status_video": "pendente",
        "status_upload": "pendente",
        "caminho_arquivo": "",
        "criado_em": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(tempo_atual))
    }

    # Persiste na fila JSON para tolerância a falhas
    try:
        fila = []
        if os.path.exists(ARQUIVO_FILA):
            with open(ARQUIVO_FILA, "r") as f:
                fila = json.load(f)
        fila.append(tarefa)
        with open(ARQUIVO_FILA, "w") as f:
            json.dump(fila, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar fila JSON: {e}")

    fila_tarefas.put(tarefa)
    return True

# ==============================================================================
# WORKER EM BACKGROUND: COSTURA DE VÍDEO + UPLOAD NUVEM + QR CODE
# ==============================================================================
def worker_processamento():
    """Worker assíncrono que costura o vídeo e envia para a nuvem sem travar o botão."""
    global executando, QUADRA_ID

    while executando:
        try:
            tarefa = fila_tarefas.get(timeout=1)
        except queue.Empty:
            continue

        tarefa_id = tarefa["id"]
        print(f"\n⚙️  [WORKER] Iniciando processamento do lance {tarefa_id}...")

        # 1. Costura dos Segmentos (Gera os últimos 30 segundos)
        arquivo_final = f"{PASTA_REPLAYS}/replay_{tarefa_id}.mp4"
        lista_txt_path = f"lista_{tarefa_id}.txt"

        sucesso_video = False
        try:
            arquivos = [f for f in os.listdir(PASTA_SEGMENTOS) if f.endswith('.mp4')]
            # Quantidade de segmentos necessários para fechar os segundos de replay solicitados (ex: 30s / 5s = 6 blocos)
            num_segmentos_necessarios = max(1, SEGUNDOS_REPLAY // TEMPO_SEGMENTO)

            if len(arquivos) >= 2:
                arquivos_ordenados = sorted(
                    arquivos,
                    key=lambda x: os.path.getmtime(os.path.join(PASTA_SEGMENTOS, x))
                )
                # O último elemento [-1] ainda está sendo gravado pelo FFmpeg, então o ignoramos.
                # Pegamos exatamente os N segmentos anteriores para somar os 30s cravados.
                inicio_fatia = -(num_segmentos_necessarios + 1)
                if len(arquivos_ordenados) >= (num_segmentos_necessarios + 1):
                    ultimos_segmentos = arquivos_ordenados[inicio_fatia:-1]
                else:
                    ultimos_segmentos = arquivos_ordenados[:-1]

                with open(lista_txt_path, "w") as f:
                    for seg in ultimos_segmentos:
                        caminho_limpo = os.path.join(PASTA_SEGMENTOS, seg).replace('\\', '/')
                        f.write(f"file '{caminho_limpo}'\n")

                comando_concat = [
                    FFMPEG_EXEC, '-f', 'concat', '-safe', '0',
                    '-i', lista_txt_path, '-c', 'copy', '-y', arquivo_final
                ]
                subprocess.run(comando_concat, shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if os.path.exists(lista_txt_path):
                    os.remove(lista_txt_path)

                if os.path.exists(arquivo_final) and os.path.getsize(arquivo_final) > 1000:
                    sucesso_video = True
                    tarefa["caminho_arquivo"] = arquivo_final
                    print(f"🎉 [VÍDEO] Replay de {len(ultimos_segmentos) * TEMPO_SEGMENTO}s (Lance {tarefa_id}) costurado com sucesso!")
                else:
                    print(f"❌ [ERRO] Arquivo final {arquivo_final} não foi gerado corretamente.")
            else:
                print("⚠️ [AVISO] Poucos segmentos disponíveis no buffer. Aguarde acumular vídeo.")
        except Exception as e:
            print(f"❌ [ERRO] Falha ao costurar vídeo {tarefa_id}: {e}")

        if not sucesso_video:
            fila_tarefas.task_done()
            continue

        # 2. Upload para o Supabase Storage
        print(f"☁️  [NUVEM] Enviando replay_{tarefa_id}.mp4 para o Storage...")
        nome_arquivo_nuvem = f"replay_{tarefa_id}.mp4"
        endpoint_storage = f"{SUPABASE_URL}/storage/v1/object/replays/{nome_arquivo_nuvem}"
        headers_storage = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Content-Type": "video/mp4"
        }

        try:
            with open(arquivo_final, "rb") as f_video:
                resposta_storage = requests.post(endpoint_storage, headers=headers_storage, data=f_video, timeout=60)

            if resposta_storage.status_code in [200, 201]:
                print("💾 [STORAGE] Arquivo salvo no bucket com sucesso!")
                url_publica_video = f"{SUPABASE_URL}/storage/v1/object/public/replays/{nome_arquivo_nuvem}"

                # 3. Inserção no Banco de Dados
                print("📝 [BANCO] Registrando jogada na tabela...")
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

                resposta_banco = requests.post(endpoint_banco, headers=headers_banco, json=payload_banco, timeout=15)
                if resposta_banco.status_code in [200, 201]:
                    dados_replay = resposta_banco.json()
                    id_do_replay = dados_replay[0]['id']
                    link_front = f"{FRONTEND_URL}/jogada?id={id_do_replay}"

                    print(f"🚀 [SUCESSO TOTAL] Replay liberado!")
                    print(f"👉 Link do Jogador: {link_front}")

                    # 4. Geração de QR Code
                    gerar_e_exibir_qr(link_front)
                else:
                    print(f"❌ [ERRO BANCO] Falha ao registrar na tabela: {resposta_banco.status_code}")
            else:
                print(f"❌ [ERRO STORAGE] Código HTTP: {resposta_storage.status_code}")
        except Exception as e:
            print(f"📡 [REDE] Erro durante o upload: {e}")

        # 5. Limpeza de Disco (Retenção de Arquivos)
        limpar_arquivos_antigos()
        fila_tarefas.task_done()

def gerar_e_exibir_qr(link):
    """Gera o QR Code com a biblioteca qrcode."""
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        caminho_qr = "qr_replay_atual.png"
        img.save(caminho_qr)
        print("🖼️  [QR CODE] Gerado com sucesso: qr_replay_atual.png\n")
    except Exception as e:
        print(f"Erro ao gerar QR Code: {e}")

def limpar_arquivos_antigos():
    """Remove vídeos locais mais velhos que o limite estipulado para proteger o cartão SD."""
    try:
        limite_segundos = RETENCAO_LOCAL_HORAS * 3600
        agora = time.time()
        for arquivo in glob.glob(f"{PASTA_REPLAYS}/*.mp4"):
            if agora - os.path.getmtime(arquivo) > limite_segundos:
                os.remove(arquivo)
                print(f"🧹 [LIMPEZA] Removido clipe antigo expirado: {os.path.basename(arquivo)}")
    except Exception as e:
        print(f"Aviso de limpeza: {e}")

# ==============================================================================
# LISTENERS DE BOTÃO (DUAL INPUT: GPIO OU TECLADO)
# ==============================================================================
def iniciar_listener_gpio():
    """Inicia listener para o botão (com ou sem fio) e feedback de confirmação (Buzzer/LED)."""
    global feedback_dispositivo
    try:
        from gpiozero import Button, OutputDevice

        # Inicia feedback (Buzzer/LED) para cenários sem totem/tela
        try:
            feedback_dispositivo = OutputDevice(PINO_FEEDBACK_GPIO, active_high=True, initial_value=False)
            print(f"🔊 [FEEDBACK] Buzzer/LED ativo no pino GPIO {PINO_FEEDBACK_GPIO} (Pino Físico 13).")
        except Exception as ef:
            print(f"ℹ️  [FEEDBACK] Buzzer/LED opcional não conectado ({ef}).")

        botao = Button(PINO_BOTAO_GPIO, bounce_time=0.2)
        botao.when_pressed = registrar_lance_solicitado
        print(f"🔌 [GPIO] Botão físico/wireless monitorado no pino GPIO {PINO_BOTAO_GPIO} (Pino 11).")
        return True
    except Exception as e:
        print(f"ℹ️  [GPIO Não Detectado] ({e}). Utilizando listener de teclado para testes.")
        return False

# ==============================================================================
# PAREAMENTO AUTOMÁTICO (ZERO-TOUCH VIA CÓDIGO DE 6 DÍGITOS)
# ==============================================================================
def salvar_config_no_env(token, camera_url=None):
    """Grava o novo token e a URL da câmera recebidos no arquivo .env para persistência."""
    try:
        linhas = []
        if os.path.exists('.env'):
            with open('.env', 'r', encoding='utf-8') as f:
                linhas = f.readlines()

        token_atualizado = False
        camera_atualizada = False
        novas_linhas = []

        for l in linhas:
            if l.startswith("TOKEN_DISPOSITIVO="):
                novas_linhas.append(f"TOKEN_DISPOSITIVO={token}\n")
                token_atualizado = True
            elif camera_url and l.startswith("CAMERA_NOME="):
                novas_linhas.append(f"CAMERA_NOME={camera_url}\n")
                camera_atualizada = True
            else:
                novas_linhas.append(l)

        if not token_atualizado:
            novas_linhas.append(f"\nTOKEN_DISPOSITIVO={token}\n")
        if camera_url and not camera_atualizada:
            novas_linhas.append(f"CAMERA_NOME={camera_url}\n")

        with open('.env', 'w', encoding='utf-8') as f:
            f.writelines(novas_linhas)
        print("💾 Configurações salvas com sucesso no arquivo .env local!")
    except Exception as e:
        print(f"Aviso ao salvar .env: {e}")

def salvar_token_no_env(token):
    salvar_config_no_env(token)

def iniciar_modo_pareamento():
    """Gera código de 6 dígitos estilo Smart TV e aguarda ativação pelo celular."""
    import random
    codigo = f"{random.randint(100, 999)}-{random.randint(100, 999)}"

    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    endpoint_pareamento = f"{SUPABASE_URL}/rest/v1/pareamentos"
    payload = {"codigo": codigo, "status": "pendente"}

    try:
        requests.post(endpoint_pareamento, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao registrar pareamento no banco: {e}")

    print("\n" + "=" * 65)
    print("🦊 FOX REPLAY — PAREAMENTO RÁPIDO DO TOTEM")
    print("=" * 65)
    print("  Totem ligado e pronto para ativação sem complicação!\n")
    print(f"  👉 CÓDIGO DE ATIVAÇÃO:    [  {codigo}  ]\n")
    print(f"  👉 Acesse no celular: {FRONTEND_URL}/dashboard")
    print("     Clique em 'Vincular Totem por Código' e digite os dígitos acima.")
    print("=" * 65)
    print("  Aguardando ativação pelo celular...")

    # Salva QR Code com link direto para agilizar ainda mais
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=8, border=3)
        qr.add_data(f"{FRONTEND_URL}/ativar?codigo={codigo}")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save("qr_pareamento.png")
    except Exception:
        pass

    # Loop de escuta do pareamento
    while True:
        time.sleep(3)
        try:
            url_check = f"{SUPABASE_URL}/rest/v1/pareamentos?codigo=eq.{codigo}&select=status,token_gerado,quadra_id,camera_url"
            r = requests.get(url_check, headers=headers, timeout=6)
            if r.status_code == 200:
                dados = r.json()
                if dados and len(dados) > 0 and dados[0].get("status") == "vinculado":
                    token = dados[0].get("token_gerado")
                    quadra_id = dados[0].get("quadra_id")
                    camera_remota = dados[0].get("camera_url")
                    if token and quadra_id:
                        print(f"\n🎉 [SUCESSO TOTAL] Totem pareado e vinculado à quadra {quadra_id}!")
                        if camera_remota:
                            print(f"📹 Câmera configurada remotamente: {camera_remota}")
                            os.environ['CAMERA_NOME'] = camera_remota
                        salvar_config_no_env(token, camera_remota)
                        return token, quadra_id
        except Exception:
            pass
            pass

# ==============================================================================
# FLUXO DE EXECUÇÃO PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
    if not autenticar_e_ativar_totem():
        print("⚠️ Totem não vinculado. Entrando no modo de pareamento automático...")
        token_novo, quadra_id_nova = iniciar_modo_pareamento()
        TOKEN_DISPOSITIVO = token_novo
        QUADRA_ID = quadra_id_nova

    # Inicia buffer de vídeo
    iniciar_buffer_circular()

    # Inicia Watchdog de vídeo
    thread_watchdog = threading.Thread(target=supervisor_ffmpeg, daemon=True)
    thread_watchdog.start()

    # Inicia Worker de processamento e upload
    thread_worker = threading.Thread(target=worker_processamento, daemon=True)
    thread_worker.start()

    # Inicia Listener GPIO se disponível
    gpio_ativo = iniciar_listener_gpio()

    print("\n🟢 SISTEMA PRONTO E MONITORANDO!")
    print("👉 Pressione [ESPAÇO] no teclado ou o botão físico na quadra para salvar um lance.")
    print("👉 Pressione [Ctrl + C] para finalizar.\n")

    try:
        # Loop do teclado / supervisor principal
        import keyboard
        while True:
            try:
                if keyboard.is_pressed('space'):
                    registrar_lance_solicitado()
                    time.sleep(0.3)
            except Exception:
                # Caso rode no Linux sem privilégios de root para teclado
                pass
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nFinalizando o Fox Replay Totem...")
    finally:
        executando = False
        if processo_ffmpeg:
            if os.name == 'nt':
                subprocess.run(f"taskkill /F /T /PID {processo_ffmpeg.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                processo_ffmpeg.terminate()
        print("Totem finalizado com sucesso.")
