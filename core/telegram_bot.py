# Caminho: core/telegram_bot.py
import os
import re
import time
import threading
import requests
from dotenv import load_dotenv
from core.database import (
    obter_ou_vincular_usuario_telegram,
    iniciar_2fa_leitura_qrcode,
    verificar_pendencia_2fa_telegram,
    confirmar_codigo_2fa_telegram,
    salvar_mensagem_historico
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
        "text": str(texto),
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            # Se falhar por formatação Markdown, envia como texto puro
            payload.pop("parse_mode", None)
            res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"⚠️ [Telegram] Erro ao enviar mensagem: {e}")
        return False


def enviar_foto_telegram(chat_id: str, caminho_arquivo: str, legenda: str = "") -> bool:
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
            res = requests.post(url, data=dados, files={"photo": arquivo_img}, timeout=20)
        if res.status_code != 200 and "parse_mode" in dados:
            dados.pop("parse_mode", None)
            with open(caminho_arquivo, "rb") as arquivo_img:
                res = requests.post(url, data=dados, files={"photo": arquivo_img}, timeout=20)
        return res.status_code == 200
    except Exception as e:
        print(f"⚠️ [Telegram] Erro ao enviar imagem do gráfico: {e}")
        return False


def processar_update_telegram(update: dict) -> dict:
    """
    Fluxo completo do Bot no Telegram:
    1. /start <token_qr>: gera código 2FA de 6 dígitos e envia ao e-mail do dono da conta.
    2. Mensagem de 6 dígitos (ex: 123456): valida o código 2FA, vincula o chat_id e libera o uso.
    3. Mensagens financeiras ("saldo", "extrato", "gastei 50 no mercado"): processadas pela IA.
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

    # Comando rápido para consultar o próprio Chat ID
    if texto.lower() in ("/id", "/meuid", "meu id"):
        enviar_mensagem_telegram(
            chat_id,
            f"🆔 *Dados do seu Telegram:*\n"
            f"• *Chat ID:* `{chat_id}`\n"
            f"• *Username:* `@{username or 'não definido'}`"
        )
        return {"processado": True, "chat_id": chat_id}

    # 1. LEITURA DO QR CODE (/start <TOKEN>): envia o código 2FA por e-mail
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
                f"🔐 *Verificação de Dupla Autenticação (2FA)*\n\n"
                f"Você escaneou o QR Code da conta de *{inicio_2fa['nome']}*.\n"
                f"Enviamos um código de *6 dígitos* para o e-mail `{inicio_2fa['email_mascarado']}`.\n\n"
                f"👉 *Envie os 6 números aqui no chat para liberar o acesso:*"
            )
            enviar_mensagem_telegram(chat_id, msg_2fa)
            return {"processado": True, "chat_id": chat_id}

    # 2. SE O USUÁRIO ENVIOU UM CÓDIGO DE 6 DÍGITOS NO CHAT (ex: 482910), VALIDA O 2FA IMEDIATAMENTE
    apenas_digitos = re.sub(r"\D", "", texto)
    if len(apenas_digitos) == 6 and len(texto.strip()) <= 8:
        validacao = confirmar_codigo_2fa_telegram(chat_id, apenas_digitos, username=username)
        if validacao.get("sucesso"):
            usr = validacao["usuario"]
            enviar_mensagem_telegram(
                chat_id,
                f"✅ *Código 2FA confirmado com sucesso!*\n\n"
                f"Sua conta *{usr['nome']}* (`{usr['email']}`) está vinculada a este Telegram.\n\n"
                f"Você já pode enviar comandos normalmente:\n"
                f"• `saldo` ou `extrato`\n"
                f"• `gastei 50 no mercado`\n"
                f"• `salario dia 5 4000`\n"
                f"• `me manda o gráfico`"
            )
            return {"processado": True, "chat_id": chat_id}
        elif verificar_pendencia_2fa_telegram(chat_id):
            enviar_mensagem_telegram(chat_id, validacao.get("erro", "❌ Código 2FA incorreto."))
            return {"processado": True, "chat_id": chat_id}

    # 3. SE ESTÁ COM 2FA PENDENTE E AINDA NÃO ESTÁ VINCULADO, SOLICITA OS 6 DÍGITOS
    usuario = obter_ou_vincular_usuario_telegram(
        chat_id=chat_id,
        username=username,
        first_name=first_name
    )

    if verificar_pendencia_2fa_telegram(chat_id) and not usuario.get("autenticado"):
        enviar_mensagem_telegram(
            chat_id,
            "🔐 *Aguardando código 2FA:* Digite os *6 números* enviados para o seu e-mail para concluir o vínculo da conta."
        )
        return {"processado": True, "chat_id": chat_id}

    if not usuario.get("autenticado"):
        enviar_mensagem_telegram(
            chat_id,
            "🔒 *Este Telegram ainda não está vinculado a uma conta FinanceControl.*\n\n"
            "1. Vá na aba *Configurações* do painel Web.\n"
            "2. Clique em *Gerar QR Code (Telegram / Mobile)* e escaneie.\n"
            "3. Digite aqui no chat o código de *6 dígitos* enviado ao seu e-mail."
        )
        return {"processado": True, "chat_id": chat_id}

    if texto.startswith("/start"):
        enviar_mensagem_telegram(
            chat_id,
            f"👋 Olá, *{usuario['nome']}*! Seu Assistente Financeiro está ativo.\n"
            f"Envie seus gastos, receitas ou digite `saldo`, `extrato` ou `gráfico`."
        )
        return {"processado": True, "chat_id": chat_id}

    # 4. PROCESSAMENTO NORMAL DA MENSAGEM PELA IA E SINCRONIZAÇÃO COM O HISTÓRICO WEB
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

        if caminho_grafico:
            enviar_foto_telegram(
                chat_id=chat_id,
                caminho_arquivo=caminho_grafico,
                legenda="📊 *Gráfico atualizado das suas finanças*"
            )
    except Exception as e:
        print(f"⚠️ [Telegram IA] Erro ao processar mensagem '{texto}': {e}")
        enviar_mensagem_telegram(chat_id, "⚠️ Ocorreu um erro ao processar sua mensagem. Tente novamente.")

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