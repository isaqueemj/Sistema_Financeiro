# Caminho: core/database.py
import os
import re
import random
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, text, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SQLITE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'historico_ia.db')}"

# Lê e higieniza a URL do banco de dados (.env)
raw_db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
elif raw_db_url.startswith("mysql://"):
    raw_db_url = raw_db_url.replace("mysql://", "mysql+pymysql://", 1)

DATABASE_URL = raw_db_url if raw_db_url else DEFAULT_SQLITE_URL


def garantir_schema_mysql(url_conexao: str):
    """
    Se a URL for MySQL, conecta ao servidor MySQL Workbench e cria o banco (SCHEMA)
    automaticamente caso ele ainda não exista.
    """
    if not url_conexao.startswith("mysql"):
        return
    try:
        parsed = urlparse(url_conexao)
        nome_banco = (parsed.path or "").lstrip("/")
        if not nome_banco:
            return
        url_sem_banco = f"{parsed.scheme}://{parsed.netloc}/"
        temp_engine = create_engine(url_sem_banco, pool_pre_ping=True)
        with temp_engine.connect() as conn:
            conn.execute(
                text(f"CREATE DATABASE IF NOT EXISTS `{nome_banco}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            )
            conn.commit()
        temp_engine.dispose()
    except Exception as err:
        print(f"⚠️ Aviso ao verificar/criar schema no MySQL: {err}")


garantir_schema_mysql(DATABASE_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=280)

# Testa a conexão com o MySQL/PostgreSQL; se falhar, exibe o motivo e usa SQLite como fallback seguro
if not DATABASE_URL.startswith("sqlite"):
    try:
        with engine.connect() as _conn:
            _conn.execute(text("SELECT 1"))
        tipo_sgbd = "MySQL Workbench" if DATABASE_URL.startswith("mysql") else "PostgreSQL"
        print(f"✅ Conectado com sucesso ao banco de dados {tipo_sgbd}!")
    except Exception as _err:
        print(f"⚠️ Não foi possível conectar ao banco principal ({_err}). Usando SQLite local como fallback.")
        DATABASE_URL = DEFAULT_SQLITE_URL
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()


# =====================================================================
# MODELOS ORM (Compatíveis com MySQL 8.0, PostgreSQL e SQLite)
# =====================================================================

class User(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    senha_hash = Column(String(255), nullable=False)
    telegram_username = Column(String(64), unique=False, nullable=True, index=True)
    telegram_id = Column(String(64), unique=False, nullable=True, index=True)
    telegram_chat_id = Column(String(64), unique=False, nullable=True)
    telefone_whatsapp = Column(String(32), nullable=True)
    numero_bot_whatsapp = Column(String(32), nullable=True)
    primeiro_login = Column(Boolean, default=True, nullable=False)
    codigo_2fa = Column(String(10), nullable=True)
    expira_2fa = Column(DateTime, nullable=True)
    token_reset_senha = Column(String(128), nullable=True)
    expira_reset_senha = Column(DateTime, nullable=True)
    consentimento_lgpd = Column(Boolean, default=True)
    data_criacao = Column(DateTime, default=datetime.utcnow)


class FixedIncome(Base):
    __tablename__ = "fixed_incomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    day_of_month = Column(Integer, nullable=False, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FixedExpense(Base):
    __tablename__ = "fixed_expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, default="Moradia")
    amount = Column(Float, nullable=False)
    due_day = Column(Integer, nullable=False, default=10)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(String(20), nullable=False)  # 'receita' ou 'despesa'
    valor = Column(Float, nullable=False)
    categoria = Column(String(100), nullable=False)
    descricao = Column(String(255), nullable=True)
    moeda = Column(String(10), default="BRL", nullable=False)
    data_transacao = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    remetente = Column(String(20), nullable=False)  # 'usuario' ou 'ia'
    mensagem = Column(Text, nullable=False)
    data_envio = Column(DateTime, default=datetime.utcnow)


class MobileToken(Base):
    __tablename__ = "mobile_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(128), unique=True, nullable=False, index=True)
    expira_em = Column(DateTime, nullable=False)
    usado = Column(Boolean, default=False)


# =====================================================================
# INICIALIZAÇÃO E MIGRAÇÃO AUTOMÁTICA DE COLUNAS (MySQL / PG / SQLite)
# =====================================================================

def garantir_colunas_autenticacao_2fa():
    """
    Garante que todas as colunas novas existam na tabela 'usuarios' mesmo se a tabela
    já tiver sido criada anteriormente no MySQL Workbench, PostgreSQL ou SQLite.
    """
    url_str = str(engine.url)
    eh_postgres = url_str.startswith("postgresql")
    tipo_data = "TIMESTAMP NULL" if eh_postgres else "DATETIME NULL"
    default_bool = "TRUE" if eh_postgres else "1"

    comandos_migracao = [
        "ALTER TABLE usuarios ADD COLUMN telegram_username VARCHAR(64) NULL",
        "ALTER TABLE usuarios ADD COLUMN telegram_id VARCHAR(64) NULL",
        "ALTER TABLE usuarios ADD COLUMN telegram_chat_id VARCHAR(64) NULL",
        "ALTER TABLE usuarios ADD COLUMN telefone_whatsapp VARCHAR(32) NULL",
        "ALTER TABLE usuarios ADD COLUMN numero_bot_whatsapp VARCHAR(32) NULL",
        f"ALTER TABLE usuarios ADD COLUMN primeiro_login BOOLEAN DEFAULT {default_bool}",
        "ALTER TABLE usuarios ADD COLUMN codigo_2fa VARCHAR(10) NULL",
        f"ALTER TABLE usuarios ADD COLUMN expira_2fa {tipo_data}",
        "ALTER TABLE usuarios ADD COLUMN token_reset_senha VARCHAR(128) NULL",
        f"ALTER TABLE usuarios ADD COLUMN expira_reset_senha {tipo_data}",
        "ALTER TABLE fixed_expenses ADD COLUMN category VARCHAR(100) DEFAULT 'Moradia'"
    ]

    for cmd in comandos_migracao:
        try:
            with engine.begin() as conn:
                conn.execute(text(cmd))
        except Exception:
            # Ignora silenciosamente se a coluna já existir
            pass


def init_db():
    Base.metadata.create_all(bind=engine)
    garantir_colunas_autenticacao_2fa()


# =====================================================================
# FUNÇÕES AUXILIARES DE FORMATAÇÃO
# =====================================================================

def normalizar_username_telegram(telegram: str) -> str:
    limpo = (telegram or "").strip().lstrip("@").strip()
    return f"@{limpo.lower()}" if limpo else ""


def mascarar_email(email: str) -> str:
    if not email or "@" not in email:
        return email or ""
    usuario, dominio = email.split("@", 1)
    prefixo = usuario[:2] if len(usuario) > 2 else usuario[:1]
    return f"{prefixo}***@{dominio}"


def formatar_telefone_e164(telefone: str) -> str:
    if not telefone:
        return ""
    digitos = re.sub(r"\D", "", str(telefone))
    if not digitos:
        return ""
    if len(digitos) in (10, 11) and not digitos.startswith("55"):
        digitos = "55" + digitos
    if len(digitos) < 12 or len(digitos) > 15:
        return ""
    return f"+{digitos}"


# =====================================================================
# AUTENTICAÇÃO, CADASTRO COM @TELEGRAM OBRIGATÓRIO E 2FA
# =====================================================================

def criar_usuario_com_telegram_obrigatorio(
    nome: str,
    email: str,
    senha_plana: str,
    telegram: str,
    telegram_id: str = None
) -> dict:
    garantir_colunas_autenticacao_2fa()
    email_limpo = (email or "").strip().lower()
    telegram_limpo = normalizar_username_telegram(telegram)
    tg_id_limpo = (str(telegram_id).strip() if telegram_id else None) or None

    if not telegram_limpo:
        return {"sucesso": False, "erro": "O @Telegram é obrigatório para realizar o cadastro."}

    senha_hash = generate_password_hash(senha_plana, method="pbkdf2:sha256", salt_length=16)
    db = SessionLocal()
    try:
        existente = db.execute(
            text("""
                SELECT id FROM usuarios
                WHERE lower(email) = :email
                   OR lower(telegram_username) = :tg
                   OR lower(telegram_username) = :tg_sem
            """),
            {
                "email": email_limpo,
                "tg": telegram_limpo,
                "tg_sem": telegram_limpo.lstrip("@")
            }
        ).fetchone()

        if existente:
            return {"sucesso": False, "erro": "E-mail ou @Telegram já está vinculado a outra conta."}

        novo_usuario = User(
            nome=nome.strip(),
            email=email_limpo,
            senha_hash=senha_hash,
            telegram_username=telegram_limpo,
            telegram_id=tg_id_limpo,
            telegram_chat_id=tg_id_limpo,
            primeiro_login=True
        )
        db.add(novo_usuario)
        db.commit()
        db.refresh(novo_usuario)

        return {
            "sucesso": True,
            "id": novo_usuario.id,
            "telegram_username": novo_usuario.telegram_username,
            "telegram_id": novo_usuario.telegram_id
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao cadastrar usuário no banco: {e}"}
    finally:
        db.close()


def criar_usuario(nome: str, email: str, senha_plana: str, telefone_whatsapp: str = None, telegram: str = None) -> dict:
    tg = telegram or telefone_whatsapp or f"@{email.split('@')[0]}"
    return criar_usuario_com_telegram_obrigatorio(nome, email, senha_plana, tg)


def iniciar_login_hibrido(identificador: str, senha_plana: str) -> dict:
    garantir_colunas_autenticacao_2fa()
    ident_limpo = (identificador or "").strip()
    if not ident_limpo:
        return {"sucesso": False, "erro": "Informe seu E-mail ou @Telegram."}

    busca_tg_com = normalizar_username_telegram(ident_limpo)
    busca_tg_sem = busca_tg_com.lstrip("@")

    db = SessionLocal()
    try:
        user = db.execute(
            text("""
                SELECT id, nome, email, senha_hash, telegram_username, telegram_id, primeiro_login
                FROM usuarios
                WHERE lower(email) = :ident
                   OR lower(telegram_username) = :tg_com
                   OR lower(telegram_username) = :tg_sem
            """),
            {
                "ident": ident_limpo.lower(),
                "tg_com": busca_tg_com,
                "tg_sem": busca_tg_sem
            }
        ).fetchone()

        if not user:
            return {"sucesso": False, "erro": "Usuário não encontrado com este E-mail ou @Telegram."}

        if not check_password_hash(user.senha_hash, senha_plana):
            return {"sucesso": False, "erro": "Senha incorreta."}

        if user.primeiro_login is None or bool(user.primeiro_login) is True:
            codigo = f"{random.randint(100000, 999999)}"
            expira = datetime.utcnow() + timedelta(minutes=10)
            db.execute(
                text("UPDATE usuarios SET codigo_2fa = :cod, expira_2fa = :exp WHERE id = :uid"),
                {"cod": codigo, "exp": expira, "uid": user.id}
            )
            db.commit()
            return {
                "sucesso": True,
                "requer_2fa": True,
                "codigo_gerado": codigo,
                "email_destino": user.email,
                "email": user.email,
                "email_mascarado": mascarar_email(user.email),
                "nome": user.nome,
                "identificador": user.email
            }

        return {
            "sucesso": True,
            "requer_2fa": False,
            "usuario": {
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram": user.telegram_username,
                "telegram_id": user.telegram_id
            }
        }
    finally:
        db.close()


def autenticar_usuario(email: str, senha_plana: str) -> dict:
    return iniciar_login_hibrido(email, senha_plana)


def validar_codigo_2fa_banco(identificador: str, codigo: str) -> dict:
    garantir_colunas_autenticacao_2fa()
    ident_limpo = (identificador or "").strip().lower()
    busca_tg_com = normalizar_username_telegram(ident_limpo)
    codigo_limpo = (codigo or "").strip()

    db = SessionLocal()
    try:
        user = db.execute(
            text("""
                SELECT id, nome, email, telegram_username, telegram_id, codigo_2fa, expira_2fa
                FROM usuarios
                WHERE lower(email) = :ident OR lower(telegram_username) = :tg_com
            """),
            {"ident": ident_limpo, "tg_com": busca_tg_com}
        ).fetchone()

        if not user or not user.codigo_2fa:
            return {"sucesso": False, "erro": "Nenhuma verificação 2FA pendente para este usuário."}

        if str(user.codigo_2fa).strip() != codigo_limpo:
            return {"sucesso": False, "erro": "Código de verificação de 6 dígitos incorreto."}

        db.execute(
            text("UPDATE usuarios SET primeiro_login = :falso, codigo_2fa = NULL, expira_2fa = NULL WHERE id = :uid"),
            {"falso": False, "uid": user.id}
        )
        db.commit()

        return {
            "sucesso": True,
            "usuario": {
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram": user.telegram_username,
                "telegram_id": user.telegram_id
            }
        }
    finally:
        db.close()


def reenviar_codigo_2fa_banco(identificador: str) -> dict:
    garantir_colunas_autenticacao_2fa()
    ident_limpo = (identificador or "").strip().lower()
    busca_tg_com = normalizar_username_telegram(ident_limpo)

    db = SessionLocal()
    try:
        user = db.execute(
            text("""
                SELECT id, nome, email FROM usuarios
                WHERE lower(email) = :ident OR lower(telegram_username) = :tg_com
            """),
            {"ident": ident_limpo, "tg_com": busca_tg_com}
        ).fetchone()

        if not user:
            return {"sucesso": False, "erro": "Usuário não localizado."}

        codigo = f"{random.randint(100000, 999999)}"
        expira = datetime.utcnow() + timedelta(minutes=10)
        db.execute(
            text("UPDATE usuarios SET codigo_2fa = :cod, expira_2fa = :exp WHERE id = :uid"),
            {"cod": codigo, "exp": expira, "uid": user.id}
        )
        db.commit()
        return {
            "sucesso": True,
            "codigo_gerado": codigo,
            "email_destino": user.email,
            "email_mascarado": mascarar_email(user.email),
            "nome": user.nome
        }
    finally:
        db.close()


def gerar_token_recuperacao_senha(identificador: str) -> dict:
    garantir_colunas_autenticacao_2fa()
    ident_limpo = (identificador or "").strip().lower()
    busca_tg_com = normalizar_username_telegram(ident_limpo)

    db = SessionLocal()
    try:
        user = db.execute(
            text("""
                SELECT id, nome, email FROM usuarios
                WHERE lower(email) = :ident OR lower(telegram_username) = :tg_com
            """),
            {"ident": ident_limpo, "tg_com": busca_tg_com}
        ).fetchone()

        if not user:
            return {"sucesso": False, "erro": "Nenhuma conta encontrada com este E-mail ou @Telegram."}

        # Gera um token seguro de URL para o link de redefinição
        token = secrets.token_urlsafe(24)
        expira = datetime.utcnow() + timedelta(minutes=15)
        db.execute(
            text("UPDATE usuarios SET token_reset_senha = :tok, expira_reset_senha = :exp WHERE id = :uid"),
            {"tok": token, "exp": expira, "uid": user.id}
        )
        db.commit()
        return {
            "sucesso": True,
            "token": token,
            "email": user.email,
            "email_destino": user.email,
            "email_mascarado": mascarar_email(user.email),
            "nome": user.nome
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao gerar link de recuperação: {e}"}
    finally:
        db.close()


def redefinir_senha_com_token(token_ou_identificador: str, nova_senha: str, nova_senha_opcional: str = None) -> dict:
    """
    Suporta tanto a chamada com 2 argumentos (token, nova_senha) vinda do link do e-mail
    quanto a chamada antiga com 3 argumentos (identificador, token, nova_senha).
    """
    garantir_colunas_autenticacao_2fa()

    if nova_senha_opcional is not None:
        token_limpo = (nova_senha or "").strip()
        senha_final = nova_senha_opcional
    else:
        token_limpo = (token_ou_identificador or "").strip()
        senha_final = nova_senha

    if not token_limpo:
        return {"sucesso": False, "erro": "Token de recuperação ausente ou inválido."}

    if not senha_final or len(senha_final) < 6:
        return {"sucesso": False, "erro": "A nova senha deve ter no mínimo 6 caracteres."}

    db = SessionLocal()
    try:
        user = db.execute(
            text("SELECT id, expira_reset_senha FROM usuarios WHERE token_reset_senha = :tok"),
            {"tok": token_limpo}
        ).fetchone()

        if not user:
            return {"sucesso": False, "erro": "Link de recuperação inválido ou já utilizado."}

        novo_hash = generate_password_hash(senha_final, method="pbkdf2:sha256", salt_length=16)
        db.execute(
            text("""
                UPDATE usuarios
                SET senha_hash = :sh, token_reset_senha = NULL, expira_reset_senha = NULL
                WHERE id = :uid
            """),
            {"sh": novo_hash, "uid": user.id}
        )
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao salvar nova senha: {e}"}
    finally:
        db.close()


# =====================================================================
# VÍNCULO AUTOMÁTICO DO BOT DO TELEGRAM (GRAVA telegram_username E telegram_id)
# =====================================================================

def obter_ou_vincular_usuario_telegram(
    chat_id: str,
    username: str = "",
    first_name: str = "Usuário Telegram",
    token_vinculo: str = None
) -> dict:
    garantir_colunas_autenticacao_2fa()
    chat_id_str = str(chat_id).strip()
    user_com_arroba = normalizar_username_telegram(username)
    user_sem_arroba = user_com_arroba.lstrip("@")

    db = SessionLocal()
    try:
        # 1. Busca pelo telegram_id ou telegram_chat_id já vinculado
        user = db.execute(
            text("""
                SELECT id, nome, email, telegram_username, telegram_id
                FROM usuarios
                WHERE telegram_id = :cid OR telegram_chat_id = :cid
            """),
            {"cid": chat_id_str}
        ).fetchone()

        if user:
            if user_com_arroba and user.telegram_username != user_com_arroba:
                db.execute(
                    text("UPDATE usuarios SET telegram_username = :tg WHERE id = :uid"),
                    {"tg": user_com_arroba, "uid": user.id}
                )
                db.commit()
            return {
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram_username": user.telegram_username or user_com_arroba,
                "telegram_id": chat_id_str,
                "vinculado_agora": False
            }

        # 2. Busca pelo @telegram_username cadastrado na Web e grava o telegram_id no MySQL
        if user_com_arroba:
            user = db.execute(
                text("""
                    SELECT id, nome, email, telegram_username
                    FROM usuarios
                    WHERE lower(telegram_username) = :tg_com
                       OR lower(telegram_username) = :tg_sem
                """),
                {"tg_com": user_com_arroba, "tg_sem": user_sem_arroba}
            ).fetchone()

            if user:
                db.execute(
                    text("""
                        UPDATE usuarios
                        SET telegram_id = :cid,
                            telegram_chat_id = :cid,
                            telegram_username = :tg_com
                        WHERE id = :uid
                    """),
                    {"cid": chat_id_str, "tg_com": user_com_arroba, "uid": user.id}
                )
                db.commit()
                return {
                    "id": user.id,
                    "nome": user.nome,
                    "email": user.email,
                    "telegram_username": user_com_arroba,
                    "telegram_id": chat_id_str,
                    "vinculado_agora": True
                }

        # 3. Fallback: cria usuário se iniciou conversa direto no Bot
        email_temp = f"{chat_id_str}@telegram.local"
        senha_hash = generate_password_hash(chat_id_str, method="pbkdf2:sha256")
        novo = User(
            nome=first_name,
            email=email_temp,
            senha_hash=senha_hash,
            telegram_username=user_com_arroba or None,
            telegram_id=chat_id_str,
            telegram_chat_id=chat_id_str,
            primeiro_login=False
        )
        db.add(novo)
        db.commit()
        db.refresh(novo)
        return {
            "id": novo.id,
            "nome": novo.nome,
            "email": novo.email,
            "telegram_username": novo.telegram_username,
            "telegram_id": chat_id_str,
            "vinculado_agora": True
        }
    finally:
        db.close()


def obter_usuario_por_id(usuario_id: int) -> dict:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == usuario_id).first()
        if not user:
            return None
        return {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "telegram_username": user.telegram_username or "",
            "telegram_id": user.telegram_id or user.telegram_chat_id or "",
            "telefone_whatsapp": user.telefone_whatsapp or "",
            "numero_bot_whatsapp": user.numero_bot_whatsapp or "",
            "data_criacao": user.data_criacao.strftime("%Y-%m-%d %H:%M:%S") if user.data_criacao else ""
        }
    finally:
        db.close()


def atualizar_configuracoes_usuario(
    usuario_id: int,
    nome: str,
    telefone_whatsapp: str = None,
    numero_bot_whatsapp: str = None,
    telegram_username: str = None,
    telegram_id: str = None
) -> dict:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == usuario_id).first()
        if not user:
            return {"sucesso": False, "erro": "Usuário não encontrado."}

        if nome:
            user.nome = nome.strip()
        if telegram_username:
            user.telegram_username = normalizar_username_telegram(telegram_username)
        if telegram_id:
            user.telegram_id = str(telegram_id).strip()
            user.telegram_chat_id = str(telegram_id).strip()
        if telefone_whatsapp is not None:
            user.telefone_whatsapp = formatar_telefone_e164(telefone_whatsapp) or None
        if numero_bot_whatsapp is not None:
            user.numero_bot_whatsapp = formatar_telefone_e164(numero_bot_whatsapp) or None

        db.commit()
        return {
            "sucesso": True,
            "telegram_username": user.telegram_username,
            "telegram_id": user.telegram_id
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao atualizar configurações: {e}"}
    finally:
        db.close()


# =====================================================================
# TOKENS MOBILE (QR CODE) E HISTÓRICO DO CHAT IA
# =====================================================================

def gerar_token_mobile(usuario_id: int, minutos_validade: int = 10) -> dict:
    token = secrets.token_urlsafe(32)
    expira_em = datetime.utcnow() + timedelta(minutes=minutos_validade)
    db = SessionLocal()
    try:
        db.query(MobileToken).filter(
            MobileToken.user_id == usuario_id,
            MobileToken.usado == False
        ).update({"usado": True})

        novo_token = MobileToken(
            user_id=usuario_id,
            token=token,
            expira_em=expira_em,
            usado=False
        )
        db.add(novo_token)
        db.commit()
        return {"token": token, "validade_segundos": minutos_validade * 60}
    finally:
        db.close()


def validar_e_consumir_token_mobile(token: str) -> dict:
    agora = datetime.utcnow()
    db = SessionLocal()
    try:
        reg = db.query(MobileToken).filter(MobileToken.token == token).first()
        if not reg:
            return {"sucesso": False, "erro": "QR Code inválido ou não encontrado."}
        if reg.usado:
            return {"sucesso": False, "erro": "Este QR Code já foi utilizado."}
        if reg.expira_em < agora:
            return {"sucesso": False, "erro": "Este QR Code expirou."}

        reg.usado = True
        user = db.query(User).filter(User.id == reg.user_id).first()
        db.commit()
        return {
            "sucesso": True,
            "usuario": {
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram": user.telegram_username
            }
        }
    finally:
        db.close()


def salvar_mensagem_historico(usuario_id: int, remetente: str, mensagem: str):
    db = SessionLocal()
    try:
        msg = ChatMessage(user_id=usuario_id, remetente=remetente, mensagem=mensagem)
        db.add(msg)
        db.commit()
    finally:
        db.close()


def listar_historico_mensagens(usuario_id: int, limite: int = 50) -> list:
    db = SessionLocal()
    try:
        msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.user_id == usuario_id)
            .order_by(ChatMessage.id.desc())
            .limit(limite)
            .all()
        )
        msgs.reverse()
        return [
            {
                "id": m.id,
                "remetente": m.remetente,
                "mensagem": m.mensagem,
                "data_envio": m.data_envio.strftime("%Y-%m-%d %H:%M:%S") if m.data_envio else ""
            }
            for m in msgs
        ]
    finally:
        db.close()


# =====================================================================
# TRANSAÇÕES, RENDAS FIXAS, GASTOS FIXOS E DASHBOARD
# =====================================================================

def registrar_transacao(
    usuario_id: int,
    tipo: str,
    valor: float,
    categoria: str,
    descricao: str = "",
    moeda: str = "BRL"
) -> dict:
    if (moeda or "BRL").upper() != "BRL":
        return {"sucesso": False, "erro": "Operação negada (RN04): O sistema opera exclusivamente em Real (BRL)."}
    if float(valor) <= 0:
        return {"sucesso": False, "erro": "O valor deve ser maior que zero."}

    tipo_limpo = (tipo or "").lower().strip()
    if tipo_limpo not in ("receita", "despesa"):
        return {"sucesso": False, "erro": "Tipo inválido. Use 'receita' ou 'despesa'."}

    resumo_antes = obter_resumo_financeiro(usuario_id)
    alerta_risco = None
    if tipo_limpo == "despesa" and float(valor) > resumo_antes["saldo"]:
        alerta_risco = (
            f"⚠️ Alerta de Risco (RN02): Esta despesa (R$ {float(valor):.2f}) "
            f"ultrapassa seu saldo disponível (R$ {resumo_antes['saldo']:.2f})."
        )

    db = SessionLocal()
    try:
        nova = Transaction(
            user_id=usuario_id,
            tipo=tipo_limpo,
            valor=float(valor),
            categoria=(categoria or "Outros").strip().capitalize(),
            descricao=(descricao or "").strip(),
            moeda="BRL",
            data_transacao=datetime.utcnow()
        )
        db.add(nova)
        db.commit()
        db.refresh(nova)
        return {"sucesso": True, "id": nova.id, "alerta": alerta_risco}
    finally:
        db.close()


def listar_transacoes(usuario_id: int, limite: int = 50) -> list:
    db = SessionLocal()
    try:
        rows = (
            db.query(Transaction)
            .filter(Transaction.user_id == usuario_id)
            .order_by(Transaction.id.desc())
            .limit(limite)
            .all()
        )
        return [
            {
                "id": r.id,
                "tipo": r.tipo,
                "valor": float(r.valor),
                "categoria": r.categoria,
                "descricao": r.descricao or "",
                "data_transacao": r.data_transacao.strftime("%Y-%m-%d %H:%M:%S") if r.data_transacao else ""
            }
            for r in rows
        ]
    finally:
        db.close()


def excluir_transacao(usuario_id: int, transacao_id: int) -> dict:
    db = SessionLocal()
    try:
        item = db.query(Transaction).filter(
            Transaction.id == transacao_id,
            Transaction.user_id == usuario_id
        ).first()
        if not item:
            return {"sucesso": False, "erro": "Transação não encontrada."}
        db.delete(item)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


def adicionar_renda_fixa(usuario_id: int, descricao: str, valor: float, dia_recebimento: int = 5) -> dict:
    db = SessionLocal()
    try:
        nova = FixedIncome(
            user_id=usuario_id,
            description=descricao.strip(),
            amount=float(valor),
            day_of_month=max(1, min(31, int(dia_recebimento or 5))),
            is_active=True
        )
        db.add(nova)
        db.commit()
        db.refresh(nova)
        return {"sucesso": True, "id": nova.id}
    finally:
        db.close()


def listar_rendas_fixas(usuario_id: int) -> list:
    db = SessionLocal()
    try:
        rows = db.query(FixedIncome).filter(
            FixedIncome.user_id == usuario_id,
            FixedIncome.is_active == True
        ).all()
        return [
            {
                "id": r.id,
                "descricao": r.description,
                "description": r.description,
                "valor": float(r.amount),
                "amount": float(r.amount),
                "dia": r.day_of_month,
                "day_of_month": r.day_of_month
            }
            for r in rows
        ]
    finally:
        db.close()


def remover_renda_fixa(usuario_id: int, renda_id: int) -> dict:
    db = SessionLocal()
    try:
        row = db.query(FixedIncome).filter(
            FixedIncome.id == renda_id,
            FixedIncome.user_id == usuario_id
        ).first()
        if not row:
            return {"sucesso": False, "erro": "Renda fixa não encontrada."}
        db.delete(row)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


def atualizar_renda_fixa(
    usuario_id: int,
    renda_id: int,
    descricao: str = None,
    valor: float = None,
    dia_recebimento: int = None,
    is_active: bool = None
) -> dict:
    """Atualiza os dados de uma renda fixa existente do usuário."""
    db = SessionLocal()
    try:
        renda = db.query(FixedIncome).filter(
            FixedIncome.id == renda_id,
            FixedIncome.user_id == usuario_id
        ).first()
        
        if not renda:
            return {"sucesso": False, "erro": "Renda fixa não encontrada."}
            
        if descricao is not None:
            renda.description = descricao.strip()
        if valor is not None:
            renda.amount = float(valor)
        if dia_recebimento is not None:
            renda.day_of_month = max(1, min(31, int(dia_recebimento)))
        if is_active is not None:
            renda.is_active = bool(is_active)
            
        db.commit()
        return {"sucesso": True, "id": renda.id}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao atualizar renda fixa: {str(e)}"}
    finally:
        db.close()


def atualizar_gasto_fixo(
    usuario_id: int,
    gasto_id: int,
    descricao: str = None,
    valor: float = None,
    dia_vencimento: int = None,
    categoria: str = None,
    is_active: bool = None
) -> dict:
    """Atualiza os dados de um gasto fixo existente do usuário."""
    db = SessionLocal()
    try:
        gasto = db.query(FixedExpense).filter(
            FixedExpense.id == gasto_id,
            FixedExpense.user_id == usuario_id
        ).first()
        
        if not gasto:
            return {"sucesso": False, "erro": "Gasto fixo não encontrado."}
            
        if descricao is not None:
            gasto.description = descricao.strip()
        if valor is not None:
            gasto.amount = float(valor)
        if dia_vencimento is not None:
            gasto.due_day = max(1, min(31, int(dia_vencimento)))
        if categoria is not None:
            gasto.category = categoria.strip().capitalize()
        if is_active is not None:
            gasto.is_active = bool(is_active)
            
        db.commit()
        return {"sucesso": True, "id": gasto.id}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao atualizar gasto fixo: {str(e)}"}
    finally:
        db.close()


def adicionar_gasto_fixo(
    usuario_id: int,
    descricao: str,
    valor: float,
    dia_vencimento: int = 10,
    categoria: str = "Moradia"
) -> dict:
    db = SessionLocal()
    try:
        novo = FixedExpense(
            user_id=usuario_id,
            description=descricao.strip(),
            category=(categoria or "Moradia").strip().capitalize(),
            amount=float(valor),
            due_day=max(1, min(31, int(dia_vencimento or 10))),
            is_active=True
        )
        db.add(novo)
        db.commit()
        db.refresh(novo)
        return {"sucesso": True, "id": novo.id}
    finally:
        db.close()


def listar_gastos_fixos(usuario_id: int) -> list:
    db = SessionLocal()
    try:
        rows = db.query(FixedExpense).filter(
            FixedExpense.user_id == usuario_id,
            FixedExpense.is_active == True
        ).all()
        return [
            {
                "id": r.id,
                "descricao": r.description,
                "description": r.description,
                "categoria": getattr(r, "category", "Moradia") or "Moradia",
                "valor": float(r.amount),
                "amount": float(r.amount),
                "dia_vencimento": r.due_day,
                "due_day": r.due_day
            }
            for r in rows
        ]
    finally:
        db.close()


def remover_gasto_fixo(usuario_id: int, gasto_id: int) -> dict:
    db = SessionLocal()
    try:
        row = db.query(FixedExpense).filter(
            FixedExpense.id == gasto_id,
            FixedExpense.user_id == usuario_id
        ).first()
        if not row:
            return {"sucesso": False, "erro": "Gasto fixo não encontrado."}
        db.delete(row)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


# Caminho: core/database.py (Substitua apenas a função obter_resumo_financeiro)

def obter_resumo_financeiro(usuario_id: int, periodo: str = "mes_atual") -> dict:
    db = SessionLocal()
    try:
        receitas_var = (
            db.query(func.coalesce(func.sum(Transaction.valor), 0.0))
            .filter(Transaction.user_id == usuario_id, Transaction.tipo == "receita")
            .scalar() or 0.0
        )
        despesas_var = (
            db.query(func.coalesce(func.sum(Transaction.valor), 0.0))
            .filter(Transaction.user_id == usuario_id, Transaction.tipo == "despesa")
            .scalar() or 0.0
        )
        rendas_fixas = (
            db.query(func.coalesce(func.sum(FixedIncome.amount), 0.0))
            .filter(FixedIncome.user_id == usuario_id, FixedIncome.is_active == True)
            .scalar() or 0.0
        )
        gastos_fixos = (
            db.query(func.coalesce(func.sum(FixedExpense.amount), 0.0))
            .filter(FixedExpense.user_id == usuario_id, FixedExpense.is_active == True)
            .scalar() or 0.0
        )
        total_lancamentos = (
            db.query(func.count(Transaction.id))
            .filter(Transaction.user_id == usuario_id)
            .scalar() or 0
        )

        cats = (
            db.query(Transaction.categoria, func.sum(Transaction.valor).label("total"))
            .filter(Transaction.user_id == usuario_id, Transaction.tipo == "despesa")
            .group_by(Transaction.categoria)
            .order_by(func.sum(Transaction.valor).desc())
            .all()
        )
        por_categoria = [{"categoria": c[0], "total": float(c[1])} for c in cats]

        total_entradas = float(receitas_var) + float(rendas_fixas)
        total_saidas = float(despesas_var) + float(gastos_fixos)

        labels_pizza = [c["categoria"] for c in por_categoria]
        valores_pizza = [c["total"] for c in por_categoria]
        if float(gastos_fixos) > 0:
            labels_pizza.append("Gastos Fixos")
            valores_pizza.append(float(gastos_fixos))

        return {
            "mes_referencia": datetime.utcnow().strftime("%m/%Y"),
            "total_receitas": total_entradas,
            "total_despesas": total_saidas,
            "receitas_variaveis": float(receitas_var),
            "despesas_variaveis": float(despesas_var),
            "rendas_fixas": float(rendas_fixas),
            "total_rendas_fixas": float(rendas_fixas),
            "gastos_fixos": float(gastos_fixos),
            "total_gastos_fixos": float(gastos_fixos),
            "saldo": total_entradas - total_saidas,
            "total_lancamentos": int(total_lancamentos),
            "despesas_por_categoria": por_categoria,
            "grafico_pizza": {
                "labels": labels_pizza,
                "valores": valores_pizza
            },
            "grafico_colunas": {
                "labels": ["Mês Vigente"],
                "entradas": [total_entradas],
                "saidas": [total_saidas]
            }
        }
    finally:
        db.close()

def obter_dados_graficos_dashboard(usuario_id: int) -> dict:
    resumo = obter_resumo_financeiro(usuario_id)
    return {
        "cards": {
            "entradas": resumo["total_receitas"],
            "saidas": resumo["total_despesas"],
            "saldo": resumo["saldo"],
            "lancamentos": resumo["total_lancamentos"]
        },
        "pizza_categorias": resumo["despesas_por_categoria"],
        "colunas_comparativo": {
            "labels": ["Mês Vigente"],
            "entradas": [resumo["total_receitas"]],
            "saidas": [resumo["total_despesas"]]
        }
    }