# Guia 02 — Setup do Supabase

> Tempo estimado: 15 minutos  
> Pré-requisitos: conta no [supabase.com](https://supabase.com) (gratuita)

---

## Por que Supabase?

O Render Free hiberna o processo após 15 minutos de inatividade e reinicia o container entre deploys. Qualquer dado em memória (o `dict` de sessões original) se perde.

O Supabase resolve isso com um banco PostgreSQL gerenciado gratuito. As sessões de conversa persistem mesmo que o Render reinicie.

**Free Tier:** 500 MB de banco, sem limite de tempo, 2 projetos ativos.

---

## Passo 1 — Criar o Projeto no Supabase

1. Acesse [supabase.com](https://supabase.com) → **"Start your project"**
2. Faça login com GitHub ou email
3. Clique em **"New Project"**
4. Preencha:
   - **Name:** `direciozap`
   - **Database Password:** (anote — você vai precisar)
   - **Region:** South America (São Paulo) → mais próximo do Render
5. Clique em **"Create new project"**
6. Aguarde ~2 minutos enquanto o banco é criado

---

## Passo 2 — Criar a Tabela de Sessões

Após o projeto estar pronto:

1. No menu lateral, clique em **"SQL Editor"**
2. Cole o SQL abaixo e clique em **"Run"** (ou Ctrl+Enter):

```sql
-- Tabela de sessões do bot
CREATE TABLE sessions (
  phone          TEXT PRIMARY KEY,
  state          TEXT NOT NULL DEFAULT 'SAUDACAO',
  dados          JSONB NOT NULL DEFAULT '{}',
  tentativas     JSONB NOT NULL DEFAULT '{}',
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índice para queries de limpeza por data
CREATE INDEX sessions_atualizado_em_idx ON sessions (atualizado_em);
```

3. Você deve ver a mensagem **"Success. No rows returned"**

---

## Passo 3 — Verificar a Tabela

1. No menu lateral, clique em **"Table Editor"**
2. Confirme que a tabela `sessions` aparece com as colunas:
   - `phone` (text, primary key)
   - `state` (text)
   - `dados` (jsonb)
   - `tentativas` (jsonb)
   - `criado_em` (timestamptz)
   - `atualizado_em` (timestamptz)

---

## Passo 4 — Obter as Credenciais

1. No menu lateral, clique em **"Project Settings"** → **"API"**
2. Anote:
   - **Project URL:** `https://XXXX.supabase.co` → vai no `SUPABASE_URL`
   - **anon public key:** `eyJhbGciOiJIUzI1NiIsInR5cCI...` → vai no `SUPABASE_KEY`

> **Segurança:** A `anon key` é segura para uso no servidor. Nunca use a `service_role key` exposta — ela bypassa Row Level Security.

---

## Passo 5 — Configurar no .env

Abra seu arquivo `.env` e preencha:

```env
SUPABASE_URL=https://SEU_ID_AQUI.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Passo 6 — Testar a conexão localmente

```bash
python -c "
from supabase_session import get_session, create_session, delete_session

# Cria sessão de teste
s = create_session('5500000000000')
print('Criada:', s['state'])  # SAUDACAO

# Recupera
s2 = get_session('5500000000000')
print('Recuperada:', s2['state'])  # SAUDACAO

# Remove
delete_session('5500000000000')
print('Removida com sucesso')
"
```

Se tudo funcionar, você verá:
```
Criada: SAUDACAO
Recuperada: SAUDACAO
Removida com sucesso
```

---

## Passo 7 — (Opcional) Habilitar limpeza automática de sessões antigas

Para não acumular sessões > 24h no banco, você pode usar o `pg_cron` do Supabase:

1. No SQL Editor, execute:
```sql
-- Habilita pg_cron (apenas uma vez por projeto)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Agenda limpeza todo hora
SELECT cron.schedule(
  'cleanup-sessions',
  '0 * * * *',
  'DELETE FROM sessions WHERE atualizado_em < NOW() - INTERVAL ''24 hours'''
);
```

> **Nota:** `pg_cron` pode estar disponível dependendo do plano. Se retornar erro, faça a limpeza na aplicação — o `conversation.py` já verifica e deleta sessões expiradas quando o usuário envia uma nova mensagem.

---

## Estrutura JSONB das Sessões

Exemplo de registro após o usuário informar a Razão Social:

```json
{
  "phone": "5531999990000",
  "state": "AGUARDA_CNPJ",
  "dados": {
    "razao_social": "EMPRESA EXEMPLO LTDA"
  },
  "tentativas": {},
  "criado_em": "2026-06-23T16:49:00+00:00",
  "atualizado_em": "2026-06-23T16:50:00+00:00"
}
```

---

## Próximo passo

Após confirmar que o Supabase está funcional, siga o  
[Guia 03 — Variáveis de Ambiente](./03_variaveis_ambiente.md)
