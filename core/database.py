import mysql.connector
from datetime import datetime

# ==========================================
# CONFIGURAÇÕES DO MYSQL
# ==========================================
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',      
    'password': '1234',      
    'database': 'finance_control' 
}

def get_connection():
    """Estabelece a conexão direta com o MySQL."""
    return mysql.connector.connect(**DB_CONFIG)

# ==========================================
# FUNÇÃO AUXILIAR PARA CATEGORIAS (NOVO)
# ==========================================
def obter_ou_criar_categoria(nome_categoria):
    """Busca o ID da categoria ou cria uma nova se não existir."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM categorias WHERE nome = %s', (nome_categoria,))
    resultado = cursor.fetchone()
    
    if resultado:
        cat_id = resultado[0]
    else:
        # Cria a categoria dinamicamente com limite zero
        cursor.execute('INSERT INTO categorias (nome, limite_mensal) VALUES (%s, %s)', (nome_categoria, 0.00))
        conn.commit()
        cat_id = cursor.lastrowid
        
    cursor.close()
    conn.close()
    return cat_id

# ==========================================
# FUNÇÕES DO CHAT DA IA
# ==========================================
def salvar_conversa(pergunta, resposta, usuario_id=1):
    """Salva a interação do usuário com o Newton vinculada ao ID do usuário."""
    conn = get_connection()
    cursor = conn.cursor()
    data_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Padrão DATETIME do MySQL
    
    cursor.execute('''
        INSERT INTO conversas (usuario_id, pergunta, resposta, data_hora)
        VALUES (%s, %s, %s, %s)
    ''', (usuario_id, pergunta, resposta, data_atual))
    
    conn.commit()
    cursor.close()
    conn.close()

def buscar_todo_historico(usuario_id=1):
    """Recupera o histórico para dar contexto à IA, filtrando por usuário."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT pergunta, resposta FROM conversas WHERE usuario_id = %s ORDER BY id ASC', (usuario_id,))
    rows = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return rows

def limpar_banco(usuario_id=1):
    """Apaga o histórico de conversas do usuário para testes limpos."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM conversas WHERE usuario_id = %s', (usuario_id,))
    conn.commit()
    cursor.close()
    conn.close()
    print("\n[Sistema] Histórico descartado com sucesso.")

# ==========================================
# FUNÇÕES FINANCEIRAS (CHAMADAS PELA IA)
# ==========================================
def addDespesa(dados, usuario_id=1):
    """Cadastra um gasto lidando com Chaves Estrangeiras."""
    categoria_id = obter_ou_criar_categoria(dados['categoria'])
    local = dados.get('local', None) # Extraído pela IA
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO transacoes (usuario_id, categoria_id, tipo, descricao, valor, data, local)
        VALUES (%s, %s, 'Despesa', %s, %s, %s, %s)
    ''', (usuario_id, categoria_id, dados['descricao'], dados['valor'], dados['data'], local))
    
    conn.commit()
    cursor.close()
    conn.close()

def addReceita(dados, usuario_id=1):
    """Cadastra uma entrada de dinheiro lidando com Chaves Estrangeiras."""
    categoria_id = obter_ou_criar_categoria(dados['categoria'])
    local = dados.get('local', None)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO transacoes (usuario_id, categoria_id, tipo, descricao, valor, data, local)
        VALUES (%s, %s, 'Receita', %s, %s, %s, %s)
    ''', (usuario_id, categoria_id, dados['descricao'], dados['valor'], dados['data'], local))
    
    conn.commit()
    cursor.close()
    conn.close()

def buscar_transacoes(usuario_id=1):
    """Busca transações fazendo JOIN com Categorias."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fazemos um INNER JOIN para buscar o texto do nome da categoria usando a foreign key
    cursor.execute('''
        SELECT t.id, t.tipo, t.descricao, c.nome, t.valor, t.data, t.local 
        FROM transacoes t
        INNER JOIN categorias c ON t.categoria_id = c.id
        WHERE t.usuario_id = %s
        ORDER BY t.data DESC, t.id DESC
    ''', (usuario_id,))
    
    rows = cursor.fetchall()
    
    transacoes = []
    for row in rows:
        transacoes.append({
            "id": row[0],
            "tipo": row[1],
            "descricao": row[2],
            "categoria": row[3], # Agora vem da tabela de categorias
            "valor": float(row[4]),
            "data": str(row[5]),
            "local": row[6]
        })
        
    cursor.close()
    conn.close()
    return transacoes

def verificar_login(id_plataforma):
    """
    No novo modelo do TCC (RN03), o usuário loga apenas pelo ID da plataforma.
    A senha foi removida.
    """
    conexao = get_connection()
    cursor = conexao.cursor(dictionary=True) 
    
    try:
        query = "SELECT nome_completo FROM usuarios WHERE id_plataforma = %s"
        cursor.execute(query, (id_plataforma,))
        resultado = cursor.fetchone()
        
        if resultado:
            return resultado['nome_completo']
        else:
            return None
    except Exception as e:
        print(f"Erro ao verificar login: {e}")
        return None
    finally:
        cursor.close()
        conexao.close()