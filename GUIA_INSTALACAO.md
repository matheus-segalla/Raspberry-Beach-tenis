# 🎾 GUIA OFICIAL DE INSTALAÇÃO E ATIVAÇÃO EM CAMPO — FOX REPLAY

Este manual foi elaborado para técnicos e funcionários responsáveis pela montagem física, cabeamento e ativação dos totens de replay nas quadras esportivas (Beach Tennis, Futevôlei, Padel, etc.).

---

## 📦 1. Checklist do Kit de Instalação

Antes de ir até a quadra, certifique-se de que está com todos os itens:

| Item | Descrição | Observação |
| :--- | :--- | :--- |
| **Raspberry Pi** | Raspberry Pi 3B+, 4 ou 5 | Com cooler ou dissipador instalado |
| **Fonte de Energia** | Fonte oficial 5V (mínimo 3A) | ⚠️ Não utilize carregadores comuns de celular |
| **Cartão MicroSD** | Cartão Gold / Extreme (com Imagem Mestre) | Já gravado com o sistema operacional e serviços |
| **Câmera IP** | Câmera IP Full HD (Hikvision / Intelbras) | Protocolo RTSP habilitado |
| **Switch de Rede / PoE** | Switch 10/100 ou Gigabit com PoE | Para alimentar a câmera e conectar o Raspberry |
| **Botão de Grade** | Botão tipo cogumelo ou arcade industrial | Contato seco **Normalmente Aberto (NA)** |
| **Cabo de Rede (UTP)** | Cabo CAT5e ou CAT6 homologado | Crimpado para Câmera e 1 par para o botão |
| **Cabo HDMI** | Cabo HDMI 1.5m a 3m | Conectado entre o Raspberry e a TV/Monitor |
| **TV ou Monitor** | Display para exibição dos replays | Instalado visível para os atletas na quadra |

---

## ⚡ 2. Ligação Física do Botão (Sem Arduino)

O sistema Fox Replay utiliza leitura direta pelos pinos GPIO nativos do Raspberry Pi. **Não é necessário nenhum Arduino ou placa intermediária.**

### Pinagem na Barra do Raspberry Pi:
* **Fio 1 do Botão** ➔ **Pino Físico 11** (GPIO 17)
* **Fio 2 do Botão** ➔ **Pino Físico 09** (GND - Terra)

```
        BARRA DE PINOS DO RASPBERRY PI (Top View)
       ──────────────────────────────────────────
         [01] 3.3V  ( )  ( )  5V      [02]
         [03] GPIO  ( )  ( )  5V      [04]
         [05] GPIO  ( )  ( )  GND     [06]
         [07] GPIO  ( )  ( )  GPIO    [08]
  TERRA ➔[09] GND   (X)  ( )  GPIO    [10]
 SINAL ➔ [11] GPIO17(X)  ( )  GPIO    [12]
         [13] GPIO  ( )  ( )  GND     [14]
              ...         ...
```

> 💡 **Dica de Campo (Anti-Ruído)**:  
> Use um **par trançado de cabo de rede UTP** (por exemplo, o par **Azul / Azul-Branco**) para levar o sinal da grade até o totem. O trançado natural do cabo anula interferências eletromagnéticas de refletores LED da arena.  
> *Não há polaridade positiva ou negativa no botão de contato seco; tanto faz a ordem dos 2 fios.*

---

## 🌐 3. Ligação de Rede e Câmera

1. **Posicionamento da Câmera**:
   * Instale a câmera a uma altura entre 3m e 4,5m, centralizada no fundo da quadra ou na lateral para cobertura ampla da rede e das linhas de fundo.
   * Trave bem o suporte para não vibrar com ventos ou boladas.
2. **Conexão**:
   * Ligue a Câmera IP na porta PoE do switch.
   * Ligue a porta Ethernet do Raspberry Pi no mesmo switch/roteador.
   * Certifique-se de que o roteador da arena está fornecendo internet via DHCP (ou configure o Wi-Fi se for o caso).

---

## 🎬 4. Especificações do Vídeo Gravado

* **Duração do Replay**: **30 segundos** cravados dos últimos lances da partida.
* **Buffer Circular**: O sistema mantém os últimos 70 segundos gravados na memória RAM em blocos contínuos de 5 segundos.
* **Ao Apertar o Botão**: O processador resgata os 6 blocos imediatamente anteriores (6 x 5s = 30s), junta os vídeos sem perda de qualidade e faz o upload automático.
* **Trava Anti-Spam (Cooldown)**: Após apertar o botão, o sistema bloqueia novos cliques por **20 segundos** para impedir disparos duplicados acidentais.

---

## 📱 5. Procedimento de Ativação na Quadra (Zero-Touch)

Você não precisa digitar comandos no terminal nem abrir arquivos de configuração na quadra. A ativação é feita pelo celular:

1. **Ligue o Totem na Tomada e Conecte o HDMI na TV**:
   * O sistema iniciará sozinho em menos de 45 segundos.
2. **Observe a Tela da TV**:
   * Se o totem for novo (ainda não vinculado), surgirá na tela:
     * O logotipo da **Fox Replay**;
     * Um **Código de Ativação de 6 Dígitos** (exemplo: `482-915`);
     * Um **QR Code** de ativação rápida.
3. **Ative pelo Celular**:
   * Aponte a câmera do seu celular para o QR Code da TV **OU** acesse:
     `https://fox-replay.vercel.app/ativar`
   * Faça login com a conta de administrador da arena;
   * Selecione a **Arena** e a **Quadra** correspondente (ex: *Quadra 2 - Coberta*);
   * Digite o código de 6 dígitos exibido na TV;
   * Clique em **"⚡ Ativar Totem"**.
4. **Confirmação Instantânea**:
   * Na mesma hora, a TV exibirá a mensagem de sucesso e o totem passará ao modo ativo de gravação.

---

## ✅ 6. Checklist de Teste e Entrega

Antes de liberar a quadra para os clientes, faça o teste prático:

- [ ] **1. Teste da Câmera**: Verifique se a TV ou o log do sistema mostra a imagem nítida da quadra.
- [ ] **2. Teste do Botão de Grade**: Vá até a grade e aperte o botão físico firmemente.
- [ ] **3. Tempo de Resposta**: Observe a TV. Em cerca de 5 a 10 segundos deverá surgir na tela o **QR Code do Replay**.
- [ ] **4. Teste no Celular**: Abra a câmera do celular, aponte para o QR Code e confira:
  - O vídeo tem exatamente **30 segundos** de duração?
  - A imagem está limpa e sem travamentos?
  - O lance capturado corresponde ao momento anterior ao clique?

---

## 🛠️ 7. Guia Rápido de Solução de Problemas (Troubleshooting)

### ❌ Problema: A TV exibe aviso de falha na câmera (`CAMERA_NOME`)
* **Causa**: O cabo de rede da câmera está desconectado ou o IP/senha da câmera mudou.
* **Solução**: Verifique se a porta do switch está piscando verde. Teste a URL RTSP no VLC em um notebook conectado na mesma rede para garantir que o stream está aberto.

### ❌ Problema: Aperta o botão na grade mas nada acontece
* **Causa**: Fios invertidos em pinos errados ou fio rompido no trajeto.
* **Solução**: 
  1. Confira se os fios estão exatamente no **Pino 11** e **Pino 09**.
  2. Teste fechar contato direto nos pinos do Raspberry com um clipe de papel metálico. Se funcionar, o problema está na fiação ou no botão da grade.

### ❌ Problema: O Raspberry Pi trava ou reinicia sozinho ao apertar o botão
* **Causa**: Fonte de alimentação fraca ou de baixa amperagem.
* **Solução**: Substitua a fonte por uma original com pelo menos 5.1V e 3.0A (ou 5.0A no caso do Pi 5).

---

*Fox Replay — Sistema de Gravação e Replay Esportivo Inteligente.*
