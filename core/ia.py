# Caminho: core/ia.py
import os
import re
import json
from dotenv import load_dotenv
from groq import Groq
from core.database import (
    registrar_transacao,
    obter_resumo_financeiro
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODELO_GROQ = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

MOEDAS_ESTRANGEIRAS_REGEX = re.compile(
    r"(\bUSD\b|\bEUR\b|\bGBP\b|\bARS\b|\bPYG\b|d[óo]lar|d[óo]lares|euro|euros|libra|pesos|guaranis|US\$|€|£)",
    re.IGNORECASE
)


def obter_cliente_groq():
    if not GROQ_API_KEY:
        return None
    return Groq(api_key=GROQ_API_KEY)


def interpretar_mensagem_financeira(usuario_id: int, mensagem_usuario: str) -> dict:
    texto = mensagem_usuario.strip()

    # RF07 e RN04: Bloqueio imediato de moedas estrangeiras
    if MOEDAS_ESTRANGEIRAS_REGEX.search(texto):
        return {
            "intencao": "erro_moeda",
            "resposta": (
                "⚠️ *Aviso (RN04):* O sistema opera exclusivamente com o Real Brasileiro (BRL - R$). "
                "Por favor, informe o valor convertido em Reais (ex: 'Gastei 50 reais no mercado')."
            )
        }

    resumo = obter_resumo_financeiro(usuario_id)
    client = obter_cliente_groq()

    if not client:
        return _fallback_pln_regras(usuario_id, texto, resumo)

    prompt_sistema = f"""
Você é um Assistente Financeiro Inteligente (conselheiro financeiro pessoal no Brasil).
Contexto financeiro atual do usuário (em BRL):
- Total de Receitas no período: R$ {resumo['total_receitas']:.2f}
- Total de Despesas no período: R$ {resumo['total_despesas']:.2f}
- Saldo Disponível: R$ {resumo['saldo']:.2f}

Analise a mensagem do usuário e retorne EXCLUSIVAMENTE um objeto JSON válido com a seguinte estrutura:
{{
  "intencao": "registrar_despesa" | "registrar_receita" | "consultar_saldo" | "aconselhamento" | "ambiguidade" | "conversa_geral",
  "valor": float ou null,
  "categoria": "Alimentação" | "Transporte" | "Moradia" | "Lazer" | "Saúde" | "Educação" | "Salário" | "Outros" | null,
  "descricao": string curta ou null,
  "moeda": "BRL",
  "resposta_usuario": "Texto claro, empático e prestativo em português para o usuário"
}}

Regras obrigatórias:
1. Se o usuário disser que gastou/pagou/comprou algo com valor claro e contexto (ex: 'Gastei 45 reais na padaria'), defina intencao='registrar_despesa', extraia valor e categoria.
2. Se o usuário disser apenas 'Gastei 50' sem informar onde ou com o quê, defina intencao='ambiguidade' (RF06) e pergunte em 'resposta_usuario' qual foi a categoria ou local do gasto antes de salvar.
3. Se o usuário perguntar se pode comprar/gastar algo (ex: 'Posso comprar um relógio de 200 reais?'), defina intencao='aconselhamento'.
"""

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
        return _fallback_pln_regras(usuario_id, texto, resumo)

    intencao = dados.get("intencao", "conversa_geral")
    valor = dados.get("valor")
    categoria = dados.get("categoria") or "Outros"
    descricao = dados.get("descricao") or texto
    resposta = dados.get("resposta_usuario", "")

    if intencao in ("registrar_despesa", "registrar_receita") and valor:
        tipo_banco = "despesa" if intencao == "registrar_despesa" else "receita"
        resultado_db = registrar_transacao(
            usuario_id=usuario_id,
            tipo=tipo_banco,
            valor=float(valor),
            categoria=categoria,
            descricao=descricao,
            moeda="BRL"
        )
        if not resultado_db["sucesso"]:
            return {"intencao": "erro", "resposta": resultado_db["erro"]}

        novo_resumo = obter_resumo_financeiro(usuario_id)
        msg_confirmacao = (
            f"✅ *{tipo_banco.capitalize()} registrada com sucesso!*\n"
            f"• *Valor:* R$ {float(valor):.2f}\n"
            f"• *Categoria:* {categoria}\n"
            f"• *Saldo Atual:* R$ {novo_resumo['saldo']:.2f}"
        )
        if resultado_db.get("alerta"):
            msg_confirmacao += f"\n\n{resultado_db['alerta']}"

        return {"intencao": intencao, "resposta": msg_confirmacao}

    if intencao == "aconselhamento":
        # RN01: Cálculo de viabilidade exige receitas registradas no mês
        if resumo["total_receitas"] <= 0:
            return {
                "intencao": "aconselhamento",
                "resposta": (
                    "⚠️ *Regra RN01:* Para que eu possa calcular a viabilidade desse gasto com segurança, "
                    "você precisa primeiro registrar suas receitas do mês (ex: 'Recebi 3000 reais de salário')."
                )
            }
        if valor and float(valor) > resumo["saldo"]:
            return {
                "intencao": "aconselhamento",
                "resposta": (
                    f"🚨 *Não recomendado no momento.* O item custa R$ {float(valor):.2f}, "
                    f"mas seu saldo disponível é de R$ {resumo['saldo']:.2f}. "
                    "Realizar essa compra deixará seu orçamento negativo."
                )
            }

    if intencao == "consultar_saldo":
        return {
            "intencao": "consultar_saldo",
            "resposta": (
                f"📊 *Resumo da sua Conta (BRL):*\n"
                f"• *Receitas:* R$ {resumo['total_receitas']:.2f}\n"
                f"• *Despesas:* R$ {resumo['total_despesas']:.2f}\n"
                f"• *Saldo Disponível:* R$ {resumo['saldo']:.2f}"
            )
        }

    return {"intencao": intencao, "resposta": resposta or "Como posso ajudar nas suas finanças hoje?"}


def _fallback_pln_regras(usuario_id: int, texto: str, resumo: dict) -> dict:
    texto_lower = texto.lower()
    match_valor = re.search(r"(\d+(?:[\.,]\d{1,2})?)", texto_lower)
    valor = float(match_valor.group(1).replace(",", ".")) if match_valor else None

    if any(p in texto_lower for p in ["saldo", "extrato", "resumo"]):
        return {
            "intencao": "consultar_saldo",
            "resposta": (
                f"📊 *Resumo Financeiro:*\n"
                f"• Receitas: R$ {resumo['total_receitas']:.2f}\n"
                f"• Despesas: R$ {resumo['total_despesas']:.2f}\n"
                f"• Saldo Atual: R$ {resumo['saldo']:.2f}"
            )
        }

    if valor and any(p in texto_lower for p in ["gastei", "paguei", "comprei"]):
        palavras = texto_lower.split()
        if len(palavras) <= 3:
            return {
                "intencao": "ambiguidade",
                "resposta": f"Você mencionou o valor de R$ {valor:.2f}, mas onde ou com o que foi esse gasto? (Ex: 'Gastei {valor:.2f} na padaria')"
            }
        registrar_transacao(usuario_id, "despesa", valor, "Outros", texto)
        novo = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "registrar_despesa",
            "resposta": f"✅ Despesa de R$ {valor:.2f} registrada! Saldo atual: R$ {novo['saldo']:.2f}"
        }

    if valor and any(p in texto_lower for p in ["recebi", "ganhei", "salário", "salario"]):
        registrar_transacao(usuario_id, "receita", valor, "Salário", texto)
        novo = obter_resumo_financeiro(usuario_id)
        return {
            "intencao": "registrar_receita",
            "resposta": f"✅ Receita de R$ {valor:.2f} registrada! Saldo atual: R$ {novo['saldo']:.2f}"
        }

    return {
        "intencao": "conversa_geral",
        "resposta": "Olá! Envie seus gastos ou receitas (ex: 'Gastei 45 reais no mercado' ou 'Qual meu saldo?')."
    }