# Caminho: web_app.py
import os
from functools import wraps
from flask import (
    Flask, request, jsonify, session, send_from_directory, redirect, Response
)
from dotenv import load_dotenv
from core.database import (
    init_db,
    criar_usuario,
    autenticar_usuario,
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
app.secret_key = os.getenv("FLASK_SECRET_KEY", "chave-secreta-trocar-em-producao-2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Inicializa as tabelas do banco ao subir a aplicação
init_db()


def login_obrigatorio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"sucesso": False, "erro": "Não autenticado."}), 401
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


# ==================== ROTAS DE AUTENTICAÇÃO ====================

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
    status_code = 201 if resultado["sucesso"] else 400
    return jsonify(resultado), status_code


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    dados = request.get_json(silent=True) or {}
    email = dados.get("email", "")
    senha = dados.get("senha", "")

    resultado = autenticar_usuario(email, senha)
    if resultado["sucesso"]:
        session["user_id"] = resultado["usuario"]["id"]
        session["user_nome"] = resultado["usuario"]["nome"]
        return jsonify(resultado), 200
    return jsonify(resultado), 401


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"sucesso": True}), 200


# ==================== ROTAS FINANCEIRAS E CHAT WEB ====================

@app.route("/api/resumo", methods=["GET"])
@login_obrigatorio
def api_resumo():
    resumo = obter_resumo_financeiro(session["user_id"])
    transacoes = listar_transacoes(session["user_id"], limite=30)
    return jsonify({
        "sucesso": True,
        "resumo": resumo,
        "transacoes": transacoes
    }), 200


@app.route("/api/transacoes", methods=["POST"])
@login_obrigatorio
def api_nova_transacao():
    dados = request.get_json(silent=True) or {}
    resultado = registrar_transacao(
        usuario_id=session["user_id"],
        tipo=dados.get("tipo", "despesa"),
        valor=float(dados.get("valor", 0)),
        categoria=dados.get("categoria", "Outros"),
        descricao=dados.get("descricao", ""),
        moeda=dados.get("moeda", "BRL")
    )
    status = 201 if resultado["sucesso"] else 400
    return jsonify(resultado), status


@app.route("/api/chat", methods=["POST"])
@login_obrigatorio
def api_chat():
    dados = request.get_json(silent=True) or {}
    mensagem = dados.get("mensagem", "")
    if not mensagem:
        return jsonify({"sucesso": False, "erro": "Mensagem vazia."}), 400

    resposta_ia = interpretar_mensagem_financeira(session["user_id"], mensagem)
    return jsonify({"sucesso": True, **resposta_ia}), 200


# ==================== WEBHOOK CHATBOT WHATSAPP ====================

@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def webhook_whatsapp():
    # 1. Verificação de Webhook exigida pela Meta (GET)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            return Response(challenge, status=200, mimetype="text/plain")
        return Response("Token de verificação inválido", status=403)

    # 2. Recebimento de Mensagens via Twilio (Form-UrlEncoded)
    if request.form and "Body" in request.form and "From" in request.form:
        telefone = request.form.get("From", "").replace("whatsapp:", "")
        texto = request.form.get("Body", "")
        nome = request.form.get("ProfileName", "Usuário WhatsApp")

        usuario = obter_ou_criar_usuario_por_whatsapp(telefone, nome)
        resultado = interpretar_mensagem_financeira(usuario["id"], texto)

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{resultado['resposta']}</Message>
</Response>"""
        return Response(twiml, status=200, mimetype="application/xml")

    # 3. Recebimento de Mensagens via Meta WhatsApp Cloud API (JSON)
    payload = request.get_json(silent=True) or {}
    dados_meta = extrair_dados_webhook_meta(payload)
    if dados_meta:
        usuario = obter_ou_criar_usuario_por_whatsapp(
            dados_meta["telefone"],
            dados_meta["nome"]
        )
        resultado = interpretar_mensagem_financeira(usuario["id"], dados_meta["texto"])
        enviar_mensagem_whatsapp_meta(dados_meta["telefone"], resultado["resposta"])

    return jsonify({"status": "recebido"}), 200


if __name__ == "__main__":
    porta = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)