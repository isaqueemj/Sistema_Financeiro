# Caminho: core/ia.py
import os
import io
import re
import json
import time
import difflib
from datetime import datetime
from collections import defaultdict
import requests
from dotenv import load_dotenv
from sqlalchemy import text

try:
    from groq import Groq
except Exception:
    Groq = None

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.database import (
    SessionLocal,
    registrar_transacao,
    obter_resumo_financeiro,
    listar_historico_mensagens,
    listar_transacoes,
    criar_renda_fixa,
    listar_rendas_fixas,
    criar_gasto_fixo,
    listar_gastos_fixos
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODELO_GROQ = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Cache em memória para evitar registros duplicados
_CACHE_ANTI_DUPLICACAO = {}

MOEDAS_ESTRANGEIRAS_REGEX = re.compile(
    r"(\bUSD\b|\bEUR\b|\bGBP\b|\bARS\b|\bPYG\b|d[óo]lar|d[óo]lares|euro|euros|libra|pesos|guaranis|US\$|€|£)",
    re.IGNORECASE
)

CATEGORIAS_OFICIAIS = [
    "Alimentação", "Transporte", "Moradia", "Lazer",
    "Saúde", "Educação", "Vestuário", "Salário", "Renda Extra", "Outros"
]

MAPA_CATEGORIAS = {
    "Alimentação": ["mercado", "supermercado", "padaria", "lanche", "restaurante", "ifood", "pizza", "hamburguer", "almoço", "almoco", "janta", "jantar", "café", "cafe", "açougue", "acougue", "feira", "doces"],
    "Transporte": ["uber", "99", "gasolina", "combustível", "combustivel", "posto", "etanol", "diesel", "ônibus", "onibus", "passagem", "estacionamento", "pedágio", "pedagio", "oficina", "pneu"],
    "Moradia": ["aluguel", "condomínio", "condominio", "luz", "energia", "água", "agua", "internet", "gás", "gas", "iptu"],
    "Vestuário": ["camiseta", "camisa", "calça", "calca", "tênis", "tenis", "sapato", "roupa", "blusa", "jaqueta", "relógio", "relogio", "óculos", "oculos", "loja"],
    "Saúde": ["farmácia", "farmacia", "remédio", "remedio", "médico", "medico", "consulta", "exame", "dentista", "academia"],
    "Educação": ["faculdade", "curso", "livro", "mensalidade", "material", "udc", "escola"],
    "Lazer": ["cinema", "show", "viagem", "passeio", "bar", "cerveja", "jogo", "streaming", "netflix", "spotify"],
    "Salário": ["salário", "salario", "pagamento", "adiantamento", "vale", "bolsa", "estágio", "estagio"],
    "Renda Extra": ["freela", "freelance", "venda", "vendi", "pix recebido", "rendimento", "dividendo", "bônus", "bonus"]
}


def _sem_acentos(texto: str) -> str:
    mapa = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
        "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC"
    )
    return (texto or "").translate(mapa).lower().strip()


def _ja_registrado_recentemente(usuario_id: int, tipo: str, valor: float, descricao: str, janela: float = 5.0) -> bool:
    """Bloqueia duplicação caso a mesma transação tente ser persistida duas vezes na mesma janela."""
    agora = time.time()
    chave = (int(usuario_id), str(tipo).lower(), round(float(valor), 2), str(descricao).lower().strip())
    ultimo = _CACHE_ANTI_DUPLICACAO.get(chave)
    if ultimo and (agora - ultimo) < janela:
        return True
    _CACHE_ANTI_DUPLICACAO[chave] = agora
    return False


def _limpar_unidades_reais(texto: str) -> str:
    """Remove os termos 'reais', 'real' e 'R$' com word boundaries para evitar duplicação na extração."""
    limpo = re.sub(r"\br\$\s*", " ", texto, flags=re.IGNORECASE)
    limpo = re.sub(r"\b(?:reais|real)\b", " ", limpo, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", limpo).strip()


def inferir_categoria(texto: str, tipo: str = "despesa") -> str:
    texto_lower = (texto or "").lower()
    for categoria, palavras in MAPA_CATEGORIAS.items():
        if any(re.search(rf"\b{re.escape(p)}\b", texto_lower) for p in palavras):
            return categoria
    return "Salário" if tipo == "receita" else "Outros"


def extrair_valor_monetario(texto: str):
    """Extrai o valor numérico principal ignorando palavras como 'reais'."""
    texto_sem_moeda = _limpar_unidades_reais(texto or "")
    texto_limpo = re.sub(r"(\d)\.(\d{3})", r"\1\2", texto_sem_moeda)
    matches = re.findall(r"(\d+(?:[\.,]\d{1,2})?)", texto_limpo)
    if not matches:
        return None
    return float(matches[0].replace(",", "."))


def obter_cliente_groq():
    if not Groq or not GROQ_API_KEY or GROQ_API_KEY.startswith("cole_sua_chave"):
        return None
    try:
        return Groq(api_key=GROQ_API_KEY)
    except Exception:
        return None


# ==================== EDIÇÃO DE REGISTRO EXISTENTE ====================

def editar_transacao_existente(
    usuario_id: int,
    transacao_id: int = None,
    termo_busca: str = None,
    novo_valor: float = None,
    nova_descricao: str = None,
    nova_categoria: str = None,
    novo_tipo: str = None
) -> dict:
    """
    Permite editar uma despesa ou receita já adicionada anteriormente na tabela 'transacoes'.
    Pode localizar o registro pelo ID, pela descrição (ex: 'padaria') ou editar o último lançamento.
    """
    db = SessionLocal()
    try:
        registro = None

        if transacao_id:
            registro = db.execute(
                text("""
                    SELECT id, descricao, valor, categoria, tipo
                    FROM transacoes
                    WHERE id = :tid AND usuario_id = :uid
                    LIMIT 1
                """),
                {"tid": int(transacao_id), "uid": int(usuario_id)}
            ).fetchone()

        if not registro and termo_busca:
            termo_limpo = _limpar_unidades_reais(termo_busca).lower().strip()
            if termo_limpo not in ("ultimo", "último", "ultimo gasto", "último gasto", "ultima despesa", "última despesa", "ultimo registro", "último registro"):
                registro = db.execute(
                    text("""
                        SELECT id, descricao, valor, categoria, tipo
                        FROM transacoes
                        WHERE usuario_id = :uid AND LOWER(descricao) LIKE :termo
                        ORDER BY id DESC
                        LIMIT 1
                    """),
                    {"uid": int(usuario_id), "termo": f"%{termo_limpo}%"}
                ).fetchone()

        if not registro:
            registro = db.execute(
                text("""
                    SELECT id, descricao, valor, categoria, tipo
                    FROM transacoes
                    WHERE usuario_id = :uid
                    ORDER BY id DESC
                    LIMIT 1
                """),
                {"uid": int(usuario_id)}
            ).fetchone()

        if not registro:
            return {"sucesso": False, "erro": "Nenhum registro encontrado para edição."}

        desc_final = nova_descricao.strip().capitalize() if nova_descricao else registro.descricao
        val_final = float(novo_valor) if (novo_valor is not None and float(novo_valor) > 0) else float(registro.valor)
        tipo_final = novo_tipo.strip().lower() if novo_tipo else registro.tipo
        cat_final = (
            nova_categoria.strip().capitalize()
            if nova_categoria
            else (inferir_categoria(desc_final, tipo_final) if nova_descricao else registro.categoria)
        )

        db.execute(
            text("""
                UPDATE transacoes
                SET descricao = :desc,
                    valor = :val,
                    categoria = :cat,
                    tipo = :tipo
                WHERE id = :tid AND usuario_id = :uid
            """),
            {
                "desc": desc_final,
                "val": val_final,
                "cat": cat_final,
                "tipo": tipo_final,
                "tid": registro.id,
                "uid": int(usuario_id)
            }
        )
        db.commit()

        return {
            "sucesso": True,
            "id": registro.id,
            "descricao_antiga": registro.descricao,
            "valor_antigo": float(registro.valor),
            "descricao": desc_final,
            "valor": val_final,
            "categoria": cat_final,
            "tipo": tipo_final
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao atualizar registro: {str(e)}"}
    finally:
        db.close()


# ==================== CONSULTA ESPECÍFICA POR ITEM OU CATEGORIA ====================

def _extrair_termo_consulta(texto: str) -> str:
    """
    Isola o item ou categoria perguntado pelo usuário:
    - 'quanto gastei em padaria' -> 'padaria'
    - 'Extrato em alimetacao' -> 'alimetacao'
    - 'Extrato em gasolina' -> 'gasolina'
    """
    t = _limpar_unidades_reais(texto or "").lower()
    t = re.sub(
        r"\b(?:quanto|eu|ja|já|gastei|gasto|gastos|extrato|resumo|total|ver|mostrar|me|manda|de|do|da|dos|das|em|no|na|nos|nas|com|por|sobre|categoria|mes|mês|nesse|neste|hoje)\b",
        " ",
        t,
        flags=re.IGNORECASE
    )
    t = re.sub(r"[?!.,:;]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def consultar_extrato_por_filtro(usuario_id: int, termo_busca: str, texto_original: str = "") -> str:
    """
    Atende perguntas do tipo:
    - 'quanto gastei em padaria' (busca por item/descrição específica)
    - 'Extrato em alimetacao' (busca por categoria, mesmo com erro de digitação)
    - 'Extrato em gasolina' (busca por item/local específico)
    """
    termo_extraido = _extrair_termo_consulta(texto_original) or _extrair_termo_consulta(termo_busca) or (termo_busca or "").strip()
    termo_norm = _sem_acentos(termo_extraido)

    transacoes = listar_transacoes(usuario_id, limite=200)
    despesas = [t for t in transacoes if t.get("tipo") == "despesa"]

    # 1. Verifica se o termo corresponde a uma Categoria Oficial (exata ou aproximada, ex: 'alimetacao' -> 'Alimentação')
    categorias_norm_map = {_sem_acentos(c): c for c in CATEGORIAS_OFICIAIS}
    categoria_alvo = None

    if termo_norm in categorias_norm_map:
        categoria_alvo = categorias_norm_map[termo_norm]
    else:
        similares_cat = difflib.get_close_matches(termo_norm, list(categorias_norm_map.keys()), n=1, cutoff=0.72)
        if similares_cat:
            categoria_alvo = categorias_norm_map[similares_cat[0]]

    # 2. Se não for nome de categoria, verifica se é um item/local específico (ex: 'padaria', 'gasolina', 'uber')
    if not categoria_alvo and termo_norm:
        todas_palavras_mapa = {}
        for cat_m, lista_p in MAPA_CATEGORIAS.items():
            for p in lista_p:
                todas_palavras_mapa[_sem_acentos(p)] = (p.capitalize(), cat_m)

        item_mapeado = None
        categoria_do_item = None

        if termo_norm in todas_palavras_mapa:
            item_mapeado, categoria_do_item = todas_palavras_mapa[termo_norm]
        else:
            sim_item = difflib.get_close_matches(termo_norm, list(todas_palavras_mapa.keys()), n=1, cutoff=0.78)
            if sim_item:
                item_mapeado, categoria_do_item = todas_palavras_mapa[sim_item[0]]

        # Busca nas transações do usuário pela descrição (ex: 'Padaria', 'Gasolina')
        alvo_busca_norm = _sem_acentos(item_mapeado) if item_mapeado else termo_norm
        despesas_item = [
            t for t in despesas
            if alvo_busca_norm in _sem_acentos(t.get("descricao", ""))
            or termo_norm in _sem_acentos(t.get("descricao", ""))
            or difflib.SequenceMatcher(None, alvo_busca_norm, _sem_acentos(t.get("descricao", ""))).ratio() >= 0.78
        ]

        if despesas_item or item_mapeado:
            nome_item = item_mapeado or termo_extraido.capitalize()
            total_item = sum(float(t.get("valor") or 0.0) for t in despesas_item)
            cat_ref = categoria_do_item or (despesas_item[0].get("categoria") if despesas_item else inferir_categoria(nome_item))

            despesas_cat_ref = [t for t in despesas if _sem_acentos(t.get("categoria", "")) == _sem_acentos(cat_ref)]
            total_cat_ref = sum(float(t.get("valor") or 0.0) for t in despesas_cat_ref)

            if total_item <= 0:
                msg = f"📊 *Extrato Específico — {nome_item}*\nVocê ainda não registrou nenhum gasto com *{nome_item}* neste período."
                if total_cat_ref > 0:
                    msg += f"\n\n💡 _Na categoria *{cat_ref}*, você possui R$ {total_cat_ref:.2f} em outros itens._"
                return msg

            linhas = [
                f"📊 *Extrato Específico — {nome_item}*",
                f"• *Total gasto com {nome_item}:* 💸 *R$ {total_item:.2f}*",
                f"• *Quantidade de lançamentos:* {len(despesas_item)}",
                f"• *Categoria:* {cat_ref} (Total da categoria: R$ {total_cat_ref:.2f})\n",
                f"🧾 *Histórico de {nome_item}:*"
            ]
            for t in despesas_item[:10]:
                linhas.append(f"   • #{t.get('id')} {t.get('descricao')}: R$ {float(t.get('valor') or 0):.2f}")
            return "\n".join(linhas)

    # 3. Exibe o extrato completo da Categoria Oficial (ex: "Extrato em alimetacao" -> "Alimentação")
    if categoria_alvo:
        despesas_cat = [
            t for t in despesas
            if _sem_acentos(t.get("categoria", "")) == _sem_acentos(categoria_alvo)
        ]
        total_cat = sum(float(t.get("valor") or 0.0) for t in despesas_cat)

        if total_cat <= 0:
            return f"📊 *Extrato de {categoria_alvo}*\nVocê não registrou nenhum gasto na categoria *{categoria_alvo}* neste período."

        por_local = defaultdict(float)
        for t in despesas_cat:
            desc = (t.get("descricao") or categoria_alvo).strip().capitalize()
            por_local[desc] += float(t.get("valor") or 0.0)

        linhas = [
            f"📊 *Extrato por Categoria — {categoria_alvo}*",
            f"• *Total gasto em {categoria_alvo}:* 💸 *R$ {total_cat:.2f}*",
            f"• *Quantidade de lançamentos:* {len(despesas_cat)}\n",
            "📂 *Detalhamento por Item / Local:*"
        ]
        for local, soma in sorted(por_local.items(), key=lambda x: x[1], reverse=True):
            linhas.append(f"   • *{local}:* R$ {soma:.2f}")

        linhas.append("\n🧾 *Lançamentos registrados:*")
        for t in despesas_cat[:10]:
            linhas.append(f"   • #{t.get('id')} {t.get('descricao')}: R$ {float(t.get('valor') or 0):.2f}")

        return "\n".join(linhas)

    # 4. Caso o termo não seja encontrado nem como item nem como categoria
    lista_cats = ", ".join(CATEGORIAS_OFICIAIS)
    return (
        f"🤔 Não encontrei gastos para *{termo_extraido or termo_busca}*.\n\n"
        f"📋 *Categorias disponíveis:* {lista_cats}\n"
        f"💡 _Você também pode perguntar por um item específico, como: 'quanto gastei em padaria' ou 'extrato em gasolina'._"
    )


# ==================== EXTRATO AGRUPADO E GRÁFICOS TELEGRAM ====================

def gerar_extrato_agrupado(usuario_id: int) -> str:
    """Gera o extrato financeiro separado/agrupado por tipo e categoria de gasto."""
    resumo = obter_resumo_financeiro(usuario_id)
    transacoes = listar_transacoes(usuario_id, limite=50)
    gastos_fixos = listar_gastos_fixos(usuario_id)

    linhas = [
        "📊 *EXTRATO FINANCEIRO AGRUPADO*",
        f"• *Total de Entradas:* R$ {resumo['total_receitas']:.2f}",
        f"• *Total de Saídas:* R$ {resumo['total_despesas']:.2f}",
        f"• *Saldo Disponível Atual:* R$ {resumo['saldo']:.2f}\n"
    ]

    fixos_ativos = [g for g in gastos_fixos if g.get("ativo", g.get("is_active", True))]
    if fixos_ativos:
        linhas.append("📌 *Gastos Fixos Mensais:*")
        for g in fixos_ativos:
            desc = g.get("descricao") or g.get("description") or "Gasto Fixo"
            val = float(g.get("valor") or g.get("amount") or 0.0)
            dia = g.get("dia_vencimento") or g.get("due_day") or 10
            linhas.append(f"  - {desc} (Dia {dia}): R$ {val:.2f}")
        linhas.append("")

    por_categoria = defaultdict(list)
    for t in transacoes:
        if t.get("tipo") == "despesa":
            por_categoria[t.get("categoria") or "Outros"].append(t)

    if por_categoria:
        linhas.append("🗂️ *Gastos Variáveis por Categoria:*")
        for cat, itens in por_categoria.items():
            subtotal = sum(float(i.get("valor", 0)) for i in itens)
            linhas.append(f"▸ *{cat}* (Subtotal: R$ {subtotal:.2f}):")
            for item in itens[:5]:
                linhas.append(f"   • #{item.get('id')} {item.get('descricao')}: R$ {float(item.get('valor', 0)):.2f}")

    return "\n".join(linhas)


def gerar_grafico_financeiro_png(usuario_id: int) -> io.BytesIO:
    """Renderiza em memória o gráfico PNG de Entradas vs Saídas e Pizza por Categoria."""
    resumo = obter_resumo_financeiro(usuario_id)
    entradas = float(resumo.get("total_receitas", 0.0))
    saidas = float(resumo.get("total_despesas", 0.0))
    categorias = resumo.get("despesas_por_categoria", [])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), facecolor="#0f172a")
    for ax in axes:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors="#f8fafc")
        for spine in ax.spines.values():
            spine.set_color("#334155")

    axes[0].bar(["Entradas", "Saídas"], [entradas, saidas], color=["#10b981", "#ef4444"], width=0.5)
    axes[0].set_title("Entradas vs. Saídas (R$)", color="#f8fafc", fontweight="bold")

    if categorias:
        labels = [c["categoria"] for c in categorias]
        valores = [float(c["total"]) for c in categorias]
        axes[1].pie(valores, labels=labels, autopct="%1.1f%%", textprops={"color": "#f8fafc"}, startangle=140)
    else:
        axes[1].text(0.5, 0.5, "Sem despesas no período", color="#94a3b8", ha="center", va="center")
    axes[1].set_title("Gastos por Categoria", color="#f8fafc", fontweight="bold")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def enviar_grafico_telegram(chat_id: str, buffer_png: io.BytesIO = None, usuario_id: int = None) -> bool:
    """Envia o arquivo PNG do gráfico diretamente para o chat do usuário no Telegram."""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    if buffer_png is None and usuario_id is not None:
        buffer_png = gerar_grafico_financeiro_png(usuario_id)
    if buffer_png is None:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        buffer_png.seek(0)
        files = {"photo": ("grafico_financeiro.png", buffer_png, "image/png")}
        data = {"chat_id": str(chat_id), "caption": "📊 Aqui está o seu gráfico financeiro atualizado!"}
        resp = requests.post(url, data=data, files=files, timeout=15)
        return resp.status_code == 200
    except Exception:
        return False


# ==================== NÚCLEO DE PROCESSAMENTO E EXECUÇÃO ====================

def interpretar_mensagem_financeira(usuario_id: int, mensagem_usuario: str) -> dict:
    if isinstance(usuario_id, str) and isinstance(mensagem_usuario, int):
        usuario_id, mensagem_usuario = mensagem_usuario, usuario_id

    texto = (mensagem_usuario or "").strip()

    # RF07 e RN04: Restrição estrita ao Real Brasileiro (BRL)
    if MOEDAS_ESTRANGEIRAS_REGEX.search(texto):
        return {
            "intencao": "erro_moeda",
            "transacao_registrada": False,
            "resposta": (
                "⚠️ *Operação Negada (RN04 / RF07):* O sistema opera exclusivamente com o Real Brasileiro (BRL - R$). "
                "Entradas em moedas estrangeiras não são permitidas. Converta o valor para Reais antes de enviar."
            )
        }

    resumo = obter_resumo_financeiro(usuario_id)
    historico_recente = listar_historico_mensagens(usuario_id, limite=8)
    ultimas_transacoes = listar_transacoes(usuario_id, limite=5)

    # Interceptação rápida para consultas filtradas ("quanto gastei em padaria", "Extrato em alimetacao", "Extrato em gasolina")
    # Garante precisão determinística mesmo quando a LLM está ativa
    valor_msg = extrair_valor_monetario(texto)
    texto_lower = texto.lower()
    eh_pedido_consulta_filtrada = (
        valor_msg is None and (
            any(g in texto_lower for g in ["quanto gastei", "quanto eu gastei", "gastei em", "gastei na", "gastei no", "gastei com", "gastos em", "gastos com", "gastos de"])
            or bool(re.search(r"\b(?:extrato|resumo)\s+(?:em|de|do|da|no|na|com)\s+\w+", texto_lower))
        )
    )
    if eh_pedido_consulta_filtrada:
        termo_filtro = _extrair_termo_consulta(texto)
        if termo_filtro:
            return {
                "intencao": "consultar_categoria",
                "transacao_registrada": False,
                "resumo": resumo,
                "resposta": consultar_extrato_por_filtro(usuario_id, termo_filtro, texto)
            }

    client = obter_cliente_groq()
    if client:
        resultado_llm = _processar_com_llm(client, usuario_id, texto, resumo, historico_recente, ultimas_transacoes)
        if resultado_llm is not None:
            return resultado_llm

    # Motor NLU local inteligente
    return _motor_nlu_inteligente_local(usuario_id, texto, resumo)


def _processar_com_llm(client, usuario_id: int, texto: str, resumo: dict, historico: list, ultimas_transacoes: list) -> dict:
    categorias_str = ", ".join(
        [f"{c['categoria']}: R$ {c['total']:.2f}" for c in resumo["despesas_por_categoria"]]
    ) or "Nenhuma despesa registrada ainda"

    ultimas_str = "\n".join(
        [f"- ID #{t.get('id')}: {t['tipo'].upper()} R$ {t['valor']:.2f} ({t['categoria']} - {t['descricao']})" for t in ultimas_transacoes]
    ) or "Nenhuma transação recente."

    historico_formatado = "\n".join(
        [f"{'Usuário' if h.get('remetente') == 'usuario' else 'Assistente'}: {h.get('mensagem', '')}" for h in historico[-6:]]
    )

    prompt_sistema = f"""Você é o Assistente Financeiro Inteligente do sistema FinanceControl.

=== CONTEXTO FINANCEIRO ATUAL DO USUÁRIO (MOEDA: BRL - R$) ===
• Saldo Atual Disponível: R$ {resumo['saldo']:.2f}
• Total de Receitas (Entradas): R$ {resumo['total_receitas']:.2f}
• Total de Despesas (Saídas): R$ {resumo['total_despesas']:.2f}
• Despesas por Categoria: {categorias_str}
• Últimos Lançamentos:
{ultimas_str}

=== HISTÓRICO RECENTE DA CONVERSA ===
{historico_formatado}

=== REGRAS DE CLASSIFICAÇÃO DE INTENÇÃO ===
1. "aconselhamento": Perguntas se pode comprar/gastar algo (ex: "posso comprar um relógio de 50 reais?"). NÃO registre transação.
2. "registrar_despesa" | "registrar_receita": Gastos ou ganhos variáveis (ex: "gastei 50 reais na padaria", "lanche 50", "recebi 300 de freela"). Ignore a palavra "reais" na descricao (ex: descricao="Padaria").
3. "cadastrar_gasto_fixo" | "cadastrar_renda_fixa": Compromissos ou ganhos mensais recorrentes (ex: "aluguel todo dia 10 de 1500", "salário dia 5 4000 reais").
4. "editar_transacao": Quando o usuário pedir para editar, alterar, atualizar ou corrigir um registro já salvo (ex: "editar padaria para 35 reais", "alterar lanche para 40", "editar id 12 para 100"). Coloque em "termo_busca" o item a ser buscado (ex: "Padaria"), em "transacao_id" o ID numérico se informado, em "valor" o novo valor float, e em "nova_descricao" se o usuário quiser renomear a descrição.
5. "consultar_categoria": Perguntas sobre quanto gastou ou extrato em um item/local específico OU categoria (ex: "quanto gastei em padaria", "extrato em alimetacao", "extrato em gasolina", "quanto gastei com uber"). Coloque em "termo_busca" o item ou categoria exata que o usuário perguntou (ex: "padaria", "alimentacao", "gasolina").
6. "consultar_saldo": Pedidos de saldo geral, extrato geral ou resumo completo (sem especificar categoria ou item).
7. "enviar_grafico": Pedidos de gráfico (ex: "me manda o gráfico").
8. "ambiguidade": Quando informou apenas verbo e valor sem dizer onde/o quê (ex: "gastei 50").
9. "excluir_transacao": Quando o usuário pedir para apagar, deletar ou remover um registro (ex: "apagar o gasto em padaria", "apagar o registro 15"). Coloque em "transacao_id" o número do ID ou em "termo_busca" o nome do item.

Retorne EXCLUSIVAMENTE um objeto JSON válido no formato:
{{
  "intencao": "registrar_despesa" | "registrar_receita" | "cadastrar_gasto_fixo" | "cadastrar_renda_fixa" | "editar_transacao" | "consultar_categoria" | "consultar_saldo" | "enviar_grafico" | "aconselhamento" | "ambiguidade" | "conversa_geral" | excluir_transacao",
  "valor": numero_float_ou_null,
  "dia_mes": numero_int_ou_null,
  "categoria": "Alimentação" | "Transporte" | "Moradia" | "Vestuário" | "Saúde" | "Educação" | "Lazer" | "Salário" | "Renda Extra" | "Outros",
  "descricao": "string curta descrevendo o item (sem a palavra reais)",
  "termo_busca": "nome do item ou categoria a consultar/editar ou null",
  "transacao_id": numero_int_ou_null,
  "nova_descricao": "nova descrição caso queira renomear ou null",
  "resposta_usuario": "Sua resposta clara e personalizada"
}}"""

    try:
        completion = client.chat.completions.create(
            model=MODELO_GROQ,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": texto}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        dados = json.loads(completion.choices[0].message.content)
    except Exception:
        return None

    return _executar_acao_estruturada(usuario_id, texto, dados, resumo)


def _executar_acao_estruturada(usuario_id: int, texto_original: str, dados: dict, resumo_antes: dict) -> dict:
    intencao = dados.get("intencao", "conversa_geral")
    valor = dados.get("valor")
    dia_mes = dados.get("dia_mes")
    categoria = dados.get("categoria") or inferir_categoria(texto_original)
    descricao = _limpar_unidades_reais((dados.get("descricao") or texto_original).strip())
    resposta_ia = dados.get("resposta_usuario", "")

    # 1. Cadastro de Gasto Fixo via Chat
    if intencao == "cadastrar_gasto_fixo" and valor and float(valor) > 0:
        dia_venc = int(dia_mes) if (dia_mes and 1 <= int(dia_mes) <= 31) else 10
        res_db = criar_gasto_fixo(
            usuario_id=usuario_id,
            description=descricao,
            amount=float(valor),
            due_day=dia_venc,
            is_active=True
        )
        if not res_db["sucesso"]:
            return {"intencao": "erro", "transacao_registrada": False, "resposta": res_db["erro"]}

        novo_resumo = obter_resumo_financeiro(usuario_id)
        msg = (
            f"📌 *Gasto Fixo Cadastrado com Sucesso!*\n"
            f"• *Descrição:* {descricao}\n"
            f"• *Valor Mensal:* R$ {float(valor):.2f}\n"
            f"• *Dia de Vencimento:* Todo dia {dia_venc}\n"
            f"• *Total de Gastos Fixos:* R$ {novo_resumo['total_gastos_fixos']:.2f}\n"
            f"• *Saldo Disponível Atualizado:* R$ {novo_resumo['saldo']:.2f}"
        )
        return {
            "intencao": intencao,
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": msg
        }

    # 2. Cadastro de Renda Fixa via Chat
    elif intencao == "cadastrar_renda_fixa" and valor and float(valor) > 0:
        dia_rec = int(dia_mes) if (dia_mes and 1 <= int(dia_mes) <= 31) else 5
        res_db = criar_renda_fixa(
            usuario_id=usuario_id,
            description=descricao,
            amount=float(valor),
            day_of_month=dia_rec,
            is_active=True
        )
        if not res_db["sucesso"]:
            return {"intencao": "erro", "transacao_registrada": False, "resposta": res_db["erro"]}

        novo_resumo = obter_resumo_financeiro(usuario_id)
        msg = (
            f"💼 *Renda Fixa Cadastrada com Sucesso!*\n"
            f"• *Descrição:* {descricao}\n"
            f"• *Valor Mensal:* R$ {float(valor):.2f}\n"
            f"• *Dia de Recebimento:* Todo dia {dia_rec}\n"
            f"• *Total de Rendas Fixas:* R$ {novo_resumo['total_rendas_fixas']:.2f}\n"
            f"• *Saldo Disponível Atualizado:* R$ {novo_resumo['saldo']:.2f}"
        )
        return {
            "intencao": intencao,
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": msg
        }

    # 3. Registro de Despesa ou Receita Variável (Sem duplicação para 'reais')
    elif intencao in ("registrar_despesa", "registrar_receita") and valor and float(valor) > 0:
        tipo_banco = "despesa" if intencao == "registrar_despesa" else "receita"
        descricao_final = descricao.capitalize() if descricao else "Lançamento"

        if not _ja_registrado_recentemente(usuario_id, tipo_banco, float(valor), descricao_final):
            res_db = registrar_transacao(
                usuario_id=usuario_id,
                tipo=tipo_banco,
                valor=float(valor),
                categoria=categoria,
                descricao=descricao_final,
                moeda="BRL"
            )
            if not res_db["sucesso"]:
                return {"intencao": "erro", "transacao_registrada": False, "resposta": res_db["erro"]}
        else:
            res_db = {"sucesso": True}

        novo_resumo = obter_resumo_financeiro(usuario_id)
        icone = "💸" if tipo_banco == "despesa" else "💰"
        msg = (
            f"✅ *{tipo_banco.capitalize()} registrada com sucesso!*\n"
            f"• *Descrição:* {descricao_final}\n"
            f"• *Categoria:* {categoria}\n"
            f"• *Valor:* {icone} R$ {float(valor):.2f}\n"
            f"• *Saldo Disponível Atual:* R$ {novo_resumo['saldo']:.2f}"
        )
        if res_db.get("alerta"):
            msg += f"\n\n{res_db['alerta']}"
        return {
            "intencao": intencao,
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": msg
        }

    # 4. Edição de Registro já adicionado
    elif intencao == "editar_transacao":
        res_edicao = editar_transacao_existente(
            usuario_id=usuario_id,
            transacao_id=dados.get("transacao_id"),
            termo_busca=dados.get("termo_busca") or descricao,
            novo_valor=float(valor) if (valor and float(valor) > 0) else None,
            nova_descricao=dados.get("nova_descricao"),
            nova_categoria=dados.get("nova_categoria")
        )
        if not res_edicao["sucesso"]:
            return {
                "intencao": "erro",
                "transacao_registrada": False,
                "resumo": resumo_antes,
                "resposta": (
                    f"⚠️ {res_edicao['erro']}\n"
                    f"Você pode editar dizendo, por exemplo:\n"
                    f"• *\"Editar padaria para 35 reais\"*\n"
                    f"• *\"Alterar último gasto para 40\"*\n"
                    f"• *\"Editar id 10 para 80 reais\"*"
                )
            }

        novo_resumo = obter_resumo_financeiro(usuario_id)
        icone = "💸" if res_edicao["tipo"] == "despesa" else "💰"
        msg = (
            f"✏️ *Registro #{res_edicao['id']} editado com sucesso!*\n"
            f"• *Descrição:* {res_edicao['descricao']}\n"
            f"• *Categoria:* {res_edicao['categoria']}\n"
            f"• *Valor Anterior:* R$ {res_edicao['valor_antigo']:.2f}\n"
            f"• *Novo Valor:* {icone} R$ {res_edicao['valor']:.2f}\n"
            f"• *Saldo Disponível Atual:* R$ {novo_resumo['saldo']:.2f}"
        )
        return {
            "intencao": "editar_transacao",
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": msg
        }

    # 5. Consulta por Item/Local Específico ou Categoria ("quanto gastei em padaria", "Extrato em alimetacao", "Extrato em gasolina")
    elif intencao == "consultar_categoria":
        termo_alvo = dados.get("termo_busca") or _extrair_termo_consulta(texto_original) or categoria
        resposta_final = consultar_extrato_por_filtro(usuario_id, termo_alvo, texto_original)
        return {
            "intencao": "consultar_categoria",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": resposta_final
        }

    # 6. Solicitação de Extrato Geral ou Gráfico
    elif intencao == "consultar_saldo":
        return {
            "intencao": "consultar_saldo",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": gerar_extrato_agrupado(usuario_id)
        }

    elif intencao == "enviar_grafico":
        return {
            "intencao": "enviar_grafico",
            "enviar_grafico": True,
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": "📈 Gerando seu gráfico financeiro atualizado...\n\n" + gerar_extrato_agrupado(usuario_id)
        }

    elif intecao == "":
        return {
            "intencao": "excluir_transacao",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": resposta_ia
        }

    return {
        "intencao": intencao,
        "transacao_registrada": False,
        "resumo": resumo_antes,
        "resposta": resposta_ia
    }

def excluir_transacao_por_termo_ou_id(usuario_id: int, transacao_id: int = None, termo_busca: str = None) -> dict:
    """Exclui uma transação do banco por ID ou pelo termo da descrição."""
    db = SessionLocal()
    try:
        registro = None
        if transacao_id:
            registro = db.execute(
                text("SELECT id, descricao, valor FROM transacoes WHERE id = :tid AND usuario_id = :uid LIMIT 1"),
                {"tid": int(transacao_id), "uid": int(usuario_id)}
            ).fetchone()
        elif termo_busca:
            registro = db.execute(
                text("SELECT id, descricao, valor FROM transacoes WHERE usuario_id = :uid AND LOWER(descricao) LIKE :termo ORDER BY id DESC LIMIT 1"),
                {"uid": int(usuario_id), "termo": f"%{termo_busca.strip().lower()}%"}
            ).fetchone()

        if not registro:
            return {"sucesso": False, "erro": "Registro não encontrado para exclusão."}

        db.execute(
            text("DELETE FROM transacoes WHERE id = :tid AND usuario_id = :uid"),
            {"tid": registro.id, "uid": int(usuario_id)}
        )
        db.commit()
        return {"sucesso": True, "id": registro.id, "descricao": registro.descricao, "valor": float(registro.valor)}
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def _motor_nlu_inteligente_local(usuario_id: int, texto: str, resumo: dict) -> dict:
    """
    Motor NLU determinístico local para garantir funcionamento mesmo sem chave da Groq
    e sem duplicar lançamentos quando a palavra 'reais' é usada.
    """
    texto_limpo_moeda = _limpar_unidades_reais(texto)
    texto_lower = texto_limpo_moeda.lower().strip()
    valor = extrair_valor_monetario(texto_limpo_moeda)

    # 0. Detecção de Edição de Registro (Ex: "editar padaria para 35 reais", "alterar id 5 para 80")
    if re.match(r"^(?:editar|alterar|corrigir|atualizar|mudar)\b", texto_lower):
        match_id = re.search(r"(?:id|registro|transa[cç][aã]o|#)\s*(\d+).*?(\d+(?:[.,]\d{1,2})?)", texto_lower)
        if match_id:
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "editar_transacao",
                "transacao_id": int(match_id.group(1)),
                "valor": float(match_id.group(2).replace(",", "."))
            }, resumo)

        match_termo = re.search(
            r"^(?:editar|alterar|corrigir|atualizar|mudar)\s+(?:o\s+|a\s+|gasto\s+|despesa\s+|receita\s+)?(.+?)\s+(?:para|por|valor)\s*(\d+(?:[.,]\d{1,2})?)$",
            texto_lower
        )
        if match_termo:
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "editar_transacao",
                "termo_busca": match_termo.group(1).strip(),
                "valor": float(match_termo.group(2).replace(",", "."))
            }, resumo)

        if valor:
            termo_restante = re.sub(
                r"\b(?:editar|alterar|corrigir|atualizar|mudar|para|por|valor|de|o|a)\b|\d+(?:[.,]\d{1,2})?",
                " ",
                texto_lower
            ).strip()
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "editar_transacao",
                "termo_busca": termo_restante or None,
                "valor": valor
            }, resumo)

    # 1. Detecção de Pedido de Gráfico
    if any(g in texto_lower for g in ["grafico", "gráfico", "me manda o gráfico", "me manda o grafico"]):
        return _executar_acao_estruturada(usuario_id, texto, {"intencao": "enviar_grafico"}, resumo)

    # 2. Detecção de Perguntas Consultivas / Viabilidade de Compra (RF05, RN01, RN02)
    gatilhos_consulta_compra = [
        "posso comprar", "posso gastar", "consigo comprar", "dá para comprar", "da para comprar",
        "dá pra comprar", "da pra comprar", "vale a pena comprar", "é viável", "e viavel",
        "devo comprar", "tenho saldo para", "tenho dinheiro para", "posso pegar"
    ]
    eh_pergunta_compra = any(g in texto_lower for g in gatilhos_consulta_compra) or (
        texto_lower.endswith("?") and any(p in texto_lower for p in ["comprar", "gastar", "pagar", "relógio", "relogio"])
    )

    if eh_pergunta_compra:
        saldo = resumo["saldo"]
        receitas = resumo["total_receitas"]
        despesas = resumo["total_despesas"]

        if valor is None:
            return {
                "intencao": "aconselhamento",
                "transacao_registrada": False,
                "resumo": resumo,
                "resposta": (
                    f"🧐 Para eu analisar se essa compra cabe no seu bolso, informe o valor do item! "
                    f"Atualmente seu saldo disponível é de *R$ {saldo:.2f}* (Receitas: R$ {receitas:.2f} | Despesas: R$ {despesas:.2f})."
                )
            }

        novo_saldo_simulado = saldo - valor
        if receitas <= 0 or saldo < valor:
            motivo_rn01 = (
                "\n• *Atenção (RN01):* Você ainda não cadastrou nenhuma receita neste mês (R$ 0,00)."
                if receitas <= 0 else ""
            )
            return {
                "intencao": "aconselhamento",
                "transacao_registrada": False,
                "resumo": resumo,
                "resposta": (
                    f"🚨 *Análise de Viabilidade: Compra NÃO recomendada no momento.*\n\n"
                    f"• *Valor desejado:* R$ {valor:.2f}\n"
                    f"• *Seu Saldo Atual:* R$ {saldo:.2f}\n"
                    f"• *Saldo após a compra:* R$ {novo_saldo_simulado:.2f}{motivo_rn01}\n\n"
                    f"💡 *Conselho do Assistente:* Realizar esse gasto de R$ {valor:.2f} agora comprometerá seu orçamento."
                )
            }

        percentual_comprometido = (valor / saldo) * 100 if saldo > 0 else 100
        aviso_cautela = (
            "⚠️ Apesar de ter saldo, essa compra consome mais de 50% de toda a sua reserva disponível."
            if percentual_comprometido > 50 else
            "✅ O valor representa uma fatia segura do seu saldo disponível."
        )
        return {
            "intencao": "aconselhamento",
            "transacao_registrada": False,
            "resumo": resumo,
            "resposta": (
                f"✅ *Análise de Viabilidade: Compra Viável!*\n\n"
                f"• *Valor do item:* R$ {valor:.2f}\n"
                f"• *Saldo Atual:* R$ {saldo:.2f}\n"
                f"• *Saldo restante após a compra:* R$ {novo_saldo_simulado:.2f}\n\n"
                f"💡 *Conselho:* {aviso_cautela}"
            )
        }

    # 2.5 Consulta Filtrada por Item ou Categoria ("quanto gastei em padaria", "Extrato em alimetacao", "Extrato em gasolina")
    if valor is None:
        termo_extraido = _extrair_termo_consulta(texto_lower)
        tem_gatilho_filtro = (
            any(g in texto_lower for g in ["quanto gastei", "quanto eu gastei", "gastei em", "gastei na", "gastei no", "gastei com", "gastos em", "gastos com", "gastos de"])
            or (any(p in texto_lower for p in ["extrato", "resumo"]) and bool(termo_extraido))
        )
        if tem_gatilho_filtro and termo_extraido:
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "consultar_categoria",
                "termo_busca": termo_extraido
            }, resumo)

    # 3. Detecção de Consulta de Saldo / Extrato Geral / Resumo (RF03)
    if any(p in texto_lower for p in ["saldo", "extrato", "resumo", "quanto eu tenho", "minhas finanças", "minhas financas"]):
        return _executar_acao_estruturada(usuario_id, texto, {"intencao": "consultar_saldo"}, resumo)

    # 4. Detecção de Renda Fixa ou Gasto Fixo
    if "renda fixa" in texto_lower or ("salario" in texto_lower and "dia" in texto_lower) or ("salário" in texto_lower and "dia" in texto_lower):
        match_dia = re.search(r"dia\s*(\d{1,2})", texto_lower)
        dia_mes = int(match_dia.group(1)) if match_dia else 5
        texto_sem_dia = re.sub(r"todo\s*dia\s*\d{1,2}|dia\s*\d{1,2}", "", texto_lower)
        val_fixo = extrair_valor_monetario(texto_sem_dia)
        if val_fixo:
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "cadastrar_renda_fixa",
                "valor": val_fixo,
                "dia_mes": dia_mes,
                "descricao": "Salário"
            }, resumo)

    if "gasto fixo" in texto_lower or ("aluguel" in texto_lower and "dia" in texto_lower):
        match_dia = re.search(r"dia\s*(\d{1,2})", texto_lower)
        dia_mes = int(match_dia.group(1)) if match_dia else 10
        texto_sem_dia = re.sub(r"todo\s*dia\s*\d{1,2}|dia\s*\d{1,2}", "", texto_lower)
        val_fixo = extrair_valor_monetario(texto_sem_dia)
        if val_fixo:
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "cadastrar_gasto_fixo",
                "valor": val_fixo,
                "dia_mes": dia_mes,
                "descricao": "Aluguel" if "aluguel" in texto_lower else "Gasto Fixo"
            }, resumo)

    # 5. Detecção de Registro de Receita (RF01)
    gatilhos_receita = ["recebi", "ganhei", "entrou", "salário", "salario", "depositaram", "me pagaram", "renda", "freela"]
    if valor and any(p in texto_lower for p in gatilhos_receita):
        categoria = inferir_categoria(texto_limpo_moeda, "receita")
        desc_receita = re.sub(
            r"\b(?:recebi|ganhei|entrou|depositaram|me pagaram|de|do|da|no|na|valor|por)\b|\d+(?:[\.,]\d{1,2})?",
            " ",
            texto_limpo_moeda,
            flags=re.IGNORECASE
        )
        desc_receita = re.sub(r"\s+", " ", desc_receita).strip().capitalize() or "Receita"
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "registrar_receita",
            "valor": valor,
            "categoria": categoria,
            "descricao": desc_receita
        }, resumo)

    # 6. Detecção de Registro de Despesa (RF01, RF04, RF06) — Passagem única sem duplicar 'reais'
    gatilhos_despesa = [
        "gastei", "paguei", "comprei", "cadastre", "cadastrar", "lance", "lançar", "lancar",
        "despesa", "gasto", "almocei", "jantei", "abasteci", "fui no mercado", "no mercado"
    ]
    if valor and (any(p in texto_lower for p in gatilhos_despesa) or len(texto_lower.split()) >= 2):
        texto_sem_numeros = re.sub(
            r"\b(?:gastei|paguei|comprei|cadastre|cadastrar|lance|lançar|lancar|gasto|despesa|de|do|da|no|na|nos|nas|em|valor|com|por)\b|\d+(?:[\.,]\d{1,2})?",
            " ",
            texto_lower,
            flags=re.IGNORECASE
        )
        palavras_restantes = [p for p in texto_sem_numeros.split() if p.strip()]

        if len(palavras_restantes) == 0:
            return {
                "intencao": "ambiguidade",
                "transacao_registrada": False,
                "resumo": resumo,
                "resposta": (
                    f"🤔 *Confirmação necessária (RF06):* Identifiquei o valor de *R$ {valor:.2f}*, "
                    f"mas onde ou com o que foi esse gasto? (Exemplo: *'Gastei {valor:.0f} reais na padaria'*)."
                )
            }

        descricao_limpa = " ".join(palavras_restantes).capitalize()
        categoria = inferir_categoria(descricao_limpa, "despesa")
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "registrar_despesa",
            "valor": valor,
            "categoria": categoria,
            "descricao": descricao_limpa
        }, resumo)
    
    # Interceptador de exclusão/apagamento (Ex: "apagar o gasto em padaria", "apagar o registro 15")
    if re.match(r"^(?:apagar|deletar|remover|excluir)\b", texto_lower):
        match_id = re.search(r"(?:id|registro|transa[cç][aã]o|#)?\s*(\d+)", texto_lower)
        if match_id:
            tid = int(match_id.group(1))
            res = excluir_transacao_por_termo_ou_id(usuario_id, transacao_id=tid)
            if res["sucesso"]:
                resumo = obter_resumo_financeiro(usuario_id)
                return {
                    "sucesso": True,
                    "intencao": "excluir_transacao",
                    "resposta": f"🗑️ Registro #{res['id']} (*{res['descricao']}* - R$ {res['valor']:.2f}) apagado com sucesso!\n• Saldo Atual Atualizado: R$ {resumo['saldo']:.2f}"
                }
        
        # Extrai o termo a ser apagado (ex: "padaria")
        termo_del = re.sub(r"^(?:apagar|deletar|remover|excluir)\s+(?:o\s+|a\s+|gasto\s+|despesa\s+|registro\s+)?", "", texto_lower).strip()
        termo_del = re.sub(r"\d+", "", termo_del).strip()
        if termo_del:
            res = excluir_transacao_por_termo_ou_id(usuario_id, termo_busca=termo_del)
            if res["sucesso"]:
                resumo = obter_resumo_financeiro(usuario_id)
                return {
                    "sucesso": True,
                    "intencao": "excluir_transacao",
                    "resposta": f"🗑️ Registro correspondente a *{res['descricao']}* (R$ {res['valor']:.2f}) apagado com sucesso!\n• Saldo Atual Atualizado: R$ {resumo['saldo']:.2f}"
                }
        
        return {
            "sucesso": False,
            "intencao": "excluir_transacao",
            "resposta": "⚠️ Não consegui identificar qual registro apagar. Tente informar o ID (ex: *'apagar registro 15'*) ou o nome (ex: *'apagar padaria'*)."
        }

    # 7. Resposta contextual amigável para conversas gerais
    return {
        "intencao": "conversa_geral",
        "transacao_registrada": False,
        "resumo": resumo,
        "resposta": (
            f"Olá! Estou acompanhando seu orçamento (seu saldo atual é de *R$ {resumo['saldo']:.2f}*).\n\n"
            f"Você pode falar naturalmente comigo para:\n"
            f"• *Registrar gastos:* \"Gastei 50 reais na padaria\" ou \"Lanche 50\"\n"
            f"• *Editar um registro:* \"Editar padaria para 35 reais\"\n"
            f"• *Consultar por item ou categoria:* \"Quanto gastei em padaria\", \"Extrato em alimentação\" ou \"Extrato em gasolina\"\n"
            f"• *Consultar resumo ou gráfico:* \"Qual meu saldo?\" ou \"Me manda o gráfico\""
        )
    }