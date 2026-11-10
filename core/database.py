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
# MODELOS ORM (TABELAS EM PORTUGUÊS)
# =====================================================================

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, default="Usuário")
    email = Column(String(150), unique=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    telegram_username = Column(String(50), unique=True, nullable=True)
    telegram_id = Column(String(50), unique=True, nullable=True)
    telegram_chat_id = Column(String(64), nullable=True)
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


class TetoGasto(Base):
    __tablename__ = "tetos_gastos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    categoria = Column(String(100), nullable=False)
    valor_teto = Column(Numeric(10, 2), nullable=False)
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


# Aliases de compatibilidade
User = Usuario
Transaction = Transacao
FixedExpense = DespesaFixa
FixedIncome = ReceitaFixa
ChatMessage = MensagemChat
MobileToken = TokenMobile


def garantir_colunas_autenticacao_2fa():
    comandos = [
        "ALTER TABLE usuarios ADD COLUMN telegram_username VARCHAR(50) NULL",
        "ALTER TABLE usuarios ADD COLUMN telegram_id VARCHAR(50) NULL",
        "ALTER TABLE usuarios ADD COLUMN telegram_chat_id VARCHAR(64) NULL",
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
            nome=(nome or "Usuário Principal").strip(),
            email=(email or "admin@financecontrol.local").strip().lower(),
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
            telegram_chat_id=tg_id_limpo,
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
                SELECT id, nome, email, senha_hash, telegram_username, telegram_id, telegram_chat_id, primeiro_login, status_2fa
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

        hash_atual = user.senha_hash or ""
        if hash_atual.startswith(("pbkdf2:", "scrypt:", "sha256")):
            senha_ok = check_password_hash(hash_atual, senha_plana)
        else:
            senha_ok = (hash_atual == senha_plana)

        if not senha_ok:
            return {"sucesso": False, "erro": "Senha incorreta."}

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

        tg_id_final = user.telegram_id or user.telegram_chat_id or ""
        return {
            "sucesso": True,
            "requer_2fa": False,
            "usuario": {
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram": user.telegram_username,
                "telegram_username": user.telegram_username,
                "telegram_id": tg_id_final,
                "telegram_chat_id": tg_id_final
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
# QR CODE + DUPLA AUTENTICAÇÃO (2FA) NO TELEGRAM E MOBILE
# =====================================================================

# Memória auxiliar rápida para vincular chat_id -> usuario_id durante o 2FA
_PENDENCIAS_2FA_TELEGRAM = {}


def gerar_token_mobile(usuario_id: int, minutos_validade: int = 10) -> dict:
    """
    Gera um token temporário para o QR Code sem apagar tokens de 2FA pendentes.
    """
    uid_real = garantir_usuario_sincronizado(usuario_id)
    token = secrets.token_urlsafe(24)
    expira_em = datetime.utcnow() + timedelta(minutes=minutos_validade)
    db = SessionLocal()
    try:
        # Remove apenas tokens já expirados para não invalidar um QR Code recém-escaneado
        db.query(TokenMobile).filter(
            TokenMobile.expira_em < datetime.utcnow()
        ).delete(synchronize_session=False)

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
        print(f"⚠️ Erro ao gerar token mobile: {e}")
        return {"token": token, "validade_segundos": minutos_validade * 60}
    finally:
        db.close()


def iniciar_2fa_leitura_qrcode(token: str, chat_id_telegram: str = None) -> dict:
    """
    Acionado quando o QR Code é lido (no Telegram ou no navegador do celular).
    Salva um código de 6 dígitos em `usuarios.codigo_2fa` e registra a pendência para o chat_id.
    """
    token_limpo = (token or "").strip()
    if not token_limpo:
        return {"sucesso": False, "erro": "Token do QR Code ausente."}

    agora = datetime.utcnow()
    db = SessionLocal()
    try:
        reg = db.query(TokenMobile).filter(TokenMobile.token == token_limpo).first()
        if not reg:
            return {"sucesso": False, "erro": "QR Code inválido ou expirado. Gere um novo no painel web."}

        dono = db.query(Usuario).filter(Usuario.id == reg.usuario_id).first()
        if not dono:
            return {"sucesso": False, "erro": "Usuário titular não encontrado."}

        codigo_2fa = f"{random.randint(100000, 999999)}"
        expira_2fa = agora + timedelta(minutes=10)
        dono.codigo_2fa = codigo_2fa
        dono.expiracao_2fa = expira_2fa

        if chat_id_telegram:
            chat_id_str = str(chat_id_telegram).strip()
            _PENDENCIAS_2FA_TELEGRAM[chat_id_str] = dono.id

            # Também grava um registro de pendência no banco
            token_pendencia = f"2FA_TG:{chat_id_str}:{dono.id}"
            db.query(TokenMobile).filter(
                TokenMobile.token.like(f"2FA_TG:{chat_id_str}:%")
            ).delete(synchronize_session=False)
            db.add(TokenMobile(usuario_id=dono.id, token=token_pendencia, expira_em=expira_2fa))

        db.commit()
        return {
            "sucesso": True,
            "usuario_id": dono.id,
            "nome": dono.nome,
            "email_destino": dono.email,
            "email_mascarado": mascarar_email(dono.email),
            "codigo_gerado": codigo_2fa
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao iniciar 2FA do QR Code: {e}"}
    finally:
        db.close()


def verificar_pendencia_2fa_telegram(chat_id: str) -> bool:
    chat_id_str = str(chat_id).strip()
    if chat_id_str in _PENDENCIAS_2FA_TELEGRAM:
        return True
    db = SessionLocal()
    try:
        reg = db.query(TokenMobile).filter(
            TokenMobile.token.like(f"2FA_TG:{chat_id_str}:%")
        ).first()
        return reg is not None
    finally:
        db.close()


def confirmar_codigo_2fa_telegram(chat_id: str, codigo_digitado: str, username: str = "") -> dict:
    """
    Confirma os 6 dígitos enviados no chat do Telegram:
    - Procura o usuário pela pendência do chat_id OU diretamente pelo `codigo_2fa` na tabela `usuarios`.
    - Limpa duplicidades de `telegram_id` e `telegram_username` em outras linhas antes de salvar (evita erro 1062).
    - Remove a pendência de 2FA para destravar o chat imediatamente.
    """
    chat_id_str = str(chat_id).strip()
    codigo_limpo = re.sub(r"\D", "", str(codigo_digitado or ""))
    user_arroba = normalizar_username_telegram(username)

    if len(codigo_limpo) != 6:
        return {"sucesso": False, "erro": "O código deve conter 6 dígitos numéricos."}

    agora = datetime.utcnow()
    db = SessionLocal()
    try:
        dono = None

        # 1. Tenta localizar pelo usuário associado à pendência deste chat_id
        uid_pendente = _PENDENCIAS_2FA_TELEGRAM.get(chat_id_str)
        if not uid_pendente:
            reg_pend = db.query(TokenMobile).filter(
                TokenMobile.token.like(f"2FA_TG:{chat_id_str}:%")
            ).first()
            if reg_pend:
                uid_pendente = reg_pend.usuario_id

        if uid_pendente:
            dono = db.query(Usuario).filter(Usuario.id == int(uid_pendente)).first()

        # 2. Fallback direto: busca qualquer usuário na tabela `usuarios` que esteja com este `codigo_2fa` ativo
        if not dono or str(dono.codigo_2fa or "").strip() != codigo_limpo:
            dono_por_codigo = db.query(Usuario).filter(Usuario.codigo_2fa == codigo_limpo).first()
            if dono_por_codigo:
                dono = dono_por_codigo

        if not dono or not dono.codigo_2fa:
            return {
                "sucesso": False,
                "erro": "❌ Nenhum código 2FA ativo encontrado. Gere e escaneie o QR Code novamente."
            }

        if str(dono.codigo_2fa).strip() != codigo_limpo:
            return {
                "sucesso": False,
                "erro": "❌ Código de 6 dígitos incorreto! Confira o número mais recente enviado ao seu e-mail."
            }

        if dono.expiracao_2fa and dono.expiracao_2fa < agora:
            dono.codigo_2fa = None
            _PENDENCIAS_2FA_TELEGRAM.pop(chat_id_str, None)
            db.query(TokenMobile).filter(
                TokenMobile.token.like(f"2FA_TG:{chat_id_str}:%")
            ).delete(synchronize_session=False)
            db.commit()
            return {
                "sucesso": False,
                "erro": "⏰ Este código de 6 dígitos expirou. Escaneie o QR Code novamente."
            }

        # 3. Limpa `telegram_id`, `telegram_chat_id` e `telegram_username` de outras linhas para evitar IntegrityError (UNIQUE)
        db.execute(
            text("""
                UPDATE usuarios
                SET telegram_id = NULL, telegram_chat_id = NULL
                WHERE id != :uid AND (telegram_id = :cid OR telegram_chat_id = :cid)
            """),
            {"uid": dono.id, "cid": chat_id_str}
        )

        if user_arroba:
            db.execute(
                text("""
                    UPDATE usuarios
                    SET telegram_username = NULL
                    WHERE id != :uid
                      AND (lower(telegram_username) = :u1 OR lower(telegram_username) = :u2)
                """),
                {"uid": dono.id, "u1": user_arroba.lower(), "u2": user_arroba.lstrip("@").lower()}
            )

        db.flush()

        # 4. Vincula definitivamente a conta do titular ao Telegram atual e limpa a trava de 2FA
        dono.telegram_id = chat_id_str
        dono.telegram_chat_id = chat_id_str
        if user_arroba:
            dono.telegram_username = user_arroba
        dono.codigo_2fa = None
        dono.expiracao_2fa = None
        dono.status_2fa = 1
        dono.primeiro_login = 0
        dono.atualizado_em = agora

        _PENDENCIAS_2FA_TELEGRAM.pop(chat_id_str, None)
        db.query(TokenMobile).filter(
            TokenMobile.token.like(f"2FA_TG:{chat_id_str}:%")
        ).delete(synchronize_session=False)

        db.commit()
        return {
            "sucesso": True,
            "usuario": {
                "id": dono.id,
                "nome": dono.nome,
                "email": dono.email,
                "telegram_username": dono.telegram_username,
                "telegram_id": chat_id_str
            }
        }
    except Exception as e:
        db.rollback()
        print(f"⚠️ Erro em confirmar_codigo_2fa_telegram: {e}")
        return {"sucesso": False, "erro": f"Erro ao validar código 2FA: {e}"}
    finally:
        db.close()


def validar_e_consumir_token_mobile(token: str, codigo_2fa: str = None) -> dict:
    """Valida o código 2FA quando o QR Code é aberto pelo navegador do celular."""
    token_limpo = (token or "").strip()
    codigo_limpo = re.sub(r"\D", "", str(codigo_2fa or ""))

    if not token_limpo:
        return {"sucesso": False, "erro": "Token ausente."}
    if len(codigo_limpo) != 6:
        return {"sucesso": False, "erro": "Digite os 6 dígitos do código enviado ao seu e-mail."}

    db = SessionLocal()
    try:
        reg = db.query(TokenMobile).filter(TokenMobile.token == token_limpo).first()
        dono = None
        if reg:
            dono = db.query(Usuario).filter(Usuario.id == reg.usuario_id).first()
        if not dono:
            dono = db.query(Usuario).filter(Usuario.codigo_2fa == codigo_limpo).first()

        if not dono or not dono.codigo_2fa:
            return {"sucesso": False, "erro": "Sessão do QR Code expirada ou inválida. Gere um novo QR Code."}

        if str(dono.codigo_2fa).strip() != codigo_limpo:
            return {"sucesso": False, "erro": "Código de 6 dígitos incorreto."}

        dono.codigo_2fa = None
        dono.expiracao_2fa = None
        dono.status_2fa = 1
        dono.primeiro_login = 0
        if reg:
            db.delete(reg)
        db.commit()

        return {
            "sucesso": True,
            "usuario": {
                "id": dono.id,
                "nome": dono.nome,
                "email": dono.email,
                "telegram": dono.telegram_username
            }
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao validar 2FA mobile: {e}"}
    finally:
        db.close()


def obter_ou_vincular_usuario_telegram(
    chat_id: str,
    username: str = "",
    first_name: str = "Usuário Telegram",
    token_vinculo: str = None
) -> dict:
    """
    Retorna o usuário vinculado ao `chat_id` atual.
    Se o usuário já cadastrou seu `@telegram_username` ou `telegram_id` no painel Web,
    reconhece a conta automaticamente.
    """
    chat_id_str = str(chat_id).strip()
    user_arroba = normalizar_username_telegram(username)
    user_sem_arroba = user_arroba.lstrip("@")

    db = SessionLocal()
    try:
        # 1. Busca pelo `telegram_id` ou `telegram_chat_id` já vinculado
        user = db.execute(
            text("""
                SELECT id, nome, email, telegram_username, telegram_id, telegram_chat_id
                FROM usuarios
                WHERE telegram_id = :cid OR telegram_chat_id = :cid
            """),
            {"cid": chat_id_str}
        ).fetchone()

        if user:
            return {
                "autenticado": True,
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram_username": user.telegram_username or user_arroba,
                "telegram_id": chat_id_str
            }

        # 2. Se não achou por ID, verifica se o @username do Telegram pertence a uma conta Web sem outro ID conflitante
        if user_arroba:
            user_por_nome = db.execute(
                text("""
                    SELECT id, nome, email, telegram_username, telegram_id, telegram_chat_id
                    FROM usuarios
                    WHERE lower(telegram_username) = :u1 OR lower(telegram_username) = :u2
                """),
                {"u1": user_arroba.lower(), "u2": user_sem_arroba.lower()}
            ).fetchone()

            if user_por_nome:
                id_atual = str(user_por_nome.telegram_id or user_por_nome.telegram_chat_id or "").strip()
                if not id_atual or id_atual == chat_id_str:
                    db.execute(
                        text("""
                            UPDATE usuarios
                            SET telegram_id = :cid, telegram_chat_id = :cid
                            WHERE id = :uid
                        """),
                        {"cid": chat_id_str, "uid": user_por_nome.id}
                    )
                    db.commit()
                    return {
                        "autenticado": True,
                        "id": user_por_nome.id,
                        "nome": user_por_nome.nome,
                        "email": user_por_nome.email,
                        "telegram_username": user_arroba,
                        "telegram_id": chat_id_str
                    }

        return {
            "autenticado": False,
            "id": None,
            "nome": first_name,
            "email": ""
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
        tg_id_final = user.telegram_id or user.telegram_chat_id or ""
        return {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "telegram": user.telegram_username or "",
            "telegram_username": user.telegram_username or "",
            "telegram_id": tg_id_final,
            "telegram_chat_id": tg_id_final,
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
            tg_norm = normalizar_username_telegram(telegram_username)
            db.execute(
                text("UPDATE usuarios SET telegram_username = NULL WHERE id != :uid AND lower(telegram_username) = :tg"),
                {"uid": uid_real, "tg": tg_norm.lower()}
            )
            user.telegram_username = tg_norm

        if telegram_id is not None and str(telegram_id).strip():
            tg_id_limpo = str(telegram_id).strip()
            db.execute(
                text("""
                    UPDATE usuarios
                    SET telegram_id = NULL, telegram_chat_id = NULL
                    WHERE id != :uid AND (telegram_id = :cid OR telegram_chat_id = :cid)
                """),
                {"uid": uid_real, "cid": tg_id_limpo}
            )
            user.telegram_id = tg_id_limpo
            user.telegram_chat_id = tg_id_limpo

        user.atualizado_em = datetime.utcnow()
        db.commit()
        tg_id_final = user.telegram_id or user.telegram_chat_id or ""
        return {
            "sucesso": True,
            "mensagem": "Configurações salvas com sucesso!",
            "usuario": {
                "id": user.id,
                "nome": user.nome,
                "email": user.email,
                "telegram_username": user.telegram_username or "",
                "telegram_id": tg_id_final,
                "telegram_chat_id": tg_id_final
            }
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao atualizar configurações: {e}"}
    finally:
        db.close()


# =====================================================================
# CHAT E HISTÓRICO (`mensagens_chat` / `historico_mensagens`)
# =====================================================================

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

        nova_msg = MensagemChat(
            conversa_id=conversa_id,
            usuario_id=uid_real,
            remetente=rem,
            mensagem=str(mensagem)
        )
        db.add(nova_msg)

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


def limpar_historico_conversa(usuario_id: int) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        db.query(MensagemChat).filter(MensagemChat.usuario_id == uid_real).delete()
        db.query(HistoricoMensagem).filter(HistoricoMensagem.usuario_id == uid_real).delete()
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


# =====================================================================
# TRANSAÇÕES, RENDAS FIXAS, GASTOS FIXOS E TETOS DE GASTOS
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


adicionar_renda_fixa = criar_renda_fixa


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


adicionar_gasto_fixo = criar_gasto_fixo


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


def salvar_teto_gasto(usuario_id: int, categoria: str, valor_teto: float) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    cat_limpa = (categoria or "").strip()
    if not cat_limpa or float(valor_teto) <= 0:
        return {"sucesso": False, "erro": "Informe uma categoria válida e valor maior que zero."}

    db = SessionLocal()
    try:
        existente = (
            db.query(TetoGasto)
            .filter(TetoGasto.usuario_id == uid_real, func.lower(TetoGasto.categoria) == cat_limpa.lower())
            .first()
        )
        if existente:
            existente.valor_teto = round(float(valor_teto), 2)
            existente.atualizado_em = datetime.utcnow()
        else:
            novo = TetoGasto(
                usuario_id=uid_real,
                categoria=cat_limpa,
                valor_teto=round(float(valor_teto), 2)
            )
            db.add(novo)
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao salvar teto de gastos: {e}"}
    finally:
        db.close()


def listar_tetos_gastos(usuario_id: int) -> list:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    db = SessionLocal()
    try:
        tetos = db.query(TetoGasto).filter(TetoGasto.usuario_id == uid_real).order_by(TetoGasto.categoria.asc()).all()
        transacoes_despesa = (
            db.query(Transacao)
            .filter(Transacao.usuario_id == uid_real, Transacao.tipo == "despesa")
            .all()
        )
        fixas_ativas = (
            db.query(DespesaFixa)
            .filter(DespesaFixa.usuario_id == uid_real, DespesaFixa.ativo == 1)
            .all()
        )

        resultado = []
        for t in tetos:
            alvo = (t.categoria or "").strip().lower()
            gasto_var = sum(
                float(tr.valor or 0.0)
                for tr in transacoes_despesa
                if (tr.categoria or "").strip().lower() == alvo or alvo in (tr.descricao or "").strip().lower()
            )
            gasto_fix = sum(
                float(fx.valor or 0.0)
                for fx in fixas_ativas
                if (fx.categoria or "").strip().lower() == alvo or alvo in (fx.descricao or "").strip().lower()
            )
            gasto_atual = round(gasto_var + gasto_fix, 2)
            val_teto = float(t.valor_teto or 0.0)
            perc = round((gasto_atual / val_teto) * 100, 1) if val_teto > 0 else 0.0
            resultado.append({
                "id": t.id,
                "categoria": t.categoria,
                "valor_teto": val_teto,
                "gasto_atual": gasto_atual,
                "disponivel": max(0.0, round(val_teto - gasto_atual, 2)),
                "percentual": perc,
                "estourou": gasto_atual > val_teto
            })
        return resultado
    finally:
        db.close()


def excluir_teto_gasto(usuario_id: int, categoria: str) -> dict:
    uid_real = garantir_usuario_sincronizado(usuario_id)
    cat_limpa = (categoria or "").strip().lower()
    db = SessionLocal()
    try:
        item = (
            db.query(TetoGasto)
            .filter(TetoGasto.usuario_id == uid_real, func.lower(TetoGasto.categoria) == cat_limpa)
            .first()
        )
        if not item:
            return {"sucesso": False, "erro": "Teto não encontrado."}
        db.delete(item)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


# Caminho: core/database.py (Substitua a função obter_resumo_financeiro inteira)

def obter_resumo_financeiro(usuario_id: int, periodo: str = "mes_atual") -> dict:
    """
    Calcula o resumo financeiro completo diretamente nas tabelas em português do MySQL:
    - transacoes (usuario_id, valor, tipo, categoria, descricao)
    - receitas_fixas (usuario_id, valor, ativo)
    - despesas_fixas (usuario_id, valor, ativo)
    - tetos_gastos (via listar_tetos_gastos)
    """
    db = SessionLocal()
    try:
        uid = int(usuario_id)

        receitas_var = db.execute(
            text("SELECT COALESCE(SUM(valor), 0) FROM transacoes WHERE usuario_id = :uid AND tipo = 'receita'"),
            {"uid": uid}
        ).scalar() or 0.0

        despesas_var = db.execute(
            text("SELECT COALESCE(SUM(valor), 0) FROM transacoes WHERE usuario_id = :uid AND tipo = 'despesa'"),
            {"uid": uid}
        ).scalar() or 0.0

        try:
            rendas_fixas = db.execute(
                text("SELECT COALESCE(SUM(valor), 0) FROM receitas_fixas WHERE usuario_id = :uid AND ativo = 1"),
                {"uid": uid}
            ).scalar() or 0.0
        except Exception:
            db.rollback()
            rendas_fixas = 0.0

        try:
            gastos_fixos = db.execute(
                text("SELECT COALESCE(SUM(valor), 0) FROM despesas_fixas WHERE usuario_id = :uid AND ativo = 1"),
                {"uid": uid}
            ).scalar() or 0.0
        except Exception:
            db.rollback()
            gastos_fixos = 0.0

        total_lancamentos = db.execute(
            text("SELECT COUNT(id) FROM transacoes WHERE usuario_id = :uid"),
            {"uid": uid}
        ).scalar() or 0

        # 1. Agrupamento por Categoria (Gráfico de Pizza)
        cats_rows = db.execute(
            text("""
                SELECT COALESCE(categoria, 'Outros') AS categoria, COALESCE(SUM(valor), 0) AS total
                FROM transacoes
                WHERE usuario_id = :uid AND tipo = 'despesa'
                GROUP BY categoria
                ORDER BY total DESC
            """),
            {"uid": uid}
        ).fetchall()

        por_categoria = [{"categoria": r[0] or "Outros", "total": float(r[1] or 0.0)} for r in cats_rows]

        total_entradas = float(receitas_var) + float(rendas_fixas)
        total_saidas = float(despesas_var) + float(gastos_fixos)
        saldo_atual = total_entradas - total_saidas

        labels_pizza = [c["categoria"] for c in por_categoria]
        valores_pizza = [c["total"] for c in por_categoria]
        if float(gastos_fixos) > 0:
            labels_pizza.append("Gastos Fixos")
            valores_pizza.append(float(gastos_fixos))

        # 2. Evolução Acumulada do Saldo (Gráfico de Linha)
        movs_rows = db.execute(
            text("""
                SELECT id, tipo, COALESCE(valor, 0) AS valor
                FROM transacoes
                WHERE usuario_id = :uid
                ORDER BY id ASC
            """),
            {"uid": uid}
        ).fetchall()

        saldo_base_fixo = float(rendas_fixas) - float(gastos_fixos)
        labels_evolucao = []
        saldos_evolucao = []
        saldo_acumulado = saldo_base_fixo

        if saldo_base_fixo != 0 or not movs_rows:
            labels_evolucao.append("Base Fixa")
            saldos_evolucao.append(round(saldo_acumulado, 2))

        for m in movs_rows:
            mov_id, mov_tipo, mov_val = m[0], m[1], float(m[2] or 0.0)
            if mov_tipo == "receita":
                saldo_acumulado += mov_val
            else:
                saldo_acumulado -= mov_val
            labels_evolucao.append(f"#{mov_id}")
            saldos_evolucao.append(round(saldo_acumulado, 2))

        tetos = listar_tetos_gastos(uid)

        return {
            "mes_referencia": datetime.utcnow().strftime("%m/%Y"),
            "total_receitas": total_entradas,
            "total_despesas": total_saidas,
            "total_entradas": total_entradas,
            "total_saidas": total_saidas,
            "receitas_variaveis": float(receitas_var),
            "despesas_variaveis": float(despesas_var),
            "rendas_fixas": float(rendas_fixas),
            "total_rendas_fixas": float(rendas_fixas),
            "gastos_fixos": float(gastos_fixos),
            "total_gastos_fixos": float(gastos_fixos),
            "saldo": saldo_atual,
            "saldo_atual": saldo_atual,
            "total_lancamentos": int(total_lancamentos),
            "despesas_por_categoria": por_categoria,
            "tetos_gastos": tetos,
            "grafico_pizza": {
                "labels": labels_pizza,
                "valores": valores_pizza
            },
            "grafico_colunas": {
                "labels": ["Entradas vs. Saídas"],
                "entradas": [total_entradas],
                "saidas": [total_saidas]
            },
            "grafico_evolucao": {
                "labels": labels_evolucao[-15:],
                "saldos": saldos_evolucao[-15:]
            }
        }
    finally:
        db.close()