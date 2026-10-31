# Caminho: core/telegram_bot.py
import os
import time
import threading
import requests
from dotenv import load_dotenv
from core.database import (
    obter_ou_vincular_usuario_telegram,
    salvar_mensagem_historico
)
from core.ia import interpretar_mensagem_financeira

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "FinanceControlBot").strip().lstrip("@")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

_polling_started = False
_polling_lock = threading.Lock()


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
        "text": texto,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            # Fallback sem parse_mode caso haja algum caractere especial não escapado
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=10)
        return True
    except Exception:
        return False


def enviar_foto_telegram(chat_id: str, caminho_arquivo: str, legenda: str = "") -> bool:
    """
    Envia o arquivo de imagem (.png) do gráfico financeiro para o usuário no Telegram
    através do endpoint /sendPhoto da API oficial.
    """
    if not telegram_configurado():
        return False
    if not caminho_arquivo or not os.path.exists(caminho_arquivo):
        return False

    url = f"{TELEGRAM_API_BASE}/sendPhoto"
    dados = {"chat_id": str(chat_id)}
    if legenda:
        dados["caption"] = legenda
        dados["parse_mode"] = "Markdown"

    try:
        with open(caminho_arquivo, "rb") as arquivo_img:
            res = requests.post(
                url,
                data=dados,
                files={"photo": arquivo_img},
                timeout=20
            )
        if res.status_code != 200 and "parse_mode" in dados:
            dados.pop("parse_mode", None)
            with open(caminho_arquivo, "rb") as arquivo_img:
                res = requests.post(
                    url,
                    data=dados,
                    files={"photo": arquivo_img},
                    timeout=20
                )
        return res.status_code == 200
    except Exception as e:
        print(f"⚠️ [Telegram] Erro ao enviar imagem do gráfico: {e}")
        return False


def processar_update_telegram(update: dict) -> dict:
    """
    Processa qualquer mensagem recebida do Telegram (via Polling ou Webhook).
    Suporta /start <TOKEN> para vínculo automático de conta, /id, /saldo e linguagem natural (IA).
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

    # Tratamento do comando /start (com ou sem token de vínculo vindo do QR Code Web)
    token_vinculo = None
    if texto.startswith("/start"):
        partes = texto.split(maxsplit=1)
        if len(partes) > 1:
            token_vinculo = partes[1].strip()

    usuario = obter_ou_vincular_usuario_telegram(
        chat_id=chat_id,
        username=username,
        first_name=first_name,
        token_vinculo=token_vinculo
    )

    if texto.startswith("/start"):
        status_vinculo = (
            f"✅ *Sua conta Web ({usuario['email']}) foi vinculada com sucesso a este Telegram!*"
            if usuario.get("vinculado_agora")
            else f"👋 Olá, *{usuario['nome']}*! Seu Assistente Financeiro Inteligente está ativo."
        )
        boas_vindas = (
            f"{status_vinculo}\n"
            f"🆔 *Seu Chat ID:* `{chat_id}`\n\n"
            f"Você já pode conversar comigo naturalmente:\n"
            f"• _\"Cadastrar meu aluguel como gasto fixo no valor de R$ 1500 todo dia 10\"_\n"
            f"• _\"Meu salário é uma renda fixa de R$ 4000 todo dia 5\"_\n"
            f"• _\"Gastei 50 reais no supermercado\"_\n"
            f"• _\"Qual meu saldo atual?\"_ ou _\"Me manda o gráfico\"_"
        )
        enviar_mensagem_telegram(chat_id, boas_vindas)
        return {"processado": True, "chat_id": chat_id}

    if texto.lower() in ("/id", "/meuid", "meu id"):
        enviar_mensagem_telegram(
            chat_id,
            f"🆔 *Dados para vínculo no FinanceControl Web:*\n• *Telegram Chat ID:* `{chat_id}`\n• *Username:* `@{username or 'não definido'}`"
        )
        return {"processado": True, "chat_id": chat_id}

    # Salva mensagem do usuário no histórico compartilhado e aciona o motor de IA
    salvar_mensagem_historico(usuario["id"], "usuario", f"[Telegram] {texto}")
    resultado_ia = interpretar_mensagem_financeira(usuario["id"], texto)
    resposta_texto = resultado_ia.get("resposta", "Processado com sucesso.")
    salvar_mensagem_historico(usuario["id"], "ia", resposta_texto)

    # 1. Envia a resposta em texto (extrato agrupado, confirmação ou análise)
    enviar_mensagem_telegram(chat_id, resposta_texto)

    # 2. Se a IA gerou o arquivo do gráfico, envia a imagem para o usuário no Telegram
    caminho_grafico = resultado_ia.get("grafico_path")
    if caminho_grafico:
        enviar_foto_telegram(
            chat_id=chat_id,
            caminho_arquivo=caminho_grafico,
            legenda="📊 *Gráfico atualizado das suas finanças (Entradas vs. Saídas e Gastos por Categoria)*"
        )

    return {"processado": True, "chat_id": chat_id}


def _loop_polling_telegram():
    """Loop contínuo de Long-Polling para funcionamento imediato sem necessidade de Webhook externo."""
    try:
        requests.post(f"{TELEGRAM_API_BASE}/deleteWebhook", timeout=5)
    except Exception:
        pass

    offset = 0
    while True:
        try:
            resp = requests.get(
                f"{TELEGRAM_API_BASE}/getUpdates",
                params={"offset": offset, "timeout": 25},
                timeout=30
            )
            if resp.status_code == 200:
                dados = resp.json()
                if dados.get("ok"):
                    for upd in dados.get("result", []):
                        offset = upd["update_id"] + 1
                        processar_update_telegram(upd)
        except Exception:
            time.sleep(3)


def iniciar_bot_telegram_background():
    """Inicia a thread de escuta do Telegram caso TELEGRAM_BOT_TOKEN esteja configurado."""
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