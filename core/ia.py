# Caminho: core/ia.py
import os
import io
import re
import json
import time
import unicodedata
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
    listar_gastos_fixos,
    salvar_teto_gasto,
    listar_tetos_gastos,
    excluir_teto_gasto
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODELO_GROQ = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

_CACHE_ANTI_DUPLICACAO = {}

MOEDAS_ESTRANGEIRAS_REGEX = re.compile(
    r"(\bUSD\b|\bEUR\b|\bGBP\b|\bARS\b|\bPYG\b|d[óo]lar|d[óo]lares|euro|euros|libra|pesos|guaranis|US\$|€|£)",
    re.IGNORECASE
)

# Regex prioritário para impedir que "apague 26" vire despesa
COMANDO_EXCLUSAO_REGEX = re.compile(
    r"^(?:apague|apagar|apaga|excluir|exclua|exclui|deletar|delete|deleta|remover|remova|remove)\b",
    re.IGNORECASE
)

CATEGORIAS_OFICIAIS = [
    "Alimentação", "Transporte", "Moradia", "Lazer",
    "Saúde", "Educação", "Vestuário", "Salário", "Renda Extra", "Outros"
]

MAPA_CATEGORIAS = {
    "Alimentação": ["alimentacao", "alimentação", "mercado", "supermercado", "padaria", "lanche", "restaurante", "ifood", "pizza", "hamburguer", "almoço", "almoco", "janta", "jantar", "café", "cafe", "açougue", "acougue", "feira"],
    "Transporte": ["transporte", "uber", "99", "gasolina", "combustível", "combustivel", "ônibus", "onibus", "passagem", "estacionamento", "pedágio", "pedagio", "oficina", "pneu", "posto"],
    "Moradia": ["moradia", "aluguel", "condomínio", "condominio", "luz", "energia", "água", "agua", "internet", "gás", "gas", "iptu"],
    "Vestuário": ["vestuario", "vestuário", "camiseta", "camisa", "calça", "calca", "tênis", "tenis", "sapato", "roupa", "blusa", "jaqueta", "relógio", "relogio", "óculos", "oculos", "loja"],
    "Saúde": ["saude", "saúde", "farmácia", "farmacia", "remédio", "remedio", "médico", "medico", "consulta", "exame", "dentista", "academia"],
    "Educação": ["educacao", "educação", "faculdade", "curso", "livro", "mensalidade", "material", "udc", "escola"],
    "Lazer": ["lazer", "cinema", "show", "viagem", "passeio", "bar", "cerveja", "jogo", "streaming", "netflix", "spotify"],
    "Salário": ["salário", "salario", "pagamento", "adiantamento", "vale", "bolsa", "estágio", "estagio"],
    "Renda Extra": ["freela", "freelance", "venda", "vendi", "pix recebido", "rendimento", "dividendo", "bônus", "bonus"]
}


def _normalizar(texto: str) -> str:
    if not texto:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto).lower().strip())
        if unicodedata.category(c) != "Mn"
    )


def _ja_registrado_recentemente(usuario_id: int, tipo: str, valor: float, descricao: str, janela: float = 5.0) -> bool:
    agora = time.time()
    chave = (int(usuario_id), str(tipo).lower(), round(float(valor), 2), str(descricao).lower().strip())
    ultimo = _CACHE_ANTI_DUPLICACAO.get(chave)
    if ultimo and (agora - ultimo) < janela:
        return True
    _CACHE_ANTI_DUPLICACAO[chave] = agora
    return False


def _limpar_unidades_reais(texto: str) -> str:
    limpo = re.sub(r"\br\$\s*", " ", texto or "", flags=re.IGNORECASE)
    limpo = re.sub(r"\b(?:reais|real)\b", " ", limpo, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", limpo).strip()


def inferir_categoria(texto: str, tipo: str = "despesa") -> str:
    texto_lower = (texto or "").lower()
    texto_norm = _normalizar(texto_lower)
    for cat_oficial in CATEGORIAS_OFICIAIS:
        if _normalizar(cat_oficial) in texto_norm:
            return cat_oficial
    for categoria, palavras in MAPA_CATEGORIAS.items():
        if any(re.search(rf"\b{re.escape(p)}\b", texto_lower) or re.search(rf"\b{re.escape(_normalizar(p))}\b", texto_norm) for p in palavras):
            return categoria
    return "Salário" if tipo == "receita" else "Outros"


def extrair_valor_monetario(texto: str):
    texto_sem_moeda = _limpar_unidades_reais(texto or "")
    texto_limpo = re.sub(r"(?:todo\s+dia|vencimento\s+dia|dia)\s+\d{1,2}\b", " ", texto_sem_moeda, flags=re.IGNORECASE)
    texto_limpo = re.sub(r"\b(?:id|item|registro|numero|número|#)\s*\d+\b", " ", texto_limpo, flags=re.IGNORECASE)
    texto_limpo = re.sub(r"(\d)\.(\d{3})", r"\1\2", texto_limpo)
    matches = re.findall(r"(\d+(?:[\.,]\d{1,2})?)", texto_limpo)
    if not matches:
        return None
    return float(matches[-1].replace(",", "."))


def extrair_dia_do_mes(texto: str):
    match = re.search(r"(?:todo\s+dia|vencimento\s+dia|no\s+dia|dia)\s+(\d{1,2})\b", texto or "", flags=re.IGNORECASE)
    if match:
        dia = int(match.group(1))
        if 1 <= dia <= 31:
            return dia
    return None


def obter_cliente_groq():
    if not Groq or not GROQ_API_KEY or GROQ_API_KEY.startswith("cole_sua_chave"):
        return None
    try:
        return Groq(api_key=GROQ_API_KEY)
    except Exception:
        return None


# ==================== FUNÇÕES DE BANCO: EDIÇÃO, EXCLUSÃO E CONSULTAS ====================

def excluir_transacao_por_termo_ou_id(usuario_id: int, transacao_id: int = None, termo_busca: str = None) -> dict:
    db = SessionLocal()
    try:
        registro = None
        if transacao_id is not None:
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
            termo_limpo = _limpar_unidades_reais(termo_busca).strip().lower()
            registro = db.execute(
                text("""
                    SELECT id, descricao, valor, categoria, tipo
                    FROM transacoes
                    WHERE usuario_id = :uid AND (LOWER(descricao) LIKE :termo OR LOWER(categoria) LIKE :termo)
                    ORDER BY id DESC
                    LIMIT 1
                """),
                {"uid": int(usuario_id), "termo": f"%{termo_limpo}%"}
            ).fetchone()

        if not registro:
            alvo = f"#{transacao_id}" if transacao_id else f"'{termo_busca}'"
            return {"sucesso": False, "erro": f"Não encontrei o registro {alvo} no seu extrato para exclusão."}

        db.execute(
            text("DELETE FROM transacoes WHERE id = :tid AND usuario_id = :uid"),
            {"tid": registro.id, "uid": int(usuario_id)}
        )
        db.commit()
        return {
            "sucesso": True,
            "id": registro.id,
            "descricao": registro.descricao,
            "valor": float(registro.valor),
            "categoria": registro.categoria,
            "tipo": registro.tipo
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": f"Erro ao apagar registro: {str(e)}"}
    finally:
        db.close()


def _tentar_interceptar_exclusao(usuario_id: int, texto: str) -> dict:
    """
    Intercepta comandos como 'apague 26', 'apagar #26', 'excluir o gasto em padaria', 'deletar registro 15'.
    Se for 'apagar teto de lazer', encaminha para exclusão de teto.
    """
    texto_limpo = (texto or "").strip()
    if not COMANDO_EXCLUSAO_REGEX.match(texto_limpo):
        return None

    # Se o usuário pediu para apagar/remover um TETO/LIMITE de gastos
    if re.search(r"\b(?:teto|limite|or[cç]amento)\b", texto_limpo, re.IGNORECASE):
        cat_alvo = re.sub(
            r"^(?:apague|apagar|apaga|excluir|exclua|deletar|delete|remover|remova)\s+(?:o\s+|a\s+)?(?:teto|limite|or[cç]amento)\s*(?:de\s+|da\s+|do\s+|para\s+)?",
            "",
            texto_limpo,
            flags=re.IGNORECASE
        ).strip()
        cat_inferida = inferir_categoria(cat_alvo) if cat_alvo else "Outros"
        nome_final = cat_inferida if cat_inferida != "Outros" else cat_alvo.capitalize()
        excluir_teto_gasto(usuario_id, nome_final)
        novo_resumo = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "excluir_teto",
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": f"🗑️ *Teto de gastos removido:* O limite configurado para *{nome_final}* foi excluído."
        }

    # Limpa verbos e palavras de ligação ("apague o registro 26" -> "26", "apagar o gasto em padaria" -> "padaria")
    corpo = COMANDO_EXCLUSAO_REGEX.sub("", texto_limpo).strip()
    corpo = re.sub(
        r"^(?:o\s+|a\s+|os\s+|as\s+)?(?:gasto|despesa|receita|item|id|registro|lan[cç]amento|transa[cç][aã]o|n[uú]mero|#)?\s*(?:em|de|do|da|no|na|com)?\s*#?",
        "",
        corpo,
        flags=re.IGNORECASE
    ).strip()

    match_id = re.match(r"^#?(\d+)\b", corpo)
    if match_id:
        tid = int(match_id.group(1))
        res = excluir_transacao_por_termo_ou_id(usuario_id, transacao_id=tid)
    elif corpo:
        termo = re.sub(r"\d+(?:[.,]\d{1,2})?", "", _limpar_unidades_reais(corpo)).strip()
        res = excluir_transacao_por_termo_ou_id(usuario_id, termo_busca=termo or corpo)
    else:
        resumo_atual = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "excluir_transacao",
            "transacao_registrada": False,
            "resumo": resumo_atual,
            "resposta": "⚠️ Informe o número do ID ou nome do item que deseja apagar (ex: *apague 26* ou *apagar gasto em padaria*)."
        }

    novo_resumo = obter_resumo_financeiro(usuario_id)
    if res["sucesso"]:
        return {
            "intencao": "excluir_transacao",
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": (
                f"🗑️ *Registro #{res['id']} excluído com sucesso!*\n"
                f"• *Item removido:* {res['descricao']} ({res['categoria']})\n"
                f"• *Valor estornado:* R$ {res['valor']:.2f}\n"
                f"• *Saldo Disponível Atual:* R$ {novo_resumo['saldo']:.2f}"
            )
        }
    return {
        "intencao": "excluir_transacao",
        "transacao_registrada": False,
        "resumo": novo_resumo,
        "resposta": f"⚠️ {res['erro']}\nDigite *extrato* para consultar os IDs (#) disponíveis."
    }


def editar_transacao_existente(
    usuario_id: int,
    transacao_id: int = None,
    termo_busca: str = None,
    novo_valor: float = None,
    nova_descricao: str = None,
    nova_categoria: str = None
) -> dict:
    db = SessionLocal()
    try:
        registro = None
        if transacao_id is not None:
            registro = db.execute(
                text("SELECT id, descricao, valor, categoria, tipo FROM transacoes WHERE id = :tid AND usuario_id = :uid LIMIT 1"),
                {"tid": int(transacao_id), "uid": int(usuario_id)}
            ).fetchone()

        if not registro and termo_busca:
            termo_limpo = _limpar_unidades_reais(termo_busca).lower().strip()
            termo_limpo = re.sub(r"\b(?:editar|alterar|atualizar|corrigir|mudar|para|valor|id|item|gasto|de|em)\b", "", termo_limpo).strip()
            if termo_limpo:
                registro = db.execute(
                    text("""
                        SELECT id, descricao, valor, categoria, tipo
                        FROM transacoes
                        WHERE usuario_id = :uid AND (LOWER(descricao) LIKE :termo OR LOWER(categoria) LIKE :termo)
                        ORDER BY id DESC LIMIT 1
                    """),
                    {"uid": int(usuario_id), "termo": f"%{termo_limpo}%"}
                ).fetchone()

        if not registro:
            registro = db.execute(
                text("SELECT id, descricao, valor, categoria, tipo FROM transacoes WHERE usuario_id = :uid ORDER BY id DESC LIMIT 1"),
                {"uid": int(usuario_id)}
            ).fetchone()

        if not registro:
            return {"sucesso": False, "erro": "Não encontrei nenhum lançamento para editar."}

        desc_final = _limpar_unidades_reais(nova_descricao).capitalize() if nova_descricao else registro.descricao
        val_final = float(novo_valor) if (novo_valor is not None and float(novo_valor) > 0) else float(registro.valor)
        cat_final = nova_categoria.capitalize() if nova_categoria else registro.categoria

        db.execute(
            text("UPDATE transacoes SET descricao = :desc, valor = :val, categoria = :cat WHERE id = :tid AND usuario_id = :uid"),
            {"desc": desc_final, "val": val_final, "cat": cat_final, "tid": registro.id, "uid": int(usuario_id)}
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
            "tipo": registro.tipo
        }
    except Exception as e:
        db.rollback()
        return {"sucesso": False, "erro": str(e)}
    finally:
        db.close()


def gerar_consulta_categoria_ou_item(usuario_id: int, termo_busca: str) -> str:
    """
    Intenção 5 ('consultar_categoria'): Busca quanto o usuário gastou em uma categoria oficial
    (ex: 'Alimentação', 'Transporte') OU em um item/local específico (ex: 'padaria', 'gasolina', 'uber').
    """
    termo_limpo = _limpar_unidades_reais(termo_busca or "").strip()
    termo_limpo = re.sub(
        r"^(?:quanto\s+eu\s+gastei|quanto\s+gastei|extrato|resumo|gastos?)\s*(?:em|de|do|da|no|na|com)?\s*",
        "",
        termo_limpo,
        flags=re.IGNORECASE
    ).strip(" ?!.")

    termo_norm = _normalizar(termo_limpo)
    transacoes = listar_transacoes(usuario_id, limite=200)
    despesas = [t for t in transacoes if t.get("tipo") == "despesa"]

    # Verifica se bate com uma Categoria Oficial ou palavra do mapa
    cat_oficial_alvo = None
    for cat in CATEGORIAS_OFICIAIS:
        if _normalizar(cat) == termo_norm or (termo_norm and termo_norm in _normalizar(cat)):
            cat_oficial_alvo = cat
            break

    # Filtra por item específico (ex: "padaria", "uber", "gasolina")
    itens_por_descricao = [
        t for t in despesas
        if termo_norm and (termo_norm in _normalizar(t.get("descricao", "")) or _normalizar(t.get("descricao", "")) in termo_norm)
    ]

    # Se o usuário perguntou por um item específico (ex: "padaria") e há lançamentos com esse nome
    if itens_por_descricao and not cat_oficial_alvo:
        total_item = sum(float(i.get("valor", 0)) for i in itens_por_descricao)
        linhas = [
            f"🔎 *CONSULTA POR ITEM/LOCAL: {termo_limpo.upper()}*",
            f"• *Total gasto em '{termo_limpo.capitalize()}':* R$ {total_item:.2f}",
            f"• *Quantidade de lançamentos:* {len(itens_por_descricao)}\n",
            "📋 *Detalhamento:*"
        ]
        for item in itens_por_descricao[:15]:
            linhas.append(f"  • #{item.get('id')} {item.get('descricao')} ({item.get('categoria')}): R$ {float(item.get('valor', 0)):.2f}")
        alerta_teto = verificar_alerta_teto_categoria(usuario_id, termo_limpo)
        if alerta_teto:
            linhas.append(f"\n{alerta_teto}")
        return "\n".join(linhas)

    # Se não achou direto como categoria oficial, tenta inferir pelo mapa (ex: "mercado" -> Alimentação)
    if not cat_oficial_alvo:
        cat_inferida = inferir_categoria(termo_limpo, "despesa")
        if cat_inferida != "Outros":
            cat_oficial_alvo = cat_inferida

    if cat_oficial_alvo:
        itens_cat = [t for t in despesas if _normalizar(t.get("categoria", "")) == _normalizar(cat_oficial_alvo)]
        total_cat = sum(float(i.get("valor", 0)) for i in itens_cat)
        linhas = [
            f"📂 *EXTRATO DA CATEGORIA: {cat_oficial_alvo.upper()}*",
            f"• *Total gasto na categoria:* R$ {total_cat:.2f}",
            f"• *Lançamentos registrados:* {len(itens_cat)}"
        ]
        alerta_teto = verificar_alerta_teto_categoria(usuario_id, cat_oficial_alvo)
        if alerta_teto:
            linhas.append(alerta_teto)

        if itens_cat:
            linhas.append("\n📋 *Itens lançados nesta categoria:*")
            for item in itens_cat[:15]:
                linhas.append(f"  • #{item.get('id')} {item.get('descricao')}: R$ {float(item.get('valor', 0)):.2f}")
        else:
            linhas.append("\nNenhum gasto registrado nesta categoria até o momento.")
        return "\n".join(linhas)

    # Caso não exista nem como item nem como categoria do mapa, retorna a lista de categorias oficiais
    lista_str = ", ".join(CATEGORIAS_OFICIAIS)
    return (
        f"🤔 Não encontrei registros para *'{termo_limpo}'*.\n\n"
        f"📌 *Categorias oficiais disponíveis:*\n{lista_str}\n\n"
        f"💡 Experimente perguntar: *'quanto gastei em Alimentação'* ou *'quanto gastei em padaria'*."
    )


def analisar_viabilidade_gasto(usuario_id: int, valor_compra: float, categoria: str, descricao: str) -> str:
    """
    Intenção 1 ('aconselhamento'): Responde se o usuário pode comprar algo (NÃO registra transação),
    cruzando saldo atual, gastos fixos e Teto de Gastos da categoria.
    """
    resumo = obter_resumo_financeiro(usuario_id)
    saldo_atual = float(resumo.get("saldo", 0.0))
    total_entradas = float(resumo.get("total_receitas", 0.0))
    novo_saldo = saldo_atual - float(valor_compra)

    if total_entradas <= 0 and saldo_atual <= 0:
        return (
            "⚠️ *Aconselhamento Financeiro (RN01):* Você ainda não possui rendas ou saldo positivo cadastrado. "
            "Cadastre seu salário ou receita antes de realizar novos gastos."
        )

    tetos = listar_tetos_gastos(usuario_id)
    aviso_teto = ""
    estoura_teto = False
    for t in tetos:
        if _normalizar(t["categoria"]) in (_normalizar(categoria), _normalizar(descricao)):
            projecao_cat = t["gasto_atual"] + float(valor_compra)
            if projecao_cat > t["valor_teto"]:
                estoura_teto = True
                aviso_teto = (
                    f"\n🚨 *Atenção ao Teto de {t['categoria']}:* Seu limite é R$ {t['valor_teto']:.2f} "
                    f"e com esta compra você atingirá *R$ {projecao_cat:.2f}* (ultrapassando o teto!)."
                )
            else:
                aviso_teto = (
                    f"\n🎯 *Dentro do Teto de {t['categoria']}:* Após a compra, seu consumo ficará em "
                    f"R$ {projecao_cat:.2f} de R$ {t['valor_teto']:.2f}."
                )

    if novo_saldo < 0:
        return (
            f"🛑 *Compra Não Recomendada ({descricao} - R$ {valor_compra:.2f}):*\n"
            f"• Seu saldo disponível atual é de *R$ {saldo_atual:.2f}*.\n"
            f"• Essa despesa deixaria sua conta no negativo em *R$ {novo_saldo:.2f}*.{aviso_teto}\n"
            f"*(Nenhuma transação foi registrada)*"
        )

    if estoura_teto or novo_saldo < (saldo_atual * 0.2):
        return (
            f"⚠️ *Cautela Recomendada ({descricao} - R$ {valor_compra:.2f}):*\n"
            f"• Você tem saldo suficiente (sobrariam *R$ {novo_saldo:.2f}*), mas a compra compromete sua reserva ou teto.{aviso_teto}\n"
            f"*(Nenhuma transação foi registrada)*"
        )

    return (
        f"✅ *Compra Viável ({descricao} - R$ {valor_compra:.2f})!*\n"
        f"• *Saldo Atual:* R$ {saldo_atual:.2f}\n"
        f"• *Saldo Projetado após a compra:* R$ {novo_saldo:.2f}{aviso_teto}\n"
        f"*(Simulação concluída — nenhuma transação foi registrada)*"
    )


def verificar_alerta_teto_categoria(usuario_id: int, categoria_ou_item: str) -> str:
    tetos = listar_tetos_gastos(usuario_id)
    alvo_norm = _normalizar(categoria_ou_item)
    for t in tetos:
        if _normalizar(t["categoria"]) == alvo_norm:
            if t["estourou"]:
                excesso = t["gasto_atual"] - t["valor_teto"]
                return (
                    f"🚨 *ALERTA DE TETO EXCEDIDO ({t['categoria']}):* "
                    f"Gasto acumulado de *R$ {t['gasto_atual']:.2f}* ({t['percentual']:.0f}%) para um teto de *R$ {t['valor_teto']:.2f}* "
                    f"(excedeu R$ {excesso:.2f})!"
                )
            elif t["percentual"] >= 80:
                return (
                    f"⚠️ *Alerta de Teto ({t['categoria']}):* Você já atingiu *{t['percentual']:.0f}%* do limite "
                    f"(R$ {t['gasto_atual']:.2f} / R$ {t['valor_teto']:.2f}). Restam R$ {t['disponivel']:.2f}."
                )
            else:
                return (
                    f"🎯 *Teto {t['categoria']}:* R$ {t['gasto_atual']:.2f} / R$ {t['valor_teto']:.2f} ({t['percentual']:.0f}% usado)."
                )
    return ""


def gerar_relatorio_tetos_texto(usuario_id: int) -> str:
    tetos = listar_tetos_gastos(usuario_id)
    if not tetos:
        return (
            "🎯 *TETOS DE GASTOS (ORÇAMENTO MENSAL)*\n"
            "Nenhum teto de gastos configurado até o momento.\n\n"
            "💡 *Exemplos para criar pelo chat:*\n"
            "• `definir teto de Alimentação para 600`\n"
            "• `teto Lazer 300`"
        )
    linhas = ["🎯 *ACOMPANHAMENTO DOS TETOS DE GASTOS*"]
    for t in tetos:
        icone = "🔴" if t["estourou"] else ("🟡" if t["percentual"] >= 80 else "🟢")
        linhas.append(
            f"{icone} *{t['categoria']}*: R$ {t['gasto_atual']:.2f} de R$ {t['valor_teto']:.2f} "
            f"({t['percentual']:.0f}%) — Disponível: R$ {t['disponivel']:.2f}"
        )
    return "\n".join(linhas)


def gerar_extrato_agrupado(usuario_id: int) -> str:
    resumo = obter_resumo_financeiro(usuario_id)
    transacoes = listar_transacoes(usuario_id, limite=50)
    gastos_fixos = listar_gastos_fixos(usuario_id)
    tetos_map = {_normalizar(t["categoria"]): t for t in resumo.get("tetos_gastos", [])}

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
            info_teto = ""
            if _normalizar(cat) in tetos_map:
                t_obj = tetos_map[_normalizar(cat)]
                info_teto = f" | 🎯 Teto: R$ {t_obj['valor_teto']:.2f} ({t_obj['percentual']:.0f}%)"
            linhas.append(f"▸ *{cat}* (Subtotal: R$ {subtotal:.2f}{info_teto}):")
            for item in itens[:10]:
                linhas.append(f"   • #{item.get('id')} {item.get('descricao')}: R$ {float(item.get('valor', 0)):.2f}")

    linhas.append("\n💡 *Dica:* Para excluir um item, digite `apague ID` (ex: `apague 26`).")
    return "\n".join(linhas)


def gerar_grafico_financeiro_png(usuario_id: int) -> io.BytesIO:
    resumo = obter_resumo_financeiro(usuario_id)
    entradas = float(resumo.get("total_receitas", 0.0))
    saidas = float(resumo.get("total_despesas", 0.0))
    categorias = resumo.get("despesas_por_categoria", [])
    evolucao = resumo.get("grafico_evolucao", {"labels": ["Hoje"], "saldos": [resumo.get("saldo", 0.0)]})

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), facecolor="#0f172a")
    for ax in axes:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors="#f8fafc", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#334155")

    axes[0].bar(["Entradas", "Saídas"], [entradas, saidas], color=["#10b981", "#ef4444"], width=0.45)
    axes[0].set_title("Entradas vs. Saídas (R$)", color="#f8fafc", fontweight="bold", fontsize=10)

    if categorias:
        axes[1].pie(
            [float(c["total"]) for c in categorias],
            labels=[c["categoria"] for c in categorias],
            autopct="%1.1f%%",
            textprops={"color": "#f8fafc", "fontsize": 8},
            startangle=140
        )
    else:
        axes[1].text(0.5, 0.5, "Sem despesas", color="#94a3b8", ha="center", va="center")
    axes[1].set_title("Gastos por Categoria", color="#f8fafc", fontweight="bold", fontsize=10)

    ev_labels = evolucao.get("labels") or ["Hoje"]
    ev_saldos = evolucao.get("saldos") or [resumo.get("saldo", 0.0)]
    axes[2].plot(ev_labels, ev_saldos, color="#3b82f6", marker="o", linewidth=2)
    axes[2].fill_between(range(len(ev_saldos)), ev_saldos, color="#3b82f6", alpha=0.18)
    axes[2].set_title("Evolução do Saldo (R$)", color="#f8fafc", fontweight="bold", fontsize=10)
    axes[2].tick_params(axis="x", rotation=25)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def enviar_grafico_telegram(chat_id: str, usuario_id: int, legenda: str = "📊 Seus Relatórios Gráficos Financeiros") -> bool:
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    try:
        buf = gerar_grafico_financeiro_png(usuario_id)
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {"photo": ("relatorio_financeiro.png", buf.getvalue(), "image/png")}
        data = {"chat_id": str(chat_id), "caption": legenda}
        resp = requests.post(url, data=data, files=files, timeout=15)
        return resp.status_code == 200
    except Exception:
        return False


# ==================== INTERPRETAÇÃO CENTRAL (AS 12 INTENÇÕES) ====================

def interpretar_mensagem_financeira(usuario_id: int, mensagem_usuario: str) -> dict:
    if isinstance(usuario_id, str) and isinstance(mensagem_usuario, int):
        usuario_id, mensagem_usuario = mensagem_usuario, usuario_id

    texto = (mensagem_usuario or "").strip()

    # RF07: Bloqueio de Moeda Estrangeira
    if MOEDAS_ESTRANGEIRAS_REGEX.search(texto):
        return {
            "intencao": "erro_moeda",
            "transacao_registrada": False,
            "resposta": (
                "⚠️ *Operação Negada (RF07):* O sistema utiliza exclusivamente o Real Brasileiro (BRL - R$). "
                "Valores em moedas estrangeiras não são aceitos."
            )
        }

    # PRIORIDADE 1: Comando de Exclusão ("apague 26", "excluir #26", "apagar padaria", "remover teto lazer")
    exclusao = _tentar_interceptar_exclusao(usuario_id, texto)
    if exclusao is not None:
        return exclusao

    resumo = obter_resumo_financeiro(usuario_id)
    historico_recente = listar_historico_mensagens(usuario_id, limite=8)
    ultimas_transacoes = listar_transacoes(usuario_id, limite=6)

    client = obter_cliente_groq()
    if client:
        resultado_llm = _processar_com_llm(client, usuario_id, texto, resumo, historico_recente, ultimas_transacoes)
        if resultado_llm is not None:
            return resultado_llm

    return _motor_nlu_inteligente_local(usuario_id, texto, resumo)


def _processar_com_llm(client, usuario_id: int, texto: str, resumo: dict, historico: list, ultimas_transacoes: list) -> dict:
    tetos_str = ", ".join(
        [f"{t['categoria']}: R$ {t['gasto_atual']:.2f}/R$ {t['valor_teto']:.2f}" for t in resumo.get("tetos_gastos", [])]
    ) or "Nenhum teto configurado"

    ultimas_str = "\n".join(
        [f"- ID #{t.get('id')}: {t['tipo'].upper()} R$ {t['valor']:.2f} ({t['categoria']} - {t['descricao']})" for t in ultimas_transacoes]
    ) or "Sem transações recentes."

    prompt_sistema = f"""Você é o Assistente Financeiro Inteligente do sistema FinanceControl.
=== CONTEXTO ATUAL DO USUÁRIO (BRL - R$) ===
• Saldo Disponível: R$ {resumo['saldo']:.2f} | Entradas: R$ {resumo['total_receitas']:.2f} | Saídas: R$ {resumo['total_despesas']:.2f}
• Tetos de Gastos Ativos: {tetos_str}
• Últimas Transações:
{ultimas_str}

=== REGRAS DE CLASSIFICAÇÃO DAS 12 INTENÇÕES ===
1. "aconselhamento": Perguntas se pode comprar/gastar algo (ex: "posso comprar um relógio de 50 reais?"). NÃO registre transação.
2. "registrar_despesa" | "registrar_receita": Gastos ou ganhos variáveis (ex: "gastei 50 reais na padaria", "lanche 50", "recebi 300 de freela"). Ignore a palavra "reais" na descricao (ex: descricao="Padaria").
3. "cadastrar_gasto_fixo" | "cadastrar_renda_fixa": Compromissos ou ganhos mensais recorrentes (ex: "aluguel todo dia 10 de 1500", "salário dia 5 4000 reais"). Preencha "dia_mes".
4. "editar_transacao": Quando o usuário pedir para editar, alterar, atualizar ou corrigir um registro já salvo (ex: "editar padaria para 35 reais", "alterar lanche para 40", "editar id 12 para 100"). Coloque em "termo_busca" o item a ser buscado (ex: "Padaria"), em "transacao_id" o ID numérico se informado, em "valor" o novo valor float, e em "nova_descricao" se quiser renomear.
5. "consultar_categoria": Perguntas sobre quanto gastou ou extrato em um item/local específico OU categoria (ex: "quanto gastei em padaria", "extrato em alimentacao", "extrato em gasolina", "quanto gastei com uber"). Coloque em "termo_busca" o item ou categoria exata que o usuário perguntou (ex: "padaria", "alimentacao", "gasolina").
6. "consultar_saldo": Pedidos de saldo geral, extrato geral ou resumo completo (sem especificar categoria ou item).
7. "enviar_grafico": Pedidos de gráfico ou relatório visual (ex: "me manda o gráfico", "mostrar gráficos", "evolução do saldo").
8. "ambiguidade": Quando informou apenas verbo e valor sem dizer onde/o quê (ex: "gastei 50", "paguei 100") ou ação sem valor (ex: "comprei um tênis").
9. "excluir_transacao": Quando o usuário pedir para apagar, deletar, excluir ou remover um registro (ex: "apague 26", "apagar o gasto em padaria", "apagar o registro 15"). Coloque em "transacao_id" o número do ID ou em "termo_busca" o nome do item. JAMAIS classifique "apague" como registrar_despesa!
10. "definir_teto": Quando pedir para definir, criar ou configurar um teto de gastos / limite / orçamento para uma categoria ou item (ex: "definir teto de alimentação para 600", "teto lazer 300"). Coloque a categoria/item em "categoria" (ou "termo_busca") e o limite em "valor".
11. "consultar_teto": Quando perguntar sobre seus tetos ou limites de gastos (ex: "como estão meus tetos?", "ver limites de gastos").
12. "excluir_teto": Quando pedir para remover/apagar um teto de gastos (ex: "remover teto de lazer").

Responda APENAS com um objeto JSON válido:
{{
  "intencao": "aconselhamento" | "registrar_despesa" | "registrar_receita" | "cadastrar_gasto_fixo" | "cadastrar_renda_fixa" | "editar_transacao" | "consultar_categoria" | "consultar_saldo" | "enviar_grafico" | "ambiguidade" | "excluir_transacao" | "definir_teto" | "consultar_teto" | "excluir_teto" | "conversa_geral",
  "valor": numero_float_ou_null,
  "dia_mes": numero_int_ou_null,
  "categoria": "Alimentação" | "Transporte" | "Moradia" | "Vestuário" | "Saúde" | "Educação" | "Lazer" | "Salário" | "Renda Extra" | "Outros",
  "descricao": "descrição limpa sem a palavra reais",
  "termo_busca": "item/categoria para busca, edição ou exclusão ou null",
  "transacao_id": numero_int_ou_null,
  "nova_descricao": "novo nome se edição ou null",
  "nova_categoria": "nova categoria se edição ou null",
  "resposta_usuario": "resposta amigável em português"
}}"""

    mensagens_llm = [{"role": "system", "content": prompt_sistema}]
    for m in historico[-4:]:
        role = "user" if m.get("remetente") == "user" else "assistant"
        mensagens_llm.append({"role": role, "content": m.get("mensagem", "")})
    mensagens_llm.append({"role": "user", "content": texto})

    try:
        completion = client.chat.completions.create(
            model=MODELO_GROQ,
            messages=mensagens_llm,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        dados = json.loads(completion.choices[0].message.content)
        return _executar_acao_estruturada(usuario_id, texto, dados, resumo)
    except Exception:
        return None


def _executar_acao_estruturada(usuario_id: int, texto_original: str, dados: dict, resumo_antes: dict) -> dict:
    intencao = dados.get("intencao", "conversa_geral")
    valor = dados.get("valor")
    dia_mes = dados.get("dia_mes") or extrair_dia_do_mes(texto_original)
    categoria = dados.get("categoria") or inferir_categoria(texto_original)
    descricao = _limpar_unidades_reais((dados.get("descricao") or texto_original).strip())
    resposta_ia = dados.get("resposta_usuario", "")

    # Trava de segurança: qualquer comando iniciado por "apague/excluir/deletar" vai para exclusão
    if COMANDO_EXCLUSAO_REGEX.match(texto_original.strip()) or COMANDO_EXCLUSAO_REGEX.match(descricao):
        interceptado = _tentar_interceptar_exclusao(usuario_id, texto_original)
        if interceptado:
            return interceptado

    # 1. ACONSELHAMENTO FINANCEIRO (NÃO registra transação)
    if intencao == "aconselhamento":
        val_simulado = float(valor) if (valor and float(valor) > 0) else (extrair_valor_monetario(texto_original) or 0.0)
        if val_simulado <= 0:
            return {
                "intencao": "ambiguidade",
                "transacao_registrada": False,
                "resumo": resumo_antes,
                "resposta": "🤔 Para eu analisar se a compra vale a pena, informe o valor em Reais (ex: *'posso comprar um relógio de 150 reais?'*)."
            }
        analise = analisar_viabilidade_gasto(usuario_id, val_simulado, categoria, descricao)
        return {
            "intencao": "aconselhamento",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": analise
        }

    # 2. REGISTRAR DESPESA OU RECEITA VARIÁVEL (Ignorando "reais")
    elif intencao in ("registrar_despesa", "registrar_receita") and valor and float(valor) > 0:
        tipo_banco = "despesa" if intencao == "registrar_despesa" else "receita"
        descricao_limpa = re.sub(r"\b(?:reais|real|r\$)\b", "", descricao, flags=re.IGNORECASE).strip().capitalize() or "Lançamento"

        if not _ja_registrado_recentemente(usuario_id, tipo_banco, float(valor), descricao_limpa):
            res_db = registrar_transacao(
                usuario_id=usuario_id,
                tipo=tipo_banco,
                valor=float(valor),
                categoria=categoria,
                descricao=descricao_limpa,
                moeda="BRL"
            )
            if not res_db.get("sucesso"):
                return {"intencao": "erro", "transacao_registrada": False, "resposta": res_db.get("erro", "Erro ao registrar.")}
        else:
            res_db = {"sucesso": True}

        novo_resumo = obter_resumo_financeiro(usuario_id)
        icone = "💸" if tipo_banco == "despesa" else "💰"
        msg = (
            f"✅ *{tipo_banco.capitalize()} registrada com sucesso!*\n"
            f"• *Descrição:* {descricao_limpa}\n"
            f"• *Categoria:* {categoria}\n"
            f"• *Valor:* {icone} R$ {float(valor):.2f}\n"
            f"• *Saldo Disponível Atual:* R$ {novo_resumo['saldo']:.2f}"
        )
        if res_db.get("alerta"):
            msg += f"\n\n{res_db['alerta']}"
        if tipo_banco == "despesa":
            alerta_teto = verificar_alerta_teto_categoria(usuario_id, categoria) or verificar_alerta_teto_categoria(usuario_id, descricao_limpa)
            if alerta_teto:
                msg += f"\n\n{alerta_teto}"

        return {
            "intencao": intencao,
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": msg
        }

    # 3. CADASTRAR GASTO FIXO OU RENDA FIXA RECORRENTE
    elif intencao == "cadastrar_renda_fixa" and valor and float(valor) > 0:
        dia_pag = int(dia_mes) if (dia_mes and 1 <= int(dia_mes) <= 31) else 5
        desc_fixa = re.sub(r"\b(?:reais|real|todo\s+dia\s+\d+|dia\s+\d+)\b", "", descricao, flags=re.IGNORECASE).strip().capitalize() or "Salário"
        criar_renda_fixa(usuario_id, desc_fixa, float(valor), dia_pag, True)
        novo_resumo = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "cadastrar_renda_fixa",
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": (
                f"✅ *Renda Fixa Mensal Cadastrada!*\n"
                f"• *Descrição:* {desc_fixa}\n"
                f"• *Valor:* 💰 R$ {float(valor):.2f} (Todo dia {dia_pag})\n"
                f"• *Saldo Disponível Atual:* R$ {novo_resumo['saldo']:.2f}"
            )
        }

    elif intencao == "cadastrar_gasto_fixo" and valor and float(valor) > 0:
        dia_venc = int(dia_mes) if (dia_mes and 1 <= int(dia_mes) <= 31) else 10
        desc_fixa = re.sub(r"\b(?:reais|real|todo\s+dia\s+\d+|dia\s+\d+)\b", "", descricao, flags=re.IGNORECASE).strip().capitalize() or "Gasto Fixo"
        criar_gasto_fixo(usuario_id, desc_fixa, float(valor), dia_venc, True)
        novo_resumo = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "cadastrar_gasto_fixo",
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": (
                f"📌 *Gasto Fixo Mensal Cadastrado!*\n"
                f"• *Descrição:* {desc_fixa}\n"
                f"• *Valor:* 💸 R$ {float(valor):.2f} (Vencimento dia {dia_venc})\n"
                f"• *Saldo Disponível Atual:* R$ {novo_resumo['saldo']:.2f}"
            )
        }

    # 4. EDITAR TRANSAÇÃO JÁ SALVA
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
                "resposta": f"⚠️ {res_edicao['erro']}\nExemplo: *'editar padaria para 35 reais'* ou *'editar id 12 para 100'*."
            }
        novo_resumo = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "editar_transacao",
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": (
                f"✏️ *Registro #{res_edicao['id']} editado com sucesso!*\n"
                f"• *Descrição:* {res_edicao['descricao']} ({res_edicao['categoria']})\n"
                f"• *Valor Anterior:* R$ {res_edicao['valor_antigo']:.2f} ➡️ *Novo Valor:* R$ {res_edicao['valor']:.2f}\n"
                f"• *Saldo Disponível Atual:* R$ {novo_resumo['saldo']:.2f}"
            )
        }

    # 5. CONSULTAR CATEGORIA OU ITEM ESPECÍFICO ("quanto gastei em padaria", "extrato em alimentacao")
    elif intencao == "consultar_categoria":
        termo = dados.get("termo_busca") or dados.get("categoria") or texto_original
        relatorio_cat = gerar_consulta_categoria_ou_item(usuario_id, termo)
        return {
            "intencao": "consultar_categoria",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": relatorio_cat
        }

    # 6. CONSULTAR SALDO / EXTRATO GERAL AGRUPADO
    elif intencao == "consultar_saldo":
        return {
            "intencao": "consultar_saldo",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": gerar_extrato_agrupado(usuario_id)
        }

    # 7. ENVIAR GRÁFICO (WEB + TELEGRAM)
    elif intencao == "enviar_grafico":
        novo_resumo = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "enviar_grafico",
            "enviar_grafico": True,
            "exibir_graficos_web": True,
            "transacao_registrada": False,
            "resumo": novo_resumo,
            "graficos": {
                "pizza": novo_resumo["grafico_pizza"],
                "colunas": novo_resumo["grafico_colunas"],
                # "evolucao": novo_resumo["grafico_evolucao"]
            },
            "resposta": (
                "📈 *Aqui está o resumo visual das suas finanças!*\n"
                "Foram gerados os 3 relatórios: **Pizza (Gastos por Categoria)**, **Barras (Entradas vs. Saídas)** e **Linha (Evolução do Saldo)**."
            )
        }

    # 8. AMBIGUIDADE (Informou apenas verbo e valor sem dizer onde/o quê: ex "gastei 50")
    elif intencao == "ambiguidade":
        return {
            "intencao": "ambiguidade",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": resposta_ia or (
                "🤔 *Preciso de mais um detalhe (RF06):* Você informou o valor, mas não especificou onde ou com o que foi o gasto.\n"
                "Por favor, envie novamente completo (ex: *'Gastei 50 na padaria'* ou *'Lanche 50'*)."
            )
        }

    # 9. EXCLUIR TRANSAÇÃO ("apague 26", "apagar o gasto em padaria", "apagar o registro 15")
    elif intencao == "excluir_transacao":
        tid = dados.get("transacao_id")
        termo = dados.get("termo_busca") or descricao
        res_del = excluir_transacao_por_termo_ou_id(usuario_id, transacao_id=tid, termo_busca=termo)
        novo_resumo = obter_resumo_financeiro(usuario_id)
        if res_del["sucesso"]:
            return {
                "intencao": "excluir_transacao",
                "transacao_registrada": True,
                "resumo": novo_resumo,
                "resposta": (
                    f"🗑️ *Registro #{res_del['id']} excluído com sucesso!*\n"
                    f"• *Item removido:* {res_del['descricao']} ({res_del['categoria']})\n"
                    f"• *Valor estornado:* R$ {res_del['valor']:.2f}\n"
                    f"• *Saldo Disponível Atual:* R$ {novo_resumo['saldo']:.2f}"
                )
            }
        return {
            "intencao": "excluir_transacao",
            "transacao_registrada": False,
            "resumo": novo_resumo,
            "resposta": f"⚠️ {res_del['erro']}"
        }

    # 10. DEFINIR TETO DE GASTOS
    elif intencao == "definir_teto" and valor and float(valor) > 0:
        alvo_teto = dados.get("termo_busca") or categoria
        if _normalizar(alvo_teto) in ("outros", "teto", "limite", ""):
            alvo_teto = inferir_categoria(texto_original)
        res_teto = definir_teto_gasto(usuario_id, alvo_teto, float(valor))
        novo_resumo = obter_resumo_financeiro(usuario_id)
        alerta = verificar_alerta_teto_categoria(usuario_id, alvo_teto)
        return {
            "intencao": "definir_teto",
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": (
                f"🎯 *Teto de Gastos Definido!*\n"
                f"• *Categoria / Item:* {res_teto.get('categoria', alvo_teto)}\n"
                f"• *Orçamento Máximo:* R$ {float(valor):.2f}\n"
                f"{alerta}"
            )
        }

    # 11. CONSULTAR TETOS DE GASTOS
    elif intencao == "consultar_teto":
        return {
            "intencao": "consultar_teto",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": gerar_relatorio_tetos_texto(usuario_id)
        }

    # 12. EXCLUIR TETO DE GASTOS
    elif intencao == "excluir_teto":
        alvo = dados.get("termo_busca") or categoria
        excluir_teto_gasto(usuario_id, alvo)
        novo_resumo = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "excluir_teto",
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": f"🗑️ O teto de gastos para *{alvo}* foi removido com sucesso."
        }

    return {
        "intencao": intencao,
        "transacao_registrada": False,
        "resumo": resumo_antes,
        "resposta": resposta_ia or gerar_extrato_agrupado(usuario_id)
    }


# ==================== FALLBACK DETERMINÍSTICO LOCAL (AS 12 INTENÇÕES OFFLINE) ====================

def _motor_nlu_inteligente_local(usuario_id: int, texto: str, resumo: dict) -> dict:
    # 9. Exclusão prioritária ("apague 26", "excluir padaria")
    exclusao = _tentar_interceptar_exclusao(usuario_id, texto)
    if exclusao is not None:
        return exclusao

    texto_limpo = _limpar_unidades_reais(texto)
    texto_lower = texto_limpo.lower().strip()
    valor = extrair_valor_monetario(texto_limpo)
    dia_mes = extrair_dia_do_mes(texto_limpo)

    # 10, 11, 12. Teto de Gastos ("definir teto alimentação 600", "meus tetos")
    if any(k in texto_lower for k in ["teto", "limite de gasto", "orcamento", "orçamento"]):
        if valor and valor > 0:
            cat = inferir_categoria(texto_limpo, "despesa")
            if cat == "Outros":
                palavras = [
                    p for p in re.findall(r"[a-zA-ZÀ-ÿ]+", texto_limpo)
                    if p.lower() not in ("definir", "criar", "teto", "limite", "orcamento", "orçamento", "de", "da", "do", "para", "em", "gasto", "gastos")
                ]
                cat = " ".join(palavras).capitalize() if palavras else "Outros"
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "definir_teto",
                "categoria": cat,
                "termo_busca": cat,
                "valor": valor
            }, resumo)
        return _executar_acao_estruturada(usuario_id, texto, {"intencao": "consultar_teto"}, resumo)

    # 7. Enviar Gráfico ("me manda o gráfico", "mostrar gráficos")
    if any(g in texto_lower for g in ["grafico", "gráfico", "graficos", "gráficos", "pizza", "evolução", "evolucao"]):
        return _executar_acao_estruturada(usuario_id, texto, {"intencao": "enviar_grafico"}, resumo)

    # 4. Editar Transação ("editar padaria para 35 reais", "editar id 12 para 100")
    if re.match(r"^(?:editar|edite|alterar|altere|atualizar|corrigir|mudar)\b", texto_lower):
        match_id = re.search(r"\b(?:id|item|registro|#)\s*(\d+)\b", texto_lower)
        tid = int(match_id.group(1)) if match_id else None
        termo_edicao = re.sub(
            r"^(?:editar|edite|alterar|altere|atualizar|corrigir|mudar)\s+|\b(?:id|item|registro|#)\s*\d+\b|\bpara\s+.*$|\d+(?:[.,]\d{1,2})?",
            "",
            texto_lower
        ).strip()
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "editar_transacao",
            "transacao_id": tid,
            "termo_busca": termo_edicao or None,
            "valor": valor
        }, resumo)

    # 1. Aconselhamento ("posso comprar um relógio de 50 reais?")
    if any(p in texto_lower for p in ["posso comprar", "posso gastar", "da pra comprar", "dá pra comprar", "vale a pena comprar", "consigo comprar"]):
        desc_compra = re.sub(
            r"^(?:posso|da pra|dá pra|vale a pena|consigo)\s+(?:comprar|gastar)\s+(?:um|uma|o|a)?\s*|\b(?:de|por|no valor de)\b|\d+(?:[.,]\d{1,2})?|\?",
            " ",
            texto_limpo,
            flags=re.IGNORECASE
        ).strip().capitalize() or "Compra"
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "aconselhamento",
            "valor": valor,
            "categoria": inferir_categoria(desc_compra, "despesa"),
            "descricao": desc_compra
        }, resumo)

    # 5. Consultar Categoria ou Item Específico ("quanto gastei em padaria", "extrato em alimentacao", "quanto gastei com uber")
    match_cat = re.search(
        r"(?:quanto\s+(?:eu\s+)?gastei|gastei\s+quanto|extrato|resumo|gastos?)\s+(?:em|de|do|da|no|na|com)\s+([a-zA-ZÀ-ÿ0-9\s]+)",
        texto_lower
    )
    if match_cat:
        termo_especifico = match_cat.group(1).strip(" ?.!").strip()
        if termo_especifico and termo_especifico not in ("hoje", "mes", "mês", "semana", "geral", "total", "tudo"):
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "consultar_categoria",
                "termo_busca": termo_especifico
            }, resumo)

    # 6. Consultar Saldo / Extrato Geral
    if any(p in texto_lower for p in ["saldo", "extrato", "resumo", "quanto eu tenho"]):
        return _executar_acao_estruturada(usuario_id, texto, {"intencao": "consultar_saldo"}, resumo)

    # 3. Cadastrar Renda Fixa ou Gasto Fixo Recorrente ("aluguel todo dia 10 de 1500", "salário dia 5 4000 reais")
    if valor and (dia_mes is not None or any(f in texto_lower for f in ["todo dia", "todo mes", "todo mês", "gasto fixo", "renda fixa", "mensal"])):
        eh_renda_fixa = any(r in texto_lower for r in ["salario", "salário", "renda", "recebo", "bolsa", "aposentadoria"])
        desc_fixo = re.sub(
            r"\b(?:cadastrar|cadastre|como|gasto\s+fixo|renda\s+fixa|fixo|fixa|mensal|todo\s+dia\s+\d+|dia\s+\d+|de|no\s+valor\s+de)\b|\d+(?:[.,]\d{1,2})?",
            " ",
            texto_limpo,
            flags=re.IGNORECASE
        ).strip().capitalize() or ("Salário" if eh_renda_fixa else "Gasto Fixo")
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "cadastrar_renda_fixa" if eh_renda_fixa else "cadastrar_gasto_fixo",
            "valor": valor,
            "dia_mes": dia_mes or (5 if eh_renda_fixa else 10),
            "categoria": inferir_categoria(desc_fixo, "receita" if eh_renda_fixa else "despesa"),
            "descricao": desc_fixo
        }, resumo)

    # 8. Ambiguidade ("gastei 50", "paguei 100", "comprei hoje")
    verbos_soltos = re.sub(r"\b(?:gastei|paguei|comprei|recebi|ganhei|hoje|ontem|agora|valor|de)\b|\d+(?:[.,]\d{1,2})?", "", texto_lower).strip()
    if (valor and not verbos_soltos) or (not valor and any(v in texto_lower for v in ["gastei", "paguei", "comprei"])):
        return _executar_acao_estruturada(usuario_id, texto, {"intencao": "ambiguidade"}, resumo)

    # 2A. Registrar Receita Variável ("recebi 300 de freela")
    if valor and any(r in texto_lower for r in ["recebi", "ganhei", "entrou", "freela", "pix recebido", "vendi"]):
        desc_rec = re.sub(
            r"\b(?:recebi|ganhei|entrou|de|do|da|no|na|valor|por)\b|\d+(?:[.,]\d{1,2})?",
            " ",
            texto_limpo,
            flags=re.IGNORECASE
        ).strip().capitalize() or "Receita"
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "registrar_receita",
            "valor": valor,
            "categoria": inferir_categoria(desc_rec, "receita"),
            "descricao": desc_rec
        }, resumo)

    # 2B. Registrar Despesa Variável ("gastei 50 reais na padaria", "lanche 50")
    if valor and not COMANDO_EXCLUSAO_REGEX.match(texto_lower):
        desc_desp = re.sub(
            r"\b(?:gastei|paguei|comprei|cadastre|cadastrar|lance|lancar|lançar|gasto|despesa|de|do|da|no|na|nos|nas|em|com|por|valor)\b|\d+(?:[.,]\d{1,2})?",
            " ",
            texto_limpo,
            flags=re.IGNORECASE
        ).strip()
        desc_desp = re.sub(r"\s+", " ", desc_desp).strip().capitalize()
        if desc_desp:
            return _executar_acao_estruturada(usuario_id, texto, {
                "intencao": "registrar_despesa",
                "valor": valor,
                "categoria": inferir_categoria(desc_desp, "despesa"),
                "descricao": desc_desp
            }, resumo)

    return {
        "intencao": "conversa_geral",
        "transacao_registrada": False,
        "resumo": resumo,
        "resposta": (
            f"Olá! Seu saldo disponível é de *R$ {resumo['saldo']:.2f}*.\n\n"
            f"Você pode enviar comandos como:\n"
            f"• *Gasto/Ganho:* `Gastei 50 reais na padaria` ou `Recebi 300 de freela`\n"
            f"• *Fixos:* `Aluguel todo dia 10 de 1500` ou `Salário dia 5 4000 reais`\n"
            f"• *Consulta por item/categoria:* `Quanto gastei em padaria?` ou `Extrato em alimentação`\n"
            f"• *Editar ou Apagar:* `Editar padaria para 35 reais` ou `apague 26`\n"
            f"• *Teto de Gastos e Gráficos:* `Teto Alimentação 600` ou `Me manda o gráfico`"
        )
    }