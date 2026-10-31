# Caminho: core/ia.py
import os
import re
import json

from dotenv import load_dotenv
try:
    from groq import Groq
except Exception:
    Groq = None

try:
    import matplotlib
    matplotlib.use("Agg")  # Modo sem janela gráfica para rodar em background no Flask/Telegram
    import matplotlib.pyplot as plt
except Exception:
    plt = None

from core.database import (
    registrar_transacao,
    criar_renda_fixa,
    criar_gasto_fixo,
    listar_rendas_fixas,
    listar_gastos_fixos,
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
    "Alimentação": ["mercado", "supermercado", "padaria", "lanche", "restaurante", "ifood", "pizza", "hamburguer", "almoço", "almoco", "janta", "jantar", "café", "cafe", "açougue", "acougue", "feira", "sorvete", "doce"],
    "Transporte": ["uber", "99", "gasolina", "combustível", "combustivel", "posto", "etanol", "diesel", "ônibus", "onibus", "passagem", "estacionamento", "pedágio", "pedagio", "oficina", "mecânico", "mecanico"],
    "Moradia": ["aluguel", "condomínio", "condominio", "luz", "energia", "água", "agua", "internet", "gás", "gas", "iptu"],
    "Vestuário": ["camiseta", "camisa", "calça", "calca", "tênis", "tenis", "sapato", "roupa", "blusa", "jaqueta", "relógio", "relogio", "loja", "bermuda", "vestido"],
    "Saúde": ["farmácia", "farmacia", "remédio", "remedio", "médico", "medico", "consulta", "exame", "dentista", "academia", "hospital"],
    "Educação": ["faculdade", "curso", "livro", "mensalidade", "material", "udc", "escola", "apostila"],
    "Lazer": ["cinema", "show", "viagem", "passeio", "bar", "cerveja", "jogo", "streaming", "netflix", "spotify", "ingresso"],
    "Salário": ["salário", "salario", "pagamento", "adiantamento", "vale", "bolsa", "estágio", "estagio"],
    "Renda Extra": ["freela", "freelance", "venda", "vendi", "pix recebido", "rendimento", "dividendo", "bônus", "bonus", "comissão", "comissao"]
}

CATEGORIAS_OFICIAIS = [
    "Alimentação", "Transporte", "Moradia", "Lazer",
    "Saúde", "Educação", "Vestuário", "Outros"
]


def _normalizar_texto(texto: str) -> str:
    mapa = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
        "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC"
    )
    return (texto or "").translate(mapa).lower().strip()


def inferir_categoria(texto: str, tipo: str = "despesa") -> str:
    texto_lower = texto.lower()
    for categoria, palavras in MAPA_CATEGORIAS.items():
        if any(p in texto_lower for p in palavras):
            return categoria
    return "Salário" if tipo == "receita" else "Outros"


def extrair_dia_E_valor(texto: str):
    """
    Separa corretamente o dia do mês (ex: 'dia 30', 'todo dia 10', 'vencimento 15')
    e o valor monetário (ex: 'R$ 1500', '5000').
    """
    texto_limpo = re.sub(r"(\d)\.(\d{3})", r"\1\2", texto)
    dia_extraido = None

    match_dia = re.search(
        r"(?:todo\s+dia|no\s+dia|vencimento\s+dia|recebo\s+dia|vencimento|dia)\s*(\d{1,2})\b",
        texto_limpo,
        flags=re.IGNORECASE
    )
    if match_dia:
        d = int(match_dia.group(1))
        if 1 <= d <= 31:
            dia_extraido = d
            inicio, fim = match_dia.span()
            texto_sem_dia = texto_limpo[:inicio] + " " + texto_limpo[fim:]
        else:
            texto_sem_dia = texto_limpo
    else:
        texto_sem_dia = texto_limpo

    matches_valor = re.findall(r"(?:r\$\s*)?(\d+(?:[\.,]\d{1,2})?)", texto_sem_dia, flags=re.IGNORECASE)
    valor_extraido = float(matches_valor[0].replace(",", ".")) if matches_valor else None
    return valor_extraido, dia_extraido


def montar_extrato_separado_por_tipo(usuario_id: int, resumo: dict = None) -> str:
    """
    Monta o extrato completo separado por tipo de gasto (Gastos Fixos e Categorias Variáveis)
    mostrando exatamente onde cada valor foi gasto.
    """
    if not resumo:
        resumo = obter_resumo_financeiro(usuario_id)

    gastos_fixos = [g for g in listar_gastos_fixos(usuario_id) if g.get("is_active", True)]
    transacoes = listar_transacoes(usuario_id, limite=100)

    por_categoria = {}
    for t in transacoes:
        if t.get("tipo") == "despesa":
            cat = (t.get("categoria") or "Outros").strip()
            desc = (t.get("descricao") or cat).strip().capitalize()
            val = float(t.get("valor") or 0.0)
            por_categoria.setdefault(cat, []).append((desc, val))

    linhas = [
        "📊 *Resumo Financeiro Consolidado (BRL):*",
        f"• *Rendas Fixas Mensais:* R$ {resumo['total_rendas_fixas']:.2f}",
        f"• *Receitas Variáveis:* R$ {resumo['receitas_variaveis']:.2f}",
        f"• *Gastos Fixos Mensais:* R$ {resumo['total_gastos_fixos']:.2f}",
        f"• *Despesas Variáveis:* R$ {resumo['despesas_variaveis']:.2f}",
        f"• *Saldo Líquido Disponível:* *R$ {resumo['saldo']:.2f}*"
    ]

    if gastos_fixos:
        linhas.append("\n📌 *Gastos Fixos Ativos:*")
        for g in gastos_fixos:
            linhas.append(f"  • {g['description']} (Dia {g['due_day']}): R$ {float(g['amount']):.2f}")

    if por_categoria:
        linhas.append("\n📂 *Gastos Separados por Tipo / Onde Gastou:*")
        for cat, lista_itens in sorted(por_categoria.items(), key=lambda x: sum(v for _, v in x[1]), reverse=True):
            subtotal = sum(v for _, v in lista_itens)
            linhas.append(f"🏷️ *{cat}:* R$ {subtotal:.2f}")
            agrupado_local = {}
            for desc_item, val_item in lista_itens:
                agrupado_local[desc_item] = agrupado_local.get(desc_item, 0.0) + val_item
            for local_nome, soma_local in sorted(agrupado_local.items(), key=lambda x: x[1], reverse=True):
                linhas.append(f"   └ {local_nome}: R$ {soma_local:.2f}")

    return "\n".join(linhas)


def gerar_grafico_financeiro_png(usuario_id: int, resumo: dict = None) -> str | None:
    """
    Gera a imagem (.png) com os dois gráficos disponíveis no sistema Web:
    1. Colunas: Entradas vs. Saídas
    2. Rosca/Pizza: Gastos separados por Categoria/Tipo
    Retorna o caminho do arquivo salvo para envio pelo bot do Telegram.
    """
    if plt is None:
        return None

    try:
        if not resumo:
            resumo = obter_resumo_financeiro(usuario_id)

        pasta_temp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graficos_temp")
        os.makedirs(pasta_temp, exist_ok=True)
        caminho_png = os.path.join(pasta_temp, f"grafico_financeiro_user_{usuario_id}.png")

        # Aproveita os dados de gráfico de pizza já calculados em obter_resumo_financeiro, ou monta a partir das transações
        labels_pizza = []
        valores_pizza = []
        grafico_pizza_db = resumo.get("grafico_pizza") or {}

        if grafico_pizza_db.get("labels") and grafico_pizza_db.get("valores"):
            for lbl, val in zip(grafico_pizza_db["labels"], grafico_pizza_db["valores"]):
                if float(val or 0) > 0:
                    labels_pizza.append(str(lbl))
                    valores_pizza.append(float(val))
        else:
            soma_cat = {}
            for t in listar_transacoes(usuario_id, limite=100):
                if t.get("tipo") == "despesa" and float(t.get("valor") or 0) > 0:
                    c = t.get("categoria") or "Outros"
                    soma_cat[c] = soma_cat.get(c, 0.0) + float(t["valor"])
            for g in listar_gastos_fixos(usuario_id):
                if g.get("is_active", True) and float(g.get("amount") or 0) > 0:
                    nome_fixo = f"Fixo: {g['description']}"
                    soma_cat[nome_fixo] = soma_cat.get(nome_fixo, 0.0) + float(g["amount"])
            labels_pizza = list(soma_cat.keys())
            valores_pizza = list(soma_cat.values())

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.8), facecolor="#0f172a")
        fig.suptitle(
            f"FinanceControl — Visão Geral (Saldo: R$ {resumo['saldo']:.2f})",
            color="#f8fafc", fontsize=13, fontweight="bold", y=0.97
        )

        # Gráfico 1: Entradas vs Saídas
        ax1.set_facecolor("#1e293b")
        eixo_x = ["Entradas", "Saídas"]
        eixo_y = [float(resumo.get("total_receitas", 0.0)), float(resumo.get("total_despesas", 0.0))]
        barras = ax1.bar(eixo_x, eixo_y, color=["#10b981", "#ef4444"], width=0.45)
        ax1.set_title("Entradas vs. Saídas (BRL)", color="#e2e8f0", fontsize=11, fontweight="bold")
        ax1.tick_params(colors="#cbd5e1", labelsize=9)
        for spine in ax1.spines.values():
            spine.set_color("#334155")

        topo = max(eixo_y + [100.0]) * 1.22
        ax1.set_ylim(0, topo)
        for b in barras:
            h = b.get_height()
            ax1.annotate(
                f"R$ {h:.2f}",
                xy=(b.get_x() + b.get_width() / 2, h),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center", va="bottom",
                color="#f8fafc", fontsize=9, fontweight="bold"
            )

        # Gráfico 2: Distribuição por Categoria/Local
        ax2.set_facecolor("#1e293b")
        if valores_pizza and sum(valores_pizza) > 0:
            cores = ["#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4", "#f97316"]
            _, _, autotexts = ax2.pie(
                valores_pizza,
                labels=labels_pizza,
                autopct="%1.1f%%",
                startangle=135,
                colors=cores[:len(labels_pizza)],
                textprops={"color": "#f8fafc", "fontsize": 8.5},
                wedgeprops={"width": 0.45, "edgecolor": "#1e293b", "linewidth": 2}
            )
            for at in autotexts:
                at.set_color("#ffffff")
                at.set_fontweight("bold")
            ax2.set_title("Onde Você Gastou (Por Categoria)", color="#e2e8f0", fontsize=11, fontweight="bold")
        else:
            ax2.text(
                0.5, 0.5, "Sem despesas registradas\npara gerar o gráfico",
                ha="center", va="center", color="#94a3b8", fontsize=10
            )
            ax2.set_axis_off()

        plt.tight_layout(rect=[0, 0, 1, 0.92])
        plt.savefig(caminho_png, dpi=140, facecolor=fig.get_facecolor())
        plt.close(fig)
        return caminho_png
    except Exception as e:
        print(f"⚠️ Erro ao gerar gráfico PNG: {e}")
        return None


def obter_cliente_groq():
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("sua_chave"):
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
                "Converta o valor para Reais antes de enviar."
            )
        }

    resumo = obter_resumo_financeiro(usuario_id)
    rendas_fixas = listar_rendas_fixas(usuario_id)
    gastos_fixos = listar_gastos_fixos(usuario_id)
    historico_recente = listar_historico_mensagens(usuario_id, limite=8)
    ultimas_transacoes = listar_transacoes(usuario_id, limite=5)

    resultado = None
    client = obter_cliente_groq()
    if client:
        resultado = _processar_com_llm(client, usuario_id, texto, resumo, rendas_fixas, gastos_fixos, historico_recente, ultimas_transacoes)

    if not resultado:
        resultado = _motor_nlu_inteligente_local(usuario_id, texto, resumo)

    # Anexa o caminho da imagem do gráfico sempre que o usuário pedir saldo, extrato, gráfico ou consulta de categoria
    if resultado.get("intencao") in ("consultar_saldo", "consultar_categoria"):
        caminho_img = gerar_grafico_financeiro_png(usuario_id, resultado.get("resumo") or resumo)
        if caminho_img:
            resultado["grafico_path"] = caminho_img

    return resultado


def _processar_com_llm(client, usuario_id: int, texto: str, resumo: dict, rendas_fixas: list, gastos_fixos: list, historico: list, ultimas_transacoes: list) -> dict:
    rendas_str = ", ".join([f"{r['description']}: R$ {r['amount']:.2f} (Dia {r['day_of_month']})" for r in rendas_fixas if r["is_active"]]) or "Nenhuma renda fixa cadastrada"
    gastos_str = ", ".join([f"{g['description']}: R$ {g['amount']:.2f} (Venc. dia {g['due_day']})" for g in gastos_fixos if g["is_active"]]) or "Nenhum gasto fixo cadastrado"
    historico_formatado = "\n".join([f"{'Usuário' if h['remetente'] == 'usuario' else 'Assistente'}: {h['mensagem']}" for h in historico[-6:]])

    prompt_sistema = f"""Você é o Assistente Financeiro Inteligente do sistema FinanceControl (integrado ao Telegram e Web).
Você entende linguagem natural totalmente livre, comandos curtos e abreviados.

=== CONTEXTO FINANCEIRO ATUAL DO USUÁRIO (MOEDA: BRL - R$) ===
- Saldo Disponível Atual: R$ {resumo['saldo']:.2f}
- Total de Receitas (Fixas + Variáveis): R$ {resumo['total_receitas']:.2f} (Rendas Fixas: R$ {resumo['total_rendas_fixas']:.2f} | Variáveis: R$ {resumo['receitas_variaveis']:.2f})
- Total de Despesas (Fixas + Variáveis): R$ {resumo['total_despesas']:.2f} (Gastos Fixos: R$ {resumo['total_gastos_fixos']:.2f} | Variáveis: R$ {resumo['despesas_variaveis']:.2f})
- Rendas Fixas Ativas: {rendas_str}
- Gastos Fixos Ativos: {gastos_str}

=== HISTÓRICO RECENTE DA CONVERSA ===
{historico_formatado}

=== INSTRUÇÕES DE CLASSIFICAÇÃO DE INTENÇÕES ===
1. CADASTRAR GASTO FIXO (intencao = "cadastrar_gasto_fixo"):
   - Despesas recorrentes mensais ou contas com dia de vencimento informado.
   - Aceite frases completas OU comandos curtos: "aluguel dia 10 1500", "internet dia 15 120", "gasto fixo luz 200", "aluguel 1500", "Cadastrar meu aluguel como gasto fixo no valor de R$ 1500 todo dia 10".
   - Extraia: `valor` (float), `descricao` (ex: "Aluguel", "Internet"), `dia_mes` (int de 1 a 31; padrão 10 se não informado).

2. CADASTRAR RENDA FIXA (intencao = "cadastrar_renda_fixa"):
   - Ganhos recorrentes mensais (salário, vale, bolsa, aposentadoria) ou receitas com dia de recebimento.
   - Aceite frases completas OU comandos curtos: "salario dia 30 5000 reais", "salario 4000", "vale dia 5 600", "Meu salário é uma renda fixa de R$ 4000".
   - Extraia: `valor` (float), `descricao` (ex: "Salário", "Vale-Alimentação"), `dia_mes` (int de 1 a 31; padrão 5 se não informado).

3. REGISTRAR DESPESA VARIÁVEL AVULSA (intencao = "registrar_despesa"):
   - Gastos pontuais do dia a dia, com ou sem verbo.
   - Exemplos: "lanche 30", "gasolina 150", "gasto 150 posto de combustivel", "uber 25", "Gastei 45 reais na padaria".

4. REGISTRAR RECEITA VARIÁVEL AVULSA (intencao = "registrar_receita"):
   - Ganhos pontuais/extras: "receita 1000 salario", "freela 300", "ganhei 200 reais", "pix recebido 150".

5. CONSULTA DE VIABILIDADE / ACONSELHAMENTO (intencao = "aconselhamento"):
   - Perguntas como "Posso comprar um relógio de 200 reais?". Analise o Saldo Disponível (R$ {resumo['saldo']:.2f}).

6. CONSULTA DE SALDO / EXTRATO / GRÁFICO (intencao = "consultar_saldo"):
   - Comandos como "saldo", "extrato", "extrato da semana", "resumo", "grafico", "gráfico", "me manda o grafico", "onde gastei".

7. AMBIGUIDADE (intencao = "ambiguidade"):
   - Quando o usuário informar APENAS um valor sem nenhuma descrição (ex: "Gastei 50", "150").

8. CONSULTA DE CATEGORIA (intencao = "consultar_categoria"):
   - Perguntas específicas sobre quanto foi gasto em um local ou categoria (ex: "quanto gastei em mercado?", "resumo de lazer").

Retorne EXCLUSIVAMENTE um JSON válido com estas chaves:
{{
  "intencao": "cadastrar_gasto_fixo" | "cadastrar_renda_fixa" | "registrar_despesa" | "registrar_receita" | "aconselhamento" | "consultar_saldo" | "consultar_categoria" | "ambiguidade" | "conversa_geral",
  "valor": float_ou_null,
  "dia_mes": int_1_a_31_ou_null,
  "categoria": "string",
  "descricao": "string curta (ex: Aluguel, Salário, Lanche, Gasolina)",
  "resposta_usuario": "Texto claro e amigável em português"
}}"""

    try:
        completion = client.chat.completions.create(
            model=MODELO_GROQ,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": texto}
            ],
            temperature=0.15,
            response_format={"type": "json_object"}
        )
        dados = json.loads(completion.choices[0].message.content)
        return _executar_acao_estruturada(usuario_id, texto, dados, resumo)
    except Exception:
        return None


def _executar_acao_estruturada(usuario_id: int, texto_original: str, dados: dict, resumo_antes: dict) -> dict:
    intencao = dados.get("intencao", "conversa_geral")
    valor = dados.get("valor")
    dia_mes = dados.get("dia_mes")
    categoria = dados.get("categoria") or inferir_categoria(texto_original)
    descricao = (dados.get("descricao") or texto_original).strip()
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

    # 3. Registro de Despesa ou Receita Variável
    elif intencao in ("registrar_despesa", "registrar_receita") and valor and float(valor) > 0:
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
            f"• *Descrição:* {descricao}\n"
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

    # 4. Consulta de Saldo / Extrato Separado por Tipo + Gráfico
    elif intencao == "consultar_saldo":
        return {
            "intencao": "consultar_saldo",
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": montar_extrato_separado_por_tipo(usuario_id, resumo_antes)
        }

    # 5. Consulta por Categoria de Gasto Específica (Usando listar_transacoes do core.database)
    elif intencao == "consultar_categoria":
        cat_inferida = inferir_categoria(texto_original, "despesa")
        cat_buscada_norm = _normalizar_texto(categoria or "")
        cat_oficial_encontrada = None

        if cat_inferida != "Outros":
            cat_oficial_encontrada = cat_inferida
        else:
            for cat_oficial in CATEGORIAS_OFICIAIS:
                if _normalizar_texto(cat_oficial) in cat_buscada_norm or _normalizar_texto(cat_oficial) in _normalizar_texto(texto_original):
                    cat_oficial_encontrada = cat_oficial
                    break

        if not cat_oficial_encontrada:
            lista_cats = ", ".join(CATEGORIAS_OFICIAIS)
            resposta_final = (
                f"🤔 Não encontrei a categoria *{categoria}*.\n\n"
                f"Aqui estão as categorias oficiais:\n"
                f"📌 {lista_cats}\n\n"
                f"Tente perguntar usando uma delas! (Ex: 'quanto gastei com Alimentação?')"
            )
        else:
            transacoes = listar_transacoes(usuario_id, limite=200)
            gastos_cat = [
                t for t in transacoes
                if t.get("tipo") == "despesa" and _normalizar_texto(t.get("categoria", "")) == _normalizar_texto(cat_oficial_encontrada)
            ]
            total_cat = sum(float(t.get("valor") or 0.0) for t in gastos_cat)

            if total_cat > 0:
                por_local = {}
                for t in gastos_cat:
                    loc = (t.get("descricao") or cat_oficial_encontrada).strip().capitalize()
                    por_local[loc] = por_local.get(loc, 0.0) + float(t.get("valor") or 0.0)
                detalhes = "\n".join([f"  • {k}: R$ {v:.2f}" for k, v in sorted(por_local.items(), key=lambda x: x[1], reverse=True)])
                resposta_final = (
                    f"📊 *Resumo de {cat_oficial_encontrada}*\n"
                    f"Neste mês, você já gastou *R$ {total_cat:.2f}* nesta categoria:\n{detalhes}"
                )
            else:
                resposta_final = f"📊 *Resumo de {cat_oficial_encontrada}*\nVocê não registrou nenhum gasto nesta categoria neste mês."

        return {
            "intencao": intencao,
            "transacao_registrada": False,
            "resumo": resumo_antes,
            "resposta": resposta_final
        }

    # Fallback caso não seja nenhuma das intenções acima
    return {
        "intencao": intencao,
        "transacao_registrada": False,
        "resumo": resumo_antes,
        "resposta": resposta_ia
    }


def _extrair_descricao_limpa(texto: str, padroes_remover: list) -> str:
    t = re.sub(r"(\d)\.(\d{3})", r"\1\2", texto.lower())
    t = re.sub(r"(?:todo\s+dia|no\s+dia|vencimento\s+dia|recebo\s+dia|vencimento|dia)\s*\d{1,2}\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"r\$\s*\d+(?:[\.,]\d{1,2})?|\d+(?:[\.,]\d{1,2})?\s*(?:reais|real)?", "", t, flags=re.IGNORECASE)
    for p in padroes_remover:
        t = re.sub(rf"\b{p}\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:\s*(?:de|do|da|no|na|em|com|por|para|um|uma|meu|minha|o|a)\b)+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"(?:\b(?:de|do|da|no|na|em|com|por|para|um|uma|meu|minha|o|a)\s*)+$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" -.,:;")
    return t.capitalize() if t else ""


def _motor_nlu_inteligente_local(usuario_id: int, texto: str, resumo: dict) -> dict:
    texto_lower = texto.lower().strip()
    valor, dia_extraido = extrair_dia_E_valor(texto_lower)

    # 1. Consulta de Viabilidade de Compra (RF05, RN01, RN02)
    gatilhos_consulta_compra = [
        "posso comprar", "posso gastar", "consigo comprar", "dá para comprar", "da para comprar",
        "vale a pena comprar", "é viável", "e viavel", "devo comprar", "tenho saldo para"
    ]
    if any(g in texto_lower for g in gatilhos_consulta_compra) or (texto_lower.endswith("?") and "comprar" in texto_lower):
        saldo = resumo["saldo"]
        receitas = resumo["total_receitas"]
        if valor is None:
            return {
                "intencao": "aconselhamento",
                "transacao_registrada": False,
                "resumo": resumo,
                "resposta": f"🧐 Informe o valor do item para eu avaliar! Seu saldo disponível hoje é de *R$ {saldo:.2f}*."
            }
        novo_saldo = saldo - valor
        if receitas <= 0 or saldo < valor:
            return {
                "intencao": "aconselhamento",
                "transacao_registrada": False,
                "resumo": resumo,
                "resposta": (
                    f"🚨 *Compra NÃO recomendada no momento (RN01/RN02).*\n"
                    f"• *Valor do item:* R$ {valor:.2f}\n"
                    f"• *Seu Saldo Atual:* R$ {saldo:.2f}\n"
                    f"• *Saldo projetado:* R$ {novo_saldo:.2f}\n\n"
                    f"💡 *Recomendação:* Esse gasto deixaria seu orçamento negativo. Priorize quitar compromissos fixos ou registrar suas rendas antes."
                )
            }
        return {
            "intencao": "aconselhamento",
            "transacao_registrada": False,
            "resumo": resumo,
            "resposta": (
                f"✅ *Compra Viável!*\n"
                f"• *Valor do item:* R$ {valor:.2f}\n"
                f"• *Saldo Atual:* R$ {saldo:.2f}\n"
                f"• *Saldo após a compra:* R$ {novo_saldo:.2f}"
            )
        }

    # 2. Consulta por Categoria (quando o usuário pergunta "quanto gastei em mercado?", etc.)
    if valor is None and any(g in texto_lower for g in ["quanto gastei", "quanto eu gastei", "gastei em", "gastei com", "gastei no", "gastei na", "resumo de"]):
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "consultar_categoria",
            "categoria": _extrair_descricao_limpa(texto, ["quanto", "eu", "gastei", "resumo", "total", "categoria"])
        }, resumo)

    # 3. Consulta de Saldo, Extrato Agrupado e Gráfico (quando não há valor numérico sendo lançado)
    if valor is None and any(p in texto_lower for p in ["saldo", "extrato", "resumo", "minhas finanças", "gastos fixos", "rendas fixas", "grafico", "gráfico", "onde gastei"]):
        return {
            "intencao": "consultar_saldo",
            "transacao_registrada": False,
            "resumo": resumo,
            "resposta": montar_extrato_separado_por_tipo(usuario_id, resumo)
        }

    # 4. Detecção de Renda Fixa (ex: "salario dia 30 5000 reais", "meu salario é 4000", "salario 5000")
    palavras_renda_fixa = ["salário", "salario", "vale-alimentação", "vale alimentacao", "bolsa", "aposentadoria", "pensão", "pensao"]
    gatilhos_avulsos_receita = ["recebi", "ganhei", "entrou", "receita", "pix recebido", "freela", "freelance"]

    eh_renda_fixa = False
    if valor:
        if any(termo in texto_lower for termo in ["renda fixa", "receita fixa", "salário fixo", "salario fixo", "ganho fixo"]):
            eh_renda_fixa = True
        elif dia_extraido is not None and any(p in texto_lower for p in palavras_renda_fixa + ["renda", "receita", "ganho", "recebo", "vale"]):
            eh_renda_fixa = True
        elif any(p in texto_lower for p in palavras_renda_fixa) and not any(g in texto_lower for g in gatilhos_avulsos_receita):
            eh_renda_fixa = True

    if eh_renda_fixa and valor:
        desc = _extrair_descricao_limpa(
            texto,
            ["cadastrar", "cadastre", "adicionar", "é", "e", "como", "renda", "receita", "fixa", "fixo", "mensal", "valor", "reais", "real"]
        )
        if not desc or "salário" in texto_lower or "salario" in texto_lower:
            desc = "Salário"
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "cadastrar_renda_fixa",
            "valor": valor,
            "dia_mes": dia_extraido or 5,
            "descricao": desc
        }, resumo)

    # 5. Detecção de Gasto Fixo (ex: "aluguel dia 10 1500", "internet dia 15 120", "gasto fixo luz 200")
    palavras_contas_fixas = ["aluguel", "condomínio", "condominio", "mensalidade", "internet", "plano", "faculdade", "financiamento", "iptu"]
    eh_gasto_fixo = False
    if valor:
        if any(termo in texto_lower for termo in ["gasto fixo", "despesa fixa", "conta fixa", "custo fixo"]):
            eh_gasto_fixo = True
        elif dia_extraido is not None:
            eh_gasto_fixo = True
        elif any(p in texto_lower for p in palavras_contas_fixas) and not any(v in texto_lower for v in ["paguei", "gastei"]):
            eh_gasto_fixo = True

    if eh_gasto_fixo and valor:
        desc = _extrair_descricao_limpa(
            texto,
            ["cadastrar", "cadastre", "adicionar", "é", "e", "como", "gasto", "despesa", "conta", "custo", "fixa", "fixo", "mensal", "valor", "reais", "real"]
        )
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "cadastrar_gasto_fixo",
            "valor": valor,
            "dia_mes": dia_extraido or 10,
            "descricao": desc or "Gasto Fixo"
        }, resumo)

    # 6. Receita Variável (ex: "receita 1000 salario", "ganhei 200 freela", "recebi 500")
    palavras_receita_var = [
        "recebi", "ganhei", "entrou", "receita", "renda", "freela", "freelance",
        "venda", "vendi", "pix recebido", "rendimento", "dividendo", "bônus", "bonus", "adiantamento", "vale"
    ]
    if valor and any(p in texto_lower for p in palavras_receita_var):
        desc = _extrair_descricao_limpa(
            texto,
            ["registrar", "lancar", "lançar", "receita", "renda", "recebi", "ganhei", "entrou", "valor", "reais", "real"]
        )
        categoria = inferir_categoria(texto, "receita")
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "registrar_receita",
            "valor": valor,
            "categoria": categoria,
            "descricao": desc or categoria
        }, resumo)

    # 7. Despesa Variável (aceita comandos curtos como "lanche 30", "gasolina 150", "gasto 150 posto de combustivel")
    if valor:
        desc = _extrair_descricao_limpa(
            texto,
            ["registrar", "lancar", "lançar", "gastei", "gasto", "despesa", "paguei", "comprei", "almocei", "jantei", "valor", "reais", "real"]
        )
        if not desc:
            return {
                "intencao": "ambiguidade",
                "transacao_registrada": False,
                "resumo": resumo,
                "resposta": f"🤔 *Confirmação necessária (RF06):* Identifiquei o valor de *R$ {valor:.2f}*, mas com o que foi esse gasto? (Ex: `lanche {valor:.0f}` ou `gasolina {valor:.0f}`)"
            }
        categoria = inferir_categoria(texto, "despesa")
        return _executar_acao_estruturada(usuario_id, texto, {
            "intencao": "registrar_despesa",
            "valor": valor,
            "categoria": categoria,
            "descricao": desc
        }, resumo)

    return {
        "intencao": "conversa_geral",
        "transacao_registrada": False,
        "resumo": resumo,
        "resposta": (
            f"🤖 *Olá! Sou seu Assistente Financeiro no Telegram e Web.*\n"
            f"Seu saldo disponível atual é de *R$ {resumo['saldo']:.2f}*.\n\n"
            f"Veja como é simples falar comigo:\n"
            f"• *Lançar gasto rápido:* `lanche 30` ou `gasolina 150`\n"
            f"• *Cadastrar Renda Fixa:* `salario dia 30 5000 reais`\n"
            f"• *Cadastrar Gasto Fixo:* `aluguel dia 10 1500`\n"
            f"• *Consultar valores e gráfico:* `extrato`, `saldo` ou `gráfico`"
        )
    }