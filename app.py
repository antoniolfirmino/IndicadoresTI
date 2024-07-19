from flask import Flask, render_template, request, jsonify
import mysql.connector
import json
from decimal import Decimal
import google.generativeai as genai
from datetime import datetime

app = Flask(__name__)

# Conexão com o banco de dados MySQL
db = mysql.connector.connect(
    host="localhost",
    user="root",
    passwd="",
    database="glpi2"
)

# Configuração da API do Google Generative AI
genai.configure(api_key='APIAQUI')
generation_config = {
  "temperature": 1,
  "top_p": 0.95,
  "top_k": 64,
  "max_output_tokens": 8192,
  "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
  model_name="gemini-1.5-flash",
  generation_config=generation_config,
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/graficos', methods=['POST'])
def graficos():
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    entidade = request.form['entidade']
    
    #print(f'Entidade:{entidade}')

    # Consulta 1
    query_chamados = """
        SELECT glpi_tickets.id AS id, glpi_tickets.name AS descr, glpi_tickets.date AS date, glpi_tickets.solvedate as solvedate,
        glpi_tickets.status, glpi_tickets.time_to_resolve AS duedate, sla_waiting_duration AS slawait, glpi_tickets.type,
        FROM_UNIXTIME(UNIX_TIMESTAMP(glpi_tickets.solvedate), '%Y-%m') AS date_unix, AVG(glpi_tickets.solve_delay_stat) AS time
        FROM glpi_tickets
        WHERE glpi_tickets.is_deleted = 0
        AND glpi_tickets.date BETWEEN '{} 00:00:00' AND '{} 23:59:59'
        AND glpi_tickets.status IN ('5', '6')
        AND glpi_tickets.entities_id in ('{}')
        GROUP BY id
        ORDER BY id DESC
    """.format(start_date, end_date, entidade)

    cursor = db.cursor(dictionary=True)
    cursor.execute(query_chamados)
    result_cham = cursor.fetchall()

    query_conta = """
        SELECT COUNT(glpi_tickets.id) AS total, FROM_UNIXTIME(UNIX_TIMESTAMP(glpi_tickets.solvedate), '%Y-%m') AS date_unix, AVG(glpi_tickets.solve_delay_stat) AS time
        FROM glpi_tickets
        WHERE glpi_tickets.is_deleted = 0
        AND glpi_tickets.date BETWEEN '{} 00:00:00' AND '{} 23:59:59'
        AND glpi_tickets.status IN ('5', '6')
        AND glpi_tickets.entities_id in ('{}')
        GROUP BY id
        ORDER BY id DESC
    """.format(start_date, end_date, entidade)

    cursor.execute(query_conta)
    result_cons1 = cursor.fetchall()
    conta_cons = len(result_cons1)
    
    # Contar tickets vencidos
    v = 0
    for row in result_cham:
        if row['solvedate'] > row['duedate'] and row['slawait'] == 0:
            v += 1

    # Contar tickets no prazo
    w = conta_cons - v
    
    #print(f'total:{conta_cons}')

    if conta_cons > 0:
        percentual_no_prazo = round((w * 100) / conta_cons, 0)
        percentual_fora_prazo = round((v * 100) / conta_cons, 0)
    else:
        percentual_no_prazo = 0
        percentual_fora_prazo = 0

    

#AND glpi_tickets.slas_id_ttr in ('16','17','18','19')
     
    # Consulta 1
    query1 = """
        SELECT
            SUM(case when glpi_tickets.status = 1 then 1 else 0 end) AS novo,
            SUM(case when glpi_tickets.status = 4 then 1 else 0 end) AS pendente,
            SUM(case when glpi_tickets.status = 5 then 1 else 0 end) AS solucionado,
            SUM(case when glpi_tickets.status = 6 then 1 else 0 end) AS fechado,
            COUNT(*) as total
        FROM glpi_tickets
        WHERE glpi_tickets.is_deleted = 0      
        AND glpi_tickets.date BETWEEN '{} 00:00:00' AND '{} 23:59:59'
        AND glpi_tickets.entities_id in ('{}')
    """.format(start_date, end_date, entidade)

    cursor = db.cursor()
    cursor.execute(query1)
    result1 = cursor.fetchone()

    novo, pendente, solucionado, fechado, total = map(lambda x: int(x) if isinstance(x, Decimal) else x, result1)

    # Calcular porcentagem de fechados
    fechados_percent = ((fechado + solucionado)/ total) * 100 if total > 0 else 0

    # Consulta 2
    query2 = """
        SELECT 
            CONCAT(glpi_ticketsatisfactions.satisfaction, ' estrelas') as nota, 
            count(*) as total
        FROM glpi_tickets, glpi_ticketsatisfactions
        WHERE glpi_tickets.is_deleted = 0
        AND glpi_tickets.status = 6
        AND glpi_tickets.date BETWEEN '{} 00:00:00' AND '{} 23:59:59'
        AND glpi_tickets.entities_id in ('{}')
        AND glpi_ticketsatisfactions.tickets_id = glpi_tickets.id
        AND glpi_ticketsatisfactions.satisfaction IS NOT NULL
        GROUP BY glpi_ticketsatisfactions.satisfaction
    """.format(start_date, end_date, entidade)

    cursor.execute(query2)
    result2 = cursor.fetchall()

    # Inicializar a variável com todas as notas possíveis e suas quantidades como 0
    satisfacao_por_nota = {
        '1 estrelas': 0,
        '2 estrelas': 0,
        '3 estrelas': 0,
        '4 estrelas': 0,
        '5 estrelas': 0
    }

    # Atualizar o dicionário com os resultados da consulta
    for item in result2:
        satisfacao_por_nota[item[0]] = item[1]

    satisfacao_total = sum(item[1] for item in result2)
    

    # Formatar os dados para os gráficos
    labels1 = ["Novo", "Pendente", "Solucionado", "Fechado"]
    data1 = [novo, pendente, solucionado, fechado]
    labels2 = [str(item[0]) for item in result2]
    data2 = [item[1] for item in result2]

    

    # Definindo uma função para obter a descrição da entidade
    def get_entidade_descricao(entidade):
        cursor = db.cursor()
        cursor.execute("SELECT name FROM glpi_entities WHERE id = %s", (entidade,))
        result = cursor.fetchone()
        cursor.close()
        if result:
            return result[0]
        else:
            return "Desconhecido"
    
  
   

    dti = datetime.strptime(start_date, '%Y-%m-%d')
    dtf = datetime.strptime(end_date, '%Y-%m-%d')

    return render_template('graficos.html', 
                           start_date=start_date, 
                           end_date=end_date,
                           dti=dti,
                           dtf=dtf,
                           novo=novo, 
                           pendente=pendente, 
                           solucionado=solucionado, 
                           fechado=fechado,
                           satisfacao_por_nota=satisfacao_por_nota, 
                           total=total, 
                           fechados_percent=float(fechados_percent),
                           satisfacao_total=satisfacao_total,
                           labels1=json.dumps(labels1), 
                           data1=json.dumps(data1), 
                           labels2=json.dumps(labels2), 
                           data2=json.dumps(data2),
                           w=w,
                           v=v,
                           percentual_fora_prazo= percentual_fora_prazo,
                           entidade_descricao = get_entidade_descricao(entidade),
                           percentual_no_prazo=percentual_no_prazo)

@app.route('/get_entidades', methods=['GET'])
def get_entidades():
    cursor = db.cursor()
    cursor.execute("select id,name from glpi_entities ge where id <> '0'")
    entidades = cursor.fetchall()
    cursor.close()
    
    entidades_list = [{"id": row[0], "descricao": row[1]} for row in entidades]
    
    # Printar para depuração
    #print(entidades_list)
    
    return jsonify(entidades_list)
       

@app.route('/gerar_analise', methods=['POST'])
def gerar_analise():
    entidade_descricao = request.form['entidade_descricao']
    total = request.form['total']
    novo = request.form['novo']
    pendente = request.form['pendente']
    solucionado = request.form['solucionado']
    fechado = request.form['fechado']
    fechados_percent = request.form['fechados_percent']
    satisfacao_total = request.form['satisfacao_total']
    satisfacao_por_nota = request.form['satisfacao_por_nota']
    percentual_fora_prazo = request.form['percentual_fora_prazo']   
    percentual_no_prazo = request.form['percentual_no_prazo']
    chat_session = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    "qual capital do brasil\n",
                ],
            },
            {
                "role": "model",
                "parts": [
                    "A capital do Brasil é **Brasília**. \n",
                ],
            },
        ]
    )

    mensagem = f"""Realize uma análise crítica com base nos seguintes dados:

Total de chamados: {total}
Chamados com status Novo: {novo}
Chamados com status Pendente: {pendente}
Chamados com status Solucionado: {solucionado}
Chamados com status Fechado: {fechado}
Percentual de chamados : {fechados_percent}%
Total de pesquisa de satisfação respondida: {satisfacao_total} de {fechado}
Observações:
{satisfacao_por_nota} são a quantidade de estrelas recebidas na pesquisa de satisfação respondida.
Quando a pesquisa de satisfação resulta em {satisfacao_por_nota} = '1 estrelas', o atendimento é considerado péssimo.
Quando a pesquisa de satisfação resulta em {satisfacao_por_nota} = '2 estrelas', o atendimento é considerado ruim.
Quando a pesquisa de satisfação resulta em {satisfacao_por_nota} = '3 estrelas', o atendimento é considerado bom.
Quando a pesquisa de satisfação resulta em {satisfacao_por_nota} = '4 estrelas', o atendimento é considerado ótimo.
Quando a pesquisa de satisfação resulta em {satisfacao_por_nota} = '5 estrelas', o atendimento é considerado excelente.

chamados que foram resolvidos dentro do prazo{percentual_no_prazo} e fora do prazo{percentual_fora_prazo}

Os chamados são fechados somente após a aprovação da solução pelo cliente.
Após o fechamento, os clientes podem optar por responder ou não à pesquisa de satisfação. Portanto, um chamado sem pesquisa de satisfação não representa má qualidade do atendimento ou que o atendimento não foi resolvido.

Para a análise do percentual de chamados resolvidos, considere que quanto maior a porcentagem, melhor foi o atendimento.

Instruções para a análise:

Forneça uma analise em cima da porcentagem de chamados dentro e fora do prazo 

Percentual de Chamados Resolvidos:

Forneça três itens de análise:
Fato: Observe e registre um fato significativo relacionado ao percentual de chamados resolvidos.
Causa: Identifique a causa provável desse fato.
Ação: Sugira uma ação que possa ser tomada com base nesse fato e sua causa.

Satisfação:

Forneça três itens de análise:
Fato: Observe e registre um fato significativo relacionado à distribuição das avaliações de satisfação em estrelas.
Causa: Identifique a possível causa por trás da distribuição observada das avaliações.
Ação: Sugira uma ação que possa ser tomada com base na distribuição das avaliações para melhorar a experiência do cliente.

Para análise mais aprofundada, considere o seguinte:

- Observe se há uma predominância de avaliações de uma estrela em relação a outras classificações. Isso pode indicar áreas específicas de insatisfação que precisam de atenção imediata.
- Analise as razões subjacentes para as avaliações de uma ou duas estrelas. Podem surgir padrões que apontem para problemas recorrentes ou falhas no processo de atendimento ao cliente.
- Avalie se as avaliações de três, quatro ou cinco estrelas estão alinhadas com as expectativas dos clientes. Identifique as áreas em que o serviço está sendo bem avaliado e explore maneiras de replicar esses sucessos em outras partes do processo de atendimento.
- Considere a implementação de medidas proativas para aumentar as avaliações de satisfação. Isso pode incluir treinamento adicional da equipe, melhorias nos processos de resolução de problemas ou atualizações nos sistemas de suporte ao cliente.
"""

    response = chat_session.send_message(mensagem)

    return render_template('analise.html', 
                           entidade_descricao=entidade_descricao,
                           analysis=response.text)
   
    

if __name__ == '__main__':
    app.run(debug=True)
