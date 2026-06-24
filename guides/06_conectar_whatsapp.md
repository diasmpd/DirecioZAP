# Guia 06 — Conectar WhatsApp à Evolution API

> Este guia resolve o problema de **IP de nuvem bloqueado pelo WhatsApp** ao tentar conectar
> uma instância hospedada na Render (ou qualquer cloud AWS/GCP).

---

## Contexto: por que o QR não aparece na Render?

O WhatsApp bloqueia registros de novos dispositivos originados de IPs de datacenters conhecidos
(AWS, GCP, Render, Railway, etc.). O sintoma é o WebSocket fechar imediatamente com:

```
attrs: {"105": "405"}   ← código 405 = rejeição de registro
```

Isso acontece **antes** de qualquer QR ser gerado, independente da versão do Baileys ou patches.

---

## Solução: escanear QR localmente e reutilizar sessão na nuvem

A sessão WhatsApp (chaves de autenticação) é armazenada no **PostgreSQL da Render**.  
O fluxo é:

1. Rodar Evolution API **localmente** (IP residencial → sem bloqueio)
2. Criar instância e escanear QR
3. Sessão gravada no PostgreSQL remoto da Render
4. Parar o Docker local
5. Redeploy do serviço `evolution-direciozap` na Render → lê sessão do banco → reconecta sem QR

---

## Pré-requisito

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e rodando

---

## Passo 1 — Obter o External Database URL

No painel Render → serviço `evolution-db` → **Info** → seção **Connections**:

- Clique no olho em **External Database URL**
- Formato: `postgresql://USER:SENHA@dpg-XXXX.oregon-postgres.render.com:5432/DBNAME`

---

## Passo 2 — Rodar Evolution API localmente

**PowerShell:**

```powershell
docker run --rm `
  -e AUTHENTICATION_API_KEY=direciozap123 `
  -e SERVER_URL=http://localhost:8080 `
  -e DATABASE_PROVIDER=postgresql `
  -e "DATABASE_CONNECTION_URI=<EXTERNAL_DATABASE_URL>?schema=public" `
  -e DATABASE_CONNECTION_CLIENT_NAME=direciozap `
  -e CACHE_REDIS_ENABLED=false `
  -e CACHE_LOCAL_ENABLED=true `
  -e CONFIG_SESSION_PHONE_CLIENT=Chrome `
  -e CONFIG_SESSION_PHONE_NAME=Chrome `
  -p 8080:8080 `
  atendai/evolution-api:latest
```

**Bash/macOS:**

```bash
docker run --rm \
  -e AUTHENTICATION_API_KEY=direciozap123 \
  -e SERVER_URL=http://localhost:8080 \
  -e DATABASE_PROVIDER=postgresql \
  -e "DATABASE_CONNECTION_URI=<EXTERNAL_DATABASE_URL>?schema=public" \
  -e DATABASE_CONNECTION_CLIENT_NAME=direciozap \
  -e CACHE_REDIS_ENABLED=false \
  -e CACHE_LOCAL_ENABLED=true \
  -e CONFIG_SESSION_PHONE_CLIENT=Chrome \
  -e CONFIG_SESSION_PHONE_NAME=Chrome \
  -p 8080:8080 \
  atendai/evolution-api:latest
```

Aguarde a mensagem `HTTP - ON: 8080` nos logs.

---

## Passo 3 — Criar a instância e escanear o QR

1. Abra `http://localhost:8080/manager` no browser
2. Clique em **New Instance**
   - Nome: `direciozap`
   - Token: `direciozap123`
3. Clique na instância → **Get QR Code**
4. No celular: **WhatsApp → Dispositivos Vinculados → Vincular Dispositivo**
5. Escaneie o QR

Quando o status mudar para **open** ou **connected**, a sessão está salva no banco.

---

## Passo 4 — Parar o container local

```
Ctrl+C
```

O container é removido automaticamente (`--rm`). A sessão permanece no PostgreSQL da Render.

---

## Passo 5 — Reconectar na Render

Acesse o serviço `evolution-direciozap` na Render → **Manual Deploy → Deploy latest commit**.

A Evolution API iniciará, lerá a instância `direciozap` do banco e reconectará ao WhatsApp
sem solicitar novo QR.

Confirme nos logs da Render:

```
[Baileys] connection.update: open
```

---

## Passo 6 — Verificar o webhook

```bash
curl -X GET https://evolution-direciozap.onrender.com/webhook/find/direciozap \
  -H "apikey: direciozap123"
```

Deve retornar `"url": "https://direciozap-bot.onrender.com/webhook"` e `"enabled": true`.

Se não retornar, reconfigurar:

```bash
curl -X POST https://evolution-direciozap.onrender.com/webhook/set/direciozap \
  -H "apikey: direciozap123" \
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

## Passo 7 — Teste end-to-end

Envie uma mensagem WhatsApp para o número vinculado.  
Verifique os logs do `direciozap-bot` na Render — deve aparecer a conversa iniciada.

---

## Notas importantes

### Expiração do banco PostgreSQL (Render Free)
O banco `evolution-db` expira em **23 de julho de 2026**. Após essa data, a sessão WhatsApp
será perdida e será necessário repetir este processo com um novo banco.

### Reconexão automática
Após a primeira conexão, a Evolution API reconecta automaticamente ao reiniciar, desde que
a sessão no banco seja válida (WhatsApp não tenha revogado o dispositivo).

### Se o QR expirar antes de escanear
O QR tem validade de ~60 segundos. Se expirar, clique em **Refresh** no Manager local para
gerar um novo.
