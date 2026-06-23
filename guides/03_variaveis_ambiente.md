# Guia 03 — Variáveis de Ambiente

> Tempo estimado: 5 minutos

---

## Arquivo .env (desenvolvimento local)

Copie o arquivo de exemplo e preencha:

```bash
cp .env.example .env
```

Abra o `.env` e configure cada variável:

```env
# ─── Evolution API ────────────────────────────────────────────
# URL onde a Evolution API está rodando
# Local: http://localhost:8080
# Produção: https://sua-evolution-api.com ou http://IP_DO_VPS:8080
EVOLUTION_API_URL=http://localhost:8080

# API Key configurada na Evolution API (mesma do docker-compose.yml)
EVOLUTION_API_KEY=troque_por_chave_segura

# Nome da instância criada na Evolution API
EVOLUTION_INSTANCE=direciozap

# ─── Segurança ────────────────────────────────────────────────
# Token para proteger o endpoint GET /exportar
# Qualquer string aleatória serve (ex: openssl rand -hex 32)
VERIFY_TOKEN=troque_por_token_seguro

# ─── Supabase ─────────────────────────────────────────────────
# Obtidos no painel Supabase: Project Settings → API
SUPABASE_URL=https://XXXX.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# ─── Opcional ─────────────────────────────────────────────────
# Caminho onde o Excel será salvo (padrão: ./data/fornecedores.xlsx)
# EXCEL_PATH=./data/fornecedores.xlsx
```

---

## Variáveis e seus significados

| Variável | Obrigatória | De onde obtém |
|---|---|---|
| `EVOLUTION_API_URL` | Sim | URL da sua instância Evolution API |
| `EVOLUTION_API_KEY` | Sim | Definida ao subir o Docker / painel Evolution |
| `EVOLUTION_INSTANCE` | Sim | Nome criado no Passo 3 do Guia 01 |
| `VERIFY_TOKEN` | Sim | Você cria — use `openssl rand -hex 32` |
| `SUPABASE_URL` | Sim | Painel Supabase → Project Settings → API |
| `SUPABASE_KEY` | Sim | Painel Supabase → Project Settings → API (anon key) |
| `EXCEL_PATH` | Não | Padrão: `./data/fornecedores.xlsx` |

---

## Gerar um VERIFY_TOKEN seguro

```bash
# No terminal:
python -c "import secrets; print(secrets.token_hex(32))"
# Ou:
openssl rand -hex 32
```

---

## Verificar se as variáveis foram carregadas

```bash
python -c "
from config import settings
print('Evolution URL:', settings.EVOLUTION_API_URL)
print('Instance:', settings.EVOLUTION_INSTANCE)
print('Supabase URL:', settings.SUPABASE_URL[:30] + '...')
print('Excel path:', settings.EXCEL_PATH)
print('OK — todas as variáveis carregadas!')
"
```

---

## No Render (produção)

As variáveis **não** ficam no `.env` em produção — elas são configuradas diretamente no painel do Render.

No Render:
1. Acesse seu serviço → **"Environment"**
2. Clique em **"Add Environment Variable"**
3. Adicione cada variável:

| Key | Value |
|---|---|
| EVOLUTION_API_URL | URL da Evolution API em produção |
| EVOLUTION_API_KEY | Sua API Key |
| EVOLUTION_INSTANCE | direciozap |
| VERIFY_TOKEN | Seu token seguro |
| SUPABASE_URL | URL do Supabase |
| SUPABASE_KEY | Anon key do Supabase |

> O `render.yaml` já declara quais variáveis o serviço espera com `sync: false` (o valor deve ser inserido manualmente pelo painel, não fica no repositório).

---

## Segurança

- **Nunca** commite o `.env` no Git. O `.gitignore` já deve incluir `.env`.
- Use `SUPABASE_KEY` com a `anon key`, não a `service_role key`.
- O `VERIFY_TOKEN` protege apenas o `/exportar` — não é usado para autenticar webhooks (a Evolution API pode ser configurada para enviar um header de autenticação se necessário).

---

## Próximo passo

Com as variáveis configuradas, siga o  
[Guia 04 — Deploy no Render](./04_deploy_render.md)
