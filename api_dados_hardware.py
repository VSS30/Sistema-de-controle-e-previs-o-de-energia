from flask import Flask, request, render_template, jsonify, redirect, url_for, session
import sqlite3
import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np
from datetime import datetime


app = Flask(__name__)
app.secret_key = 'seu_segredo_aqui'  # Substitua por um segredo seguro

# Nome do banco de dados SQLite
db_file = "dados_consumo_energia.db"

# Função para carregar todos os dados da tabela dados_hardware
def carregar_dados():
    conn = sqlite3.connect(db_file)
    query = "SELECT * FROM dados_hardware"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# Função para exibir todos os registros e o total no terminal
def exibir_registros_terminal():
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Recuperar todos os registros
    cursor.execute("SELECT * FROM dados_hardware")
    registros = cursor.fetchall()
    
    # Fechar a conexão
    conn.close()
    
    # Exibir registros no terminal
    print("\n--- Registros no Banco de Dados ---")
    total_registros = len(registros)
    for registro in registros:
        print(registro)
    
    # Exibir o total de registros
    print(f"\nTotal de registros: {total_registros}\n")


# Inicializar banco de dados SQLite
def inicializar_banco():
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Tabela para armazenar dados de consumo
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dados_hardware (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tomada TEXT,
            data_hora TEXT,
            dia_semana TEXT,
            corrente_bruta INTEGER,
            corrente_calibrada REAL,
            potencia REAL,
            custo_minuto REAL,
            custo_total REAL
        )
    """)
    # Tabela de usuários
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    # Adicionar usuário padrão se não existir
    cursor.execute("""
        INSERT OR IGNORE INTO usuarios (username, password) VALUES (?, ?)
    """, ("admin", "admin123"))

    # Tabela para cadastrar eletrodomésticos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eletrodomesticos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tomada TEXT NOT NULL UNIQUE
        )
    """)
    conn.commit()
    conn.close()
    exibir_registros_terminal()

# Função para garantir que a data esteja no formato correto
def formatar_data(data_hora):
    try:
        # Tenta converter para o formato de data
        data = datetime.strptime(data_hora, "%Y-%m-%d %H:%M:%S")
        return data.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Se a data for inválida, retorna uma data padrão
        return "0000-00-00 00:00:00"




@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        try:
            cursor.execute("INSERT INTO usuarios (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            return redirect(url_for('login'))  # Redirecionar para login após sucesso
        except sqlite3.IntegrityError:
            return "Usuário já existe. Tente outro nome de usuário.", 400
        finally:
            conn.close()

    return render_template('cadastro.html')  # Renderizar a página de cadastro




# Rota para receber dados do hardware
@app.route('/dados-hardware', methods=['POST'])
def receber_dados():
    if request.is_json:
        dados = request.get_json()
        tomada = dados.get("tomada")
        data_hora = dados.get("data_hora")
        dia_semana = dados.get("dia_semana")
        corrente_bruta = dados.get("corrente_bruta")
        corrente_calibrada = dados.get("corrente_calibrada")
        potencia = dados.get("potencia")
        custo_minuto = dados.get("custo_minuto")
        
        # Formatar a data para garantir que esteja no formato correto
        data_hora = formatar_data(data_hora)

        # Calcular custo total acumulado a partir do custo_minuto
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Verificar o custo total atual para essa tomada
        cursor.execute("SELECT custo_total FROM dados_hardware WHERE tomada=?", (tomada,))
        resultado = cursor.fetchone()
        if resultado:
            custo_total = resultado[0]
        else:
            custo_total = 0  # Caso não exista o custo total, inicializamos com 0

        # Somar o custo por minuto ao custo total
        custo_total += custo_minuto
        
        cursor.execute("""
            INSERT INTO dados_hardware (tomada, data_hora, dia_semana, corrente_bruta, corrente_calibrada, potencia, custo_minuto, custo_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (tomada, data_hora, dia_semana, corrente_bruta, corrente_calibrada, potencia, custo_minuto, custo_total))
        conn.commit()
        conn.close()
        return jsonify({"message": "Dados recebidos com sucesso", "custo_total": custo_total}), 200
    return jsonify({"error": "Requisição inválida, JSON esperado"}), 400




# Rota para a página de login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session['user'] = username
            return redirect(url_for('exibir_dados'))
        else:
            return "Usuário ou senha inválidos!", 401

    return render_template('login.html')

# Rota para logout
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.before_request
def autenticar():
    if request.endpoint not in ['login', 'cadastro', 'static'] and 'user' not in session:
        return redirect(url_for('login'))




# Rota para exibir os dados, gráficos e previsão
@app.route('/')
def exibir_dados():
    # Abrir a conexão uma vez
    conn = sqlite3.connect(db_file)
    
    # Carregar os dados do banco de dados
    df = pd.read_sql_query("SELECT * FROM dados_hardware", conn)

    if df.empty:
        return render_template('index.html', dados={"labels": [], "potencia": [], "custo_total": []}, previsao="Nenhum dado disponível", insights=[], grafico_diario=[])

    df['data_hora'] = pd.to_datetime(df['data_hora'], errors='coerce')  # Coerção para valores inválidos
    df['hora'] = df['data_hora'].dt.strftime('%Y-%m-%d %H:00:00')
    dados_agrupados = df.groupby('hora').agg({
        'potencia': 'mean',
        'custo_total': 'sum'
    }).reset_index()

    df.fillna(0, inplace=True)
    dados_agrupados.fillna(0, inplace=True)
    if not np.isfinite(df[['corrente_calibrada', 'potencia']]).all().all():
        return jsonify({"error": "Conjunto de dados contém valores inválidos após o tratamento"}), 500

    previsao = "Dados insuficientes para previsão."

    dados_grafico = {
        "labels": dados_agrupados['hora'].tolist(),
        "potencia": dados_agrupados['potencia'].tolist(),
        "custo_total": dados_agrupados['custo_total'].tolist()
    }

    # Consulta para obter o gráfico de consumo total, custo total e corrente média por dia
    query_diario = """
    SELECT
        strftime('%Y-%m-%d', data_hora) AS data,
        SUM(potencia) AS consumo_total,
        SUM(custo_total) AS custo_total,
        AVG(corrente_calibrada) AS corrente_media
    FROM dados_hardware
    GROUP BY strftime('%Y-%m-%d', data_hora)
    ORDER BY data DESC;
    """
    df_diario = pd.read_sql_query(query_diario, conn)
    
    # Prepare os dados para os novos gráficos
    grafico_diario = df_diario.to_dict(orient='records')

    # Consultar os insights
    query_insights = """
    SELECT
        strftime('%Y-%m-%d', data_hora) AS data,
        SUM(potencia) AS consumo_total,
        SUM(custo_total) AS custo_total,
        AVG(corrente_calibrada) AS corrente_media,
        AVG(potencia) AS potencia_media
    FROM dados_hardware
    GROUP BY strftime('%Y-%m-%d', data_hora)
    ORDER BY data DESC
    LIMIT 5;
    """
    df_insights = pd.read_sql_query(query_insights, conn)
    
    insights = df_insights.to_dict(orient='records')

    # Calcular a previsão mensal de consumo com base na média diária
    if len(df_diario) > 0:
        consumo_diario_medio = df_diario['consumo_total'].mean()
        previsao_mensal = consumo_diario_medio * 30  # Aproximando para 30 dias no mês
        previsao = f"R$ {previsao_mensal:.2f}"
    else:
        previsao = "Dados insuficientes para previsão."

    # Fechar a conexão após todas as consultas
    conn.close()

    return render_template('index.html', dados=dados_grafico, previsao=previsao, insights=insights, grafico_diario=grafico_diario)

# Inicializar banco de dados e iniciar servidor Flask
if __name__ == '__main__':
    inicializar_banco()
    app.run(debug=True, host='0.0.0.0', port=5000)
