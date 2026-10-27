# Caminho: main.py (copie também para web_app.py)
import os
import io
import re
import socket
import base64
import urllib.parse
from functools import wraps
import qrcode
from dotenv import load_dotenv
from flask import (
    Flask, request, jsonify, session, send_from_directory, redirect, Response
)

from core.database import (
    init_db,
    formatar_telefone_e164,
    criar_usuario,
    autenticar_usuario,
    obter_usuario_por_id,
    atualizar_configuracoes_usuario,
    gerar_token_mobile,
    validar_e_consumir_token_mobile,
    salvar_mensagem_historico,
    listar_historico_mensagens,
    obter_ou_criar_usuario_por_whatsapp,
    registrar_transacao,
    obter_resumo_financeiro,
    listar_transacoes
)
from core.ia import interpretar_mensagem_financeira
from core.whatsapp import (
    WHATSAPP_VERIFY_TOKEN,
    extrair_dados_webhook_meta,
    enviar_mensagem_whatsapp_meta
)

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "chave-secreta-tcc-financecontrol-2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

init_db()


def obter_ip_rede_local() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def login_obrigatorio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"sucesso": False, "erro": "Sessão expirada. Faça login novamente."}), 401
        return f(*args, **kwargs)
    return decorated_function


# ==================== ROTAS DE PÁGINAS WEB ====================

@app.route("/")
def index():
    if "user_id" in session:
        return redirect("/pages/dashboard.html")
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/pages/<path:filename>")
def serve_pages(filename):
    if "user_id" not in session:
        return redirect("/")
    return send_from_directory(os.path.join(WEB_DIR, "pages"), filename)


# ==================== ROTAS DE AUTENTICAÇÃO E PERFIL ====================

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    dados = request.get_json(silent=True) or {}
    nome = dados.get("nome", "")
    email = dados.get("email", "")
    senha = dados.get("senha", "")
    telefone = dados.get("telefone_whatsapp") or None

    if not nome or not email or len(senha) < 6:
        return jsonify({"sucesso": False, "erro": "Preencha todos os campos (senha mín. 6 caracteres)."}), 400

    resultado = criar_usuario(nome, email, senha, telefone)
    return jsonify(resultado), (201 if resultado["sucesso"] else 400)


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    dados = request.get_json(silent=True) or {}
    email = dados.get("email", "")
    senha = dados.get("senha", "")

    resultado = autenticar_usuario(email, senha)
    if resultado["sucesso"]:
        session.clear()
        session["user_id"] = resultado["usuario"]["id"]
        session["user_nome"] = resultado["usuario"]["nome"]
        session["user_email"] = resultado["usuario"]["email"]
        return jsonify(resultado), 200
    return jsonify(resultado), 401


@app.route("/api/auth/logout", methods=["POST", "GET"])
def api_logout():
    session.clear()
    if request.method == "GET":
        return redirect("/")
    return jsonify({"sucesso": True}), 200


@app.route("/api/auth/me", methods=["GET"])
@login_obrigatorio
def api_me():
    usuario = obter_usuario_por_id(session["user_id"])
    if not usuario:
        session.clear()
        return jsonify({"sucesso": False, "erro": "Usuário não encontrado."}), 404
    return jsonify({"sucesso": True, "usuario": usuario}), 200


@app.route("/api/usuario/configuracoes", methods=["PUT"])
@login_obrigatorio
def api_atualizar_config():
    dados = request.get_json(silent=True) or {}
    nome = dados.get("nome", "").strip()
    telefone_usuario = dados.get("telefone_whatsapp", "").strip()
    numero_bot = dados.get("numero_bot_whatsapp", "").strip()

    if not nome:
        return jsonify({"sucesso": False, "erro": "O nome não pode ficar vazio."}), 400

    res = atualizar_configuracoes_usuario(session["user_id"], nome, telefone_usuario, numero_bot)
    if res["sucesso"]:
        session["user_nome"] = nome
        return jsonify(res), 200
    return jsonify(res), 400


# ==================== LÓGICA DO QR CODE E E.164 ====================

@app.route("/api/qrcode/gerar", methods=["POST"])
@login_obrigatorio
def api_gerar_qrcode():
    usuario = obter_usuario_por_id(session["user_id"])
    dados_token = gerar_token_mobile(session["user_id"], minutos_validade=10)
    token = dados_token["token"]

    host_atual = request.host
    esquema = request.headers.get("X-Forwarded-Proto", request.scheme)

    if "127.0.0.1" in host_atual or "localhost" in host_atual:
        porta = host_atual.split(":")[1] if ":" in host_atual else "5001"
        ip_lan = obter_ip_rede_local()
        base_url = f"http://{ip_lan}:{porta}"
    else:
        base_url = f"{esquema}://{host_atual}"

    url_continuar_celular = f"{base_url}/api/auth/mobile-login?token={token}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url_continuar_celular)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # Obtém o número E.164 configurado pelo usuário ou no .env (sem hardcode estático)
    numero_e164 = (
        usuario.get("numero_bot_efetivo")
        or formatar_telefone_e164(os.getenv("WHATSAPP_BOT_NUMBER", ""))
        or usuario.get("telefone_whatsapp")
        or ""
    )
    digitos_wa = re.sub(r"\D", "", numero_e164)
    texto_wpp = f"Olá Assistente FinanceControl! Quero continuar minha gestão financeira (Sessão #{session['user_id']})."

    if digitos_wa:
        url_whatsapp = f"https://wa.me/{digitos_wa}?text={urllib.parse.quote(texto_wpp)}"
    else:
        url_whatsapp = ""

    return jsonify({
        "sucesso": True,
        "qr_code_base64": f"data:image/png;base64,{qr_base64}",
        "url_mobile": url_continuar_celular,
        "url_whatsapp": url_whatsapp,
        "numero_e164": numero_e164,
        "validade_segundos": dados_token["validade_segundos"],
        "ip_detectado": base_url
    }), 200


@app.route("/api/auth/mobile-login", methods=["GET"])
def api_mobile_login():
    token = request.args.get("token", "")
    resultado = validar_e_consumir_token_mobile(token)

    if not resultado["sucesso"]:
        html_erro = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>QR Code Inválido - FinanceControl</title>
            <style>
                body {{ background:#0f172a; color:#f8fafc; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; padding:20px; text-align:center; }}
                .box {{ background:#1e293b; padding:30px; border-radius:12px; max-width:380px; border:1px solid #ef4444; }}
                a {{ display:inline-block; margin-top:15px; padding:10px 20px; background:#3b82f6; color:#fff; text-decoration:none; border-radius:8px; font-weight:bold; }}
            </style>
        </head>
        <body>
            <div class="box">
                <h2>⚠️ Link Expirado ou Utilizado</h2>
                <p>{resultado['erro']}</p>
                <a href="/">Ir para Login</a>
            </div>
        </body>
        </html>
        """
        return Response(html_erro, status=400, mimetype="text/html")

    session.clear()
    session["user_id"] = resultado["usuario"]["id"]
    session["user_nome"] = resultado["usuario"]["nome"]
    session["user_email"] = resultado["usuario"]["email"]
    return redirect("/pages/assistente.html?origem=qrcode")


# ==================== ROTAS DE DASHBOARD, TRANSAÇÕES E CHAT IA ====================

@app.route("/api/dashboard/stats", methods=["GET"])
@app.route("/api/resumo", methods=["GET"])
@login_obrigatorio
def api_dashboard_stats():
    """Endpoint unificado em tempo real para alimentar os cards e gráficos do Dashboard."""
    resumo = obter_resumo_financeiro(session["user_id"])
    transacoes = listar_transacoes(session["user_id"], limite=40)
    return jsonify({
        "sucesso": True,
        "usuario": {
            "id": session["user_id"],
            "nome": session.get("user_nome", "Usuário"),
            "email": session.get("user_email", "")
        },
        "resumo": resumo,
        "transacoes": transacoes
    }), 200


@app.route("/api/transacoes", methods=["GET", "POST"])
@login_obrigatorio
def api_transacoes():
    if request.method == "GET":
        transacoes = listar_transacoes(session["user_id"], limite=50)
        resumo = obter_resumo_financeiro(session["user_id"])
        return jsonify({"sucesso": True, "transacoes": transacoes, "resumo": resumo}), 200

    dados = request.get_json(silent=True) or {}
    resultado = registrar_transacao(
        usuario_id=session["user_id"],
        tipo=dados.get("tipo", "despesa"),
        valor=float(dados.get("valor", 0)),
        categoria=dados.get("categoria", "Outros"),
        descricao=dados.get("descricao", ""),
        moeda=dados.get("moeda", "BRL")
    )
    resumo_atualizado = obter_resumo_financeiro(session["user_id"])
    resultado["resumo"] = resumo_atualizado
    return jsonify(resultado), (201 if resultado["sucesso"] else 400)


@app.route("/api/chat/historico", methods=["GET"])
@login_obrigatorio
def api_chat_historico():
    mensagens = listar_historico_mensagens(session["user_id"], limite=60)
    resumo = obter_resumo_financeiro(session["user_id"])
    return jsonify({
        "sucesso": True,
        "usuario_nome": session.get("user_nome", "Usuário"),
        "resumo": resumo,
        "historico": mensagens
    }), 200


@app.route("/api/chat", methods=["POST"])
@login_obrigatorio
def api_chat():
    dados = request.get_json(silent=True) or {}
    mensagem = dados.get("mensagem", "").strip()
    if not mensagem:
        return jsonify({"sucesso": False, "erro": "Mensagem vazia."}), 400

    user_id = session["user_id"]
    salvar_mensagem_historico(user_id, "usuario", mensagem)

    resposta_ia = interpretar_mensagem_financeira(user_id, mensagem)
    texto_resposta = resposta_ia.get("resposta", "Processado com sucesso.")
    salvar_mensagem_historico(user_id, "ia", texto_resposta)

    resumo_atualizado = obter_resumo_financeiro(user_id)
    return jsonify({
        "sucesso": True,
        **resposta_ia,
        "resumo": resumo_atualizado
    }), 200


# ==================== WEBHOOK CHATBOT WHATSAPP ====================

@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def webhook_whatsapp():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            return Response(challenge, status=200, mimetype="text/plain")
        return Response("Token de verificação inválido", status=403)

    if request.form and "Body" in request.form and "From" in request.form:
        telefone = request.form.get("From", "").replace("whatsapp:", "")
        texto = request.form.get("Body", "")
        nome = request.form.get("ProfileName", "Usuário WhatsApp")

        usuario = obter_ou_criar_usuario_por_whatsapp(telefone, nome)
        salvar_mensagem_historico(usuario["id"], "usuario", texto)
        resultado = interpretar_mensagem_financeira(usuario["id"], texto)
        salvar_mensagem_historico(usuario["id"], "ia", resultado["resposta"])

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{resultado['resposta']}</Message>
</Response>"""
        return Response(twiml, status=200, mimetype="application/xml")

    payload = request.get_json(silent=True) or {}
    dados_meta = extrair_dados_webhook_meta(payload)
    if dados_meta:
        usuario = obter_ou_criar_usuario_por_whatsapp(
            dados_meta["telefone"],
            dados_meta["nome"]
        )
        salvar_mensagem_historico(usuario["id"], "usuario", dados_meta["texto"])
        resultado = interpretar_mensagem_financeira(usuario["id"], dados_meta["texto"])
        salvar_mensagem_historico(usuario["id"], "ia", resultado["resposta"])
        enviar_mensagem_whatsapp_meta(dados_meta["telefone"], resultado["resposta"])

    return jsonify({"status": "recebido"}), 200


if __name__ == "__main__":
    porta = int(os.getenv("PORT", 5001))
    ip_rede = obter_ip_rede_local()
    print("=" * 65)
    print(f"🚀 SERVIDOR FINANCECONTROL RODANDO COM SUCESSO!")
    print(f"💻 Acesso no Computador: http://127.0.0.1:{porta}")
    print(f"📱 Acesso no Celular (Wi-Fi): http://{ip_rede}:{porta}")
    print("=" * 65)
    app.run(host="0.0.0.0", port=porta, debug=True)