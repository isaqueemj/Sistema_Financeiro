from . import database
from . import ia
import os

"""
Esta parte do codigo funciona perfeitamente, entrando em contato com o back-end e a comunicação com a IA para retornar teoricamente uma resposta para 
web_app que faz a comunicação com o front-end
"""

class App:
    def __init__(self):
        # Como você importou o arquivo (módulo) ia, 
        # deve acessar a classe IA que está dentro dele:
        self.ia_instancia = ia.IA() 
        
        # Limpa apenas o histórico de conversas sempre que o servidor iniciar
        # Como as tabelas já foram criadas no Workbench, o TRUNCATE vai funcionar perfeitamente
        database.limpar_banco()

    def executar(self):
        try:
            while True:
                # Opcional: limpa a tela para manter o chat organizado
                # os.system('cls' if os.name == 'nt' else 'clear')
                
                # Descomentei o input para você conseguir testar direto no terminal se quiser
                prompt_usuario = input("\nSua pergunta (ou 0 para sair): ")
                
                if prompt_usuario == '0':
                    break

                # Busca histórico completo no banco dentro da pasta core
                historico = database.buscar_todo_historico()

                resposta = self.ia_instancia.perguntar(prompt_usuario, historico)

                # Salva a nova interação
                database.salvar_conversa(prompt_usuario, resposta)
                
                print(f"\nIA: {resposta}")

        finally:
            database.limpar_banco()

if __name__ == "__main__":
    # Teste rápido executando via terminal
    print("Iniciando modo terminal do Newton...")
    app = App()
    app.executar()