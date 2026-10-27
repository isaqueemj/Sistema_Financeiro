# Caminho: core/database.py
import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "historico_ia.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        # Tabela de Usuários com senha em Hash e vínculo WhatsApp (RN03)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                telefone_whatsapp TEXT UNIQUE,
                consentimento_lgpd INTEGER DEFAULT 1,
                data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabela de Transações Financeiras (RF01, RF04, RN04)
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

        # Tabela de Limites de Orçamento por Categoria (RN02)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS limites_orcamento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                valor_limite REAL NOT NULL,
                UNIQUE(usuario_id, categoria),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
        """)

        # Tabela de Histórico de Conversas com a IA
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historico_mensagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                remetente TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                data_envio DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def criar_usuario(nome: str, email: str, senha_plana: str, telefone_whatsapp: str = None) -> dict:
    email_limpo = email.strip().lower()
    senha_hash = generate_password_hash(senha_plana, method="pbkdf2:sha256", salt_length=16)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usuarios (nome, email, senha_hash, telefone_whatsapp)
                VALUES (?, ?, ?, ?)
                """,
                (nome.strip(), email_limpo, senha_hash, telefone_whatsapp)
            )
            conn.commit()
            return {"sucesso": True, "id": cursor.lastrowid}
    except sqlite3.IntegrityError:
        return {"sucesso": False, "erro": "E-mail ou telefone já cadastrado."}


def autenticar_usuario(email: str, senha_plana: str) -> dict:
    email_limpo = email.strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email_limpo,))
        user = cursor.fetchone()

        if not user:
            return {"sucesso": False, "erro": "Credenciais inválidas."}

        senha_armazenada = user["senha_hash"]

        # Migração transparente caso exista usuário antigo com senha em texto puro no banco
        if not senha_armazenada.startswith(("pbkdf2:", "scrypt:")):
            if senha_armazenada == senha_plana:
                novo_hash = generate_password_hash(senha_plana, method="pbkdf2:sha256", salt_length=16)
                cursor.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (novo_hash, user["id"]))
                conn.commit()
                return {
                    "sucesso": True,
                    "usuario": {"id": user["id"], "nome": user["nome"], "email": user["email"]}
                }
            return {"sucesso": False, "erro": "Credenciais inválidas."}

        if check_password_hash(senha_armazenada, senha_plana):
            return {
                "sucesso": True,
                "usuario": {"id": user["id"], "nome": user["nome"], "email": user["email"]}
            }

        return {"sucesso": False, "erro": "Credenciais inválidas."}


def obter_ou_criar_usuario_por_whatsapp(telefone: str, nome_perfil: str = "Usuário WhatsApp") -> dict:
    telefone_limpo = "".join(filter(str.isdigit, str(telefone)))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE telefone_whatsapp = ?", (telefone_limpo,))
        user = cursor.fetchone()
        if user:
            return dict(user)

        email_temp = f"{telefone_limpo}@whatsapp.local"
        senha_hash = generate_password_hash(telefone_limpo, method="pbkdf2:sha256")
        cursor.execute(
            """
            INSERT INTO usuarios (nome, email, senha_hash, telefone_whatsapp)
            VALUES (?, ?, ?, ?)
            """,
            (nome_perfil, email_temp, senha_hash, telefone_limpo)
        )
        conn.commit()
        cursor.execute("SELECT * FROM usuarios WHERE id = ?", (cursor.lastrowid,))
        return dict(cursor.fetchone())


def registrar_transacao(usuario_id: int, tipo: str, valor: float, categoria: str, descricao: str = "", moeda: str = "BRL") -> dict:
    # RN04 e RF07: Restrição estrita à moeda Real (BRL)
    if moeda.upper() != "BRL":
        return {
            "sucesso": False,
            "erro": "Operação negada: O sistema utiliza exclusivamente o Real (BRL). Converta o valor para R$ antes de registrar."
        }
    if valor <= 0:
        return {"sucesso": False, "erro": "O valor da transação deve ser maior que zero."}

    tipo_formatado = tipo.lower().strip()
    if tipo_formatado not in ("receita", "despesa"):
        return {"sucesso": False, "erro": "Tipo inválido. Use 'receita' ou 'despesa'."}

    resumo_antes = obter_resumo_financeiro(usuario_id)
    alerta_risco = None

    # RN02: Alerta se despesa ultrapassar o saldo atual
    if tipo_formatado == "despesa" and valor > resumo_antes["saldo"]:
        alerta_risco = f"⚠️ Alerta de Risco: Esta despesa (R$ {valor:.2f}) ultrapassa seu saldo disponível (R$ {resumo_antes['saldo']:.2f})."

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
                COALESCE(SUM(CASE WHEN tipo = 'despesa' THEN valor ELSE 0 END), 0) AS total_despesas
            FROM transacoes
            WHERE usuario_id = ?
            """,
            (usuario_id,)
        )
        row = cursor.fetchone()
        receitas = float(row["total_receitas"])
        despesas = float(row["total_despesas"])

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
            ORDER BY data_transacao DESC
            LIMIT ?
            """,
            (usuario_id, limite)
        )
        return [dict(r) for r in cursor.fetchall()]