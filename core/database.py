import os
import secrets
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, scoped_session
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Conexão padrão apontando para o MySQL Workbench local
# Substitua SUA_SENHA pela senha do seu MySQL Workbench (ou deixe vazio 'root:@127.0.0.1...' se não tiver)
DEFAULT_MYSQL_URL = "mysql+pymysql://root:1234@127.0.0.1:3306/finance_control"

raw_db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
elif raw_db_url.startswith("mysql://"):
    raw_db_url = raw_db_url.replace("mysql://", "mysql+pymysql://", 1)

DATABASE_URL = raw_db_url if raw_db_url else DEFAULT_MYSQL_URL

IS_SQLITE = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if IS_SQLITE else {"connect_timeout": 10}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=280
)

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


def get_db():
    """Retorna uma sessão ativa do banco de dados."""
    return SessionLocal()


# =====================================================================
# 1. INICIALIZAÇÃO E MIGRAÇÃO AUTOMÁTICA DE TABELAS
# =====================================================================
def init_db():
    pk_auto = "INTEGER PRIMARY KEY AUTOINCREMENT" if IS_SQLITE else "INT AUTO_INCREMENT PRIMARY KEY"
    ts_update = (
        "DATETIME DEFAULT CURRENT_TIMESTAMP"
        if IS_SQLITE
        else "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
    )

    queries_criacao = [
        # 1. Tabela de Usuários
        f"""
        CREATE TABLE IF NOT EXISTS usuarios (
            id {pk_auto},
            nome VARCHAR(100) NOT NULL DEFAULT 'Usuário',
            email VARCHAR(150) UNIQUE NOT NULL,
            senha_hash VARCHAR(255) NOT NULL,
            telegram_username VARCHAR(50) UNIQUE,
            telegram_id VARCHAR(50) UNIQUE,
            primeiro_login INT DEFAULT 1,
            status_2fa INT DEFAULT 0,
            codigo_2fa VARCHAR(10),
            expiracao_2fa DATETIME,
            token_recuperacao VARCHAR(255),
            expiracao_recuperacao DATETIME,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """,
        # 2. Transações
        f"""
        CREATE TABLE IF NOT EXISTS transacoes (
            id {pk_auto},
            usuario_id INT NOT NULL,
            descricao VARCHAR(255) NOT NULL,
            valor DECIMAL(10,2) NOT NULL,
            categoria VARCHAR(100) DEFAULT 'Outros',
            tipo VARCHAR(20) NOT NULL,
            data DATETIME DEFAULT CURRENT_TIMESTAMP,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """,
        # 3. Despesas Fixas (Gastos Fixos)
        f"""
        CREATE TABLE IF NOT EXISTS despesas_fixas (
            id {pk_auto},
            usuario_id INT NOT NULL,
            descricao VARCHAR(255) NOT NULL,
            valor DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            categoria VARCHAR(100) DEFAULT 'Fixas',
            dia_vencimento INT DEFAULT 1,
            ativo INT DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """,
        # 4. Receitas Fixas
        f"""
        CREATE TABLE IF NOT EXISTS receitas_fixas (
            id {pk_auto},
            usuario_id INT NOT NULL,
            descricao VARCHAR(255) NOT NULL,
            valor DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            dia_recebimento INT DEFAULT 1,
            ativo INT DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """,
        # 5. Limites de Orçamento
        f"""
        CREATE TABLE IF NOT EXISTS limites_orcamento (
            id {pk_auto},
            usuario_id INT NOT NULL,
            categoria VARCHAR(100) NOT NULL,
            valor_limite DECIMAL(10,2) NOT NULL,
            mes_ano VARCHAR(7),
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """,
        # 6. Conversas
        f"""
        CREATE TABLE IF NOT EXISTS conversas (
            id {pk_auto},
            usuario_id INT NOT NULL,
            titulo VARCHAR(150) DEFAULT 'Nova Conversa',
            status VARCHAR(50) DEFAULT 'ativa',
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """,
        # 7. Mensagens de Chat
        f"""
        CREATE TABLE IF NOT EXISTS mensagens_chat (
            id {pk_auto},
            conversa_id INT,
            usuario_id INT NOT NULL,
            remetente VARCHAR(50) NOT NULL,
            mensagem TEXT NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """,
        # 8. Histórico de Mensagens
        f"""
        CREATE TABLE IF NOT EXISTS historico_mensagens (
            id {pk_auto},
            usuario_id INT NOT NULL,
            mensagem TEXT,
            resposta TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """,
        # 9. Tokens Mobile
        f"""
        CREATE TABLE IF NOT EXISTS tokens_mobile (
            id {pk_auto},
            usuario_id INT NOT NULL,
            token VARCHAR(255) UNIQUE NOT NULL,
            expira_em DATETIME,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em {ts_update}
        )
        """
    ]

    with engine.begin() as conn:
        for sql in queries_criacao:
            conn.execute(text(sql))


def formatar_telegram(handle: str) -> str:
    if not handle:
        return ""
    limpo = handle.strip().lower()
    return limpo if limpo.startswith("@") else f"@{limpo}"


def montar_objeto_usuario(row) -> dict:
    nome_real = getattr(row, "nome", None)
    email_real = getattr(row, "email", "")
    tg_real = getattr(row, "telegram_username", "")

    if not nome_real or str(nome_real).strip().lower() in ("", "none", "usuário", "usuario"):
        if email_real and "@" in email_real:
            nome_real = email_real.split("@")[0].capitalize()
        elif tg_real:
            nome_real = tg_real.lstrip("@").capitalize()
        else:
            nome_real = "Usuário"

    return {
        "id": row.id,
        "nome": nome_real,
        "username": nome_real,
        "name": nome_real,
        "email": email_real,
        "telegram_username": tg_real,
        "primeiro_login": getattr(row, "primeiro_login", 0),
        "criado_em": str(getattr(row, "criado_em", "")),
        "atualizado_em": str(getattr(row, "atualizado_em", ""))
    }


# =====================================================================
# 2. FUNÇÕES DE AUTENTICAÇÃO E CADASTRO (TODAS AS EXIGIDAS PELO MAIN.PY)
# =====================================================================

def criar_usuario(nome: str, email: str, senha: str, telegram_username: str = "") -> dict:
    return registrar_usuario_hibrido(nome, email, senha, telegram_username)


def criar_usuario_com_telegram_obrigatorio(nome: str, email: str, senha: str, telegram_username: str) -> dict:
    if not telegram_username or not telegram_username.strip():
        return {"sucesso": False, "erro": "O @ do Telegram é obrigatório para o cadastro."}
    return registrar_usuario_hibrido(nome, email, senha, telegram_username)


def registrar_usuario_hibrido(nome: str, email: str, senha: str, telegram_username: str) -> dict:
    db = get_db()
    try:
        nome_limpo = (nome or "").strip()
        email_limpo = (email or "").strip().lower()
        tg_limpo = formatar_telegram(telegram_username)

        if not nome_limpo or not email_limpo or not senha:
            return {"sucesso": False, "erro": "Preencha nome, e-mail e senha."}

        existente = db.execute(
            text("""
                SELECT id FROM usuarios
                WHERE lower(email) = :email OR (:tg != '' AND lower(telegram_username) = :tg)
            """),
            {"email": email_limpo, "tg": tg_limpo}
        ).fetchone()

        if existente:
            return {"sucesso": False, "erro": "E-mail ou @Telegram já cadastrado no sistema."}

        senha_hash = generate_password_hash(senha)
        agora = datetime.now()

        db.execute(
            text("""
                INSERT INTO usuarios
                (nome, email, senha_hash, telegram_username, primeiro_login, status_2fa, criado_em, atualizado_em)
                VALUES (:nome, :email, :senha_hash, :tg, 1, 0, :agora, :agora)
            """),
            {
                "nome": nome_limpo,
                "email": email_limpo,
                "senha_hash": senha_hash,
                "tg": tg_limpo,
                "agora": agora
            }
        )
        db.commit()
        return {"sucesso": True, "mensagem": "Cadastro realizado com sucesso!"}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao cadastrar: {str(e)}"}
    finally:
        db.close()


def autenticar_usuario(email_ou_tg: str, senha: str):
    return iniciar_login_hibrido(email_ou_tg, senha)


def iniciar_login_hibrido(identificador: str, senha: str) -> dict:
    db = get_db()
    try:
        ident_limpo = (identificador or "").strip().lower()
        tg_busca = formatar_telegram(ident_limpo)

        user = db.execute(
            text("""
                SELECT id, nome, email, senha_hash, telegram_username, primeiro_login, criado_em, atualizado_em
                FROM usuarios
                WHERE lower(email) = :email OR lower(telegram_username) = :tg
            """),
            {"email": ident_limpo, "tg": tg_busca}
        ).fetchone()

        if not user or not check_password_hash(user.senha_hash, senha):
            return {"sucesso": False, "erro": "Credenciais inválidas."}

        dados_usuario = montar_objeto_usuario(user)

        if user.primeiro_login == 1:
            codigo = f"{secrets.randbelow(900000) + 100000}"
            expiracao = datetime.now() + timedelta(minutes=15)
            agora = datetime.now()

            db.execute(
                text("""
                    UPDATE usuarios
                    SET codigo_2fa = :codigo, expiracao_2fa = :exp, atualizado_em = :agora
                    WHERE id = :uid
                """),
                {"codigo": codigo, "exp": expiracao, "agora": agora, "uid": user.id}
            )
            db.commit()

            return {
                "sucesso": True,
                "requer_2fa": True,
                "email": user.email,
                "codigo_2fa_gerado": codigo,
                "usuario": dados_usuario
            }

        return {
            "sucesso": True,
            "requer_2fa": False,
            "usuario": dados_usuario,
            "user": dados_usuario
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro no login: {str(e)}"}
    finally:
        db.close()


def validar_codigo_2fa_banco(identificador_ou_email: str, codigo: str) -> dict:
    db = get_db()
    try:
        ident_limpo = (identificador_ou_email or "").strip().lower()
        tg_busca = formatar_telegram(ident_limpo)
        codigo_limpo = (codigo or "").strip()

        user = db.execute(
            text("""
                SELECT id, nome, email, telegram_username, codigo_2fa, expiracao_2fa, criado_em, atualizado_em
                FROM usuarios
                WHERE lower(email) = :email OR lower(telegram_username) = :tg
            """),
            {"email": ident_limpo, "tg": tg_busca}
        ).fetchone()

        if not user or not user.codigo_2fa or user.codigo_2fa != codigo_limpo:
            return {"sucesso": False, "erro": "Código 2FA inválido."}

        agora = datetime.now()
        db.execute(
            text("""
                UPDATE usuarios
                SET primeiro_login = 0, status_2fa = 1, codigo_2fa = NULL, expiracao_2fa = NULL, atualizado_em = :agora
                WHERE id = :uid
            """),
            {"agora": agora, "uid": user.id}
        )
        db.commit()

        dados_usuario = montar_objeto_usuario(user)
        return {"sucesso": True, "usuario": dados_usuario, "user": dados_usuario}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro 2FA: {str(e)}"}
    finally:
        db.close()


def obter_usuario_por_id(user_id: int) -> dict:
    db = get_db()
    try:
        user = db.execute(
            text("SELECT id, nome, email, telegram_username, primeiro_login, criado_em, atualizado_em FROM usuarios WHERE id = :uid"),
            {"uid": user_id}
        ).fetchone()
        if not user:
            return {"id": None, "nome": "Usuário", "username": "Usuário"}
        return montar_objeto_usuario(user)
    finally:
        db.close()


def atualizar_configuracoes_usuario(user_id: int, nome: str, telegram_username: str) -> dict:
    db = get_db()
    try:
        agora = datetime.now()
        db.execute(
            text("""
                UPDATE usuarios
                SET nome = :nome, telegram_username = :tg, atualizado_em = :agora
                WHERE id = :uid
            """),
            {"nome": nome, "tg": formatar_telegram(telegram_username), "agora": agora, "uid": user_id}
        )
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


# =====================================================================
# 3. RECUPERAÇÃO DE SENHA
# =====================================================================

def gerar_token_recuperacao_senha(email: str) -> dict:
    db = get_db()
    try:
        email_limpo = email.strip().lower()
        user = db.execute(text("SELECT id FROM usuarios WHERE lower(email) = :email"), {"email": email_limpo}).fetchone()
        if not user:
            return {"sucesso": False, "erro": "E-mail não encontrado."}

        token = secrets.token_urlsafe(32)
        expira = datetime.now() + timedelta(hours=1)
        agora = datetime.now()

        db.execute(
            text("""
                UPDATE usuarios
                SET token_recuperacao = :token, expiracao_recuperacao = :exp, atualizado_em = :agora
                WHERE id = :uid
            """),
            {"token": token, "exp": expira, "agora": agora, "uid": user.id}
        )
        db.commit()
        return {"sucesso": True, "token": token}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def redefinir_senha_com_token(token: str, nova_senha: str) -> dict:
    db = get_db()
    try:
        user = db.execute(
            text("SELECT id, expiracao_recuperacao FROM usuarios WHERE token_recuperacao = :token"),
            {"token": token}
        ).fetchone()

        if not user or (user.expiracao_recuperacao and datetime.now() > user.expiracao_recuperacao):
            return {"sucesso": False, "erro": "Token inválido ou expirado."}

        senha_hash = generate_password_hash(nova_senha)
        agora = datetime.now()

        db.execute(
            text("""
                UPDATE usuarios
                SET senha_hash = :hash, token_recuperacao = NULL, expiracao_recuperacao = NULL, atualizado_em = :agora
                WHERE id = :uid
            """),
            {"hash": senha_hash, "agora": agora, "uid": user.id}
        )
        db.commit()
        return {"sucesso": True, "mensagem": "Senha redefinida com sucesso!"}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


# =====================================================================
# 4. MÓDULO FINANCEIRO E HISTÓRICO DE MENSAGENS
# =====================================================================

def registrar_transacao(user_id: int, descricao: str, valor: float, tipo: str, categoria: str = "Outros") -> dict:
    db = get_db()
    try:
        agora = datetime.now()
        db.execute(
            text("""
                INSERT INTO transacoes (usuario_id, descricao, valor, tipo, categoria, data, criado_em, atualizado_em)
                VALUES (:uid, :desc, :val, :tipo, :cat, :agora, :agora, :agora)
            """),
            {"uid": user_id, "desc": descricao, "val": valor, "tipo": tipo, "cat": categoria, "agora": agora}
        )
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def listar_transacoes(user_id: int) -> list:
    db = get_db()
    try:
        res = db.execute(
            text("SELECT id, descricao, valor, tipo, categoria, data, criado_em FROM transacoes WHERE usuario_id = :uid ORDER BY data DESC"),
            {"uid": user_id}
        ).fetchall()
        return [dict(row._mapping) for row in res]
    finally:
        db.close()


def obter_resumo_financeiro(user_id: int) -> dict:
    trans = listar_transacoes(user_id)
    receitas = sum(t["valor"] for t in trans if t["tipo"].lower() in ("receita", "income"))
    despesas = sum(t["valor"] for t in trans if t["tipo"].lower() in ("despesa", "expense"))
    return {"receitas": receitas, "despesas": despesas, "saldo": receitas - despesas}


def criar_renda_fixa(user_id: int, descricao: str, valor: float, dia_recebimento: int) -> dict:
    db = get_db()
    try:
        agora = datetime.now()
        db.execute(
            text("""
                INSERT INTO receitas_fixas (usuario_id, descricao, valor, dia_recebimento, criado_em, atualizado_em)
                VALUES (:uid, :desc, :val, :dia, :agora, :agora)
            """),
            {"uid": user_id, "desc": descricao, "val": valor, "dia": dia_recebimento, "agora": agora}
        )
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def listar_rendas_fixas(user_id: int) -> list:
    db = get_db()
    try:
        res = db.execute(text("SELECT * FROM receitas_fixas WHERE usuario_id = :uid"), {"uid": user_id}).fetchall()
        return [dict(row._mapping) for row in res]
    finally:
        db.close()


def atualizar_renda_fixa(id_renda: int, user_id: int, descricao: str, valor: float, dia_recebimento: int) -> dict:
    db = get_db()
    try:
        agora = datetime.now()
        db.execute(
            text("UPDATE receitas_fixas SET descricao=:desc, valor=:val, dia_recebimento=:dia, atualizado_em=:agora WHERE id=:id AND usuario_id=:uid"),
            {"desc": descricao, "val": valor, "dia": dia_recebimento, "agora": agora, "id": id_renda, "uid": user_id}
        )
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def deletar_renda_fixa(id_renda: int, user_id: int) -> dict:
    db = get_db()
    try:
        db.execute(text("DELETE FROM receitas_fixas WHERE id=:id AND usuario_id=:uid"), {"id": id_renda, "uid": user_id})
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def criar_gasto_fixo(user_id: int, descricao: str, valor: float, dia_vencimento: int, categoria: str = "Fixas") -> dict:
    db = get_db()
    try:
        agora = datetime.now()
        db.execute(
            text("""
                INSERT INTO despesas_fixas (usuario_id, descricao, valor, dia_vencimento, categoria, criado_em, atualizado_em)
                VALUES (:uid, :desc, :val, :dia, :cat, :agora, :agora)
            """),
            {"uid": user_id, "desc": descricao, "val": valor, "dia": dia_vencimento, "cat": categoria, "agora": agora}
        )
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def listar_gastos_fixos(user_id: int) -> list:
    db = get_db()
    try:
        res = db.execute(text("SELECT * FROM despesas_fixas WHERE usuario_id = :uid"), {"uid": user_id}).fetchall()
        return [dict(row._mapping) for row in res]
    finally:
        db.close()


def atualizar_gasto_fixo(id_gasto: int, user_id: int, descricao: str, valor: float, dia_vencimento: int) -> dict:
    db = get_db()
    try:
        agora = datetime.now()
        db.execute(
            text("UPDATE despesas_fixas SET descricao=:desc, valor=:val, dia_vencimento=:dia, atualizado_em=:agora WHERE id=:id AND usuario_id=:uid"),
            {"desc": descricao, "val": valor, "dia": dia_vencimento, "agora": agora, "id": id_gasto, "uid": user_id}
        )
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def deletar_gasto_fixo(id_gasto: int, user_id: int) -> dict:
    db = get_db()
    try:
        db.execute(text("DELETE FROM despesas_fixas WHERE id=:id AND usuario_id=:uid"), {"id": id_gasto, "uid": user_id})
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def salvar_mensagem_historico(user_id: int, mensagem: str, resposta: str) -> dict:
    db = get_db()
    try:
        agora = datetime.now()
        db.execute(
            text("""
                INSERT INTO historico_mensagens (usuario_id, mensagem, resposta, criado_em, atualizado_em)
                VALUES (:uid, :msg, :resp, :agora, :agora)
            """),
            {"uid": user_id, "msg": mensagem, "resp": resposta, "agora": agora}
        )
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def listar_historico_mensagens(user_id: int) -> list:
    db = get_db()
    try:
        res = db.execute(
            text("SELECT mensagem, resposta, criado_em FROM historico_mensagens WHERE usuario_id = :uid ORDER BY criado_em DESC LIMIT 50"),
            {"uid": user_id}
        ).fetchall()
        return [dict(row._mapping) for row in res]
    finally:
        db.close()


def gerar_token_mobile(user_id: int) -> str:
    db = get_db()
    try:
        token = secrets.token_urlsafe(32)
        expira = datetime.now() + timedelta(days=30)
        agora = datetime.now()
        db.execute(
            text("INSERT INTO tokens_mobile (usuario_id, token, expira_em, criado_em, atualizado_em) VALUES (:uid, :token, :exp, :agora, :agora)"),
            {"uid": user_id, "token": token, "exp": expira, "agora": agora}
        )
        db.commit()
        return token
    except Exception:
        db.rollback()
        return ""
    finally:
        db.close()


def validar_e_consumir_token_mobile(token: str) -> int:
    db = get_db()
    try:
        res = db.execute(
            text("SELECT usuario_id, expira_em FROM tokens_mobile WHERE token = :token"),
            {"token": token}
        ).fetchone()
        if not res or (res.expira_em and datetime.now() > res.expira_em):
            return None
        return res.usuario_id
    finally:
        db.close()

def obter_ou_vincular_usuario_telegram(chat_id: str, username: str = None, first_name: str = "Usuário Telegram", token_vinculo: str = None) -> dict:
    """
    Localiza o usuário pelo telegram_chat_id, ou vincula via token (/start TOKEN),
    ou vincula pelo telegram_username, ou cria um perfil integrado automaticamente.
    """
    db = SessionLocal()
    try:
        chat_id_str = str(chat_id).strip()
        clean_username = username.strip().lstrip("@") if username else None

        # 1. Se enviou token via comando /start <token>, vincula diretamente à conta web
        if token_vinculo:
            reg_token = db.query(MobileToken).filter(
                MobileToken.token == token_vinculo,
                MobileToken.usado == False,
                MobileToken.expira_em >= datetime.utcnow()
            ).first()
            if reg_token:
                usuario_web = db.query(User).filter(User.id == reg_token.user_id).first()
                if usuario_web:
                    # Libera o chat_id caso estivesse em conta temporária
                    antigo = db.query(User).filter(User.telegram_chat_id == chat_id_str, User.id != usuario_web.id).first()
                    if antigo:
                        antigo.telegram_chat_id = None
                    usuario_web.telegram_chat_id = chat_id_str
                    if clean_username:
                        usuario_web.telegram_username = clean_username
                    reg_token.usado = True
                    db.commit()
                    return {"id": usuario_web.id, "nome": usuario_web.name, "email": usuario_web.email, "vinculado_agora": True}

        # 2. Busca direta por telegram_chat_id
        user = db.query(User).filter(User.telegram_chat_id == chat_id_str).first()
        if user:
            if clean_username and user.telegram_username != clean_username:
                user.telegram_username = clean_username
                db.commit()
            return {"id": user.id, "nome": user.name, "email": user.email, "vinculado_agora": False}

        # 3. Busca por telegram_username preenchido previamente na aba Configurações
        if clean_username:
            user_by_uname = db.query(User).filter(
                func.lower(User.telegram_username) == clean_username.lower()
            ).first()
            if user_by_uname:
                user_by_uname.telegram_chat_id = chat_id_str
                db.commit()
                return {"id": user_by_uname.id, "nome": user_by_uname.name, "email": user_by_uname.email, "vinculado_agora": True}

        # 4. Cria conta automática vinculada ao Telegram (RN03)
        email_temp = f"tg_{chat_id_str}@telegram.financecontrol.local"
        senha_hash = generate_password_hash(chat_id_str, method="pbkdf2:sha256")
        novo_user = User(
            name=first_name or "Usuário Telegram",
            email=email_temp,
            password_hash=senha_hash,
            telegram_chat_id=chat_id_str,
            telegram_username=clean_username
        )
        db.add(novo_user)
        db.commit()
        db.refresh(novo_user)
        return {"id": novo_user.id, "nome": novo_user.name, "email": novo_user.email, "vinculado_agora": False}
    finally:
        db.close()


# Inicializa o banco automaticamente ao importar
init_db()