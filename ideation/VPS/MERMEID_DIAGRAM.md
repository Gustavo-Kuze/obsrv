```
flowchart TD

    %% VPS Única
    subgraph VPS ["VPS Única - Ubuntu / Docker Compose"]
        
        subgraph API ["Backend API - FastAPI"]
            A1[Endpoints REST - Autenticação e Usuários]
            A2[WebSocket - Notificações em tempo real]
            A3[Orquestracao de tarefas Celery]
        end

        subgraph WORKER ["Worker - Celery e crawl4ai"]
            W1[Agendador - Celery Beat]
            W2[crawl4ai - Coleta e Extracao]
            W3[Comparador - Detecao de Mudancas]
            W4[Persistencia e Gatilhos de Notificacao]
        end

        subgraph DB ["Banco de Dados - PostgreSQL"]
            D1[(Tabelas: sites, produtos, historico)]
            D2[(Logs de crawl e resultados JSONB)]
        end

        subgraph CACHE ["Redis"]
            R1[(Fila Celery)]
            R2[(Cache de resultados)]
            R3[(Locks e Controle de execucao)]
        end

        subgraph FRONT ["Frontend - React e TypeScript"]
            F1[Dashboard de Produtos]
            F2[Historico de Precos]
            F3[Alertas e Configuracoes]
        end
    end

    %% Fluxos principais
    U[Usuario ou Cliente] -->|"HTTP / HTTPS"| F1
    F1 -->|"REST ou WebSocket"| A1

    A3 -->|"Envia tarefa Celery"| R1
    R1 -->|"Fila de mensagens"| W1

    W1 -->|"Executa tarefa de coleta"| W2
    W2 -->|"Extracao estruturada de dados"| W3
    W3 -->|"Atualiza dados no banco"| D1
    W3 -->|"Grava log do resultado"| D2

    W4 -->|"Evento de alteracao detectado"| A2
    A2 -->|"Push ou WebSocket"| F3

    W1 <--> R2
    W1 <--> R3

    A1 --> D1
    F1 -->|"Consulta via API"| A1

    %% Estilos
    classDef infra fill:#c6f3ff,stroke:#2a9df4,color:#000;
    classDef service fill:#f7e8b3,stroke:#bfa42a,color:#000;
    classDef storage fill:#e0e0e0,stroke:#666,color:#000;
    classDef user fill:#d2f5c4,stroke:#32a852,color:#000;

    class VPS infra
    class API,WORKER,FRONT service
    class DB,CACHE storage
    class U user

```