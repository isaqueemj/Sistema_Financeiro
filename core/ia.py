import os
import json
from datetime import datetime
from openai import OpenAI

class IA:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )

    def perguntar(self, prompt_atual, historico):
        try:
            mensagens = []

            # System Prompt
            mensagens.append({
                "role": "system",
                "content": (
                    "Você é o Newton, assistente financeiro do FinanceControl. "
                    "REGRAS DE RESPOSTA:\n"
                    "1. Seja extremamente curto, direto e objetivo. Responda em no máximo 2 frases curtas.\n"
                    "2. Utilize formatação Markdown limpa quando necessário.\n"
                    "3. Nunca crie tabelas longas ou explicações excessivas.\n"
                    "4. Acione a ferramenta 'cadastrar_transacao' sempre que o usuário pedir para registrar um gasto ou ganho."
                )
            })

            for item in historico:
                mensagens.append({"role": "user", "content": item[0]})
                mensagens.append({"role": "assistant", "content": item[1]})

            mensagens.append({"role": "user", "content": prompt_atual})

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "cadastrar_transacao",
                        "description": "Cadastra um novo gasto, despesa ou receita no sistema financeiro.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "tipo": {
                                    "type": "string",
                                    "enum": ["Despesa", "Receita"], # Ajustado para o Enum do Banco
                                    "description": "Indica se é uma Despesa (gasto) ou uma Receita (entrada)."
                                },
                                "descricao": {
                                    "type": "string",
                                    "description": "Descrição breve do gasto ou receita."
                                },
                                "categoria": {
                                    "type": "string",
                                    "description": "Categoria do lançamento (ex: Alimentação, Vestuário, Transporte, etc)."
                                },
                                "valor": {
                                    "type": "number",
                                    "description": "O valor numérico da transação."
                                },
                                "local": {
                                    "type": "string",
                                    "description": "Local extraído da transação (ex: Shopping, Padaria, Loja de Roupas). Pode ser vazio."
                                },
                                "data": {
                                    "type": "string",
                                    "description": "Data e hora no formato YYYY-MM-DD HH:MM:SS."
                                }
                            },
                            "required": ["tipo", "descricao", "valor", "data", "categoria"]
                        }
                    }
                }
            ]

            response = self.client.chat.completions.create(
                model="openai/gpt-oss-20b",          
                messages=mensagens,
                tools=tools,
                tool_choice="auto"
            )

            mensagem_resposta = response.choices[0].message

            if mensagem_resposta.tool_calls:
                tool_call = mensagem_resposta.tool_calls[0]
                if tool_call.function.name == "cadastrar_transacao":
                    args = json.loads(tool_call.function.arguments)
                    
                    # Registra o horário exato no formato aceito pelo DATETIME do MySQL
                    args["data"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    if not args.get("categoria"):
                        args["categoria"] = "Outros"

                    return {
                        "tipo_acao": "tool_call",
                        "nome_funcao": tool_call.function.name,
                        "args": args
                    }

            return {
                "tipo_acao": "texto",
                "conteudo": mensagem_resposta.content or "Olá! Como posso ajudar nas suas finanças hoje?"
            }

        except Exception as e:
            return {
                "tipo_acao": "texto",
                "conteudo": f"Erro ao processar IA: {e}"
            }