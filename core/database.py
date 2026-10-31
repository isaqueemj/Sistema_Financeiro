# Caminho: core/database.py
import os
import secrets
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, func, extract
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SQLITE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'historico_ia.db')}"

raw_db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

DATABASE_URL = raw_db_url if raw_db_url else DEFAULT_SQLITE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

# Oتستea pe jeike Supabase-pe; oiméramo ojavy, oipuru SQLite local ani hag̃ua opyta pe sistema
if not DATABASE_URL.startswith("sqlite"):
    try:
        with engine.connect() as _conn:
            _conn.execute(text("SELECT 1"))
        print("✅ Ojekonekta porã PostgreSQL (Supabase) rehe!")
    except Exception as _err:
        print(f"⚠️ Ndikatúi ojekonekta Supabase rehe ({_err}). Ojeipurúta SQLite local.")
        DATABASE_URL = DEFAULT_SQLITE_URL
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()

# ==================== MODELOS SQLALCHEMY ====================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    telegram_chat_id = Column(String(50), unique=True, nullable=True, index=True)
    telegram_username = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    incomes = relationship("FixedIncome", back_populates="user", cascade="all, delete-orphan")
    expenses = relationship("FixedExpense", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")


class FixedIncome(Base):
    __tablename__ = "fixed_incomes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    day_of_month = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="incomes")


class FixedExpense(Base):
    __tablename__ = "fixed_expenses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    due_day = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="expenses")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(20), nullable=False)  # 'receita' ou 'despesa'
    valor = Column(Float, nullable=False)
    categoria = Column(String(100), nullable=False)
    descricao = Column(String(255), nullable=True)
    moeda = Column(String(10), default="BRL", nullable=False)
    data_transacao = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    remetente = Column(String(20), nullable=False)  # 'usuario' ou 'ia'
    mensagem = Column(String, nullable=False)
    data_envio = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="messages")


class MobileToken(Base):
    __tablename__ = "mobile_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(100), unique=True, nullable=False, index=True)
    expira_em = Column(DateTime, nullable=False)
    usado = Column(Boolean, default=False)


def init_db():
    Base.metadata.create_all(bind=engine)


# ==================== FUNÇÕES DE USUÁRIO E AUTENTICAÇÃO ====================

def criar_usuario(nome: str, email: str, senha_plana: str, telegram_username: str = None) -> dict:
    db = SessionLocal()
    try:
        email_limpo = email.strip().lower()
        tg_user = telegram_username.strip().lstrip("@") if telegram_username else None
        senha_hash = generate_password_hash(senha_plana, method="pbkdf2:sha256", salt_length=16)

        novo = User(
            name=nome.strip(),
            email=email_limpo,
            password_hash=senha_hash,
            telegram_username=tg_user
        )
        db.add(novo)
        db.commit()
        db.refresh(novo)
        return {"sucesso": True, "id": novo.id}
    except IntegrityError:
        db.rollback()
        return {"sucesso": False, "erro": "E-mail já cadastrado no sistema."}
    finally:
        db.close()


def autenticar_usuario(email: str, senha_plana: str) -> dict:
    db = SessionLocal()
    try:
        email_limpo = email.strip().lower()
        user = db.query(User).filter(User.email == email_limpo).first()
        if not user:
            return {"sucesso": False, "erro": "E-mail ou senha incorretos."}

        if not user.password_hash.startswith(("pbkdf2:", "scrypt:")):
            if user.password_hash == senha_plana:
                user.password_hash = generate_password_hash(senha_plana, method="pbkdf2:sha256", salt_length=16)
                db.commit()
            else:
                return {"sucesso": False, "erro": "E-mail ou senha incorretos."}
        elif not check_password_hash(user.password_hash, senha_plana):
            return {"sucesso": False, "erro": "E-mail ou senha incorretos."}

        return {
            "sucesso": True,
            "usuario": {
                "id": user.id,
                "nome": user.name,
                "email": user.email,
                "telegram_chat_id": user.telegram_chat_id,
                "telegram_username": user.telegram_username
            }
        }
    finally:
        db.close()


def obter_usuario_por_id(usuario_id: int) -> dict:
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == usuario_id).first()
        if not u:
            return None
        return {
            "id": u.id,
            "nome": u.name,
            "email": u.email,
            "telegram_chat_id": u.telegram_chat_id or "",
            "telegram_username": u.telegram_username or "",
            "data_criacao": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""
        }
    finally:
        db.close()


def atualizar_configuracoes_usuario(usuario_id: int, nome: str, telegram_username: str = None, telegram_chat_id: str = None) -> dict:
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == usuario_id).first()
        if not u:
            return {"sucesso": False, "erro": "Usuário não encontrado."}

        u.name = nome.strip()
        u.telegram_username = telegram_username.strip().lstrip("@") if telegram_username else None
        if telegram_chat_id is not None:
            chat_id_clean = str(telegram_chat_id).strip()
            u.telegram_chat_id = chat_id_clean if chat_id_clean else None

        db.commit()
        return {
            "sucesso": True,
            "telegram_username": u.telegram_username or "",
            "telegram_chat_id": u.telegram_chat_id or ""
        }
    except IntegrityError:
        db.rollback()
        return {"sucesso": False, "erro": "Este Chat ID do Telegram já está vinculado a outra conta."}
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


# ==================== CRUD DE RENDAS FIXAS (FixedIncome) ====================

def criar_renda_fixa(usuario_id: int, description: str, amount: float, day_of_month: int, is_active: bool = True) -> dict:
    if amount <= 0:
        return {"sucesso": False, "erro": "O valor da renda fixa deve ser maior que zero."}
    if not (1 <= int(day_of_month) <= 31):
        return {"sucesso": False, "erro": "O dia de recebimento deve estar entre 1 e 31."}

    db = SessionLocal()
    try:
        nova = FixedIncome(
            user_id=usuario_id,
            description=description.strip(),
            amount=float(amount),
            day_of_month=int(day_of_month),
            is_active=bool(is_active)
        )
        db.add(nova)
        db.commit()
        db.refresh(nova)
        return {
            "sucesso": True,
            "item": {
                "id": nova.id,
                "description": nova.description,
                "amount": nova.amount,
                "day_of_month": nova.day_of_month,
                "is_active": nova.is_active
            }
        }
    finally:
        db.close()


def listar_rendas_fixas(usuario_id: int) -> list:
    db = SessionLocal()
    try:
        itens = db.query(FixedIncome).filter(FixedIncome.user_id == usuario_id).order_by(FixedIncome.day_of_month.asc()).all()
        return [
            {
                "id": i.id,
                "description": i.description,
                "amount": float(i.amount),
                "day_of_month": i.day_of_month,
                "is_active": bool(i.is_active),
                "created_at": i.created_at.strftime("%Y-%m-%d") if i.created_at else ""
            }
            for i in itens
        ]
    finally:
        db.close()


def atualizar_renda_fixa(usuario_id: int, renda_id: int, description: str, amount: float, day_of_month: int, is_active: bool = True) -> dict:
    if amount <= 0 or not (1 <= int(day_of_month) <= 31):
        return {"sucesso": False, "erro": "Verifique se o valor é positivo e o dia está entre 1 e 31."}

    db = SessionLocal()
    try:
        item = db.query(FixedIncome).filter(FixedIncome.id == renda_id, FixedIncome.user_id == usuario_id).first()
        if not item:
            return {"sucesso": False, "erro": "Renda fixa não encontrada."}

        item.description = description.strip()
        item.amount = float(amount)
        item.day_of_month = int(day_of_month)
        item.is_active = bool(is_active)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


def deletar_renda_fixa(usuario_id: int, renda_id: int) -> dict:
    db = SessionLocal()
    try:
        item = db.query(FixedIncome).filter(FixedIncome.id == renda_id, FixedIncome.user_id == usuario_id).first()
        if not item:
            return {"sucesso": False, "erro": "Renda fixa não encontrada."}
        db.delete(item)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


# ==================== CRUD DE GASTOS FIXOS (FixedExpense) ====================

def criar_gasto_fixo(usuario_id: int, description: str, amount: float, due_day: int, is_active: bool = True) -> dict:
    if amount <= 0:
        return {"sucesso": False, "erro": "O valor do gasto fixo deve ser maior que zero."}
    if not (1 <= int(due_day) <= 31):
        return {"sucesso": False, "erro": "O dia de vencimento deve estar entre 1 e 31."}

    db = SessionLocal()
    try:
        novo = FixedExpense(
            user_id=usuario_id,
            description=description.strip(),
            amount=float(amount),
            due_day=int(due_day),
            is_active=bool(is_active)
        )
        db.add(novo)
        db.commit()
        db.refresh(novo)
        return {
            "sucesso": True,
            "item": {
                "id": novo.id,
                "description": novo.description,
                "amount": novo.amount,
                "due_day": novo.due_day,
                "is_active": novo.is_active
            }
        }
    finally:
        db.close()


def listar_gastos_fixos(usuario_id: int) -> list:
    db = SessionLocal()
    try:
        itens = db.query(FixedExpense).filter(FixedExpense.user_id == usuario_id).order_by(FixedExpense.due_day.asc()).all()
        return [
            {
                "id": i.id,
                "description": i.description,
                "amount": float(i.amount),
                "due_day": i.due_day,
                "is_active": bool(i.is_active),
                "created_at": i.created_at.strftime("%Y-%m-%d") if i.created_at else ""
            }
            for i in itens
        ]
    finally:
        db.close()


def atualizar_gasto_fixo(usuario_id: int, gasto_id: int, description: str, amount: float, due_day: int, is_active: bool = True) -> dict:
    if amount <= 0 or not (1 <= int(due_day) <= 31):
        return {"sucesso": False, "erro": "Verifique se o valor é positivo e o dia de vencimento está entre 1 e 31."}

    db = SessionLocal()
    try:
        item = db.query(FixedExpense).filter(FixedExpense.id == gasto_id, FixedExpense.user_id == usuario_id).first()
        if not item:
            return {"sucesso": False, "erro": "Gasto fixo não encontrado."}

        item.description = description.strip()
        item.amount = float(amount)
        item.due_day = int(due_day)
        item.is_active = bool(is_active)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


def deletar_gasto_fixo(usuario_id: int, gasto_id: int) -> dict:
    db = SessionLocal()
    try:
        item = db.query(FixedExpense).filter(FixedExpense.id == gasto_id, FixedExpense.user_id == usuario_id).first()
        if not item:
            return {"sucesso": False, "erro": "Gasto fixo não encontrado."}
        db.delete(item)
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()


# ==================== TRANSAÇÕES VARIÁVEIS E RESUMO CONSOLIDADO ====================

def registrar_transacao(usuario_id: int, tipo: str, valor: float, categoria: str, descricao: str = "", moeda: str = "BRL") -> dict:
    if moeda.upper() != "BRL":
        return {"sucesso": False, "erro": "Operação negada (RN04): O sistema utiliza exclusivamente o Real (BRL)."}
    if valor <= 0:
        return {"sucesso": False, "erro": "O valor da transação deve ser maior que zero."}

    tipo_formatado = tipo.lower().strip()
    if tipo_formatado not in ("receita", "despesa"):
        return {"sucesso": False, "erro": "Tipo inválido. Use 'receita' ou 'despesa'."}

    resumo_antes = obter_resumo_financeiro(usuario_id)
    alerta_risco = None
    if tipo_formatado == "despesa" and valor > resumo_antes["saldo"]:
        alerta_risco = (
            f"⚠️ Alerta de Risco (RN02): Esta despesa (R$ {valor:.2f}) ultrapassa seu saldo disponível "
            f"antes do lançamento (R$ {resumo_antes['saldo']:.2f})."
        )

    db = SessionLocal()
    try:
        nova = Transaction(
            user_id=usuario_id,
            tipo=tipo_formatado,
            valor=float(valor),
            categoria=categoria.strip().capitalize(),
            descricao=descricao.strip(),
            moeda="BRL"
        )
        db.add(nova)
        db.commit()
        db.refresh(nova)
        return {"sucesso": True, "id": nova.id, "alerta": alerta_risco}
    finally:
        db.close()


def obter_resumo_financeiro(usuario_id: int, periodo: str = "mes_atual") -> dict:
    """
    Calcula em tempo real os valores exatos de Entradas (Receitas), Saídas (Gastos)
    e Saldo Atual do mês vigente (ou de todo o período), preparando também os payloads
    para o Gráfico de Pizza e para o Gráfico de Colunas.
    """
    db = SessionLocal()
    try:
        agora = datetime.now()
        inicio_mes = datetime(agora.year, agora.month, 1, 0, 0, 0)

        # Query base de transações variáveis do usuário
        query_base = db.query(Transaction).filter(Transaction.user_id == usuario_id)

        if periodo == "mes_atual":
            query_periodo = query_base.filter(Transaction.data_transacao >= inicio_mes)
        elif periodo == "ultimos_30_dias":
            limite_30d = agora - timedelta(days=30)
            query_periodo = query_base.filter(Transaction.data_transacao >= limite_30d)
        else:
            query_periodo = query_base

        transacoes_filtradas = query_periodo.all()

        # Fallback inteligente: se o mês vigente não tiver transações variáveis mas o usuário
        # tiver lançamentos anteriores e o filtro for padrão, calcula ambos para não zerar a tela indevidamente
        receitas_var = sum(float(t.valor) for t in transacoes_filtradas if t.tipo == "receita")
        despesas_var = sum(float(t.valor) for t in transacoes_filtradas if t.tipo == "despesa")
        qtd_var = len(transacoes_filtradas)

        # Busca Rendas Fixas Ativas e Gastos Fixos Ativos do mês
        rendas_fixas_lista = db.query(FixedIncome).filter(
            FixedIncome.user_id == usuario_id,
            FixedIncome.is_active == True
        ).all()

        gastos_fixos_lista = db.query(FixedExpense).filter(
            FixedExpense.user_id == usuario_id,
            FixedExpense.is_active == True
        ).all()

        total_rendas_fixas = sum(float(r.amount) for r in rendas_fixas_lista)
        total_gastos_fixos = sum(float(g.amount) for g in gastos_fixos_lista)

        # Totais consolidados do mês vigente
        total_entradas = round(receitas_var + total_rendas_fixas, 2)
        total_saidas = round(despesas_var + total_gastos_fixos, 2)
        saldo_atual = round(total_entradas - total_saidas, 2)

        # 1. Agrupamento para o GRÁFICO DE PIZZA (Gastos por Categoria / Local)
        mapa_categorias = {}
        for t in transacoes_filtradas:
            if t.tipo == "despesa":
                chave = (t.categoria or "Outros").strip().capitalize()
                mapa_categorias[chave] = round(mapa_categorias.get(chave, 0.0) + float(t.valor), 2)

        # Inclui os Gastos Fixos detalhados por descrição/categoria no Gráfico de Pizza
        for gf in gastos_fixos_lista:
            nome_fixo = f"Fixo: {gf.description.strip().capitalize()}"
            mapa_categorias[nome_fixo] = round(mapa_categorias.get(nome_fixo, 0.0) + float(gf.amount), 2)

        despesas_por_categoria = [
            {"categoria": k, "total": v}
            for k, v in sorted(mapa_categorias.items(), key=lambda item: item[1], reverse=True)
        ]

        # 2. Agrupamento para o GRÁFICO DE COLUNAS (Entradas vs. Saídas nos últimos 6 meses)
        nomes_meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        todas_transacoes = query_base.all()

        historico_mensal = []
        for i in range(5, -1, -1):
            mes_calc = agora.month - i
            ano_calc = agora.year
            while mes_calc <= 0:
                mes_calc += 12
                ano_calc -= 1

            label_mes = f"{nomes_meses[mes_calc - 1]}/{str(ano_calc)[2:]}"

            rec_mes = sum(
                float(t.valor) for t in todas_transacoes
                if t.tipo == "receita" and t.data_transacao and t.data_transacao.year == ano_calc and t.data_transacao.month == mes_calc
            )
            desp_mes = sum(
                float(t.valor) for t in todas_transacoes
                if t.tipo == "despesa" and t.data_transacao and t.data_transacao.year == ano_calc and t.data_transacao.month == mes_calc
            )

            # No mês vigente (ou meses com movimentação), soma as parcelas fixas ativas
            eh_mes_atual = (ano_calc == agora.year and mes_calc == agora.month)
            entradas_periodo = round(rec_mes + (total_rendas_fixas if (eh_mes_atual or rec_mes > 0) else 0.0), 2)
            saidas_periodo = round(desp_mes + (total_gastos_fixos if (eh_mes_atual or desp_mes > 0) else 0.0), 2)

            historico_mensal.append({
                "periodo": label_mes,
                "entradas": entradas_periodo,
                "saidas": saidas_periodo,
                "saldo": round(entradas_periodo - saidas_periodo, 2)
            })

        return {
            "periodo_selecionado": periodo,
            "mes_referencia": f"{nomes_meses[agora.month - 1]}/{agora.year}",
            "receitas_variaveis": round(receitas_var, 2),
            "despesas_variaveis": round(despesas_var, 2),
            "total_rendas_fixas": round(total_rendas_fixas, 2),
            "total_gastos_fixos": round(total_gastos_fixos, 2),
            "total_receitas": total_entradas,
            "total_despesas": total_saidas,
            "saldo": saldo_atual,
            "total_lancamentos": qtd_var + len(rendas_fixas_lista) + len(gastos_fixos_lista),
            "despesas_por_categoria": despesas_por_categoria,
            "grafico_pizza": {
                "labels": [item["categoria"] for item in despesas_por_categoria],
                "valores": [item["total"] for item in despesas_por_categoria]
            },
            "grafico_colunas": {
                "labels": [m["periodo"] for m in historico_mensal],
                "entradas": [m["entradas"] for m in historico_mensal],
                "saidas": [m["saidas"] for m in historico_mensal]
            }
        }
    finally:
        db.close()

def listar_transacoes(usuario_id: int, limite: int = 50) -> list:
    db = SessionLocal()
    try:
        rows = db.query(Transaction).filter(
            Transaction.user_id == usuario_id
        ).order_by(Transaction.id.desc()).limit(limite).all()
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


# ==================== HISTÓRICO DE CONVERSA E TOKENS MOBILE ====================

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
        rows = db.query(ChatMessage).filter(
            ChatMessage.user_id == usuario_id
        ).order_by(ChatMessage.id.desc()).limit(limite).all()
        rows.reverse()
        return [
            {
                "id": r.id,
                "remetente": r.remetente,
                "mensagem": r.mensagem,
                "data_envio": r.data_envio.strftime("%Y-%m-%d %H:%M:%S") if r.data_envio else ""
            }
            for r in rows
        ]
    finally:
        db.close()


def gerar_token_mobile(usuario_id: int, minutos_validade: int = 10) -> dict:
    db = SessionLocal()
    try:
        token = secrets.token_urlsafe(24)
        expira = datetime.utcnow() + timedelta(minutes=minutos_validade)
        db.query(MobileToken).filter(MobileToken.user_id == usuario_id, MobileToken.usado == False).update({"usado": True})
        novo = MobileToken(user_id=usuario_id, token=token, expira_em=expira, usado=False)
        db.add(novo)
        db.commit()
        return {"token": token, "validade_segundos": minutos_validade * 60}
    finally:
        db.close()


def validar_e_consumir_token_mobile(token: str) -> dict:
    db = SessionLocal()
    try:
        reg = db.query(MobileToken).filter(MobileToken.token == token).first()
        if not reg:
            return {"sucesso": False, "erro": "QR Code inválido ou não encontrado."}
        if reg.usado:
            return {"sucesso": False, "erro": "Este QR Code já foi utilizado. Gere um novo no computador."}
        if reg.expira_em < datetime.utcnow():
            return {"sucesso": False, "erro": "Este QR Code expirou. Gere um novo na aba Configurações."}

        user = db.query(User).filter(User.id == reg.user_id).first()
        if not user:
            return {"sucesso": False, "erro": "Usuário não encontrado."}

        reg.usado = True
        db.commit()
        return {
            "sucesso": True,
            "usuario": {"id": user.id, "nome": user.name, "email": user.email}
        }
    finally:
        db.close()

def garantir_colunas_autenticacao_2fa():
    """Garante que a tabela de usuários possua as colunas para @Telegram obrigatório, 2FA e Reset de Senha."""
    comandos_migracao = [
        "ALTER TABLE users ADD COLUMN telegram_username VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN primeiro_login BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN codigo_2fa VARCHAR(10)",
        "ALTER TABLE users ADD COLUMN expira_2fa DATETIME",
        "ALTER TABLE users ADD COLUMN token_reset_senha VARCHAR(128)",
        "ALTER TABLE users ADD COLUMN expira_reset_senha DATETIME"
    ]
    with engine.begin() as conn:
        for cmd in comandos_migracao:
            try:
                conn.execute(text(cmd))
            except Exception:
                pass


def mascarar_email(email: str) -> str:
    if not email or "@" not in email:
        return email
    usuario, dominio = email.split("@", 1)
    prefixo = usuario[:2] if len(usuario) > 2 else usuario[:1]
    return f"{prefixo}***@{dominio}"

def criar_usuario_com_telegram_obrigatorio(nome: str, email: str, senha_plana: str, telegram: str) -> dict:
    garantir_colunas_autenticacao_2fa()
    email_limpo = (email or "").strip().lower()
    telegram_limpo = (telegram or "").strip()

    if not telegram_limpo:
        return {"sucesso": False, "erro": "O @Telegram é obrigatório para realizar o cadastro."}

    if not telegram_limpo.startswith("@"):
        telegram_limpo = "@" + telegram_limpo

    senha_hash = generate_password_hash(senha_plana, method="pbkdf2:sha256", salt_length=16)
    db = SessionLocal()
    try:
        # Verifica duplicidade de e-mail ou @Telegram
        existente = db.execute(
            text("SELECT id FROM users WHERE lower(email) = :email OR lower(telegram_username) = :tg"),
            {"email": email_limpo, "tg": telegram_limpo.lower()}
        ).fetchone()

        if existente:
            return {"sucesso": False, "erro": "E-mail ou @Telegram já está cadastrado em outra conta."}

        res = db.execute(
            text("""
                INSERT INTO users (nome, email, senha_hash, telegram_username, primeiro_login)
                VALUES (:nome, :email, :senha_hash, :tg, 1)
            """),
            {
                "nome": nome.strip(),
                "email": email_limpo,
                "senha_hash": senha_hash,
                "tg": telegram_limpo
            }
        )
        db.commit()
        return {"sucesso": True, "id": res.lastrowid}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao salvar usuário: {e}"}
    finally:
        db.close()

def iniciar_login_hibrido(identificador: str, senha_plana: str) -> dict:
    """
    Autentica por E-mail ou @Telegram.
    Se for o 1º login do usuário (primeiro_login == 1), gera código 2FA de 6 dígitos.
    """
    garantir_colunas_autenticacao_2fa()
    ident_limpo = (identificador or "").strip()
    if not ident_limpo:
        return {"sucesso": False, "erro": "Informe seu E-mail ou @Telegram."}

    busca_tg = ident_limpo if ident_limpo.startswith("@") else f"@{ident_limpo}"
    db = SessionLocal()
    try:
        user = db.execute(
            text("""
                SELECT id, nome, email, senha_hash, telegram_username, primeiro_login
                FROM users
                WHERE lower(email) = :ident OR lower(telegram_username) = :tg
            """),
            {"ident": ident_limpo.lower(), "tg": busca_tg.lower()}
        ).fetchone()

        if not user:
            return {"sucesso": False, "erro": "Usuário não encontrado com este E-mail ou @Telegram."}

        if not check_password_hash(user.senha_hash, senha_plana):
            return {"sucesso": False, "erro": "Senha incorreta."}

        # Verifica se é o 1º Login (exige 2FA)
        if user.primeiro_login is None or bool(user.primeiro_login) is True:
            codigo = f"{random.randint(100000, 999999)}"
            expira = datetime.utcnow() + timedelta(minutes=10)
            db.execute(
                text("UPDATE users SET codigo_2fa = :cod, expira_2fa = :exp WHERE id = :uid"),
                {"cod": codigo, "exp": expira, "uid": user.id}
            )
            db.commit()
            return {
                "sucesso": True,
                "requer_2fa": True,
                "codigo_gerado": codigo,
                "email_destino": user.email,
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
                "telegram": user.telegram_username
            }
        }
    finally:
        db.close()


def validar_codigo_2fa_banco(identificador: str, codigo: str) -> dict:
    garantir_colunas_autenticacao_2fa()
    ident_limpo = (identificador or "").strip().lower()
    codigo_limpo = (codigo or "").strip()

    db = SessionLocal()
    try:
        user = db.execute(
            text("""
                SELECT id, nome, email, telegram_username, codigo_2fa, expira_2fa
                FROM users
                WHERE lower(email) = :ident OR lower(telegram_username) = :ident
            """),
            {"ident": ident_limpo}
        ).fetchone()

        if not user or not user.codigo_2fa:
            return {"sucesso": False, "erro": "Nenhuma verificação pendente encontrada."}

        if str(user.codigo_2fa).strip() != codigo_limpo:
            return {"sucesso": False, "erro": "Código 2FA inválido."}

        # Marca primeiro_login = 0 e limpa o código usado
        db.execute(
            text("UPDATE users SET primeiro_login = 0, codigo_2fa = NULL, expira_2fa = NULL WHERE id = :uid"),
            {"uid": user.id}
        )
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


def gerar_token_recuperacao_senha(email: str) -> dict:
    garantir_colunas_autenticacao_2fa()
    email_limpo = (email or "").strip().lower()
    db = SessionLocal()
    try:
        user = db.execute(
            text("SELECT id, nome, email FROM users WHERE lower(email) = :email"),
            {"email": email_limpo}
        ).fetchone()

        if not user:
            return {"sucesso": False, "erro": "Não encontramos nenhuma conta cadastrada com este e-mail."}

        token = secrets.token_urlsafe(32)
        expira = datetime.utcnow() + timedelta(minutes=15)

        db.execute(
            text("UPDATE users SET token_reset_senha = :tok, expira_reset_senha = :exp WHERE id = :uid"),
            {"tok": token, "exp": expira, "uid": user.id}
        )
        db.commit()
        return {
            "sucesso": True,
            "token": token,
            "nome": user.nome,
            "email": user.email
        }
    finally:
        db.close()


def redefinir_senha_com_token(token: str, nova_senha: str) -> dict:
    garantir_colunas_autenticacao_2fa()
    if not token:
        return {"sucesso": False, "erro": "Token de recuperação ausente."}

    db = SessionLocal()
    try:
        user = db.execute(
            text("SELECT id, expira_reset_senha FROM users WHERE token_reset_senha = :tok"),
            {"tok": token.strip()}
        ).fetchone()

        if not user:
            return {"sucesso": False, "erro": "Link de recuperação inválido ou já utilizado."}

        novo_hash = generate_password_hash(nova_senha, method="pbkdf2:sha256", salt_length=16)
        db.execute(
            text("""
                UPDATE users 
                SET senha_hash = :sh, token_reset_senha = NULL, expira_reset_senha = NULL 
                WHERE id = :uid
            """),
            {"sh": novo_hash, "uid": user.id}
        )
        db.commit()
        return {"sucesso": True}
    finally:
        db.close()
