from flask import Flask, render_template, request, jsonify
from core.conecta_ia import App # Importamos a classe App, que gerencia tudo
from core import database
# from database import get_conexao

"""
Nao sei como esta merda esta funcionado
Essa porcaria agora esta comunicando com as demais classes e com o front trnaquilamente
"""

app = Flask(__name__, 
            template_folder='web', 
            static_folder='web',
            static_url_path='')

# Instanciamos o App do seu core (que já cria a IA e inicia o banco)
sistema_ia = App()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/usuario/<nome_usuario>', methods=['GET'])
def obter_usuario(nome_usuario):
    conexao = get_conexao()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute("SELECT nome_completo FROM usuarios WHERE usuario = %s", (nome_usuario,))
        resultado = cursor.fetchone()
        if resultado:
            return jsonify({"nome": resultado['nome_completo']}), 200
        else:
            return jsonify({"erro": "Usuário não encontrado"}), 404
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        cursor.close()
        conexao.close()

@app.route('/api/transacoes', methods=['GET'])
def api_transacoes():
    try:
        # Busca no banco de dados
        dados = core.database.buscar_transacoes()
        # Envia para o front-end em formato JSON
        return jsonify(dados)
    except Exception as e:
        return jsonify({"erro": f"Falha ao carregar dados: {str(e)}"}), 500

@app.route('/perguntar', methods=['POST'])
def perguntar():
    try:
        dados = request.get_json()
        pergunta_usuario = dados.get('msg')

        if not pergunta_usuario:
            return jsonify({"resposta": "Por favor, digite algo."})

        # 1. Busca o histórico que já está no banco de dados
        historico = database.buscar_todo_historico()

        # 2. Pede para a IA processar a pergunta
        resultado_ia = sistema_ia.ia_instancia.perguntar(pergunta_usuario, historico)

        # 3. Verifica se a IA solicitou a execução de uma ferramenta (tool call)
        if isinstance(resultado_ia, dict) and resultado_ia.get("tipo_acao") == "tool_call":
            args = resultado_ia.get("args", {})
            tipo = args.get("tipo")
            
            # Prepara os dados alinhados com o padrão que seu database espera
            transacao_data = {
                "id": str(database.generate_id() if hasattr(database, 'generate_id') else __import__('time').time()),
                "descricao": args.get("descricao", "Sem descrição"),
                "categoria": args.get("categoria", "Geral"),
                "valor": float(args.get("valor", 0)),
                "data": args.get("data", __import__('datetime').date.today().isoformat())
            }

            # Executa o salvamento no banco de dados dependendo se é despesa ou receita
            if tipo == "despesa":
                # Verifique se a função no seu database se chama addDespesa ou similar, ajuste se necessário
                database.addDespesa(transacao_data) if hasattr(database, 'addDespesa') else database.salvar_despesa(transacao_data)
                resposta_ia = f"Despesa de R$ {transacao_data['valor']} ({transacao_data['descricao']}) cadastrada com sucesso!"
            else:
                database.addReceita(transacao_data) if hasattr(database, 'addReceita') else database.salvar_receita(transacao_data)
                resposta_ia = f"Receita de R$ {transacao_data['valor']} ({transacao_data['descricao']}) cadastrada com sucesso!"
        else:
            # Resposta de texto normal da IA
            resposta_ia = resultado_ia.get("conteudo", "Não consegui processar sua solicitação.")

        # 4. Salva a conversa no banco (para manter o contexto)
        database.salvar_conversa(pergunta_usuario, resposta_ia)

        return jsonify({"resposta": resposta_ia})
    
    except Exception as e:
        return jsonify({"resposta": f"Erro no servidor: {str(e)}"})


@app.route('/listar_chats')
def listar_chats():
    chats = database.listar_chats()
    return jsonify(chats)


@app.route('/historico/<chat_id>')
def historico(chat_id):
    dados = database.buscar_historico(chat_id)

    return jsonify([
        {"pergunta": p, "resposta": r} for p, r in dados
    ])


@app.route('/apagar_chat', methods=['POST'])
def apagar_chat():
    dados = request.get_json()
    chat_id = dados.get("chat_id")

    database.limpar_chat(chat_id)

    return jsonify({"status": "ok"})

@app.route('/api/login', methods=['POST'])
def login():
    dados = request.json
    usuario = dados.get('usuario')
    senha = dados.get('senha')
    
    # Chama a função do seu database.py
    nome_usuario = verificar_login(usuario, senha)

    if nome_usuario:
        return jsonify({"mensagem": "Login aprovado", "nome": nome_usuario}), 200
    else:
        return jsonify({"mensagem": "Login aprovado", "nome": nome_usuario}), 200

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 SERVIDOR INTELIGENCE NEWTON ATIVO")
    print("🔗 Link: http://127.0.0.1:5000")
    print("="*50 + "\n")
    app.run(host='127.0.0.1', port=5000, debug=False)