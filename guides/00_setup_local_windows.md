# Setup Local — Windows (PC novo / formatado)

## Pré-requisitos

### 1. Python 3.11
```powershell
winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
```
Após instalar, feche e reabra o terminal para atualizar o PATH.

Verifique:
```powershell
python --version   # deve mostrar Python 3.11.x
pip --version
```

### 2. WSL2 (obrigatório para Docker no Windows 11 Home)
```powershell
winget install Microsoft.WSL --silent --accept-package-agreements --accept-source-agreements
```
**Reinicie o Windows** após instalar o WSL2 — sem isso o Docker não funciona.

### 3. Docker Desktop
Necessário para rodar a Evolution API localmente.
```powershell
winget install Docker.DockerDesktop --silent --accept-package-agreements --accept-source-agreements
```
Após instalar, abra o Docker Desktop e aguarde o ícone na bandeja ficar verde.

### 4. ngrok (expõe o backend para o webhook)
```powershell
winget install Ngrok.Ngrok --silent --accept-package-agreements --accept-source-agreements
```

---

## Criando a venv do projeto

Dentro da pasta `DirecioZAP`, crie e ative a venv isolada:

```powershell
cd C:\projetos\DirecioZAP

# Criar a venv (só na primeira vez)
python -m venv .venv

# Ativar (toda vez que abrir o terminal)
.\.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt
```

> A pasta `.venv/` está no `.gitignore` — nunca é commitada.

---

## Configurando variáveis de ambiente

Copie o arquivo de exemplo e preencha:

```powershell
Copy-Item .env.example .env
notepad .env
```

Campos obrigatórios:

| Variável | Onde obter |
|---|---|
| `EVOLUTION_API_URL` | `http://localhost:8080` (dev local) |
| `EVOLUTION_API_KEY` | Definida no `docker-compose.yml` |
| `EVOLUTION_INSTANCE` | Nome criado no painel Evolution API |
| `VERIFY_TOKEN` | Qualquer string segura (ex: uuid gerado) |
| `SUPABASE_URL` | Painel do projeto em supabase.com |
| `SUPABASE_KEY` | Chave `anon` ou `service_role` do Supabase |

---

## Subindo tudo de uma vez (após reiniciar o PC)

O arquivo `start.ps1` na raiz do projeto faz tudo automaticamente:
1. Sobe Evolution API + PostgreSQL via Docker
2. Inicia o backend FastAPI na porta 3000
3. Inicia o ngrok (tunelamento público)
4. Cria a instância `direciozap` na Evolution API
5. Configura o webhook automaticamente

```powershell
cd C:\projetos\DirecioZAP
powershell -ExecutionPolicy Bypass -File start.ps1
```

Após rodar, acesse `http://localhost:8080/manager` e conecte o WhatsApp (QR Code).

---

## Subindo manualmente (passo a passo)

```powershell
# 1. Evolution API
docker compose up -d

# 2. Backend (nova aba do terminal, com venv ativada)
.\.venv\Scripts\Activate.ps1
uvicorn main:app --port 3000

# 3. ngrok (outra aba)
ngrok http 3000
```

---

## Executando os testes

Os testes não precisam de serviços reais (Supabase e Evolution API são mockados):

```powershell
# Com a venv ativada
pytest tests/ -v
```

Resultado esperado: **103 passed** em ~4 segundos.

---

## Expondo o webhook localmente (opcional)

Para testar o fluxo real com WhatsApp, exponha a porta 3000 via [ngrok](https://ngrok.com/):

```powershell
winget install Ngrok.Ngrok
ngrok http 3000
```

Configure a URL pública do ngrok como webhook na Evolution API.

---

## Credenciais geradas (salvas no .env)

| Variável | Valor |
|---|---|
| `EVOLUTION_API_KEY` | `HXsWhL0Ddp1JSOImTjw5xu8lVYPzMe4f` |
| `VERIFY_TOKEN` | `db7ebc94edcb4c9c89f72911c6418d3a` |
| `SUPABASE_URL` | `https://wawjmfaukdpyxwzqulfn.supabase.co` |

> A `SUPABASE_KEY` está no `.env`. O `.env` não é commitado (`.gitignore`).

---

## Estrutura da venv

```
DirecioZAP/
├── .venv/              ← isolado aqui, não commitar
├── requirements.txt    ← fonte da verdade das dependências
└── ...
```

Para atualizar dependências após alterar o `requirements.txt`:
```powershell
pip install -r requirements.txt
```

Para ver o que está instalado:
```powershell
pip list
```
