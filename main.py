# Caminho: main.py
import os
import io
import re
import socket
import random
import base64
import urllib.parse
from datetime import datetime, timedelta
from functools import wraps
import qrcode
from dotenv import load_dotenv
from flask import (
    Flask, request, jsonify, session, send_from_directory, redirect, Response
)
from sqlalchemy import text

from core.database import (
    init_db,
    SessionLocal,
    garantir_usuario_sincronizado,
    formatar_telefone_e164,
    criar_usuario_com_telegram_obrigatorio,
    iniciar_login_hibrido,
    validar_codigo_2fa_banco,
    gerar_token_recuperacao_senha,
    redefinir_senha_com_token,
    obter_usuario_por_id,
    atualizar_configuracoes_usuario,
    gerar_token_mobile,
    validar_e_consumir_token_mobile,
    salvar_mensagem_historico,
    listar_historico_mensagens,
    obter_ou_criar_usuario_por_whatsapp,
    registrar_transacao,
    listar_transacoes,
    excluir_transacao,
    criar_renda_fixa,
    atualizar_renda_fixa,
    listar_rendas_fixas,
    remover_renda_fixa,
    criar_gasto_fixo,
    atualizar_gasto_fixo,
    listar_gastos_fixos,
    remover_gasto_fixo,
    obter_resumo_financeiro,
    salvar_teto_gasto, 
    listar_tetos_gastos, 
    excluir_teto_gasto
)
from core.ia import interpretar_mensagem_financeira
from core.email_service import enviar_email_codigo_2fa, enviar_email_recuperacao_senha
from core.telegram_bot import iniciar_bot_telegram_background, obter_username_bot, processar_update_telegram, enviar_mensagem_telegram

from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "chave-secreta-tcc-financecontrol-2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False

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


def gerar_data_uri_qrcode(conteudo: str) -> str:
    """Gera a imagem PNG do QR Code em memória e retorna em formato data:image/png;base64."""
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
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def registrar_sessao_usuario(usuario: dict):
    session.clear()
    session.permanent = True
    uid = garantir_usuario_sincronizado(
        usuario.get("id"),
        nome=usuario.get("nome"),
        email=usuario.get("email")
    )
    nome = usuario.get("nome") or "Usuário"
    email = usuario.get("email") or ""

    session["user_id"] = uid
    session["usuario_id"] = uid
    session["user_nome"] = nome
    session["usuario_nome"] = nome
    session["user_email"] = email
    session["usuario_email"] = email
    session.modified = True


def login_obrigatorio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        uid = session.get("user_id") or session.get("usuario_id")
        if not uid:
            return jsonify({"sucesso": False, "erro": "Sessão expirada. Faça login novamente."}), 401
        uid_real = garantir_usuario_sincronizado(
            uid,
            nome=session.get("user_nome"),
            email=session.get("user_email")
        )
        session["user_id"] = uid_real
        session["usuario_id"] = uid_real
        return f(*args, **kwargs)
    return decorated_function


# ==================== ROTAS DE PÁGINAS WEB ====================

@app.route("/")
def index():
    if request.args.get("reset_token"):
        return send_from_directory(WEB_DIR, "index.html")
    if session.get("user_id") or session.get("usuario_id"):
        return redirect("/pages/dashboard.html")
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/pages/<path:filename>")
def serve_pages(filename):
    uid = session.get("user_id") or session.get("usuario_id")
    if not uid:
        return redirect("/")
    session["user_id"] = garantir_usuario_sincronizado(
        uid,
        nome=session.get("user_nome"),
        email=session.get("user_email")
    )
    return send_from_directory(os.path.join(WEB_DIR, "pages"), filename)


# ==================== ROTAS DE AUTENTICAÇÃO, 2FA E RECUPERAÇÃO ====================

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    email = (dados.get("email") or "").strip()
    telegram = (
        dados.get("telegram_username")
        or dados.get("telegram")
        or dados.get("arroba_telegram")
        or ""
    ).strip()
    telegram_id = (
        dados.get("telegram_id")
        or dados.get("telegram_chat_id")
        or ""
    ).strip()
    senha = dados.get("senha") or ""

    if not nome or not email or len(senha) < 6:
        return jsonify({
            "sucesso": False,
            "erro": "Preencha nome, e-mail, @Telegram e senha (mín. 6 caracteres)."
        }), 400

    resultado = criar_usuario_com_telegram_obrigatorio(
        nome=nome,
        email=email,
        senha_plana=senha,
        telegram=telegram,
        telegram_id=telegram_id
    )
    status_code = 201 if resultado.get("sucesso") else 400
    return jsonify(resultado), status_code


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    dados = request.get_json(silent=True) or {}
    identificador = (dados.get("identificador") or dados.get("email") or "").strip()
    senha = dados.get("senha") or ""

    resultado = iniciar_login_hibrido(identificador, senha)
    if not resultado.get("sucesso"):
        return jsonify(resultado), 401

    if resultado.get("requer_2fa"):
        email_destino = resultado.get("email_destino") or resultado.get("email") or identificador
        nome_usuario = resultado.get("nome") or "Usuário"
        codigo_2fa = resultado.get("codigo_gerado") or "000000"

        envio = enviar_email_codigo_2fa(
            destinatario=email_destino,
            nome=nome_usuario,
            codigo=codigo_2fa
        )
        return jsonify({
            "sucesso": True,
            "requer_2fa": True,
            "identificador": resultado.get("identificador") or email_destino,
            "email_mascarado": resultado.get("email_mascarado") or email_destino,
            "aviso_smtp": envio.get("aviso")
        }), 200

    usuario = resultado.get("usuario") or {}
    registrar_sessao_usuario(usuario)
    return jsonify({"sucesso": True, "usuario": usuario, "redirect": "/pages/dashboard.html"}), 200


@app.route("/api/auth/verificar-2fa", methods=["POST"])
def api_verificar_2fa():
    dados = request.get_json(silent=True) or {}
    identificador = (dados.get("identificador") or "").strip()
    codigo = (dados.get("codigo") or "").strip()

    resultado = validar_codigo_2fa_banco(identificador, codigo)
    if not resultado.get("sucesso"):
        return jsonify(resultado), 400

    usuario = resultado.get("usuario") or {}
    registrar_sessao_usuario(usuario)

    return jsonify({
        "sucesso": True,
        "usuario": usuario,
        "redirect": "/pages/dashboard.html"
    }), 200


@app.route("/api/auth/reenviar-2fa", methods=["POST"])
def api_reenviar_2fa():
    dados = request.get_json(silent=True) or {}
    identificador = (dados.get("identificador") or "").strip().lower()

    db = SessionLocal()
    try:
        user = db.execute(
            text("SELECT id, nome, email FROM usuarios WHERE lower(email) = :ident OR lower(telegram_username) = :ident"),
            {"ident": identificador}
        ).fetchone()
        if not user:
            return jsonify({"sucesso": False, "erro": "Usuário não encontrado."}), 404

        novo_codigo = f"{random.randint(100000, 999999)}"
        db.execute(
            text("UPDATE usuarios SET codigo_2fa = :cod, expiracao_2fa = :exp WHERE id = :uid"),
            {"cod": novo_codigo, "exp": datetime.utcnow() + timedelta(minutes=10), "uid": user.id}
        )
        db.commit()

        envio = enviar_email_codigo_2fa(user.email, user.nome, novo_codigo)
        return jsonify({"sucesso": True, "aviso_smtp": envio.get("aviso")}), 200
    finally:
        db.close()


@app.route("/api/auth/recuperar-senha", methods=["POST"])
def api_recuperar_senha():
    dados = request.get_json(silent=True) or {}
    email = (dados.get("email") or dados.get("identificador") or "").strip()

    if not email:
        return jsonify({"sucesso": False, "erro": "Informe o e-mail cadastrado."}), 400

    res = gerar_token_recuperacao_senha(email)
    if not res.get("sucesso"):
        return jsonify(res), 404

    email_destino = res.get("email_destino") or res.get("email") or email
    nome_usuario = res.get("nome") or "Usuário"
    base_url = request.host_url.rstrip("/")
    link_redefinicao = f"{base_url}/?reset_token={res['token']}"

    envio = enviar_email_recuperacao_senha(
        destinatario=email_destino,
        nome=nome_usuario,
        link_redefinicao=link_redefinicao
    )

    return jsonify({
        "sucesso": True,
        "mensagem": f"Link de alteração de senha enviado para {email_destino}!",
        "aviso_smtp": envio.get("aviso")
    }), 200


@app.route("/api/auth/redefinir-senha", methods=["POST"])
def api_redefinir_senha():
    dados = request.get_json(silent=True) or {}
    token = (dados.get("token") or "").strip()
    nova_senha = dados.get("nova_senha") or ""
    confirmar_senha = dados.get("confirmar_senha")

    if confirmar_senha is not None and nova_senha != confirmar_senha:
        return jsonify({"sucesso": False, "erro": "A confirmação de senha não confere."}), 400

    res = redefinir_senha_com_token(token, nova_senha)
    return jsonify(res), (200 if res.get("sucesso") else 400)


@app.route("/api/auth/logout", methods=["POST", "GET"])
def api_logout():
    session.clear()
    if request.method == "GET":
        return redirect("/")
    return jsonify({"sucesso": True}), 200


# ==================== PERFIL DO USUÁRIO (/api/me E /api/auth/me) ====================

@app.route("/api/me", methods=["GET"])
@app.route("/api/auth/me", methods=["GET"])
@login_obrigatorio
def api_me():
    usuario = obter_usuario_por_id(session["user_id"])
    if not usuario:
        return jsonify({"sucesso": False, "erro": "Usuário não encontrado."}), 404

    session["user_nome"] = usuario["nome"]
    session["usuario_nome"] = usuario["nome"]
    return jsonify({
        "sucesso": True,
        "usuario": usuario,
        **usuario
    }), 200


@app.route("/api/usuario/configuracoes", methods=["PUT", "POST"])
@app.route("/api/configuracoes", methods=["PUT", "POST"])
@login_obrigatorio
def api_atualizar_config():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or session.get("user_nome") or "Usuário").strip()
    telefone_usuario = (dados.get("telefone_whatsapp") or "").strip()
    numero_bot = (dados.get("numero_bot_whatsapp") or "").strip()
    telegram_username = (
        dados.get("telegram_username")
        or dados.get("telegram")
        or ""
    ).strip()
    telegram_id = (
        dados.get("telegram_id")
        or dados.get("telegram_chat_id")
        or ""
    ).strip()

    res = atualizar_configuracoes_usuario(
        usuario_id=session["user_id"],
        nome=nome,
        telefone_whatsapp=telefone_usuario,
        numero_bot_whatsapp=numero_bot,
        telegram_username=telegram_username,
        telegram_id=telegram_id
    )
    if res.get("sucesso"):
        session["user_nome"] = nome
        session["usuario_nome"] = nome
        return jsonify(res), 200
    return jsonify(res), 400


# ==================== QR CODE (TELEGRAM + MOBILE) ====================

@app.route("/api/qrcode/gerar", methods=["POST", "GET"])
@app.route("/api/qrcode", methods=["POST", "GET"])
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

    qr_telegram_b64 = gerar_data_uri_qrcode(url_telegram)
    qr_mobile_b64 = gerar_data_uri_qrcode(url_continuar_celular)

    return jsonify({
        "sucesso": True,
        "token": token,
        "qr_code_base64": qr_telegram_b64,
        "qr_code": qr_telegram_b64,
        "qr_code_telegram": qr_telegram_b64,
        "qr_code_mobile": qr_mobile_b64,
        "qr_code_web": qr_mobile_b64,
        "url_telegram": url_telegram,
        "link_telegram": url_telegram,
        "url_whatsapp": url_telegram,
        "url_mobile": url_continuar_celular,
        "link_mobile": url_continuar_celular,
        "url": url_telegram,
        "bot_username": f"@{bot_username}",
        "validade_segundos": dados_token["validade_segundos"],
        "ip_detectado": base_url
    }), 200


@app.route("/api/auth/mobile-login", methods=["GET", "POST"])
def api_mobile_login():
    """
    Quando o QR Code é lido pela câmera do celular:
    - GET: Gera e envia automaticamente o código 2FA de 6 dígitos para o e-mail cadastrado e exibe os 6 campos OTP.
    - POST: Valida o código 2FA de 6 dígitos, consome o token e abre a sessão no celular.
    """
    token = (request.args.get("token") or request.form.get("token") or "").strip()

    if request.method == "GET":
        inicio = iniciar_2fa_leitura_qrcode(token=token)
        if not inicio.get("sucesso"):
            html_erro = f"""
            <!DOCTYPE html>
            <html lang="pt-BR">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>QR Code Inválido - FinanceControl</title>
                <style>
                    body {{ background:#0b1320; color:#f8fafc; font-family:system-ui,sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; padding:20px; text-align:center; }}
                    .box {{ background:#152238; padding:28px; border-radius:14px; max-width:400px; width:100%; border:1px solid #ef4444; }}
                    a {{ display:inline-block; margin-top:16px; padding:10px 20px; background:#3b82f6; color:#fff; text-decoration:none; border-radius:8px; font-weight:600; }}
                </style>
            </head>
            <body>
                <div class="box">
                    <h2>⚠️ QR Code Inválido ou Expirado</h2>
                    <p style="color:#cbd5e1; margin-top:8px;">{inicio.get('erro')}</p>
                    <a href="/">Ir para o Login</a>
                </div>
            </body>
            </html>
            """
            return Response(html_erro, status=400, mimetype="text/html")

        # Dispara o código de 6 dígitos para o e-mail do titular da conta
        enviar_email_codigo_2fa(
            destinatario=inicio["email_destino"],
            nome=inicio["nome"],
            codigo=inicio["codigo_gerado"]
        )

        html_2fa = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Verificação 2FA - FinanceControl</title>
            <style>
                * {{ box-sizing: border-box; }}
                body {{ background:#0b1320; color:#f8fafc; font-family:system-ui,sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; padding:20px; }}
                .box {{ background:#152238; padding:28px; border-radius:16px; max-width:420px; width:100%; border:1px solid #3b82f6; box-shadow:0 10px 30px rgba(0,0,0,0.5); text-align:center; }}
                .badge {{ display:inline-block; background:rgba(59,130,246,0.18); color:#60a5fa; padding:5px 12px; border-radius:999px; font-size:0.78rem; font-weight:700; margin-bottom:12px; }}
                h2 {{ margin:0 0 8px; font-size:1.35rem; }}
                p {{ color:#94a3b8; font-size:0.9rem; line-height:1.45; margin-bottom:20px; }}
                .otp-row {{ display:flex; gap:8px; justify-content:center; margin-bottom:20px; }}
                .otp-box {{ width:46px; height:54px; text-align:center; font-size:1.35rem; font-weight:700; border-radius:10px; border:1px solid #334155; background:#0f172a; color:#fff; }}
                .otp-box:focus {{ outline:none; border-color:#3b82f6; box-shadow:0 0 0 3px rgba(59,130,246,0.25); }}
                button {{ width:100%; padding:13px; background:linear-gradient(135deg,#10b981,#059669); color:#fff; border:none; border-radius:10px; font-size:0.95rem; font-weight:700; cursor:pointer; }}
            </style>
        </head>
        <body>
            <div class="box">
                <span class="badge">🔐 Dupla Autenticação (2FA)</span>
                <h2>Confirme seu Acesso Mobile</h2>
                <p>Enviamos um código de 6 dígitos para o e-mail <strong>{inicio['email_mascarado']}</strong>. Digite-o abaixo para liberar o acesso:</p>
                <form method="POST" action="/api/auth/mobile-login" id="form-qr-2fa">
                    <input type="hidden" name="token" value="{token}">
                    <input type="hidden" name="codigo" id="codigo-final">
                    <div class="otp-row">
                        <input type="text" class="otp-box" maxlength="1" inputmode="numeric" pattern="[0-9]*" required autofocus>
                        <input type="text" class="otp-box" maxlength="1" inputmode="numeric" pattern="[0-9]*" required>
                        <input type="text" class="otp-box" maxlength="1" inputmode="numeric" pattern="[0-9]*" required>
                        <input type="text" class="otp-box" maxlength="1" inputmode="numeric" pattern="[0-9]*" required>
                        <input type="text" class="otp-box" maxlength="1" inputmode="numeric" pattern="[0-9]*" required>
                        <input type="text" class="otp-box" maxlength="1" inputmode="numeric" pattern="[0-9]*" required>
                    </div>
                    <button type="submit">VERIFICAR E ACESSAR</button>
                </form>
            </div>
            <script>
                const inputs = Array.from(document.querySelectorAll('.otp-box'));
                const hiddenCodigo = document.getElementById('codigo-final');
                const form = document.getElementById('form-qr-2fa');

                function atualizarHidden() {{
                    hiddenCodigo.value = inputs.map(i => i.value).join('');
                }}

                inputs.forEach((inp, idx) => {{
                    inp.addEventListener('input', (e) => {{
                        const nums = e.target.value.replace(/\\D/g, '');
                        if (nums.length > 1) {{
                            nums.slice(0, 6).split('').forEach((c, i) => {{ if (inputs[i]) inputs[i].value = c; }});
                            atualizarHidden();
                            inputs[Math.min(nums.length, 5)].focus();
                            return;
                        }}
                        e.target.value = nums;
                        atualizarHidden();
                        if (nums && idx < 5) inputs[idx + 1].focus();
                    }});
                    inp.addEventListener('keydown', (e) => {{
                        if (e.key === 'Backspace' && !inp.value && idx > 0) inputs[idx - 1].focus();
                    }});
                    inp.addEventListener('paste', (e) => {{
                        e.preventDefault();
                        const colado = (e.clipboardData || window.clipboardData).getData('text').replace(/\\D/g, '').slice(0, 6);
                        colado.split('').forEach((c, i) => {{ if (inputs[i]) inputs[i].value = c; }});
                        atualizarHidden();
                    }});
                }});

                form.addEventListener('submit', () => atualizarHidden());
            </script>
        </body>
        </html>
        """
        return Response(html_2fa, status=200, mimetype="text/html")

    # POST: Valida os 6 dígitos do código 2FA enviado
    codigo = request.form.get("codigo") or (request.get_json(silent=True) or {}).get("codigo") or ""
    resultado = validar_e_consumir_token_mobile(token=token, codigo_2fa=codigo)

    if not resultado.get("sucesso"):
        html_negado = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Código 2FA Inválido - FinanceControl</title>
            <style>
                body {{ background:#0b1320; color:#f8fafc; font-family:system-ui,sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; padding:20px; text-align:center; }}
                .box {{ background:#152238; padding:28px; border-radius:14px; max-width:400px; width:100%; border:1px solid #ef4444; }}
                a {{ display:inline-block; margin-top:16px; padding:10px 20px; background:#3b82f6; color:#fff; text-decoration:none; border-radius:8px; font-weight:600; }}
            </style>
        </head>
        <body>
            <div class="box">
                <h2>❌ Falha na Verificação 2FA</h2>
                <p style="color:#fca5a5;">{resultado.get('erro')}</p>
                <a href="/api/auth/mobile-login?token={token}">Tentar Novamente</a>
            </div>
        </body>
        </html>
        """
        return Response(html_negado, status=401, mimetype="text/html")

    registrar_sessao_usuario(resultado["usuario"])
    return redirect("/pages/assistente.html?origem=qrcode")

# ==================== ROTAS DE RECEITAS FIXAS E DESPESAS FIXAS ====================

@app.route("/api/rendas-fixas", methods=["GET", "POST"])
@app.route("/api/rendas_fixas", methods=["GET", "POST"])
@app.route("/api/receitas-fixas", methods=["GET", "POST"])
@login_obrigatorio
def api_rendas_fixas():
    user_id = session["user_id"]
    if request.method == "GET":
        itens = listar_rendas_fixas(user_id)
        total = sum(float(i["valor"]) for i in itens if i.get("is_active", True))
        return jsonify({
            "sucesso": True,
            "rendas_fixas": itens,
            "receitas_fixas": itens,
            "rendas": itens,
            "itens": itens,
            "data": itens,
            "total_mensal": total,
            "total_ativo": total,
            "total": total
        }), 200

    dados = request.get_json(silent=True) or {}
    descricao = (dados.get("description") or dados.get("descricao") or "").strip()
    valor_raw = dados.get("amount") if dados.get("amount") is not None else dados.get("valor", 0)
    dia_raw = dados.get("day_of_month") or dados.get("dia_recebimento") or dados.get("dia") or 5
    ativo_raw = dados.get("is_active") if dados.get("is_active") is not None else dados.get("ativo", True)
    if isinstance(ativo_raw, str):
        ativo_raw = ativo_raw.lower() in ("true", "1", "ativo", "ativa", "sim")

    try:
        valor = float(str(valor_raw).replace(",", "."))
        dia = int(dia_raw)
    except ValueError:
        return jsonify({"sucesso": False, "erro": "Valor ou dia inválido."}), 400

    if not descricao or valor <= 0:
        return jsonify({"sucesso": False, "erro": "Informe a descrição e um valor maior que zero."}), 400

    res = criar_renda_fixa(
        usuario_id=user_id,
        descricao=descricao,
        valor=valor,
        dia_recebimento=dia,
        ativo=bool(ativo_raw)
    )
    itens = listar_rendas_fixas(user_id)
    total = sum(float(i["valor"]) for i in itens if i.get("is_active", True))
    res["rendas_fixas"] = itens
    res["rendas"] = itens
    res["total_mensal"] = total
    res["total"] = total
    return jsonify(res), (201 if res.get("sucesso") else 400)


@app.route("/api/rendas-fixas/<int:renda_id>", methods=["PUT", "PATCH", "DELETE"])
@app.route("/api/rendas_fixas/<int:renda_id>", methods=["PUT", "PATCH", "DELETE"])
@app.route("/api/receitas-fixas/<int:renda_id>", methods=["PUT", "PATCH", "DELETE"])
@login_obrigatorio
def api_renda_fixa_item(renda_id: int):
    user_id = session["user_id"]
    if request.method == "DELETE":
        res = remover_renda_fixa(user_id, renda_id)
        return jsonify(res), (200 if res.get("sucesso") else 404)

    dados = request.get_json(silent=True) or {}
    descricao = dados.get("description") or dados.get("descricao")
    valor = dados.get("amount") if dados.get("amount") is not None else dados.get("valor")
    dia = dados.get("day_of_month") or dados.get("dia_recebimento") or dados.get("dia")
    is_active = dados.get("is_active") if dados.get("is_active") is not None else dados.get("ativo")
    if isinstance(is_active, str):
        is_active = is_active.lower() in ("true", "1", "ativo", "ativa", "sim")

    res = atualizar_renda_fixa(user_id, renda_id, descricao, valor, dia, is_active)
    return jsonify(res), (200 if res.get("sucesso") else 400)


@app.route("/api/gastos-fixos", methods=["GET", "POST"])
@app.route("/api/gastos_fixos", methods=["GET", "POST"])
@app.route("/api/despesas-fixas", methods=["GET", "POST"])
@login_obrigatorio
def api_gastos_fixos():
    user_id = session["user_id"]
    if request.method == "GET":
        itens = listar_gastos_fixos(user_id)
        total = sum(float(i["valor"]) for i in itens if i.get("is_active", True))
        return jsonify({
            "sucesso": True,
            "gastos_fixos": itens,
            "despesas_fixas": itens,
            "gastos": itens,
            "itens": itens,
            "data": itens,
            "total_mensal": total,
            "total_ativo": total,
            "total": total
        }), 200

    dados = request.get_json(silent=True) or {}
    descricao = (dados.get("description") or dados.get("descricao") or "").strip()
    categoria = (dados.get("category") or dados.get("categoria") or "Fixas").strip()
    valor_raw = dados.get("amount") if dados.get("amount") is not None else dados.get("valor", 0)
    dia_raw = dados.get("due_day") or dados.get("dia_vencimento") or dados.get("dia") or 10
    ativo_raw = dados.get("is_active") if dados.get("is_active") is not None else dados.get("ativo", True)
    if isinstance(ativo_raw, str):
        ativo_raw = ativo_raw.lower() in ("true", "1", "ativo", "ativa", "sim")

    try:
        valor = float(str(valor_raw).replace(",", "."))
        dia = int(dia_raw)
    except ValueError:
        return jsonify({"sucesso": False, "erro": "Valor ou dia de vencimento inválido."}), 400

    if not descricao or valor <= 0:
        return jsonify({"sucesso": False, "erro": "Informe a descrição e um valor maior que zero."}), 400

    res = criar_gasto_fixo(
        usuario_id=user_id,
        descricao=descricao,
        valor=valor,
        dia_vencimento=dia,
        ativo=bool(ativo_raw),
        categoria=categoria
    )
    itens = listar_gastos_fixos(user_id)
    total = sum(float(i["valor"]) for i in itens if i.get("is_active", True))
    res["gastos_fixos"] = itens
    res["gastos"] = itens
    res["total_mensal"] = total
    res["total"] = total
    return jsonify(res), (201 if res.get("sucesso") else 400)


@app.route("/api/gastos-fixos/<int:gasto_id>", methods=["PUT", "PATCH", "DELETE"])
@app.route("/api/gastos_fixos/<int:gasto_id>", methods=["PUT", "PATCH", "DELETE"])
@app.route("/api/despesas-fixas/<int:gasto_id>", methods=["PUT", "PATCH", "DELETE"])
@login_obrigatorio
def api_gasto_fixo_item(gasto_id: int):
    user_id = session["user_id"]
    if request.method == "DELETE":
        res = remover_gasto_fixo(user_id, gasto_id)
        return jsonify(res), (200 if res.get("sucesso") else 404)

    dados = request.get_json(silent=True) or {}
    descricao = dados.get("description") or dados.get("descricao")
    categoria = dados.get("category") or dados.get("categoria")
    valor = dados.get("amount") if dados.get("amount") is not None else dados.get("valor")
    dia = dados.get("due_day") or dados.get("dia_vencimento") or dados.get("dia")
    is_active = dados.get("is_active") if dados.get("is_active") is not None else dados.get("ativo")
    if isinstance(is_active, str):
        is_active = is_active.lower() in ("true", "1", "ativo", "ativa", "sim")

    res = atualizar_gasto_fixo(user_id, gasto_id, descricao, valor, dia, categoria, is_active)
    return jsonify(res), (200 if res.get("sucesso") else 400)


# ==================== ROTAS DE DASHBOARD, TRANSAÇÕES E CHAT IA ====================

@app.route("/api/dashboard/stats", methods=["GET"])
@app.route("/api/resumo", methods=["GET"])
@login_obrigatorio
def api_dashboard_stats():
    user_id = session["user_id"]
    periodo = request.args.get("periodo", "mes_atual")
    usuario = obter_usuario_por_id(user_id) or {}

    resumo = obter_resumo_financeiro(user_id, periodo=periodo)
    transacoes = listar_transacoes(user_id, limite=40)
    rendas_fixas = listar_rendas_fixas(user_id)
    gastos_fixos = listar_gastos_fixos(user_id)

    return jsonify({
        "sucesso": True,
        "usuario": {
            "id": user_id,
            "nome": usuario.get("nome") or session.get("user_nome", "Usuário"),
            "email": usuario.get("email") or session.get("user_email", "")
        },
        "resumo": resumo,
        "grafico_pizza": resumo.get("grafico_pizza"),
        "grafico_colunas": resumo.get("grafico_colunas"),
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
        return jsonify({"sucesso": True, "transacoes": transacoes, "resumo": resumo}), 200

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
    return jsonify(resultado), (201 if resultado.get("sucesso") else 400)


# @app.route("/api/transacoes/<int:transacao_id>", methods=["DELETE"])
# @login_obrigatorio
# def api_excluir_transacao(transacao_id: int):
#     res = excluir_transacao(session["user_id"], transacao_id)
#     return jsonify(res), (200 if res.get("sucesso") else 404)


@app.route("/api/chat/historico", methods=["GET"])
@login_obrigatorio
def api_chat_historico():
    user_id = session["user_id"]
    usuario = obter_usuario_por_id(user_id) or {}
    mensagens = listar_historico_mensagens(user_id, limite=60)
    resumo = obter_resumo_financeiro(user_id)
    return jsonify({
        "sucesso": True,
        "usuario_nome": usuario.get("nome") or session.get("user_nome", "Usuário"),
        "resumo": resumo,
        "historico": mensagens
    }), 200


@app.route("/api/chat", methods=["POST"])
@login_obrigatorio
def api_chat():
    dados = request.get_json(silent=True) or {}
    mensagem = (dados.get("mensagem") or "").strip()
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


@app.route("/pages/teto_gastos.html")
@login_obrigatorio
def pagina_teto_gastos():
    return send_from_directory("web/pages", "teto_gastos.html")


@app.route("/api/tetos", methods=["GET", "POST"])
@login_obrigatorio
def api_tetos_gastos():
    user_id = session["user_id"]
    if request.method == "GET":
        tetos = listar_tetos_gastos(user_id)
        resumo = obter_resumo_financeiro(user_id)
        return jsonify({
            "sucesso": True,
            "usuario": {
                "id": user_id,
                "nome": session.get("user_nome", "Usuário")
            },
            "tetos": tetos,
            "resumo": resumo
        }), 200

    dados = request.get_json(silent=True) or {}
    categoria = (dados.get("categoria") or "").strip()
    try:
        valor_teto = float(str(dados.get("valor_teto", 0)).replace(",", "."))
    except ValueError:
        return jsonify({"sucesso": False, "erro": "Informe um valor numérico válido."}), 400

    if not categoria or valor_teto <= 0:
        return jsonify({"sucesso": False, "erro": "Informe a categoria/item e um limite maior que zero."}), 400

    res = salvar_teto_gasto(user_id, categoria, valor_teto)
    res["tetos"] = listar_tetos_gastos(user_id)
    res["resumo"] = obter_resumo_financeiro(user_id)
    return jsonify(res), (200 if res.get("sucesso") else 400)


@app.route("/api/tetos/<item>", methods=["DELETE"])
@login_obrigatorio
def api_excluir_teto(item):
    user_id = session["user_id"]
    res = excluir_teto_gasto(user_id, item)
    res["tetos"] = listar_tetos_gastos(user_id)
    res["resumo"] = obter_resumo_financeiro(user_id)
    return jsonify(res), 200


@app.route("/api/transacoes/<int:transacao_id>", methods=["DELETE"])
@login_obrigatorio
def api_excluir_transacao(transacao_id):
    user_id = session["user_id"]
    res = excluir_transacao_por_termo_ou_id(user_id, transacao_id=transacao_id)
    res["resumo"] = obter_resumo_financeiro(user_id)
    return jsonify(res), (200 if res["sucesso"] else 404)
# ==================== WEBHOOKS TELEGRAM E WHATSAPP ====================

@app.route("/webhook/telegram", methods=["POST"])
def webhook_telegram():
    update = request.get_json(silent=True) or {}
    res = processar_update_telegram(update)
    return jsonify(res), 200

@app.route("/api/configuracoes/alterar-senha", methods=["POST"])
@login_obrigatorio
def api_alterar_senha_logado():
    user_id = session.get("user_id") or session.get("usuario_id")
    dados = request.get_json(silent=True) or {}
    
    senha_atual = (dados.get("senha_atual") or "").strip()
    nova_senha = (dados.get("nova_senha") or "").strip()
    confirmar_senha = (dados.get("confirmar_senha") or nova_senha).strip()

    if not senha_atual:
        return jsonify({"sucesso": False, "erro": "Digite sua senha atual."}), 400
    if len(nova_senha) < 6:
        return jsonify({"sucesso": False, "erro": "A nova senha deve ter no mínimo 6 dígitos."}), 400
    if nova_senha != confirmar_senha:
        return jsonify({"sucesso": False, "erro": "A confirmação de senha não coincide."}), 400

    db = SessionLocal()
    try:
        # Usando instrução SQL direta evita o erro "name 'Usuario' is not defined"
        user = db.execute(
            text("SELECT id, senha_hash FROM usuarios WHERE id = :uid"), 
            {"uid": user_id}
        ).fetchone()
        
        if not user:
            return jsonify({"sucesso": False, "erro": "Usuário não encontrado."}), 404

        hash_atual = user.senha_hash or ""
        
        # Validação segura da senha atual
        if hash_atual.startswith(("pbkdf2:", "scrypt:", "sha256")):
            senha_correta = check_password_hash(hash_atual, senha_atual)
        else:
            senha_correta = (hash_atual == senha_atual)

        if not senha_correta:
            return jsonify({"sucesso": False, "erro": "A senha atual informada está incorreta."}), 401

        # Gera e atualiza a nova senha
        novo_hash = generate_password_hash(nova_senha, method="pbkdf2:sha256", salt_length=16)
        db.execute(
            text("UPDATE usuarios SET senha_hash = :sh, atualizado_em = CURRENT_TIMESTAMP WHERE id = :uid"),
            {"sh": novo_hash, "uid": user_id}
        )
        db.commit()
        
        return jsonify({"sucesso": True, "mensagem": "Senha alterada com sucesso! 🔒"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"sucesso": False, "erro": f"Erro ao atualizar senha: {str(e)}"}), 500
    finally:
        db.close()


# =========================================================================
# 2. CORREÇÃO DO ERRO 404 (Rota de Perfil unificada para carregar/salvar)
# =========================================================================
@app.route("/api/configuracoes", methods=["GET", "POST", "PUT"])
@app.route("/api/auth/perfil", methods=["GET", "POST", "PUT"])
@login_obrigatorio
def api_configuracoes_perfil():
    user_id = session.get("user_id") or session.get("usuario_id")
    db = SessionLocal()
    
    try:
        # --- CARREGAR DADOS DO PERFIL (GET) ---
        if request.method == "GET":
            user = db.execute(
                text("""
                    SELECT id, nome, email, telegram_username, telegram_id, telegram_chat_id 
                    FROM usuarios WHERE id = :uid
                """),
                {"uid": user_id}
            ).fetchone()
            
            if not user:
                return jsonify({"sucesso": False, "erro": "Usuário não encontrado"}), 404
                
            tg_user = user.telegram_username or ""
            if tg_user and not tg_user.startswith("@"):
                tg_user = "@" + tg_user
                
            return jsonify({
                "sucesso": True,
                "usuario": {
                    "id": user.id,
                    "nome": user.nome,
                    "email": user.email,
                    "telegram_username": tg_user,
                    "telegram_chat_id": user.telegram_chat_id or user.telegram_id or ""
                }
            }), 200

        # --- ATUALIZAR DADOS DO PERFIL (POST/PUT) ---
        dados = request.get_json(silent=True) or {}
        nome = (dados.get("nome") or "").strip()
        telegram_username = (dados.get("telegram_username") or "").strip()
        telegram_chat_id = (dados.get("telegram_chat_id") or dados.get("chat_id") or dados.get("telegram_id") or "").strip()
        
        if telegram_username and not telegram_username.startswith(("@", "+")):
            telegram_username = "@" + telegram_username
            
        db.execute(
            text("""
                UPDATE usuarios 
                SET nome = :nome, 
                    telegram_username = :tg_user, 
                    telegram_id = :tg_id, 
                    telegram_chat_id = :tg_id,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = :uid
            """),
            {
                "nome": nome,
                "tg_user": telegram_username or None,
                "tg_id": telegram_chat_id or None,
                "uid": user_id
            }
        )
        db.commit()
        
        # Atualiza o nome armazenado no cache da sessão
        session["user_nome"] = nome
        session.modified = True
        
        return jsonify({"sucesso": True, "mensagem": "Configurações atualizadas com sucesso!"}), 200
        
    except Exception as e:
        db.rollback()
        return jsonify({"sucesso": False, "erro": str(e)}), 500
    finally:
        db.close()


@app.route("/api/configuracoes/alerta-teto", methods=["POST"])
@login_obrigatorio
def api_configurar_alerta_teto():
    user_id = session.get("user_id")
    dados = request.get_json(silent=True) or {}
    percentual = float(dados.get("percentual") or 80)
    chat_id = str(dados.get("chat_id") or "").strip()

    session["alerta_teto"] = int(percentual)
    alertas_ativos = []
    notificado_telegram = False

    try:
        from core.database import listar_tetos_gastos
        tetos = listar_tetos_gastos(user_id) or []
        for t in tetos:
            perc_atual = float(t.get("percentual") or 0)
            if perc_atual >= percentual:
                alertas_ativos.append({
                    "categoria": t.get("categoria"),
                    "percentual": perc_atual,
                    "gasto_atual": t.get("gasto_atual"),
                    "valor_teto": t.get("valor_teto")
                })

        if alertas_ativos and chat_id:
            linhas = [f"• *{a['categoria']}*: {a['percentual']:.1f}% consumido" for a in alertas_ativos]
            msg_alerta = (
                f"⚠️ *Alerta Preventivo de Teto ({int(percentual)}%)*\n\n"
                f"As seguintes categorias já atingiram ou ultrapassaram seu limite de alerta:\n"
                + "\n".join(linhas)
            )
            notificado_telegram = enviar_mensagem_telegram(chat_id, msg_alerta)
    except Exception:
        pass

    return jsonify({
        "sucesso": True,
        "percentual": int(percentual),
        "alertas_ativos": alertas_ativos,
        "notificado_telegram": notificado_telegram
    }), 200


if __name__ == "__main__":
    porta = int(os.getenv("PORT", 5001))
    ip_rede = obter_ip_rede_local()
    print("=" * 65)
    print("🚀 SERVIDOR FINANCECONTROL RODANDO COM SEGURANÇA LGPD (RNF06)!")
    print(f"💻 Acesso no Computador: http://127.0.0.1:{porta}")
    print(f"📱 Acesso no Celular (Wi-Fi): http://{ip_rede}:{porta}")
    print("=" * 65)
    app.run(host="0.0.0.0", port=porta, debug=True, use_reloader=False)