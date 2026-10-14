# Guia 02 — Setup do banco de dados (Neon)

> Tempo estimado: 5 minutos
> Pré-requisitos: conta gratuita no [neon.tech](https://neon.tech)

O DirecioZAP guarda perguntas, sessões de conversa e cadastros num banco Postgres. Até out/2026
usávamos o Supabase; migramos para o Neon porque o limite de projetos gratuitos do Supabase já estava em uso.

## Passo 1 — Criar o projeto

1. Em neon.tech, clique em **New Project**.
2. Nome: `direciozap`. Região: **AWS São Paulo** (sa-east-1), se disponível.
3. Clique em **Create project**.

## Passo 2 — Copiar a connection string

1. No painel do projeto, clique em **Connect**.
2. Copie a string `postgresql://...neon.tech/neondb?sslmode=require`.
3. Trate essa string como senha: quem a tiver lê e apaga todos os cadastros.

## Passo 3 — Configurar e criar as tabelas

1. No DirecioZAP Manager, aba **Configurações**, cole a string em **Banco de dados (Neon)**.
2. Clique em **Testar Conexão**. O teste cria as tabelas `perguntas`, `cadastros` e `sessions`
   e insere as 5 perguntas padrão se a tabela de perguntas estiver vazia.
3. Clique em **Salvar Configurações**.

Sem o Manager, o mesmo pode ser feito pela linha de comando:

```powershell
..\.venv\Scripts\python.exe -c "from db import _get_db; print(_get_db().init_schema())"
```

## Observações

- O plano gratuito suspende o banco após ~5 minutos sem uso. A primeira mensagem depois disso
  leva um pouco mais para ser respondida enquanto o banco acorda; não é erro.
- O esquema fica em `db.py` (`SCHEMA_SQL`). Sessões abandonadas são apagadas quando o mesmo número
  volta a escrever (veja `conversation.py`).
