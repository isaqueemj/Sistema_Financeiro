# Caminho: core/ia.py
import os
import re
import json
from dotenv import load_dotenv
from groq import Groq
from core.database import (
    registrar_transacao,
    obter_resumo_financeiro,
    listar_historico_mensagens,
    listar_transacoes
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODELO_GROQ = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

MOEDAS_ESTRANGEIRAS_REGEX = re.compile(
    r"(\bUSD\b|\bEUR\b|\bGBP\b|\bARS\b|\bPYG\b|d[óo]lar|d[óo]lares|euro|euros|libra|pesos|guaranis|US\$|€|£)",
    re.IGNORECASE
)

MAPA_CATEGORIAS = {
    "Alimentação": ["mercado", "supermercado", "padaria", "lanche", "restaurante", "ifood", "pizza", "hamburguer", "almoço", "almoco", "janta", "jantar", "café", "cafe", "açougue", "acougue", "feira"],
    "Transporte": ["uber", "99", "gasolina", "combustível", "combustivel", "ônibus", "onibus", "passagem", "estacionamento", "pedágio", "pedagio", "oficina", "pneu"],
    "Moradia": ["aluguel", "condomínio", "condominio", "luz", "energia", "água", "agua", "internet", "gás", "gas", "iptu"],
    "Vestuário": ["camiseta", "camisa", "calça", "calca", "tênis", "tenis", "sapato", "roupa", "blusa", "jaqueta", "relógio", "relogio", "óculos", "oculos", "loja"],
    "Saúde": ["farmácia", "farmacia", "remédio", "remedio", "médico", "medico", "consulta", "exame", "dentista", "academia"],
    "Educação": ["faculdade", "curso", "livro", "mensalidade", "material", "udc", "escola"],
    "Lazer": ["cinema", "show", "viagem", "passeio", "bar", "cerveja", "jogo", "streaming", "netflix", "spotify"],
    "Salário": ["salário", "salario", "pagamento", "adiantamento", "vale", "bolsa", "estágio", "estagio"],
    "Renda Extra": ["freela", "freelance", "venda", "vendi", "pix recebido", "rendimento", "dividendo", "bônus", "bonus"]
}


def inferir_categoria(texto: str, tipo: str = "despesa") -> str:
    texto_lower = texto.lower()
    for categoria, palavras in MAPA_CATEGORIAS.items():
        if any(p in texto_lower for p in palavras):
            return categoria
    return "Salário" if tipo == "receita" else "Outros"


def extrair_valor_monetario(texto: str):
    """Extrai valores numéricos como '50', '50,90', 'R$ 1.200,50'."""
    texto_limpo = re.sub(r"(\d)\.(\d{3})", r"\1\2", texto)
    matches = re.findall(r"(?:r\$\s*)?(\d+(?:[\.,]\d{1,2})?)", texto_limpo, flags=re.IGNORECASE)
    if not matches:
        return None
    return float(matches[0].replace(",", "."))


def obter_cliente_groq():
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("cole_sua_chave"):
        return None
    try:
        return Groq(api_key=GROQ_API_KEY)
    except Exception:
        return None


def interpretar_mensagem_financeira(usuario_id: int, mensagem_usuario: str) -> dict:
    texto = mensagem_usuario.strip()

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

    client = obter_cliente_groq()
    if client:
        resultado_llm = _processar_com_llm(client, usuario_id, texto, resumo, historico_recente, ultimas_transacoes)
        if resultado_llm:
            return resultado_llm

    # Motor NLU local inteligente (atua se a chave de API não estiver configurada ou sem internet)
    return _motor_nlu_inteligente_local(usuario_id, texto, resumo)


def _processar_com_llm(client, usuario_id: int, texto: str, resumo: dict, historico: list, ultimas_transacoes: list) -> dict:
    categorias_str = ", ".join(
        [f"{c['categoria']}: R$ {c['total']:.2f}" for c in resumo["despesas_por_categoria"]]
    ) or "Nenhuma despesa registrada ainda"

    ultimas_str = "\n".join(
        [f"- {t['tipo'].upper()}: R$ {t['valor']:.2f} ({t['categoria']} - {t['descricao']})" for t in ultimas_transacoes]
    ) or "Nenhuma transação recente."

    historico_formatado = "\n".join(
        [f"{'Usuário' if h['remetente'] == 'usuario' else 'Assistente'}: {h['mensagem']}" for h in historico[-6:]]
    )

    prompt_sistema = f"""Você é o Assistente Financeiro Inteligente do sistema FinanceControl (desenvolvido para apoio à decisão financeira pessoal no Brasil).

=== CONTEXTO FINANCEIRO ATUAL DO USUÁRIO (MOEDA: BRL - R$) ===
• Saldo Atual Disponível: R$ {resumo['saldo']:.2f}
• Total de Receitas (Entradas): R$ {resumo['total_receitas']:.2f}
• Total de Despesas (Saídas): R$ {resumo['total_despesas']:.2f}
• Despesas por Categoria: {categorias_str}
• Últimos Lançamentos:
{ultimas_str}

=== HISTÓRICO RECENTE DA CONVERSA ===
{historico_formatado}

=== REGRAS DE NEGÓCIO OBRIGATÓRIAS ===
1. CONSULTA DE VIABILIDADE / ACONSELHAMENTO (RF05, RN01, RN02):
   - Se o usuário perguntar se pode comprar/gastar algo (ex: "posso comprar um relógio no valor de 50 reais?", "dá para gastar X?", "vale a pena comprar Y por Z?"), classifique intencao="aconselhamento". NÃO registre transação no banco.
   - Analise matematicamente o valor do item frente ao Saldo Atual (R$ {resumo['saldo']:.2f}) e às Receitas (R$ {resumo['total_receitas']:.2f}).
   - Se Total de Receitas for R$ 0.00 (RN01) ou se o Saldo Atual for negativo ou menor que o valor do item, alerte claramente que a compra NÃO é recomendada no momento, explique o impacto no saldo (ex: seu saldo cairia de R$ {resumo['saldo']:.2f} para R$ {resumo['saldo'] - (extrair_valor_monetario(texto) or 0):.2f}) e oriente a registrar suas receitas primeiro.
   - Se houver saldo suficiente, informe quanto sobrará após a compra e dê uma dica consciente de educação financeira.

2. REGISTRO DE DESPESA OU RECEITA (RF01, RF02, RF04):
   - Se o usuário afirmar que realizou um gasto (ex: "comprei uma camiseta de 60", "gastei 45 reais no mercado", "paguei 120 de luz"), classifique intencao="registrar_despesa", extraia valor (float), categoria e descricao.
   - Se o usuário afirmar que recebeu um valor (ex: "recebi 2500 de salário", "ganhei 300 de freela"), classifique intencao="registrar_receita", extraia valor (float), categoria e descricao.

3. AMBIGUIDADE (RF06):
   - Se o usuário enviar apenas um verbo e número sem nenhum item/local/contexto (ex: "gastei 50", "paguei 30"), classifique intencao="ambiguidade" e pergunte onde ou com o que foi o gasto antes de registrar.

4. CONSULTA DE SALDO / EXTRATO (RF03):
   - Se pedir saldo, extrato ou resumo, classifique intencao="consultar_saldo".

Retorne EXCLUSIVAMENTE um objeto JSON válido no formato:
{{
  "intencao": "registrar_despesa" | "registrar_receita" | "aconselhamento" | "consultar_saldo" | "ambiguidade" | "conversa_geral",
  "valor": numero_float_ou_null,
  "categoria": "Alimentação" | "Transporte" | "Moradia" | "Vestuário" | "Saúde" | "Educação" | "Lazer" | "Salário" | "Renda Extra" | "Outros",
  "descricao": "string curta descrevendo o item",
  "resposta_usuario": "Sua resposta completa, consultiva, clara e personalizada com os números reais do usuário"
}}"""

    try:
        completion = client.chat.completions.create(
            model=MODELO_GROQ,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": texto}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        dados = json.loads(completion.choices[0].message.content)
        return _executar_acao_estruturada(usuario_id, texto, dados, resumo)
    except Exception:
        return None


def _executar_acao_estruturada(usuario_id: int, texto_original: str, dados: dict, resumo_antes: dict) -> dict:
    intencao = dados.get("intencao", "conversa_geral")
    valor = dados.get("valor")
    categoria = dados.get("categoria") or inferir_categoria(texto_original, "receita" if intencao == "registrar_receita" else "despesa")
    descricao = dados.get("descricao") or texto_original
    resposta_ia = dados.get("resposta_usuario", "")

    if intencao in ("registrar_despesa", "registrar_receita") and valor and float(valor) > 0:
        tipo_banco = "despesa" if intencao == "registrar_despesa" else "receita"
        res_db = registrar_transacao(
            usuario_id=usuario_id,
            tipo=tipo_banco,
            valor=float(valor),
            categoria=categoria,
            descricao=descricao,
            moeda="BRL"
        )
        if not res_db["sucesso"]:
            return {"intencao": "erro", "transacao_registrada": False, "resposta": res_db["erro"]}

        novo_resumo = obter_resumo_financeiro(usuario_id)
        icone = "💸" if tipo_banco == "despesa" else "💰"
        msg = (
            f"✅ *{tipo_banco.capitalize()} registrada com sucesso!*\n"
            f"• *Item/Descrição:* {descricao}\n"
            f"• *Categoria:* {categoria}\n"
            f"• *Valor:* {icone} R$ {float(valor):.2f}\n"
            f"• *Novo Saldo Atual:* R$ {novo_resumo['saldo']:.2f}"
        )
        if res_db.get("alerta"):
            msg += f"\n\n{res_db['alerta']}"
        return {
            "intencao": intencao,
            "transacao_registrada": True,
            "resumo": novo_resumo,
            "resposta": msg
        }

    return {
        "intencao": intencao,
        "transacao_registrada": False,
        "resumo": resumo_antes,
        "resposta": resposta_ia
    }


def _motor_nlu_inteligente_local(usuario_id: int, texto: str, resumo: dict) -> dict:
    """
    Motor NLU determinístico + heurístico completo para garantir respostas inteligentes
    mesmo se o servidor estiver sem GROQ_API_KEY configurada.
    """
    texto_lower = texto.lower().strip()
    valor = extrair_valor_monetario(texto_lower)

    # 1. Detecção de Perguntas Consultivas / Viabilidade de Compra (RF05, RN01, RN02)
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

        # RN01 e RN02: Sem receitas ou saldo insuficiente/negativo
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
                    f"💡 *Conselho do Assistente:* Realizar esse gasto de R$ {valor:.2f} agora comprometerá seu orçamento "
                    f"(deixando você em *R$ {novo_saldo_simulado:.2f}*). Priorize registrar suas entradas do mês ou aguarde ter saldo positivo antes de assumir essa despesa."
                )
            }

        percentual_comprometido = (valor / saldo) * 100 if saldo > 0 else 100
        aviso_cautela = (
            "⚠️ Apesar de ter saldo, essa compra consome mais de 50% de toda a sua reserva disponível. Avalie se é realmente urgente!"
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
                f"• *Saldo restante após a compra:* R$ {novo_saldo_simulado:.2f} ({percentual_comprometido:.1f}% do saldo atual)\n\n"
                f"💡 *Conselho:* {aviso_cautela} Se decidir realizar a compra, basta me avisar dizendo *'Comprei [item] por {valor:.2f}'* para eu lançar no seu Dashboard!"
            )
        }

    # 2. Detecção de Consulta de Saldo / Extrato / Resumo (RF03)
    if any(p in texto_lower for p in ["saldo", "extrato", "resumo", "quanto eu tenho", "quanto gastei", "minhas finanças", "minhas financas"]):
        cats = "\n".join([f"  - {c['categoria']}: R$ {c['total']:.2f}" for c in resumo["despesas_por_categoria"]])
        bloco_cats = f"\n\n📂 *Gastos por Categoria:*\n{cats}" if cats else ""
        return {
            "intencao": "consultar_saldo",
            "transacao_registrada": False,
            "resumo": resumo,
            "resposta": (
                f"📊 *Resumo Financeiro Atualizado:*\n"
                f"• *Total de Entradas (Receitas):* R$ {resumo['total_receitas']:.2f}\n"
                f"• *Total de Saídas (Despesas):* R$ {resumo['total_despesas']:.2f}\n"
                f"• *Saldo Atual:* R$ {resumo['saldo']:.2f}"
                f"{bloco_cats}"
            )
        }

    # 3. Detecção de Registro de Receita (RF01)
    gatilhos_receita = ["recebi", "ganhei", "entrou", "salário", "salario", "depositaram", "me pagaram", "renda", "freela"]
    if valor and any(p in texto_lower for p in gatilhos_receita):
        categoria = inferir_categoria(texto, "receita")
        dados = {
            "intencao": "registrar_receita",
            "valor": valor,
            "categoria": categoria,
            "descricao": texto.capitalize()
        }
        return _executar_acao_estruturada(usuario_id, texto, dados, resumo)

    # 4. Detecção de Registro de Despesa (RF01, RF04, RF06)
    gatilhos_despesa = [
        "gastei", "paguei", "comprei", "cadastre", "cadastrar", "lance", "lançar", "lancar",
        "despesa", "gasto", "almocei", "jantei", "abasteci", "fui no mercado", "no mercado"
    ]
    if valor and (any(p in texto_lower for p in gatilhos_despesa) or len(texto_lower.split()) >= 2):
        # RF06: Verifica se a mensagem é ambígua (ex: apenas "gastei 50")
        texto_sem_numeros = re.sub(r"r\$|\d+[\.,]?\d*|reais|real|de|no|na|valor|com|por", "", texto_lower).strip()
        palavras_restantes = [p for p in texto_sem_numeros.split() if p not in ("gastei", "paguei", "comprei", "cadastre", "gasto", "despesa")]

        if len(palavras_restantes) == 0:
            return {
                "intencao": "ambiguidade",
                "transacao_registrada": False,
                "resumo": resumo,
                "resposta": (
                    f"🤔 *Confirmação necessária (RF06):* Identifiquei o valor de *R$ {valor:.2f}*, "
                    f"mas onde ou com o que foi esse gasto? (Exemplo: *'Comprei uma camiseta de {valor:.2f}'* ou *'Gastei {valor:.2f} na padaria'*)."
                )
            }

        categoria = inferir_categoria(texto, "despesa")
        descricao_limpa = " ".join(palavras_restantes).capitalize() or texto.capitalize()
        dados = {
            "intencao": "registrar_despesa",
            "valor": valor,
            "categoria": categoria,
            "descricao": descricao_limpa
        }
        return _executar_acao_estruturada(usuario_id, texto, dados, resumo)

    # 5. Resposta contextual amigável para conversas gerais
    return {
        "intencao": "conversa_geral",
        "transacao_registrada": False,
        "resumo": resumo,
        "resposta": (
            f"Olá! Estou acompanhando seu orçamento (seu saldo atual é de *R$ {resumo['saldo']:.2f}*).\n\n"
            f"Você pode falar naturalmente comigo para:\n"
            f"• *Registrar gastos:* \"Comprei uma camiseta de 60\" ou \"Gastei 45 no mercado\"\n"
            f"• *Registrar ganhos:* \"Recebi 2500 de salário\"\n"
            f"• *Pedir conselhos:* \"Posso comprar um relógio no valor de 50 reais?\"\n"
            f"• *Consultar resumo:* \"Qual meu saldo e meus gastos?\""
        )
    }