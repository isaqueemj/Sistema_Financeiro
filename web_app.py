# Caminho: main.py (copie também para web_app.py)
import os
import io
import socket
import base64
from functools import wraps
import qrcode
from dotenv import load_dotenv
from flask import (
    Flask, request, jsonify, session, send_from_directory, redirect, Response
)

from core.database import (
    init_db,
    criar_usuario,
    autenticar_usuario,
    obter_usuario_por_id,
    atualizar_configuracoes_usuario,
    criar_renda_fixa,
    listar_rendas_fixas,
    atualizar_renda_fixa,
    deletar_renda_fixa,
    criar_gasto_fixo,
    listar_gastos_fixos,
    atualizar_gasto_fixo,
    deletar_gasto_fixo,
    gerar_token_mobile,
    validar_e_consumir_token_mobile,
    salvar_mensagem_historico,
    listar_historico_mensagens,
    registrar_transacao,
    obter_resumo_financeiro,
    listar_transacoes,
    
)
from core.ia import interpretar_mensagem_financeira
from core.telegram_bot import (
    iniciar_bot_telegram_background,
    processar_update_telegram,
    obter_username_bot,
    telegram_configurado
)

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "chave-secreta-tcc-financecontrol-2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Inicializa tabelas no PostgreSQL (Supabase) ou SQLite e inicia o Bot do Telegram
init_db()
iniciar_bot_telegram_background()


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


# ==================== ROTAS DE AUTENTICAÇÃO (SEM TELEFONE) ====================

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    dados = request.get_json(silent=True) or {}
    nome = dados.get("nome", "")
    email = dados.get("email", "")
    senha = dados.get("senha", "")
    telegram_username = dados.get("telegram_username") or None

    if not nome or not email or len(senha) < 6:
        return jsonify({"sucesso": False, "erro": "Preencha nome, e-mail e senha (mín. 6 caracteres)."}), 400

    resultado = criar_usuario(nome, email, senha, telegram_username)
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
    return jsonify({
        "sucesso": True,
        "usuario": usuario,
        "telegram_bot_username": obter_username_bot(),
        "telegram_ativo": telegram_configurado()
    }), 200


@app.route("/api/usuario/configuracoes", methods=["PUT"])
@login_obrigatorio
def api_atualizar_config():
    dados = request.get_json(silent=True) or {}
    nome = dados.get("nome", "").strip()
    telegram_username = dados.get("telegram_username", "").strip()
    telegram_chat_id = dados.get("telegram_chat_id", "").strip()

    if not nome:
        return jsonify({"sucesso": False, "erro": "O nome não pode ficar vazio."}), 400

    res = atualizar_configuracoes_usuario(session["user_id"], nome, telegram_username, telegram_chat_id)
    if res["sucesso"]:
        session["user_nome"] = nome
        return jsonify(res), 200
    return jsonify(res), 400


# ==================== ROTAS CRUD: RENDAS FIXAS ====================

@app.route("/api/rendas-fixas", methods=["GET", "POST"])
@login_obrigatorio
def api_rendas_fixas():
    user_id = session["user_id"]
    if request.method == "GET":
        itens = listar_rendas_fixas(user_id)
        resumo = obter_resumo_financeiro(user_id)
        return jsonify({"sucesso": True, "rendas_fixas": itens, "resumo": resumo}), 200

    dados = request.get_json(silent=True) or {}
    res = criar_renda_fixa(
        usuario_id=user_id,
        description=dados.get("description", ""),
        amount=float(dados.get("amount", 0)),
        day_of_month=int(dados.get("day_of_month", 5)),
        is_active=dados.get("is_active", True)
    )
    return jsonify(res), (201 if res["sucesso"] else 400)


@app.route("/api/rendas-fixas/<int:renda_id>", methods=["PUT", "DELETE"])
@login_obrigatorio
def api_renda_fixa_detalhe(renda_id):
    user_id = session["user_id"]
    if request.method == "DELETE":
        res = deletar_renda_fixa(user_id, renda_id)
        return jsonify(res), (200 if res["sucesso"] else 404)

    dados = request.get_json(silent=True) or {}
    res = atualizar_renda_fixa(
        usuario_id=user_id,
        renda_id=renda_id,
        description=dados.get("description", ""),
        amount=float(dados.get("amount", 0)),
        day_of_month=int(dados.get("day_of_month", 5)),
        is_active=dados.get("is_active", True)
    )
    return jsonify(res), (200 if res["sucesso"] else 400)


# ==================== ROTAS CRUD: GASTOS FIXOS ====================

@app.route("/api/gastos-fixos", methods=["GET", "POST"])
@login_obrigatorio
def api_gastos_fixos():
    user_id = session["user_id"]
    if request.method == "GET":
        itens = listar_gastos_fixos(user_id)
        resumo = obter_resumo_financeiro(user_id)
        return jsonify({"sucesso": True, "gastos_fixos": itens, "resumo": resumo}), 200

    dados = request.get_json(silent=True) or {}
    res = criar_gasto_fixo(
        usuario_id=user_id,
        description=dados.get("description", ""),
        amount=float(dados.get("amount", 0)),
        due_day=int(dados.get("due_day", 10)),
        is_active=dados.get("is_active", True)
    )
    return jsonify(res), (201 if res["sucesso"] else 400)


@app.route("/api/gastos-fixos/<int:gasto_id>", methods=["PUT", "DELETE"])
@login_obrigatorio
def api_gasto_fixo_detalhe(gasto_id):
    user_id = session["user_id"]
    if request.method == "DELETE":
        res = deletar_gasto_fixo(user_id, gasto_id)
        return jsonify(res), (200 if res["sucesso"] else 404)

    dados = request.get_json(silent=True) or {}
    res = atualizar_gasto_fixo(
        usuario_id=user_id,
        gasto_id=gasto_id,
        description=dados.get("description", ""),
        amount=float(dados.get("amount", 0)),
        due_day=int(dados.get("due_day", 10)),
        is_active=dados.get("is_active", True)
    )
    return jsonify(res), (200 if res["sucesso"] else 400)


# ==================== QR CODE (WEB MOBILE + DEEP LINK TELEGRAM) ====================

def _gerar_imagem_qr_base64(conteudo: str) -> str:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(conteudo)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"


@app.route("/api/qrcode/gerar", methods=["POST"])
@login_obrigatorio
def api_gerar_qrcode():
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
    bot_username = obter_username_bot()
    url_telegram = f"https://t.me/{bot_username}?start={token}"

    return jsonify({
        "sucesso": True,
        "qr_code_web_base64": _gerar_imagem_qr_base64(url_continuar_celular),
        "qr_code_telegram_base64": _gerar_imagem_qr_base64(url_telegram),
        "url_mobile": url_continuar_celular,
        "url_telegram": url_telegram,
        "bot_username": f"@{bot_username}",
        "validade_segundos": dados_token["validade_segundos"]
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
    """
    Rota principal do Dashboard: retorna Cards de Valores (Entradas, Saídas, Saldo),
    dados do Gráfico de Pizza (Categorias/Locais), dados do Gráfico de Colunas (Entradas vs Saídas)
    e lista unificada de movimentações.
    """
    user_id = session["user_id"]
    periodo = request.args.get("periodo", "mes_atual")

    resumo = obter_resumo_financeiro(user_id, periodo=periodo)
    transacoes = listar_transacoes(user_id, limite=40)
    rendas_fixas = listar_rendas_fixas(user_id)
    gastos_fixos = listar_gastos_fixos(user_id)

    return jsonify({
        "sucesso": True,
        "usuario": {
            "id": user_id,
            "nome": session.get("user_nome", "Usuário"),
            "email": session.get("user_email", "")
        },
        "resumo": resumo,
        "grafico_pizza": resumo["grafico_pizza"],
        "grafico_colunas": resumo["grafico_colunas"],
        "transacoes": transacoes,
        "rendas_fixas": rendas_fixas,
        "gastos_fixos": gastos_fixos
    }), 200


@app.route("/api/transacoes", methods=["GET", "POST"])
@login_obrigatorio
def api_transacoes():
    user_id = session["user_id"]
    if request.method == "GET":
        transacoes = listar_transacoes(user_id, limite=50)
        resumo = obter_resumo_financeiro(user_id, periodo="mes_atual")
        return jsonify({
            "sucesso": True,
            "transacoes": transacoes,
            "resumo": resumo
        }), 200

    dados = request.get_json(silent=True) or {}
    try:
        valor_num = float(str(dados.get("valor", 0)).replace(",", "."))
    except ValueError:
        return jsonify({"sucesso": False, "erro": "Valor numérico inválido."}), 400

    resultado = registrar_transacao(
        usuario_id=user_id,
        tipo=dados.get("tipo", "despesa"),
        valor=valor_num,
        categoria=dados.get("categoria", "Outros"),
        descricao=dados.get("descricao", ""),
        moeda=dados.get("moeda", "BRL")
    )
    resultado["resumo"] = obter_resumo_financeiro(user_id, periodo="mes_atual")
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

    return jsonify({
        "sucesso": True,
        **resposta_ia,
        "resumo": obter_resumo_financeiro(user_id)
    }), 200


# ==================== WEBHOOK DO TELEGRAM ====================

@app.route("/webhook/telegram", methods=["POST"])
def webhook_telegram():
    update = request.get_json(silent=True) or {}
    if update:
        processar_update_telegram(update)
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    porta = int(os.getenv("PORT", 5001))
    ip_rede = obter_ip_rede_local()
    print("=" * 65)
    print(f"🚀 SERVIDOR FINANCECONTROL (TELEGRAM + SQLALCHEMY) ATIVO!")
    print(f"💻 Acesso no Computador: http://127.0.0.1:{porta}")
    print(f"📱 Acesso no Celular (Wi-Fi): http://{ip_rede}:{porta}")
    print("=" * 65)
    app.run(host="0.0.0.0", port=porta, debug=True, use_reloader=False)