import subprocess
import sys
import os

"""
Esta merda é o inicio e tudo e onde tambem ocorre a maioria dos erros
"""

class Main:
    def __init__(self):
        # Descobre o caminho da pasta onde o main.py está
        self.diretorio_atual = os.path.dirname(os.path.abspath(__file__))

    def iniciar_servidor(self):
        # Monta o caminho completo para o arquivo web_app.py
        caminho_flask = os.path.join(self.diretorio_atual, "web_app.py")
        
        print(f"Procurando arquivo em: {caminho_flask}")
        
        if not os.path.exists(caminho_flask):
            print('Erro')
            return

        # print("\n🚀 INICIANDO INTERFACE WEB...")
        # print("🔗 Acesse: http://127.0.0.1:5000")
        
        try:
            processo = subprocess.Popen([sys.executable, caminho_flask])
            processo.wait()
        except KeyboardInterrupt:
            print("\nServidor parado.")

if __name__ == "__main__":
    main = Main()
    main.iniciar_servidor()