# Guia 07 — Meta WhatsApp Cloud API

> Branch de produção: `META`  
> Status: funcional para webhooks recebidos; envio bloqueado para Brasil no sandbox

---

## Como funciona

A Meta WhatsApp Cloud API é a API **oficial** do WhatsApp. Diferente do Baileys (Evolution API), ela não emula o protocolo — usa a infraestrutura real da Meta via HTTP REST.

### Fluxo de uma mensagem

```
Usuário (WhatsApp) → Meta → POST /webhook (ngrok/bot) → GET /graph.facebook.com → Usuário
```

1. Usuário envia mensagem para o número de teste Meta
2. Meta faz POST no webhook do bot com payload JSON
3. Bot processa e chama `graph.facebook.com/{PHONE_NUMBER_ID}/messages`
4. Meta entrega a resposta ao usuário

---

## Estrutura do payload recebido (POST /webhook)

```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "WABA_ID",
    "changes": [{
      "field": "messages",
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "15556741075",
          "phone_number_id": "1298332316691579"
        },
        "contacts": [{"profile": {"name": "Nome"}, "wa_id": "5531999990000"}],
        "messages": [{
          "from": "5531999990000",
          "id": "wamid.xxx",
          "timestamp": "1234567890",
          "type": "text",
          "text": {"body": "mensagem do usuário"}
        }]
      }
    }]
  }]
}
```

Eventos sem `messages` (ex: status de entrega) chegam com `statuses` no lugar — o bot ignora.

---

## Verificação de webhook (GET /webhook)

A Meta exige que o endpoint responda a um GET de verificação antes de aceitar o webhook:

```
GET /webhook?hub.mode=subscribe&hub.verify_token=SEU_TOKEN&hub.challenge=CHALLENGE
→ Responder: CHALLENGE (texto puro)
```

O bot já implementa isso em `main.py`.

---

## Envio de mensagem (POST graph.facebook.com)

```http
POST https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages
Authorization: Bearer {META_TOKEN}
Content-Type: application/json

{
  "messaging_product": "whatsapp",
  "to": "5531999990000",
  "type": "text",
  "text": {"body": "Olá! Resposta do bot."}
}
```

---

## Credenciais necessárias (.env)

| Variável | Onde obter |
|---|---|
| `META_TOKEN` | Meta Developers → App → WhatsApp → API Setup → "Generate access token" (válido 24h no sandbox; permanente em produção via System User) |
| `META_PHONE_NUMBER_ID` | Meta Developers → App → WhatsApp → API Setup → seção "From" |
| `VERIFY_TOKEN` | Qualquer string segura — você define e configura na Meta |

---

## Limitação crítica do sandbox

**Erro 130497 — Business account is restricted from messaging users in this country.**

O sandbox da Meta **não envia mensagens para números brasileiros (+55)**. Isso é uma restrição geográfica do ambiente de teste.

### O que funciona no sandbox
- Receber webhooks de qualquer número ✅
- Enviar para números americanos (+1) ✅

### O que não funciona no sandbox
- Enviar para +55 (Brasil) ❌

### Para usar em produção com Brasil
É necessário:
1. Verificar o negócio na Meta (Meta Business Verification) — exige CNPJ e documentos
2. Solicitar "Standard Access" para a API
3. Registrar um número real (não o de teste +1 555)

Processo leva 1–7 dias úteis e é gratuito para negócios verificados.

---

## Configuração do webhook no painel Meta

1. Meta Developers → App → WhatsApp → **Configuration**
2. Em "Webhook" → **Edit**
   - Callback URL: `https://SEU-NGROK.ngrok-free.app/webhook`
   - Verify token: valor de `VERIFY_TOKEN` no `.env`
3. **Verify and Save**
4. **Manage** → marcar campo `messages` → **Subscribe**

---

## Destinatários de teste (sandbox)

No sandbox, só números explicitamente adicionados podem receber mensagens:

Meta Developers → App → WhatsApp → API Setup → **"To"** → **"Manage phone number list"**

Limite: 5 números por sandbox.

---

## Token de acesso

O token gerado no painel (`Generate access token`) expira em **24 horas**.

Para produção, usar **System User Token**:
Meta Business Settings → System Users → criar usuário → gerar token permanente para o app.
