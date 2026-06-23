# Software Design Document (SDD)
## Bot de Captação de Fornecedores via WhatsApp

*Versão:* 2.0  
*Data:* 23/06/2026  
*Status:* Implementado  

> **Mudanças v2.0 vs v1.0:**
> - WhatsApp Cloud API (Meta oficial) → **Evolution API** (self-hosted, open-source)
> - Estado em memória (dict Python) → **Supabase** (PostgreSQL gerenciado, gratuito)

---

## 1. Visão Geral

### 1.1 Objetivo

Automatizar a captação de dados de fornecedores por meio de um chatbot no WhatsApp. O fluxo começa quando o fornecedor acessa um link de postagem no LinkedIn, que o redireciona para uma conversa no WhatsApp com o bot. O bot coleta os dados estruturados do fornecedor e os persiste em uma planilha Excel com campos normalizados.

### 1.2 Escopo

- Chatbot conversacional no WhatsApp via Evolution API
- Coleta de: Razão Social, CNPJ, Contato, Serviço(s) e Estados de Atuação
- Validação mínima dos campos coletados (com limite de 3 tentativas por campo)
- Normalização dos dados antes de salvar
- Persistência de sessão no Supabase (PostgreSQL)
- Persistência de dados em arquivo .xlsx
- Deploy 100% gratuito (Render Free Tier)

### 1.3 Fora do Escopo (v2.0)

- Autenticação/login de fornecedores
- Dashboard de visualização dos dados
- Integração com CRM ou ERP
- Notificações por e-mail ao receber novo fornecedor
- Deduplicação de CNPJ (v3.0)

---

## 2. Arquitetura do Sistema

### 2.1 Visão de Alto Nível

```
LinkedIn Post (link)
      │
      ▼
  wa.me/link
      │
      ▼
WhatsApp (app do fornecedor)
      │ mensagem
      ▼
Evolution API (self-hosted Docker / VPS)
      │  webhook POST /webhook
      ▼
┌─────────────────────────────────────────────────┐
│              Backend (Python/FastAPI)           │
│  ┌──────────────┐   ┌───────────────────────┐  │
│  │ Webhook      │──▶│  ConversationManager  │  │
│  │ Handler      │   │  (orquestra estados)  │  │
│  └──────────────┘   └───────────┬───────────┘  │
│                                 │               │
│                    ┌────────────▼────────────┐  │
│                    │  Validation & Normalize │  │
│                    └────────────┬────────────┘  │
│                                 │               │
│              ┌──────────────────┴──────────┐    │
│              │                             │    │
│   ┌──────────▼────────┐    ┌──────────────▼──┐ │
│   │  Supabase Client  │    │ ExcelWriter      │ │
│   │  (sessões/estado) │    │ (openpyxl .xlsx) │ │
│   └───────────────────┘    └─────────────────┘ │
└─────────────────────────────────────────────────┘
      │  resposta via Evolution API REST
      ▼
Evolution API → WhatsApp do fornecedor
```

### 2.2 Stack Tecnológica

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Backend | Python 3.11 + FastAPI | Leve, rápido, free tier compatível |
| Mensageria | Evolution API (open-source) | Gratuito, sem verificação Meta obrigatória |
| Sessão/Estado | Supabase (PostgreSQL) | Free tier: 500 MB, persist entre deploys |
| Persistência | openpyxl (arquivo .xlsx) | Zero custo, sem banco de dados extra |
| Deploy backend | Render Free | Processo persistente, disco efêmero 512 MB |
| Deploy Evolution | VPS própria ou Render Docker | Evolution API precisa de processo contínuo |

### 2.3 Por que Evolution API

Evolution API é uma implementação open-source do protocolo WhatsApp Web que expõe uma REST API. Vantagens sobre a API oficial Meta:
- Sem necessidade de aprovação/verificação de conta Meta Business
- Sem limite de 1.000 conversas/mês na fase de testes
- Webhook configurável via painel web
- Suporte a QR Code ou Pairing Code para conectar número comum

**Limitação:** baseada em WhatsApp Web (não oficial) — risco de ban de número se usado em escala abusiva. Para uso legítimo e controlado (captação de fornecedores) o risco é baixo.

### 2.4 Por que Supabase

O Render Free tem disco efêmero e reinicia o processo periodicamente. Armazenar sessões em memória (dict) perde todas as conversas em andamento a cada reinício. Supabase resolve isso:
- Free tier: 500 MB de banco PostgreSQL gerenciado
- SDK Python simples (`supabase-py`)
- Sessões persistem entre deploys e reinícios
- Row Level Security pode ser habilitado futuramente

---

## 3. Fluxo da Conversa

### 3.1 Diagrama de Estados

```
[INICIO] — qualquer mensagem recebida com sessão nova
    │
    ▼
[SAUDACAO] ──▶ Envia boas-vindas + solicita Razão Social
    │            → estado salvo no Supabase: AGUARDA_RAZAO_SOCIAL
    ▼
[AGUARDA_RAZAO_SOCIAL] ──(recebe)──▶ valida (não vazio) ──▶ salva
    │
    ▼
[AGUARDA_CNPJ] ──(recebe)──▶ valida CNPJ ──(inválido, max 3x)──▶ pede novamente
    │ (válido)                                (3ª falha) ──▶ encerra sessão
    ▼
[AGUARDA_CONTATO] ──(recebe)──▶ valida telefone/email ──(inválido, max 3x)──▶ pede novamente
    │ (válido)
    ▼
[AGUARDA_SERVICO] ──(recebe)──▶ valida (≥3 chars)
    │
    ▼
[AGUARDA_ESTADOS] ──(recebe)──▶ valida (siglas UF) ──(inválido, max 3x)──▶ pede novamente
    │ (válido)
    ▼
[CONFIRMACAO] ──▶ exibe resumo
    ├──(S/SIM) ──▶ append_fornecedor() ──▶ delete_session() ──▶ [FIM]
    └──(N/NÃO) ──▶ delete_session() ──▶ nova sessão ──▶ [AGUARDA_RAZAO_SOCIAL]
```

### 3.2 Mensagens do Bot

| Estado | Mensagem enviada |
|---|---|
| SAUDACAO | "Olá! 👋 Seja bem-vindo ao cadastro de fornecedores. Vou precisar de algumas informações. Qual é a Razão Social da sua empresa?" |
| AGUARDA_CNPJ | "Obrigado! Agora me informe o CNPJ da empresa (pode ser com ou sem pontuação):" |
| CNPJ_INVALIDO | "⚠️ CNPJ inválido. Por favor, informe um CNPJ com 14 dígitos válidos:" |
| AGUARDA_CONTATO | "Ótimo! Qual o contato principal? (telefone ou e-mail):" |
| CONTATO_INVALIDO | "⚠️ Formato não reconhecido. Informe um telefone (ex: 31999990000) ou e-mail válido:" |
| AGUARDA_SERVICO | "Que tipo de serviço sua empresa oferece?" |
| AGUARDA_ESTADOS | "Em quais estados vocês atuam? (Ex: MG, SP, RJ — pode listar todos separados por vírgula):" |
| ESTADO_INVALIDO | "⚠️ Algumas siglas não reconhecidas. Use as siglas oficiais dos estados brasileiros (ex: MG, SP, RJ):" |
| CONFIRMACAO | "📋 Resumo do cadastro:\n\n• Razão Social: {razao_social}\n• CNPJ: {cnpj}\n• Contato: {contato}\n• Serviço: {servico}\n• Estados: {estados}\n\nAs informações estão corretas? Responda S para confirmar ou N para recomeçar." |
| SUCESSO | "✅ Cadastro realizado com sucesso! Entraremos em contato em breve. Obrigado!" |
| REINICIO | "Ok, vamos começar de novo. Qual é a Razão Social da sua empresa?" |
| MAX_TENTATIVAS | "❌ Muitas tentativas inválidas. Por favor, inicie uma nova conversa para tentar novamente." |

---

## 4. Modelo de Dados

### 4.1 Schema Supabase — Tabela `sessions`

```sql
CREATE TABLE sessions (
  phone          TEXT PRIMARY KEY,
  state          TEXT NOT NULL DEFAULT 'SAUDACAO',
  dados          JSONB NOT NULL DEFAULT '{}',
  tentativas     JSONB NOT NULL DEFAULT '{}',
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índice para limpeza de sessões antigas
CREATE INDEX sessions_atualizado_em_idx ON sessions (atualizado_em);

-- Opcional: limpar sessões > 24h automaticamente (pg_cron)
-- SELECT cron.schedule('cleanup-sessions', '0 * * * *',
--   'DELETE FROM sessions WHERE atualizado_em < NOW() - INTERVAL ''24 hours''');
```

**Exemplo de registro:**
```json
{
  "phone": "5531999990000",
  "state": "AGUARDA_CNPJ",
  "dados": {
    "razao_social": "EMPRESA EXEMPLO LTDA"
  },
  "tentativas": {
    "cnpj": 1
  },
  "criado_em": "2026-06-23T16:49:00Z",
  "atualizado_em": "2026-06-23T16:50:00Z"
}
```

### 4.2 Schema do Excel — `fornecedores.xlsx`

| Coluna | Campo | Tipo | Exemplo normalizado |
|---|---|---|---|
| A | razao_social | String | EMPRESA EXEMPLO LTDA |
| B | cnpj | String | 12.345.678/0001-99 |
| C | contato | String | (31) 99999-0000 ou email@empresa.com |
| D | servico | String | Consultoria Em Ti |
| E | estados | String | MG, SP, RJ |
| F | data_cadastro | String | 2026-06-23 16:49:00 |

---

## 5. Regras de Validação e Normalização

### 5.1 Razão Social
- **Validação:** não pode ser vazio ou somente espaços
- **Normalização:** strip() + .upper() + remoção de espaços duplos
- **Exemplo:** `"  empresa exemplo ltda  "` → `"EMPRESA EXEMPLO LTDA"`

### 5.2 CNPJ
- **Validação:**
  - Extrair apenas dígitos: deve ter exatamente **14 dígitos**
  - Não pode ser sequência repetida (ex: 00000000000000)
  - Validar dígitos verificadores (algoritmo oficial)
  - Máximo 3 tentativas — depois encerra sessão
- **Normalização:** formatar como XX.XXX.XXX/XXXX-XX
- **Aceita como entrada:** `12345678000199`, `12.345.678/0001-99`, `12 345 678 0001 99`

### 5.3 Contato
- **Aceita:** telefone brasileiro ou e-mail
- **Telefone:** 10 ou 11 dígitos com DDD → `(DD) NNNNN-NNNN` ou `(DD) NNNN-NNNN`
- **E-mail:** regex `^[\w.+-]+@[\w-]+\.[a-z]{2,}$` → .lower().strip()
- **Máximo 3 tentativas**

### 5.4 Serviço
- **Validação:** não vazio, mínimo 3 caracteres
- **Normalização:** .strip() + .title()

### 5.5 Estados de Atuação
- **Aceita:** separados por vírgula, espaço, ponto e vírgula ou barra
- **Normalização:** .upper(), deduplica, ordena, junta com ", "
- **Aceita "Nacional" / "Todo o Brasil"** → `"NACIONAL"`
- **Máximo 3 tentativas**

---

## 6. Componentes do Backend

### 6.1 Estrutura de Arquivos

```
project/
├── main.py                    # FastAPI app — rotas /webhook e /exportar
├── conversation.py            # ConversationManager (máquina de estados)
├── validators.py              # Validação e normalização de campos
├── excel_writer.py            # Persistência thread-safe no .xlsx
├── whatsapp.py                # Cliente Evolution API (send_message)
├── supabase_session.py        # CRUD de sessões no Supabase
├── config.py                  # Variáveis de ambiente (pydantic-settings)
├── data/
│   └── fornecedores.xlsx      # Criado automaticamente na 1ª execução
├── tests/
│   ├── conftest.py            # Fixtures compartilhadas
│   ├── test_validators.py     # Testes A/B — validação e normalização
│   ├── test_conversation.py   # Testes A/B — fluxo de conversa
│   ├── test_excel_writer.py   # Testes A/B — persistência Excel
│   ├── test_whatsapp.py       # Testes A/B — cliente Evolution API
│   └── test_main.py           # Testes A/B — endpoints FastAPI
├── guides/
│   ├── 01_evolution_api_setup.md
│   ├── 02_supabase_setup.md
│   ├── 03_variaveis_ambiente.md
│   ├── 04_deploy_render.md
│   └── 05_linkedin_link.md
├── requirements.txt
├── render.yaml
├── docker-compose.yml         # Evolution API local (desenvolvimento)
└── .env.example
```

### 6.2 main.py — Rotas FastAPI

```
GET  /           → health check
GET  /webhook    → verificação de token Evolution API (se necessário)
POST /webhook    → recebe eventos da Evolution API, processa, responde
GET  /exportar   → download do fornecedores.xlsx (protegido por VERIFY_TOKEN)
```

### 6.3 Payload Evolution API (webhook recebido)

```json
{
  "event": "messages.upsert",
  "instance": "minha-instancia",
  "data": {
    "key": {
      "remoteJid": "5531999990000@s.whatsapp.net",
      "fromMe": false,
      "id": "MSGID123"
    },
    "pushName": "Nome Contato",
    "message": {
      "conversation": "Empresa Exemplo Ltda"
    },
    "messageType": "conversation",
    "messageTimestamp": 1687536000
  }
}
```

### 6.4 Envio de mensagem (Evolution API)

```
POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}
Headers: { "apikey": "{EVOLUTION_API_KEY}" }
Body: { "number": "5531999990000", "text": "mensagem aqui" }
```

---

## 7. Variáveis de Ambiente

| Variável | Descrição | Obrigatória |
|---|---|---|
| EVOLUTION_API_URL | URL da Evolution API (ex: http://localhost:8080) | Sim |
| EVOLUTION_API_KEY | API Key configurada na Evolution API | Sim |
| EVOLUTION_INSTANCE | Nome da instância criada na Evolution API | Sim |
| VERIFY_TOKEN | Token para proteger /exportar e webhook | Sim |
| SUPABASE_URL | URL do projeto Supabase | Sim |
| SUPABASE_KEY | Chave anon/service_role do Supabase | Sim |
| EXCEL_PATH | Caminho do arquivo Excel | Não (default: ./data/fornecedores.xlsx) |

---

## 8. Deploy

### 8.1 Desenvolvimento Local

```bash
# 1. Subir Evolution API via Docker
docker-compose up -d evolution-api

# 2. Configurar .env a partir do .env.example
cp .env.example .env && nano .env

# 3. Instalar dependências Python
pip install -r requirements.txt

# 4. Rodar o backend
uvicorn main:app --reload --port 3000

# 5. Expor para webhook (ngrok ou similar)
ngrok http 3000
```

### 8.2 Render Free Tier (backend Python)

**render.yaml** configura deploy automático. Variáveis de ambiente são configuradas no painel Render.

**Limitações Render Free:**
- Hiberna após 15 min de inatividade → latência de ~30s na 1ª mensagem após hibernação
- Disco efêmero: .xlsx é perdido a cada redeploy (mitigação: endpoint /exportar antes de cada deploy)
- Sessões não se perdem pois ficam no Supabase

### 8.3 Evolution API em produção

A Evolution API deve rodar em um processo contínuo. Opções:
1. **VPS própria** (Oracle Free Tier, Hetzner €4/mês) — recomendado
2. **Render Pro** ($7/mês) — sem hibernação, processo persistente
3. **Railway** — free tier 500h/mês, suficiente para testes

---

## 9. Tratamento de Erros e Edge Cases

| Situação | Comportamento |
|---|---|
| Mensagem não-texto (áudio, imagem, etc.) | Responder: "Por favor, responda apenas com texto." |
| Sessão abandonada (>24h) | Limpar do Supabase; reiniciar fluxo na próxima mensagem |
| CNPJ inválido 3x | Encerrar sessão com mensagem de erro |
| Contato inválido 3x | Encerrar sessão com mensagem de erro |
| Estados inválidos 3x | Encerrar sessão com mensagem de erro |
| Erro ao salvar Excel | Log + aviso ao usuário |
| Erro de conexão Supabase | HTTP 500 + log — Evolution API vai fazer retry |
| fromMe=true (mensagem do próprio bot) | Ignorar silenciosamente |
| Grupo ou broadcast (@g.us) | Ignorar silenciosamente |

---

## 10. requirements.txt

```
fastapi==0.111.0
uvicorn==0.29.0
openpyxl==3.1.2
requests==2.31.0
python-dotenv==1.0.1
pydantic-settings==2.2.1
supabase==2.4.1
pytest==8.1.1
pytest-asyncio==0.23.6
httpx==0.27.0
```

---

## 11. Limitações e Débitos Técnicos (v2.0)

| Item | Limitação | Mitigação futura |
|---|---|---|
| Evolution API não oficial | Risco de ban em uso abusivo | Migrar para Meta API quando aprovado |
| Arquivo Excel efêmero | Perdido em redeploy no Render | Integrar Google Drive ou Supabase Storage |
| Sem deduplicação de CNPJ | Permite cadastros duplicados | Checar CNPJ no Supabase antes de salvar |
| Sem retry de envio | Se Evolution API falhar, mensagem se perde | Fila com retry (Celery/RQ) |
| Sem autenticação no /exportar | Token simples via query param | JWT ou endpoint protegido |

---

## 12. Critérios de Aceite

- [ ] Fornecedor acessa link do LinkedIn → WhatsApp abre com mensagem inicial do bot
- [ ] Bot conduz conversa coletando todos os 5 campos
- [ ] CNPJ inválido (dígitos errados) é rejeitado com mensagem clara
- [ ] CNPJ aceita entrada com e sem pontuação
- [ ] Contato aceita telefone (10 ou 11 dígitos) e e-mail
- [ ] Estados inválidos são informados ao usuário
- [ ] Ao confirmar, dados são salvos normalizados no Excel
- [ ] Excel possui cabeçalho e cada cadastro em uma linha
- [ ] Sessão é persistida no Supabase (sobrevive a reinícios do Render)
- [ ] Endpoint /exportar retorna o arquivo .xlsx atual
- [ ] Deploy funciona no Render Free sem custo
- [ ] Todos os testes A/B passam (`pytest tests/ -v`)
