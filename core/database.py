# Caminho: core/database.py
import os
import re
import sqlite3
import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "historico_ia.db")


def formatar_telefone_e164(telefone: str) -> str:
    """
    Converte qualquer entrada de telefone para o padrão internacional E.164 (+55459XXXXXXXX).
    Retorna string vazia se o número for inválido.
    """
    if not telefone:
        return ""
    digitos = re.sub(r"\D", "", str(telefone))
    if not digitos:
        return ""
    # Se o usuário digitou apenas DDD + Número (10 ou 11 dígitos no Brasil), adiciona o DDI 55
    if len(digitos) in (10, 11) and not digitos.startswith("55"):
        digitos = "55" + digitos
    if len(digitos) < 12 or len(digitos) > 15:
        return ""
    return f"+{digitos}"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                telefone_whatsapp TEXT UNIQUE,
                numero_bot_whatsapp TEXT,
                consentimento_lgpd INTEGER DEFAULT 1,
                data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migração segura caso a coluna numero_bot_whatsapp não exista em bancos antigos
        cursor.execute("PRAGMA table_info(usuarios)")
        colunas = [col["name"] for col in cursor.fetchall()]
        if "numero_bot_whatsapp" not in colunas:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN numero_bot_whatsapp TEXT")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                tipo TEXT CHECK(tipo IN ('receita', 'despesa')) NOT NULL,
                valor REAL NOT NULL,
                categoria TEXT NOT NULL,
                descricao TEXT,
                moeda TEXT DEFAULT 'BRL' CHECK(moeda = 'BRL'),
                data_transacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historico_mensagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                remetente TEXT CHECK(remetente IN ('usuario', 'ia')) NOT NULL,
                mensagem TEXT NOT NULL,
                data_envio DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens_mobile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expira_em DATETIME NOT NULL,
                usado INTEGER DEFAULT 0,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def criar_usuario(nome: str, email: str, senha_plana: str, telefone_whatsapp: str = None) -> dict:
    email_limpo = email.strip().lower()
    telefone_e164 = formatar_telefone_e164(telefone_whatsapp) if telefone_whatsapp else None
    if telefone_whatsapp and not telefone_e164:
        return {"sucesso": False, "erro": "Formato de telefone inválido. Use DDI+DDD+Número (ex: +5545999999999)."}

    senha_hash = generate_password_hash(senha_plana, method="pbkdf2:sha256", salt_length=16)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usuarios (nome, email, senha_hash, telefone_whatsapp)
                VALUES (?, ?, ?, ?)
                """,
                (nome.strip(), email_limpo, senha_hash, telefone_e164)
            )
            conn.commit()
            return {"sucesso": True, "id": cursor.lastrowid}
    except sqlite3.IntegrityError:
        return {"sucesso": False, "erro": "E-mail ou WhatsApp já cadastrado."}


def autenticar_usuario(email: str, senha_plana: str) -> dict:
    email_limpo = email.strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email_limpo,))
        user = cursor.fetchone()

        if not user:
            return {"sucesso": False, "erro": "E-mail ou senha incorretos."}

        senha_armazenada = user["senha_hash"]
        if not senha_armazenada.startswith(("pbkdf2:", "scrypt:")):
            if senha_armazenada == senha_plana:
                novo_hash = generate_password_hash(senha_plana, method="pbkdf2:sha256", salt_length=16)
                cursor.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (novo_hash, user["id"]))
                conn.commit()
                return {"sucesso": True, "usuario": {"id": user["id"], "nome": user["nome"], "email": user["email"]}}
            return {"sucesso": False, "erro": "E-mail ou senha incorretos."}

        if check_password_hash(senha_armazenada, senha_plana):
            return {"sucesso": True, "usuario": {"id": user["id"], "nome": user["nome"], "email": user["email"]}}

        return {"sucesso": False, "erro": "E-mail ou senha incorretos."}


def obter_usuario_por_id(usuario_id: int) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, nome, email, telefone_whatsapp, numero_bot_whatsapp, data_criacao FROM usuarios WHERE id = ?",
            (usuario_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        dados = dict(row)
        bot_env = formatar_telefone_e164(os.getenv("WHATSAPP_BOT_NUMBER", ""))
        dados["numero_bot_efetivo"] = dados.get("numero_bot_whatsapp") or bot_env or ""
        return dados


def atualizar_configuracoes_usuario(usuario_id: int, nome: str, telefone_whatsapp: str = None, numero_bot_whatsapp: str = None) -> dict:
    tel_usuario_e164 = formatar_telefone_e164(telefone_whatsapp) if telefone_whatsapp else None
    if telefone_whatsapp and not tel_usuario_e164:
        return {"sucesso": False, "erro": "Seu telefone WhatsApp deve estar no formato E.164 (ex: +5545999999999)."}

    tel_bot_e164 = formatar_telefone_e164(numero_bot_whatsapp) if numero_bot_whatsapp else None
    if numero_bot_whatsapp and not tel_bot_e164:
        return {"sucesso": False, "erro": "O número do Bot WhatsApp deve estar no formato E.164 (ex: +5545999999999)."}

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE usuarios 
                SET nome = ?, telefone_whatsapp = ?, numero_bot_whatsapp = ?
                WHERE id = ?
                """,
                (nome.strip(), tel_usuario_e164, tel_bot_e164, usuario_id)
            )
            conn.commit()
            return {
                "sucesso": True,
                "telefone_whatsapp": tel_usuario_e164,
                "numero_bot_whatsapp": tel_bot_e164
            }
    except sqlite3.IntegrityError:
        return {"sucesso": False, "erro": "Este número de WhatsApp já está vinculado a outra conta."}


def gerar_token_mobile(usuario_id: int, minutos_validade: int = 10) -> dict:
    token = secrets.token_urlsafe(32)
    expira_em = (datetime.utcnow() + timedelta(minutes=minutos_validade)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tokens_mobile SET usado = 1 WHERE usuario_id = ? AND usado = 0", (usuario_id,))
        cursor.execute(
            "INSERT INTO tokens_mobile (usuario_id, token, expira_em, usado) VALUES (?, ?, ?, 0)",
            (usuario_id, token, expira_em)
        )
        conn.commit()
    return {"token": token, "validade_segundos": minutos_validade * 60}


def validar_e_consumir_token_mobile(token: str) -> dict:
    agora = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.id as token_id, t.usuario_id, t.expira_em, t.usado, u.nome, u.email
            FROM tokens_mobile t
            JOIN usuarios u ON u.id = t.usuario_id
            WHERE t.token = ?
            """,
            (token,)
        )
        row = cursor.fetchone()
        if not row:
            return {"sucesso": False, "erro": "QR Code inválido ou não encontrado."}
        if row["usado"] == 1:
            return {"sucesso": False, "erro": "Este QR Code já foi utilizado. Gere um novo no computador."}
        if row["expira_em"] < agora:
            return {"sucesso": False, "erro": "Este QR Code expirou. Gere um novo na aba Configurações."}

        cursor.execute("UPDATE tokens_mobile SET usado = 1 WHERE id = ?", (row["token_id"],))
        conn.commit()
        return {
            "sucesso": True,
            "usuario": {"id": row["usuario_id"], "nome": row["nome"], "email": row["email"]}
        }


def salvar_mensagem_historico(usuario_id: int, remetente: str, mensagem: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO historico_mensagens (usuario_id, remetente, mensagem) VALUES (?, ?, ?)",
            (usuario_id, remetente, mensagem)
        )
        conn.commit()


def listar_historico_mensagens(usuario_id: int, limite: int = 50) -> list:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, remetente, mensagem, data_envio
            FROM (
                SELECT id, remetente, mensagem, data_envio
                FROM historico_mensagens
                WHERE usuario_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) sub
            ORDER BY id ASC
            """,
            (usuario_id, limite)
        )
        return [dict(r) for r in cursor.fetchall()]


def obter_ou_criar_usuario_por_whatsapp(telefone: str, nome_perfil: str = "Usuário WhatsApp") -> dict:
    telefone_e164 = formatar_telefone_e164(telefone)
    if not telefone_e164:
        telefone_e164 = f"+{re.sub(r'\\D', '', str(telefone))}"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE telefone_whatsapp = ?", (telefone_e164,))
        user = cursor.fetchone()
        if user:
            return dict(user)

        apenas_digitos = re.sub(r"\D", "", telefone_e164)
        email_temp = f"{apenas_digitos}@whatsapp.local"
        senha_hash = generate_password_hash(apenas_digitos, method="pbkdf2:sha256")
        cursor.execute(
            """
            INSERT INTO usuarios (nome, email, senha_hash, telefone_whatsapp)
            VALUES (?, ?, ?, ?)
            """,
            (nome_perfil, email_temp, senha_hash, telefone_e164)
        )
        conn.commit()
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (cursor.lastrowid,))
        return dict(cursor.fetchone())


def registrar_transacao(usuario_id: int, tipo: str, valor: float, categoria: str, descricao: str = "", moeda: str = "BRL") -> dict:
    if moeda.upper() != "BRL":
        return {
            "sucesso": False,
            "erro": "Operação negada (RN04): O sistema utiliza exclusivamente o Real (BRL)."
        }
    if valor <= 0:
        return {"sucesso": False, "erro": "O valor da transação deve ser maior que zero."}

    tipo_formatado = tipo.lower().strip()
    if tipo_formatado not in ("receita", "despesa"):
        return {"sucesso": False, "erro": "Tipo inválido. Use 'receita' ou 'despesa'."}

    resumo_antes = obter_resumo_financeiro(usuario_id)
    alerta_risco = None

    # RN02: Alerta caso a despesa ultrapasse o saldo disponível
    if tipo_formatado == "despesa" and valor > resumo_antes["saldo"]:
        alerta_risco = (
            f"⚠️ Alerta de Risco (RN02): Esta despesa (R$ {valor:.2f}) ultrapassa seu saldo disponível "
            f"antes do lançamento (R$ {resumo_antes['saldo']:.2f})."
        )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO transacoes (usuario_id, tipo, valor, categoria, descricao, moeda)
            VALUES (?, ?, ?, ?, ?, 'BRL')
            """,
            (usuario_id, tipo_formatado, float(valor), categoria.strip().capitalize(), descricao.strip())
        )
        conn.commit()
        return {
            "sucesso": True,
            "id": cursor.lastrowid,
            "alerta": alerta_risco
        }


def obter_resumo_financeiro(usuario_id: int) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor ELSE 0 END), 0) AS total_receitas,
                COALESCE(SUM(CASE WHEN tipo = 'despesa' THEN valor ELSE 0 END), 0) AS total_despesas,
                COUNT(*) AS total_lancamentos
            FROM transacoes
            WHERE usuario_id = ?
            """,
            (usuario_id,)
        )
        row = cursor.fetchone()
        receitas = float(row["total_receitas"])
        despesas = float(row["total_despesas"])
        total_lancamentos = int(row["total_lancamentos"])

        cursor.execute(
            """
            SELECT categoria, SUM(valor) as total
            FROM transacoes
            WHERE usuario_id = ? AND tipo = 'despesa'
            GROUP BY categoria
            ORDER BY total DESC
            """,
            (usuario_id,)
        )
        por_categoria = [dict(r) for r in cursor.fetchall()]

        return {
            "total_receitas": receitas,
            "total_despesas": despesas,
            "saldo": receitas - despesas,
            "total_lancamentos": total_lancamentos,
            "despesas_por_categoria": por_categoria
        }


def listar_transacoes(usuario_id: int, limite: int = 50) -> list:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, tipo, valor, categoria, descricao, data_transacao
            FROM transacoes
            WHERE usuario_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (usuario_id, limite)
        )
        return [dict(r) for r in cursor.fetchall()]