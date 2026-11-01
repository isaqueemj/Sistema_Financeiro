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
    create_engine, Column, Integer, String, Numeric, DateTime, ForeignKey, Text, text, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SQLITE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'historico_ia.db')}"

raw_db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
elif raw_db_url.startswith("mysql://"):
    raw_db_url = raw_db_url.replace("mysql://", "mysql+pymysql://", 1)

DATABASE_URL = raw_db_url if raw_db_url else DEFAULT_SQLITE_URL


def garantir_schema_mysql(url_conexao: str):
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
        print(f"⚠️ Aviso ao verificar schema no MySQL: {err}")


garantir_schema_mysql(DATABASE_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=280)

if not DATABASE_URL.startswith("sqlite"):
    try:
        with engine.connect() as _conn:
            _conn.execute(text("SELECT 1"))
        tipo_sgbd = "MySQL Workbench" if DATABASE_URL.startswith("mysql") else "PostgreSQL"
        print(f"✅ Conectado com sucesso ao banco de dados {tipo_sgbd}!")
    except Exception as _err:
        print(f"⚠️ Falha ao conectar ao banco principal ({_err}). Usando SQLite local como fallback.")
        DATABASE_URL = DEFAULT_SQLITE_URL
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()


# =====================================================================
# MODELOS ORM (MAPEADOS EXCLUSIVAMENTE PARA AS 9 TABELAS EM PORTUGUÊS)
# =====================================================================

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, default="Usuário")
    email = Column(String(150), unique=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    telegram_username = Column(String(50), unique=True, nullable=True)
    telegram_id = Column(String(50), unique=True, nullable=True)
    primeiro_login = Column(Integer, default=1)
    status_2fa = Column(Integer, default=0)
    codigo_2fa = Column(String(10), nullable=True)
    expiracao_2fa = Column(DateTime, nullable=True)
    token_recuperacao = Column(String(255), nullable=True)
    expiracao_recuperacao = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Transacao(Base):
    __tablename__ = "transacoes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    descricao = Column(String(255), nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    categoria = Column(String(100), default="Outros")
    tipo = Column(String(20), nullable=False)
    data = Column(DateTime, default=datetime.utcnow)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DespesaFixa(Base):
    __tablename__ = "despesas_fixas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    descricao = Column(String(255), nullable=False)
    valor = Column(Numeric(10, 2), nullable=False, default=0.00)
    categoria = Column(String(100), default="Fixas")
    dia_vencimento = Column(Integer, default=1)
    ativo = Column(Integer, default=1)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReceitaFixa(Base):
    __tablename__ = "receitas_fixas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    descricao = Column(String(255), nullable=False)
    valor = Column(Numeric(10, 2), nullable=False, default=0.00)
    dia_recebimento = Column(Integer, default=1)
    ativo = Column(Integer, default=1)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LimiteOrcamento(Base):
    __tablename__ = "limites_orcamento"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    categoria = Column(String(100), nullable=False)
    valor_limite = Column(Numeric(10, 2), nullable=False)
    mes_ano = Column(String(7), nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Conversa(Base):
    __tablename__ = "conversas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    titulo = Column(String(150), default="Nova Conversa")
    status = Column(String(50), default="ativa")
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MensagemChat(Base):
    __tablename__ = "mensagens_chat"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversa_id = Column(Integer, ForeignKey("conversas.id", ondelete="CASCADE"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    remetente = Column(String(50), nullable=False)
    mensagem = Column(Text, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HistoricoMensagem(Base):
    __tablename__ = "historico_mensagens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    mensagem = Column(Text, nullable=True)
    resposta = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenMobile(Base):
    __tablename__ = "tokens_mobile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expira_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Aliases para caso algum módulo externo importe os nomes antigos
User = Usuario
Transaction = Transacao
FixedExpense = DespesaFixa
FixedIncome = ReceitaFixa
ChatMessage = MensagemChat
MobileToken = TokenMobile


# =====================================================================
# INICIALIZAÇÃO E VALIDAÇÃO DE USUÁRIO NA TABELA `usuarios`
# =====================================================================

def garantir_colunas_autenticacao_2fa():
    """Garante colunas na tabela `usuarios` caso o banco seja antigo."""
    comandos = [
        "ALTER TABLE usuarios ADD COLUMN telegram_username VARCHAR(50) NULL",
        "ALTER TABLE usuarios ADD COLUMN telegram_id VARCHAR(50) NULL",
        "ALTER TABLE usuarios ADD COLUMN primeiro_login TINYINT DEFAULT 1",
        "ALTER TABLE usuarios ADD COLUMN status_2fa TINYINT DEFAULT 0",
        "ALTER TABLE usuarios ADD COLUMN codigo_2fa VARCHAR(10) NULL",
        "ALTER TABLE usuarios ADD COLUMN expiracao_2fa DATETIME NULL",
        "ALTER TABLE usuarios ADD COLUMN token_recuperacao VARCHAR(255) NULL",
        "ALTER TABLE usuarios ADD COLUMN expiracao_recuperacao DATETIME NULL"
    ]
    for cmd in comandos:
        try:
            with engine.begin() as conn:
                conn.execute(text(cmd))
        except Exception:
            pass


def init_db():
    Base.metadata.create_all(bind=engine)
    garantir_colunas_autenticacao_2fa()


def garantir_usuario_sincronizado(usuario_id: int = None, nome: str = None, email: str = None) -> int:
    """
    Garante que o ID do usuário logado exista na tabela `usuarios` antes de gravar
    em `mensagens_chat`, `tokens_mobile`, `despesas_fixas`, `receitas_fixas` ou `transacoes`.
    """
    db = SessionLocal()
    try:
        if usuario_id:
            u = db.query(Usuario).filter(Usuario.id == int(usuario_id)).first()
            if u:
                return u.id

        if email:
            u_email = db.query(Usuario).filter(func.lower(Usuario.email) == email.strip().lower()).first()
            if u_email:
                return u_email.id

        primeiro = db.query(Usuario).order_by(Usuario.id.asc()).first()
        if primeiro:
            return primeiro.id

        novo = Usuario(
            nome=(nome or "Isaque Eugenio de Melo Junior").strip(),
            email=(email or "isaqueemj@gmail.com").strip().lower(),
            senha_hash=generate_password_hash("123456", method="pbkdf2:sha256", salt_length=16),
            primeiro_login=0,
            status_2fa=1
        )
        db.add(novo)
        db.commit()
        db.refresh(novo)
        return novo.id
    except Exception:
        db.rollback()
        primeiro = db.query(Usuario).order_by(Usuario.id.asc()).first()
        return primeiro.id if primeiro else 1
    finally:
        db.close()


# =====================================================================
# FUNÇÕES AUXILIARES
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
# AUTENTICAÇÃO, CADASTRO E 2FA NA TABELA `usuarios`
# =====================================================================

def criar_usuario_com_telegram_obrigatorio(
    nome: str,
    email: str,
    senha_plana: str,
    telegram: str,
    telegram_id: str = None
) -> dict:
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

        novo = Usuario(
            nome=nome.strip(),
            email=email_limpo,
            senha_hash=senha_hash,
            telegram_username=telegram_limpo,
            telegram_id=tg_id_limpo,
            primeiro_login=1,
            status_2fa=0
        )
        db.add(novo)
        db.commit()
        db.refresh(novo)

        return {
            "sucesso": True,
            "id": novo.id,
            "telegram_username": novo.telegram_username,
            "telegram_id": novo.telegram_id
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao cadastrar usuário: {e}"}
    finally:
        db.close()


def criar_usuario(nome: str, email: str, senha_plana: str, telefone_whatsapp: str = None, telegram: str = None) -> dict:
    tg = telegram or telefone_whatsapp or f"@{email.split('@')[0]}"
    return criar_usuario_com_telegram_obrigatorio(nome, email, senha_plana, tg)


def iniciar_login_hibrido(identificador: str, senha_plana: str) -> dict:
    ident_limpo = (identificador or "").strip()
    if not ident_limpo:
        return {"sucesso": False, "erro": "Informe seu E-mail ou @Telegram."}

    busca_tg_com = normalizar_username_telegram(ident_limpo)
    busca_tg_sem = busca_tg_com.lstrip("@")

    db = SessionLocal()
    try:
        user = db.execute(
            text("""
                SELECT id, nome, email, senha_hash, telegram_username, telegram_id, primeiro_login, status_2fa
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

        # Se primeiro_login == 1, exige validação 2FA por e-mail
        if user.primeiro_login is None or int(user.primeiro_login) == 1:
            codigo = f"{random.randint(100000, 999999)}"
            expira = datetime.utcnow() + timedelta(minutes=10)
            db.execute(
                text("UPDATE usuarios SET codigo_2fa = :cod, expiracao_2fa = :exp WHERE id = :uid"),
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
                "telegram_username": user.telegram_username,
                "telegram_id": user.telegram_id
            }
        }
    finally:
        db.close()


def autenticar_usuario(email: str, senha_plana: str) -> dict:
    return iniciar_login_hibrido(email, senha_plana)


def validar_codigo_2fa_banco(identificador: str, codigo: str) -> dict:
    ident_limpo = (identificador or "").strip().lower()
    busca_tg_com = normalizar_username_telegram(ident_limpo)
    codigo_limpo = (codigo or "").strip()

    db = SessionLocal()
    try:
        user = db.execute(
            text("""
                SELECT id, nome, email, telegram_username, telegram_id, codigo_2fa, expiracao_2fa
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
            text("""
                UPDATE usuarios
                SET primeiro_login = 0, status_2fa = 1, codigo_2fa = NULL, expiracao_2fa = NULL
                WHERE id = :uid
            """),
            {"uid": user.id}
        )
        db.commit()

        return {
            "sucesso": True,
            "usuario": {
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram": user.telegram_username,
                "telegram_username": user.telegram_username,
                "telegram_id": user.telegram_id
            }
        }
    finally:
        db.close()


def gerar_token_recuperacao_senha(identificador: str) -> dict:
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

        token = secrets.token_urlsafe(24)
        expira = datetime.utcnow() + timedelta(minutes=15)
        db.execute(
            text("UPDATE usuarios SET token_recuperacao = :tok, expiracao_recuperacao = :exp WHERE id = :uid"),
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
            text("SELECT id FROM usuarios WHERE token_recuperacao = :tok"),
            {"tok": token_limpo}
        ).fetchone()

        if not user:
            return {"sucesso": False, "erro": "Link de recuperação inválido ou já utilizado."}

        novo_hash = generate_password_hash(senha_final, method="pbkdf2:sha256", salt_length=16)
        db.execute(
            text("""
                UPDATE usuarios
                SET senha_hash = :sh, token_recuperacao = NULL, expiracao_recuperacao = NULL
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
# PERFIL DO USUÁRIO E INTEGRAÇÃO TELEGRAM (`usuarios`)
# =====================================================================

def obter_ou_vincular_usuario_telegram(
    chat_id: str,
    username: str = "",
    first_name: str = "Usuário Telegram",
    token_vinculo: str = None
) -> dict:
    chat_id_str = str(chat_id).strip()
    user_com_arroba = normalizar_username_telegram(username)
    user_sem_arroba = user_com_arroba.lstrip("@")

    db = SessionLocal()
    try:
        # 1. Se veio token de vínculo do QR Code (/start <token>)
        if token_vinculo:
            reg_token = db.query(TokenMobile).filter(TokenMobile.token == token_vinculo).first()
            if reg_token:
                user_tok = db.query(Usuario).filter(Usuario.id == reg_token.usuario_id).first()
                db.delete(reg_token)
                if user_tok:
                    user_tok.telegram_id = chat_id_str
                    if user_com_arroba:
                        user_tok.telegram_username = user_com_arroba
                    db.commit()
                    return {
                        "id": user_tok.id,
                        "nome": user_tok.nome,
                        "email": user_tok.email,
                        "telegram_username": user_tok.telegram_username,
                        "telegram_id": chat_id_str,
                        "vinculado_agora": True
                    }

        # 2. Procura pelo telegram_id já salvo na tabela `usuarios`
        user = db.execute(
            text("SELECT id, nome, email, telegram_username, telegram_id FROM usuarios WHERE telegram_id = :cid"),
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

        # 3. Procura pelo @telegram_username cadastrado na Web e grava o telegram_id automaticamente
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

        # 4. Fallback: cria usuário caso inicie conversa direto no Bot
        email_temp = f"{chat_id_str}@telegram.local"
        senha_hash = generate_password_hash(chat_id_str, method="pbkdf2:sha256")
        novo = Usuario(
            nome=first_name,
            email=email_temp,
            senha_hash=senha_hash,
            telegram_username=user_com_arroba or None,
            telegram_id=chat_id_str,
            primeiro_login=0,
            status_2fa=1
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


def obter_ou_criar_usuario_por_whatsapp(telefone: str, nome: str = "Usuário WhatsApp") -> dict:
    uid = garantir_usuario_sincronizado(1, nome=nome)
    user = obter_usuario_por_id(uid)
    return user or {"id": uid, "nome": nome, "email": ""}


def obter_usuario_por_id(usuario_id: int) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        user = db.query(Usuario).filter(Usuario.id == uid_real).first()
        if not user:
            return None
        return {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "telegram": user.telegram_username or "",
            "telegram_username": user.telegram_username or "",
            "telegram_id": user.telegram_id or "",
            "telegram_chat_id": user.telegram_id or "",
            "telefone_whatsapp": "",
            "numero_bot_whatsapp": "",
            "numero_bot_efetivo": os.getenv("WHATSAPP_BOT_NUMBER", ""),
            "data_criacao": user.criado_em.strftime("%Y-%m-%d %H:%M:%S") if user.criado_em else ""
        }
    finally:
        db.close()


def atualizar_configuracoes_usuario(
    usuario_id: int,
    nome: str = None,
    telefone_whatsapp: str = None,
    numero_bot_whatsapp: str = None,
    telegram_username: str = None,
    telegram_id: str = None
) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id, nome=nome)
    db = SessionLocal()
    try:
        user = db.query(Usuario).filter(Usuario.id == uid_real).first()
        if not user:
            return {"sucesso": False, "erro": "Usuário não encontrado."}

        if nome and nome.strip():
            user.nome = nome.strip()
        if telegram_username is not None and str(telegram_username).strip():
            user.telegram_username = normalizar_username_telegram(telegram_username)
        if telegram_id is not None and str(telegram_id).strip():
            user.telegram_id = str(telegram_id).strip()

        db.commit()
        return {
            "sucesso": True,
            "mensagem": "Configurações salvas com sucesso!",
            "usuario": {
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram_username": user.telegram_username or "",
                "telegram_id": user.telegram_id or "",
                "telegram_chat_id": user.telegram_id or ""
            }
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao atualizar configurações: {e}"}
    finally:
        db.close()


# =====================================================================
# TOKENS MOBILE (`tokens_mobile`) E CHAT (`mensagens_chat` / `historico_mensagens`)
# =====================================================================

def gerar_token_mobile(usuario_id: int, minutos_validade: int = 10) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    token = secrets.token_urlsafe(24)
    expira_em = datetime.utcnow() + timedelta(minutes=minutos_validade)
    db = SessionLocal()
    try:
        # Remove tokens antigos do usuário na tabela `tokens_mobile`
        db.query(TokenMobile).filter(TokenMobile.usuario_id == uid_real).delete()

        novo_token = TokenMobile(
            usuario_id=uid_real,
            token=token,
            expira_em=expira_em
        )
        db.add(novo_token)
        db.commit()
        return {"token": token, "validade_segundos": minutos_validade * 60}
    except Exception as e:
        db.rollback()
        print(f"⚠️ Erro ao gerar token mobile em tokens_mobile: {e}")
        return {"token": token, "validade_segundos": minutos_validade * 60}
    finally:
        db.close()


def validar_e_consumir_token_mobile(token: str) -> dict:
    agora = datetime.utcnow()
    db = SessionLocal()
    try:
        reg = db.query(TokenMobile).filter(TokenMobile.token == token).first()
        if not reg:
            return {"sucesso": False, "erro": "QR Code inválido ou já utilizado."}
        if reg.expira_em and reg.expira_em < agora:
            db.delete(reg)
            db.commit()
            return {"sucesso": False, "erro": "Este QR Code expirou. Gere um novo no painel."}

        user = db.query(Usuario).filter(Usuario.id == reg.usuario_id).first()
        db.delete(reg)
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


def _obter_ou_criar_conversa_ativa(db, usuario_id: int) -> int:
    conv = (
        db.query(Conversa)
        .filter(Conversa.usuario_id == usuario_id, Conversa.status == "ativa")
        .order_by(Conversa.id.desc())
        .first()
    )
    if conv:
        return conv.id
    nova = Conversa(usuario_id=usuario_id, titulo="Conversa Principal", status="ativa")
    db.add(nova)
    db.flush()
    return nova.id


def salvar_mensagem_historico(usuario_id: int, remetente: str, mensagem: str):
    if not mensagem:
        return
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        rem = "usuario" if remetente in ("usuario", "user") else "ia"
        conversa_id = _obter_ou_criar_conversa_ativa(db, uid_real)

        # 1. Salva na tabela `mensagens_chat`
        nova_msg = MensagemChat(
            conversa_id=conversa_id,
            usuario_id=uid_real,
            remetente=rem,
            mensagem=str(mensagem)
        )
        db.add(nova_msg)

        # 2. Mantém `historico_mensagens` (par pergunta/resposta) sincronizado
        if rem == "usuario":
            hist = HistoricoMensagem(usuario_id=uid_real, mensagem=str(mensagem), resposta=None)
            db.add(hist)
        else:
            ult_hist = (
                db.query(HistoricoMensagem)
                .filter(HistoricoMensagem.usuario_id == uid_real, HistoricoMensagem.resposta == None)
                .order_by(HistoricoMensagem.id.desc())
                .first()
            )
            if ult_hist:
                ult_hist.resposta = str(mensagem)
            else:
                db.add(HistoricoMensagem(usuario_id=uid_real, mensagem="", resposta=str(mensagem)))

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"⚠️ Aviso ao salvar mensagem em mensagens_chat: {e}")
    finally:
        db.close()


def listar_historico_mensagens(usuario_id: int, limite: int = 50) -> list:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        msgs = (
            db.query(MensagemChat)
            .filter(MensagemChat.usuario_id == uid_real)
            .order_by(MensagemChat.id.desc())
            .limit(limite)
            .all()
        )
        if msgs:
            msgs.reverse()
            return [
                {
                    "id": m.id,
                    "remetente": m.remetente,
                    "mensagem": m.mensagem,
                    "data_envio": m.criado_em.strftime("%Y-%m-%d %H:%M:%S") if m.criado_em else ""
                }
                for m in msgs
            ]

        # Fallback caso existam registros apenas em `historico_mensagens`
        hists = (
            db.query(HistoricoMensagem)
            .filter(HistoricoMensagem.usuario_id == uid_real)
            .order_by(HistoricoMensagem.id.asc())
            .limit(limite)
            .all()
        )
        resultado = []
        for h in hists:
            dt_str = h.criado_em.strftime("%Y-%m-%d %H:%M:%S") if h.criado_em else ""
            if h.mensagem:
                resultado.append({"id": h.id, "remetente": "usuario", "mensagem": h.mensagem, "data_envio": dt_str})
            if h.resposta:
                resultado.append({"id": h.id, "remetente": "ia", "mensagem": h.resposta, "data_envio": dt_str})
        return resultado
    finally:
        db.close()


# =====================================================================
# TRANSAÇÕES (`transacoes`), RECEITAS FIXAS (`receitas_fixas`) E DESPESAS FIXAS (`despesas_fixas`)
# =====================================================================

def registrar_transacao(
    usuario_id: int,
    tipo: str,
    valor: float,
    categoria: str,
    descricao: str = "",
    moeda: str = "BRL"
) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    if (moeda or "BRL").upper() != "BRL":
        return {"sucesso": False, "erro": "Operação negada (RN04): O sistema opera exclusivamente em Real (BRL)."}
    if float(valor) <= 0:
        return {"sucesso": False, "erro": "O valor deve ser maior que zero."}

    tipo_limpo = (tipo or "").lower().strip()
    if tipo_limpo not in ("receita", "despesa"):
        return {"sucesso": False, "erro": "Tipo inválido. Use 'receita' ou 'despesa'."}

    resumo_antes = obter_resumo_financeiro(uid_real)
    alerta_risco = None
    if tipo_limpo == "despesa" and float(valor) > resumo_antes["saldo"]:
        alerta_risco = (
            f"⚠️ Alerta de Risco (RN02): Esta despesa (R$ {float(valor):.2f}) "
            f"ultrapassa seu saldo disponível (R$ {resumo_antes['saldo']:.2f})."
        )

    db = SessionLocal()
    try:
        cat_final = (categoria or "Outros").strip().capitalize()
        desc_final = (descricao or cat_final).strip()
        nova = Transacao(
            usuario_id=uid_real,
            tipo=tipo_limpo,
            valor=round(float(valor), 2),
            categoria=cat_final,
            descricao=desc_final,
            data=datetime.utcnow()
        )
        db.add(nova)
        db.commit()
        db.refresh(nova)
        return {"sucesso": True, "id": nova.id, "alerta": alerta_risco}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao registrar transação: {e}"}
    finally:
        db.close()


def listar_transacoes(usuario_id: int, limite: int = 50) -> list:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        rows = (
            db.query(Transacao)
            .filter(Transacao.usuario_id == uid_real)
            .order_by(Transacao.id.desc())
            .limit(limite)
            .all()
        )
        return [
            {
                "id": r.id,
                "tipo": r.tipo,
                "valor": float(r.valor or 0.0),
                "categoria": r.categoria or "Outros",
                "descricao": r.descricao or "",
                "data": (r.data or r.criado_em).strftime("%Y-%m-%d %H:%M:%S") if (r.data or r.criado_em) else "",
                "data_transacao": (r.data or r.criado_em).strftime("%Y-%m-%d %H:%M:%S") if (r.data or r.criado_em) else ""
            }
            for r in rows
        ]
    finally:
        db.close()


def excluir_transacao(usuario_id: int, transacao_id: int) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        item = db.query(Transacao).filter(
            Transacao.id == transacao_id,
            Transacao.usuario_id == uid_real
        ).first()
        if not item:
            return {"sucesso": False, "erro": "Transação não encontrada."}
        db.delete(item)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


def criar_renda_fixa(
    usuario_id: int,
    description: str = None,
    amount: float = None,
    day_of_month: int = None,
    is_active: bool = True,
    descricao: str = None,
    valor: float = None,
    dia_recebimento: int = None,
    ativo: bool = None
) -> dict:
    """Salva na tabela `receitas_fixas` aceitando parâmetros tanto do ia.py quanto do main.py."""
    uid_real = garantir_usuario_sincronizado(usuario_id)
    desc_final = (description if description is not None else descricao) or "Renda Fixa"
    val_final = amount if amount is not None else (valor if valor is not None else 0.0)
    dia_final = day_of_month if day_of_month is not None else (dia_recebimento if dia_recebimento is not None else 5)
    ativo_final = ativo if ativo is not None else is_active

    db = SessionLocal()
    try:
        nova_renda = ReceitaFixa(
            usuario_id=uid_real,
            descricao=str(desc_final).strip(),
            valor=round(float(val_final), 2),
            dia_recebimento=max(1, min(31, int(dia_final or 5))),
            ativo=1 if bool(ativo_final) else 0
        )
        db.add(nova_renda)
        db.commit()
        db.refresh(nova_renda)
        return {"sucesso": True, "id": nova_renda.id}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao cadastrar receita fixa: {e}"}
    finally:
        db.close()


def adicionar_renda_fixa(
    usuario_id: int,
    description: str = None,
    amount: float = None,
    day_of_month: int = None,
    is_active: bool = True,
    descricao: str = None,
    valor: float = None,
    dia_recebimento: int = None,
    ativo: bool = None
) -> dict:
    return criar_renda_fixa(
        usuario_id=usuario_id,
        description=description,
        amount=amount,
        day_of_month=day_of_month,
        is_active=is_active,
        descricao=descricao,
        valor=valor,
        dia_recebimento=dia_recebimento,
        ativo=ativo
    )


def atualizar_renda_fixa(
    usuario_id: int,
    renda_id: int,
    descricao: str = None,
    valor: float = None,
    dia_recebimento: int = None,
    is_active: bool = None
) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        renda = db.query(ReceitaFixa).filter(
            ReceitaFixa.id == renda_id,
            ReceitaFixa.usuario_id == uid_real
        ).first()

        if not renda:
            return {"sucesso": False, "erro": "Receita fixa não encontrada."}

        if descricao is not None:
            renda.descricao = str(descricao).strip()
        if valor is not None:
            renda.valor = round(float(valor), 2)
        if dia_recebimento is not None:
            renda.dia_recebimento = max(1, min(31, int(dia_recebimento)))
        if is_active is not None:
            renda.ativo = 1 if bool(is_active) else 0

        db.commit()
        return {"sucesso": True, "id": renda.id}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao atualizar receita fixa: {e}"}
    finally:
        db.close()


def listar_rendas_fixas(usuario_id: int, apenas_ativas: bool = False) -> list:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        query = db.query(ReceitaFixa).filter(ReceitaFixa.usuario_id == uid_real)
        if apenas_ativas:
            query = query.filter(ReceitaFixa.ativo == 1)
        rows = query.order_by(ReceitaFixa.dia_recebimento.asc()).all()
        return [
            {
                "id": r.id,
                "descricao": r.descricao,
                "description": r.descricao,
                "valor": float(r.valor or 0.0),
                "amount": float(r.valor or 0.0),
                "dia": int(r.dia_recebimento or 1),
                "dia_recebimento": int(r.dia_recebimento or 1),
                "day_of_month": int(r.dia_recebimento or 1),
                "ativo": bool(r.ativo),
                "is_active": bool(r.ativo)
            }
            for r in rows
        ]
    finally:
        db.close()


def remover_renda_fixa(usuario_id: int, renda_id: int) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        row = db.query(ReceitaFixa).filter(
            ReceitaFixa.id == renda_id,
            ReceitaFixa.usuario_id == uid_real
        ).first()
        if not row:
            return {"sucesso": False, "erro": "Receita fixa não encontrada."}
        db.delete(row)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


def criar_gasto_fixo(
    usuario_id: int,
    description: str = None,
    amount: float = None,
    due_day: int = None,
    is_active: bool = True,
    categoria: str = "Fixas",
    descricao: str = None,
    valor: float = None,
    dia_vencimento: int = None,
    ativo: bool = None
) -> dict:
    """Salva na tabela `despesas_fixas` aceitando parâmetros tanto do ia.py quanto do main.py."""
    uid_real = garantir_usuario_sincronizado(usuario_id)
    desc_final = (description if description is not None else descricao) or "Despesa Fixa"
    val_final = amount if amount is not None else (valor if valor is not None else 0.0)
    dia_final = due_day if due_day is not None else (dia_vencimento if dia_vencimento is not None else 10)
    ativo_final = ativo if ativo is not None else is_active

    db = SessionLocal()
    try:
        novo_gasto = DespesaFixa(
            usuario_id=uid_real,
            descricao=str(desc_final).strip(),
            valor=round(float(val_final), 2),
            categoria=(categoria or "Fixas").strip().capitalize(),
            dia_vencimento=max(1, min(31, int(dia_final or 10))),
            ativo=1 if bool(ativo_final) else 0
        )
        db.add(novo_gasto)
        db.commit()
        db.refresh(novo_gasto)
        return {"sucesso": True, "id": novo_gasto.id}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao cadastrar despesa fixa: {e}"}
    finally:
        db.close()


def adicionar_gasto_fixo(
    usuario_id: int,
    description: str = None,
    amount: float = None,
    due_day: int = None,
    is_active: bool = True,
    categoria: str = "Fixas",
    descricao: str = None,
    valor: float = None,
    dia_vencimento: int = None,
    ativo: bool = None
) -> dict:
    return criar_gasto_fixo(
        usuario_id=usuario_id,
        description=description,
        amount=amount,
        due_day=due_day,
        is_active=is_active,
        categoria=categoria,
        descricao=descricao,
        valor=valor,
        dia_vencimento=dia_vencimento,
        ativo=ativo
    )


def atualizar_gasto_fixo(
    usuario_id: int,
    gasto_id: int,
    descricao: str = None,
    valor: float = None,
    dia_vencimento: int = None,
    categoria: str = None,
    is_active: bool = None
) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        gasto = db.query(DespesaFixa).filter(
            DespesaFixa.id == gasto_id,
            DespesaFixa.usuario_id == uid_real
        ).first()

        if not gasto:
            return {"sucesso": False, "erro": "Despesa fixa não encontrada."}

        if descricao is not None:
            gasto.descricao = str(descricao).strip()
        if valor is not None:
            gasto.valor = round(float(valor), 2)
        if dia_vencimento is not None:
            gasto.dia_vencimento = max(1, min(31, int(dia_vencimento)))
        if categoria is not None:
            gasto.categoria = str(categoria).strip().capitalize()
        if is_active is not None:
            gasto.ativo = 1 if bool(is_active) else 0

        db.commit()
        return {"sucesso": True, "id": gasto.id}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao atualizar despesa fixa: {e}"}
    finally:
        db.close()


def listar_gastos_fixos(usuario_id: int, apenas_ativos: bool = False) -> list:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        query = db.query(DespesaFixa).filter(DespesaFixa.usuario_id == uid_real)
        if apenas_ativos:
            query = query.filter(DespesaFixa.ativo == 1)
        rows = query.order_by(DespesaFixa.dia_vencimento.asc()).all()
        return [
            {
                "id": r.id,
                "descricao": r.descricao,
                "description": r.descricao,
                "categoria": r.categoria or "Fixas",
                "category": r.categoria or "Fixas",
                "valor": float(r.valor or 0.0),
                "amount": float(r.valor or 0.0),
                "dia": int(r.dia_vencimento or 1),
                "dia_vencimento": int(r.dia_vencimento or 1),
                "due_day": int(r.dia_vencimento or 1),
                "ativo": bool(r.ativo),
                "is_active": bool(r.ativo)
            }
            for r in rows
        ]
    finally:
        db.close()


def remover_gasto_fixo(usuario_id: int, gasto_id: int) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        row = db.query(DespesaFixa).filter(
            DespesaFixa.id == gasto_id,
            DespesaFixa.usuario_id == uid_real
        ).first()
        if not row:
            return {"sucesso": False, "erro": "Despesa fixa não encontrada."}
        db.delete(row)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


def obter_resumo_financeiro(usuario_id: int, periodo: str = "mes_atual") -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        receitas_var = (
            db.query(func.coalesce(func.sum(Transacao.valor), 0.0))
            .filter(Transacao.usuario_id == uid_real, Transacao.tipo == "receita")
            .scalar() or 0.0
        )
        despesas_var = (
            db.query(func.coalesce(func.sum(Transacao.valor), 0.0))
            .filter(Transacao.usuario_id == uid_real, Transacao.tipo == "despesa")
            .scalar() or 0.0
        )
        rendas_fixas = (
            db.query(func.coalesce(func.sum(ReceitaFixa.valor), 0.0))
            .filter(ReceitaFixa.usuario_id == uid_real, ReceitaFixa.ativo == 1)
            .scalar() or 0.0
        )
        gastos_fixos = (
            db.query(func.coalesce(func.sum(DespesaFixa.valor), 0.0))
            .filter(DespesaFixa.usuario_id == uid_real, DespesaFixa.ativo == 1)
            .scalar() or 0.0
        )
        total_lancamentos = (
            db.query(func.count(Transacao.id))
            .filter(Transacao.usuario_id == uid_real)
            .scalar() or 0
        )

        cats = (
            db.query(Transacao.categoria, func.sum(Transacao.valor).label("total"))
            .filter(Transacao.usuario_id == uid_real, Transacao.tipo == "despesa")
            .group_by(Transacao.categoria)
            .order_by(func.sum(Transacao.valor).desc())
            .all()
        )
        por_categoria = [{"categoria": c[0] or "Outros", "total": float(c[1] or 0.0)} for c in cats]

        total_entradas = float(receitas_var) + float(rendas_fixas)
        total_saidas = float(despesas_var) + float(gastos_fixos)

        labels_pizza = [c["categoria"] for c in por_categoria]
        valores_pizza = [c["total"] for c in por_categoria]
        if float(gastos_fixos) > 0:
            labels_pizza.append("Despesas Fixas")
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