# Caminho: core/telegram_bot.py
import os
import re
import time
import threading
import unicodedata
import requests
import socket
from dotenv import load_dotenv
from core.database import (
    obter_ou_vincular_usuario_telegram,
    iniciar_2fa_leitura_qrcode,
    verificar_pendencia_2fa_telegram,
    confirmar_codigo_2fa_telegram,
    salvar_mensagem_historico,
    obter_resumo_financeiro,
    listar_transacoes
)
from core.ia import interpretar_mensagem_financeira

try:
    from core.email_service import enviar_email_codigo_2fa
except Exception:
    def enviar_email_codigo_2fa(destinatario, nome, codigo):
        print(f"📧 [2FA QR Code] Código para {destinatario}: {codigo}")
        return {"sucesso": True, "aviso": f"Código: {codigo}"}

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "FinanceControlBot").strip().lstrip("@")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAFICOS_DIR = os.path.join(BASE_DIR, "web", "img", "graficos")
os.makedirs(GRAFICOS_DIR, exist_ok=True)

_polling_started = False
_polling_lock = threading.Lock()


def _sem_acentos(texto: str) -> str:
    if not texto:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


def telegram_configurado() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and ":" in TELEGRAM_BOT_TOKEN and not TELEGRAM_BOT_TOKEN.startswith("seu_token"))


def obter_username_bot() -> str:
    if not telegram_configurado():
        return TELEGRAM_BOT_USERNAME
    try:
        resp = requests.get(f"{TELEGRAM_API_BASE}/getMe", timeout=5)
        if resp.status_code == 200:
            dados = resp.json()
            if dados.get("ok") and dados["result"].get("username"):
                return dados["result"]["username"]
    except Exception:
        pass
    return TELEGRAM_BOT_USERNAME


def enviar_mensagem_telegram(chat_id: str, texto: str) -> bool:
    if not telegram_configurado():
        return False
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": str(texto),
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            payload.pop("parse_mode", None)
            res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"⚠️ [Telegram] Erro ao enviar mensagem: {e}")
        return False


def enviar_foto_telegram(chat_id: str, caminho_arquivo: str, legenda: str = "") -> bool:
    """Envia o arquivo de imagem (.png) do gráfico para o chat do Telegram."""
    if not telegram_configurado():
        return False
    if not caminho_arquivo or not os.path.exists(caminho_arquivo):
        print(f"⚠️ [Telegram] Arquivo de gráfico não encontrado em: {caminho_arquivo}")
        return False

    url = f"{TELEGRAM_API_BASE}/sendPhoto"
    dados = {"chat_id": str(chat_id)}
    if legenda:
        dados["caption"] = legenda
        dados["parse_mode"] = "Markdown"

    try:
        with open(caminho_arquivo, "rb") as arquivo_img:
            res = requests.post(url, data=dados, files={"photo": arquivo_img}, timeout=25)
        if res.status_code != 200 and "parse_mode" in dados:
            dados.pop("parse_mode", None)
            with open(caminho_arquivo, "rb") as arquivo_img:
                res = requests.post(url, data=dados, files={"photo": arquivo_img}, timeout=25)
        return res.status_code == 200
    except Exception as e:
        print(f"⚠️ [Telegram] Erro ao enviar imagem do gráfico: {e}")
        return False


def gerar_grafico_financeiro_telegram_png(usuario_id: int) -> str:
    """
    Gera o arquivo .PNG contendo os 3 relatórios visuais (Pizza, Barras e Linha de Evolução
    com os nomes dos gastos) de forma Thread-Safe para envio imediato no Telegram.
    """
    resumo = obter_resumo_financeiro(usuario_id)
    transacoes = listar_transacoes(usuario_id, limite=30)

    labels_pizza = resumo.get("grafico_pizza", {}).get("labels", [])
    valores_pizza = [float(v or 0) for v in resumo.get("grafico_pizza", {}).get("valores", [])]

    entradas_val = float(resumo.get("total_receitas") or 0)
    saidas_val = float(resumo.get("total_despesas") or 0)

    # Monta a evolução do saldo trocando #ID pelo nome real do gasto (ex: Mercado, Lanche)
    mapa_nomes = {f"#{t['id']}": (t.get("descricao") or t.get("categoria") or f"#{t['id']}") for t in transacoes if t.get("id")}
    labels_ev_brutos = resumo.get("grafico_evolucao", {}).get("labels", ["Hoje"])
    saldos_ev = [float(s or 0) for s in resumo.get("grafico_evolucao", {}).get("saldos", [resumo.get("saldo", 0)])]
    labels_ev = [str(mapa_nomes.get(str(lbl), lbl))[:12] for lbl in labels_ev_brutos]

    caminho_saida = os.path.join(GRAFICOS_DIR, f"grafico_telegram_user_{usuario_id}.png")

    # 1. Renderização Principal via Matplotlib (Thread-Safe com FigureCanvasAgg)
    try:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

        fig = Figure(figsize=(11, 7.5), dpi=130, facecolor="#0b1320")
        FigureCanvas(fig)

        # Subplot 1: Pizza (Gastos por Categoria)
        ax1 = fig.add_subplot(2, 2, 1, facecolor="#152238")
        cores_pizza = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4"]
        if labels_pizza and sum(valores_pizza) > 0:
            wedges, texts, autotexts = ax1.pie(
                valores_pizza,
                labels=labels_pizza,
                autopct="%1.1f%%",
                startangle=140,
                colors=cores_pizza[:len(labels_pizza)],
                wedgeprops={"width": 0.45, "edgecolor": "#152238"},
                textprops={"color": "#f8fafc", "fontsize": 8.5}
            )
            for at in autotexts:
                at.set_color("#ffffff")
                at.set_fontweight("bold")
            ax1.set_title("Gastos por Categoria", color="#f8fafc", fontsize=11, fontweight="bold", pad=10)
        else:
            ax1.text(0.5, 0.5, "Sem gastos registrados", color="#94a3b8", ha="center", va="center", fontsize=10)
            ax1.set_axis_off()

        # Subplot 2: Barras (Entradas vs. Saídas)
        ax2 = fig.add_subplot(2, 2, 2, facecolor="#152238")
        barras = ax2.bar(
            ["Entradas", "Saídas"],
            [entradas_val, saidas_val],
            color=["#10b981", "#ef4444"],
            width=0.45
        )
        ax2.set_title("Entradas vs. Saídas (R$)", color="#f8fafc", fontsize=11, fontweight="bold", pad=10)
        ax2.tick_params(colors="#cbd5e1", labelsize=9)
        ax2.grid(axis="y", color="#334155", linestyle="--", linewidth=0.5, alpha=0.5)
        for spine in ax2.spines.values():
            spine.set_color("#334155")
        for b in barras:
            h = b.get_height()
            ax2.annotate(
                f"R$ {h:.2f}",
                xy=(b.get_x() + b.get_width() / 2, h),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center", va="bottom",
                color="#f8fafc", fontsize=8.5, fontweight="bold"
            )

        # Subplot 3: Linha (Evolução do Saldo por Lançamento)
        ax3 = fig.add_subplot(2, 1, 2, facecolor="#152238")
        x_idx = list(range(len(labels_ev)))
        ax3.plot(x_idx, saldos_ev, color="#3b82f6", marker="o", linewidth=2.4, markersize=6, label="Saldo (R$)")
        ax3.fill_between(x_idx, saldos_ev, color="#3b82f6", alpha=0.18)
        ax3.set_title("Evolução do Saldo por Lançamento (R$)", color="#f8fafc", fontsize=11, fontweight="bold", pad=10)
        ax3.set_xticks(x_idx)
        ax3.set_xticklabels(labels_ev, rotation=22, ha="right", color="#cbd5e1", fontsize=8.5)
        ax3.tick_params(axis="y", colors="#cbd5e1", labelsize=9)
        ax3.grid(True, color="#334155", linestyle="--", linewidth=0.5, alpha=0.5)
        for spine in ax3.spines.values():
            spine.set_color("#334155")

        fig.tight_layout(pad=2.0)
        fig.savefig(caminho_saida, facecolor=fig.get_facecolor(), edgecolor="none")
        if os.path.exists(caminho_saida):
            return caminho_saida
    except Exception as e:
        print(f"⚠️ [Telegram Gráfico] Aviso no Matplotlib ({e}). Acionando gerador alternativo...")

    # 2. Fallback automático caso o Matplotlib não esteja instalado no ambiente
    try:
        cfg_quickchart = {
            "type": "bar",
            "data": {
                "labels": ["Entradas (R$)", "Saídas (R$)", "Saldo Atual (R$)"],
                "datasets": [{
                    "label": "Resumo Financeiro (R$)",
                    "data": [entradas_val, saidas_val, float(resumo.get("saldo") or 0)],
                    "backgroundColor": ["#10b981", "#ef4444", "#3b82f6"]
                }]
            }
        }
        r_img = requests.post(
            "https://quickchart.io/chart",
            json={"backgroundColor": "#0b1320", "width": 700, "height": 420, "chart": cfg_quickchart},
            timeout=12
        )
        if r_img.status_code == 200:
            with open(caminho_saida, "wb") as f:
                f.write(r_img.content)
            return caminho_saida
    except Exception as err_qc:
        print(f"⚠️ [Telegram Gráfico] Erro no fallback: {err_qc}")

    return ""


def _deve_enviar_grafico(texto_usuario: str, resultado_ia: dict) -> bool:
    """Detecta se o usuário solicitou gráfico ou se a IA sinalizou envio de gráfico."""
    if isinstance(resultado_ia, dict):
        if (
            resultado_ia.get("grafico_path")
            or resultado_ia.get("enviar_grafico")
            or resultado_ia.get("exibir_graficos_web")
            or resultado_ia.get("exibir_graficos")
            or resultado_ia.get("intencao") == "enviar_grafico"
            or resultado_ia.get("graficos")
        ):
            return True

    txt_norm = _sem_acentos(texto_usuario)
    gatilhos = (
        "grafico", "graficos", "me manda o grafico", "mostrar grafico",
        "ver grafico", "resumo visual", "evolucao do saldo"
    )
    return any(g in txt_norm for g in gatilhos)


def processar_update_telegram(update: dict) -> dict:
    """
    Fluxo Blindado de Segurança (2FA Obrigatório) + Envio de Gráficos em PNG:
    1. Se o chat estiver com 2FA pendente, NENHUM comando passa até digitar os 6 dígitos corretos.
    2. Se o chat não estiver autenticado no banco com status_2fa = 1, bloqueia o acesso.
    3. Quando o usuário pede gráfico, gera e envia a imagem .png diretamente no Telegram.
    """
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"processado": False}

    chat = message.get("chat", {})
    from_user = message.get("from", {})
    chat_id = str(chat.get("id", ""))
    texto = (message.get("text") or "").strip()

    if not chat_id or not texto:
        return {"processado": False}

    username = from_user.get("username") or chat.get("username") or ""
    first_name = from_user.get("first_name") or chat.get("first_name") or "Usuário Telegram"

    # Comando utilitário para ver o próprio ID
    if texto.lower() in ("/id", "/meuid", "meu id"):
        enviar_mensagem_telegram(
            chat_id,
            f"🆔 *Dados do seu Telegram:*\n"
            f"• *Chat ID:* `{chat_id}`\n"
            f"• *Username:* `@{username or 'não definido'}`"
        )
        return {"processado": True, "chat_id": chat_id}

    # =========================================================================
    # ETAPA 1: LEITURA DO QR CODE (/start <TOKEN>) -> BLOQUEIA O CHAT E PEDE 2FA
    # =========================================================================
    if texto.startswith("/start"):
        partes = texto.split(maxsplit=1)
        if len(partes) > 1:
            token_qr = partes[1].strip()
            inicio_2fa = iniciar_2fa_leitura_qrcode(token=token_qr, chat_id_telegram=chat_id)

            if not inicio_2fa.get("sucesso"):
                enviar_mensagem_telegram(chat_id, f"⚠️ {inicio_2fa.get('erro')}")
                return {"processado": True, "chat_id": chat_id}

            enviar_email_codigo_2fa(
                destinatario=inicio_2fa["email_destino"],
                nome=inicio_2fa["nome"],
                codigo=inicio_2fa["codigo_gerado"]
            )

            msg_2fa = (
                f"🔐 *Verificação de Dupla Autenticação (2FA Obrigatória)*\n\n"
                f"Você escaneou o QR Code da conta de *{inicio_2fa['nome']}*.\n"
                f"Enviamos um código de segurança de *6 dígitos* para o e-mail `{inicio_2fa['email_mascarado']}`.\n\n"
                f"⛔ *O chatbot está bloqueado até a confirmação.*\n"
                f"👉 *Digite agora os 6 números enviados ao seu e-mail:*"
            )
            enviar_mensagem_telegram(chat_id, msg_2fa)
            return {"processado": True, "chat_id": chat_id}

    # =========================================================================
    # ETAPA 2: TRAVA ESTRITA DE 2FA PENDENTE (NADA PASSA SEM O CÓDIGO CORRETO)
    # =========================================================================
    if verificar_pendencia_2fa_telegram(chat_id):
        texto_limpo = texto.strip()
        # Só aceita se o usuário digitou exatamente um código numérico de 6 dígitos
        if re.fullmatch(r"\d{6}", texto_limpo):
            validacao = confirmar_codigo_2fa_telegram(chat_id, texto_limpo, username=username)
            if validacao.get("sucesso"):
                usr = validacao["usuario"]
                enviar_mensagem_telegram(
                    chat_id,
                    f"✅ *Código 2FA verificado com sucesso!*\n\n"
                    f"Sua conta *{usr['nome']}* (`{usr['email']}`) foi autenticada e liberada neste Telegram.\n\n"
                    f"Você já pode usar normalmente:\n"
                    f"• `saldo` ou `extrato`\n"
                    f"• `gastei 50 no mercado`\n"
                    f"• `me manda o gráfico`"
                )
            else:
                # Código de 6 dígitos ERRADO: mantém bloqueado!
                enviar_mensagem_telegram(
                    chat_id,
                    validacao.get(
                        "erro",
                        "❌ *Código 2FA incorreto!* O acesso permanece bloqueado. Confira seu e-mail e digite os 6 dígitos corretos."
                    )
                )
            return {"processado": True, "chat_id": chat_id}
        else:
            # Usuário tentou mandar qualquer outra mensagem ou código inválido sem autenticar
            enviar_mensagem_telegram(
                chat_id,
                "⛔ *Acesso Bloqueado (2FA Pendente)*\n\n"
                "Você precisa digitar o código correto de *6 dígitos* enviado para o seu e-mail antes de utilizar o assistente."
            )
            return {"processado": True, "chat_id": chat_id}

    # =========================================================================
    # ETAPA 3: VERIFICA SE O CHAT ESTÁ AUTENTICADO NO BANCO
    # =========================================================================
    usuario = obter_ou_vincular_usuario_telegram(
        chat_id=chat_id,
        username=username,
        first_name=first_name
    )

    if not usuario.get("autenticado"):
        enviar_mensagem_telegram(
            chat_id,
            "🔒 *Acesso Não Autorizado — Conta Não Vinculada*\n\n"
            "Para liberar o Assistente Financeiro no seu Telegram:\n"
            "1. Acesse a aba *Configurações* no painel Web.\n"
            "2. Clique em *Gerar QR Code (Telegram / Mobile)* e escaneie.\n"
            "3. Digite aqui no chat o código de *6 dígitos (2FA)* enviado para o seu e-mail."
        )
        return {"processado": True, "chat_id": chat_id}

    if texto.startswith("/start"):
        enviar_mensagem_telegram(
            chat_id,
            f"👋 Olá, *{usuario['nome']}*! Sua conta já está autenticada.\n"
            f"Envie seus gastos, receitas ou digite `saldo`, `extrato` ou `me manda o gráfico`."
        )
        return {"processado": True, "chat_id": chat_id}

    # =========================================================================
    # ENVIO DO LINK DO DASHBOARD QUANDO SOLICITADO NO TELEGRAM
    # =========================================================================
    texto_norm = _sem_acentos(texto)
    gatilhos_link = (
        "link", "/link", "/dashboard", "link do dashboard", "me manda o link",
        "manda o link", "link do site", "link do sistema", "acessar dashboard",
        "abrir dashboard", "painel web"
    )
    if texto_norm in ("link", "/link", "dashboard", "/dashboard", "site", "painel") or any(g in texto_norm for g in gatilhos_link):
        links = obter_links_dashboard()
        msg_link = (
            f"🌐 *Acesso Rápido ao Dashboard — FinanceControl*\n\n"
            f"📱 *Acesso na Rede / Celular (Wi-Fi):*\n{links['rede']}\n\n"
            f"💻 *Acesso no Computador (Local):*\n{links['pc']}"
        )
        if links["nuvem"]:
            msg_link += f"\n\n☁️ *Acesso Externo (Nuvem):*\n{links['nuvem']}"

        enviar_mensagem_telegram(chat_id, msg_link)
        return {"processado": True, "chat_id": chat_id}
        
    # =========================================================================
    # ETAPA 4: PROCESSAMENTO PELA IA + ENVIO DO GRÁFICO EM IMAGEM (.PNG)
    # =========================================================================
    try:
        salvar_mensagem_historico(usuario["id"], "usuario", f"[Telegram] {texto}")
        resultado_ia = interpretar_mensagem_financeira(usuario["id"], texto)

        if isinstance(resultado_ia, dict):
            resposta_texto = resultado_ia.get("resposta") or "Comando processado com sucesso."
            caminho_grafico = resultado_ia.get("grafico_path")
        else:
            resposta_texto = str(resultado_ia or "Comando processado com sucesso.")
            caminho_grafico = None

        salvar_mensagem_historico(usuario["id"], "ia", resposta_texto)
        enviar_mensagem_telegram(chat_id, resposta_texto)

        # Verifica se o usuário pediu gráfico; se o ia.py não gerou o PNG, gera agora mesmo!
        if _deve_enviar_grafico(texto, resultado_ia):
            if not caminho_grafico or not os.path.exists(str(caminho_grafico)):
                caminho_grafico = gerar_grafico_financeiro_telegram_png(usuario["id"])

            if caminho_grafico and os.path.exists(caminho_grafico):
                enviar_foto_telegram(
                    chat_id=chat_id,
                    caminho_arquivo=caminho_grafico,
                    legenda="📊 *Resumo Visual das suas Finanças (Pizza, Entradas vs. Saídas e Evolução do Saldo)*"
                )
    except Exception as e:
        print(f"⚠️ [Telegram IA] Erro ao processar mensagem '{texto}': {e}")
        enviar_mensagem_telegram(chat_id, "⚠️ Ocorreu um erro ao processar sua solicitação. Tente novamente.")

    return {"processado": True, "chat_id": chat_id}


def _loop_polling_telegram():
    try:
        requests.post(f"{TELEGRAM_API_BASE}/deleteWebhook", timeout=5)
    except Exception:
        pass

    offset = 0
    while True:
        try:
            resp = requests.get(
                f"{TELEGRAM_API_BASE}/getUpdates",
                params={"offset": offset, "timeout": 20},
                timeout=25
            )
            if resp.status_code == 200:
                dados = resp.json()
                if dados.get("ok"):
                    for upd in dados.get("result", []):
                        offset = upd["update_id"] + 1
                        try:
                            processar_update_telegram(upd)
                        except Exception as err_upd:
                            print(f"⚠️ [Telegram] Erro ao processar update: {err_upd}")
            else:
                time.sleep(2)
        except Exception as err_loop:
            print(f"⚠️ [Telegram Polling] Reconectando: {err_loop}")
            time.sleep(3)


def iniciar_bot_telegram_background():
    global _polling_started
    if not telegram_configurado():
        print("ℹ️ [Telegram] TELEGRAM_BOT_TOKEN não configurado no .env. Bot em modo espera.")
        return

    usar_polling = os.getenv("TELEGRAM_USE_POLLING", "true").lower() in ("true", "1", "yes")
    if not usar_polling:
        return

    with _polling_lock:
        if _polling_started:
            return
        _polling_started = True
        t = threading.Thread(target=_loop_polling_telegram, daemon=True)
        t.start()
        print(f"🤖 [Telegram] Bot @{obter_username_bot()} ativo em background (Long-Polling)!")

def obter_links_dashboard() -> dict:
    """
    Retorna os links de acesso ao Dashboard (Rede Local Wi-Fi, Localhost e Nuvem se houver).
    """
    porta = os.getenv("PORT", "5001").strip()
    url_publica = (os.getenv("APP_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip_rede = s.getsockname()[0]
    except Exception:
        ip_rede = "127.0.0.1"
    finally:
        s.close()

    link_rede = f"http://{ip_rede}:{porta}/pages/dashboard.html"
    link_pc = f"http://127.0.0.1:{porta}/pages/dashboard.html"
    link_nuvem = f"{url_publica}/pages/dashboard.html" if url_publica else None

    return {
        "rede": link_rede,
        "pc": link_pc,
        "nuvem": link_nuvem
    }