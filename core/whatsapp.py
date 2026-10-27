# Caminho: core/whatsapp.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "tcc_assistente_token_2026")


def enviar_mensagem_whatsapp_meta(telefone_destino: str, texto_mensagem: str) -> bool:
    """Envia mensagem de texto via WhatsApp Cloud API Oficial (Meta)."""
    if not WHATSAPP_API_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        return False

    url = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": "".join(filter(str.isdigit, str(telefone_destino))),
        "type": "text",
        "text": {"body": texto_mensagem}
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        return response.status_code in (200, 201)
    except Exception:
        return False


def extrair_dados_webhook_meta(payload: dict) -> dict:
    """Extrai telefone, nome e texto do payload JSON da Meta Cloud API."""
    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return {}

        msg = messages[0]
        telefone = msg.get("from")
        texto = msg.get("text", {}).get("body", "")

        contacts = value.get("contacts", [{}])
        nome = contacts[0].get("profile", {}).get("name", "Usuário WhatsApp")

        if telefone and texto:
            return {"telefone": telefone, "nome": nome, "texto": texto}
    except (IndexError, KeyError, TypeError):
        pass
    return {}