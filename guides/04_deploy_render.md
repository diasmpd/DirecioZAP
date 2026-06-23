# Guia 04 — Deploy no Render

> Tempo estimado: 15–20 minutos  
> Pré-requisitos: conta no [render.com](https://render.com) (gratuita) e repositório Git

---

## Estrutura do Deploy

| Componente | Onde roda | Custo |
|---|---|---|
| Backend Python (FastAPI) | Render Free | Gratuito |
| Evolution API | VPS própria ou Railway | Gratuito (Oracle Free) ou ~$5/mês |
| Supabase (sessões) | Supabase Cloud | Gratuito |
| Excel | Disco efêmero Render | Gratuito (exportar antes de redeploy) |

---

## Passo 1 — Preparar o Repositório Git

```bash
# Inicializar git no projeto
cd C:/projetos/DirecioZap
git init
git add .
git commit -m "feat: implementação inicial DirecioZap Bot"

# Criar repositório no GitHub e fazer push
# (via GitHub CLI ou interface web)
gh repo create direciozap --public --source=. --push
```

Crie um `.gitignore` antes do commit:

```
.env
data/fornecedores.xlsx
__pycache__/
*.pyc
.pytest_cache/
```

---

## Passo 2 — Criar o Serviço no Render

1. Acesse [render.com](https://render.com) → **"New +"** → **"Web Service"**
2. Conecte sua conta GitHub se ainda não conectou
3. Selecione o repositório `direciozap`
4. Configure:
   - **Name:** `direciozap-bot`
   - **Region:** Oregon (US West) ou Frankfurt — qualquer um
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Clique em **"Create Web Service"**

> O `render.yaml` na raiz do projeto configura isso automaticamente se você usar **"Infrastructure as Code"** no Render. Mas criar manualmente também funciona.

---

## Passo 3 — Configurar Variáveis de Ambiente no Render

Após criar o serviço:

1. Vá em **"Environment"** no menu do serviço
2. Clique em **"Add Environment Variable"** para cada variável:

```
EVOLUTION_API_URL  = https://sua-evolution-api.com
EVOLUTION_API_KEY  = sua_chave
EVOLUTION_INSTANCE = direciozap
VERIFY_TOKEN       = seu_token_seguro
SUPABASE_URL       = https://XXXX.supabase.co
SUPABASE_KEY       = eyJhbGciOiJI...
```

3. Clique em **"Save Changes"** — o Render fará um redeploy automaticamente.

---

## Passo 4 — Aguardar o Deploy

O primeiro build demora 2–5 minutos. Acompanhe em **"Logs"**.

Quando aparecer:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:XXXXX
```

O serviço está no ar. Teste:
```
https://direciozap-bot.onrender.com/
# Deve retornar: {"status": "ok"}
```

---

## Passo 5 — Configurar o Webhook na Evolution API

Agora que o backend tem URL pública, configure o webhook:

```bash
curl -X POST https://sua-evolution-api.com/webhook/set/direciozap \
  -H "apikey: SUA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://direciozap-bot.onrender.com/webhook",
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

---

## Passo 6 — Testar em Produção

1. Envie uma mensagem WhatsApp para o número conectado na Evolution API
2. O bot deve responder com a mensagem de boas-vindas
3. Verifique os logs no painel Render em tempo real

---

## Considerações sobre o Render Free

### Hibernação (15 min)
O Render Free hiberna o processo após 15 minutos sem requisições. A próxima mensagem vai demorar ~30 segundos para despertar o serviço.

**Mitigação:** Configure um serviço de "keep-alive" gratuito:
- [UptimeRobot](https://uptimerobot.com): ping a cada 5 minutos (gratuito)
  - URL para monitorar: `https://direciozap-bot.onrender.com/`
  - Tipo: HTTP(S)
  - Intervalo: 5 minutos

### Disco efêmero
O arquivo `fornecedores.xlsx` é perdido em cada redeploy ou reinício.

**Solução para v1.0:** Baixe o arquivo antes de fazer redeploy:
```bash
curl "https://direciozap-bot.onrender.com/exportar?token=SEU_TOKEN" \
  -o fornecedores_backup_$(date +%Y%m%d).xlsx
```

**Solução futura:** Integrar com Google Drive ou Supabase Storage.

### Free tier limits
- **750 horas/mês** de compute — suficiente para um serviço 24/7
- **512 MB RAM** — mais que suficiente para este bot
- **Sem domínio customizado** no Free — use `.onrender.com`

---

## Próximo passo

Com o deploy funcionando, configure o link do LinkedIn no  
[Guia 05 — Link do LinkedIn](./05_linkedin_link.md)
