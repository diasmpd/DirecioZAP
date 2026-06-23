# Guia 05 — Link do LinkedIn para o WhatsApp

> Tempo estimado: 5 minutos

---

## Como funciona

O link `wa.me` do WhatsApp permite abrir uma conversa com uma mensagem pré-preenchida. Quando o fornecedor clica no link da postagem do LinkedIn, o WhatsApp abre automaticamente com a mensagem já digitada — e ao enviar, o bot responde imediatamente.

---

## Formato do link

```
https://wa.me/DDDNUMERO?text=MENSAGEM_CODIFICADA
```

**Exemplo:**
```
https://wa.me/5531999990000?text=Quero+me+cadastrar+como+fornecedor
```

Substitua `5531999990000` pelo número **com DDI (55) + DDD + número**, sem `+` ou espaços.

---

## Passo 1 — Montar seu link

1. Pegue o número conectado na Evolution API (o número do bot)
2. Formate: `55` + DDD + número (ex: `5531999990000`)
3. Monte o link:

```
https://wa.me/5531999990000?text=Quero%20me%20cadastrar%20como%20fornecedor
```

Você pode usar `+` ou `%20` para espaços. Ambos funcionam.

---

## Passo 2 — Testar o link

1. Abra o link em um navegador **diferente** do que você usa para o WhatsApp Web
2. O WhatsApp deve abrir com a mensagem pré-preenchida
3. Clique em enviar → o bot deve responder com a mensagem de boas-vindas

---

## Passo 3 — Incluir na postagem do LinkedIn

### Opção A: Botão CTA (Call-to-Action) do LinkedIn

Perfis pessoais e páginas podem adicionar um botão CTA:
1. Na sua Página ou Perfil → **"Editar"**
2. Procure por **"Adicionar botão"** ou **"Website"**
3. Coloque o link `wa.me` como URL

### Opção B: Link direto no texto da postagem

Inclua o link diretamente no corpo da postagem:

```
📦 Quer se tornar um fornecedor parceiro?

Cadastre sua empresa agora pelo WhatsApp em menos de 2 minutos!
👉 https://wa.me/5531999990000?text=Quero+me+cadastrar+como+fornecedor

[hashtags]
```

### Opção C: Link no primeiro comentário

Algumas empresas colocam o link no primeiro comentário para não prejudicar o alcance orgânico da postagem (o algoritmo do LinkedIn pode reduzir o alcance de posts com links externos).

---

## Passo 4 — Testar o fluxo completo

1. Clique no link como se fosse um fornecedor
2. Envie a mensagem pré-preenchida
3. Siga o fluxo completo:
   - Informe a Razão Social
   - Informe o CNPJ
   - Informe o contato (telefone ou e-mail)
   - Informe o serviço oferecido
   - Informe os estados de atuação
   - Confirme com "S"
4. Verifique se os dados foram salvos:

```bash
curl "https://direciozap-bot.onrender.com/exportar?token=SEU_TOKEN" \
  -o fornecedores.xlsx

# Abra no Excel e verifique os dados
```

---

## Troubleshooting

| Problema | Solução |
|---|---|
| Link abre o WhatsApp mas não manda mensagem automática | Normal no iOS — o usuário precisa clicar "Enviar" manualmente |
| Bot não responde | Verifique se a Evolution API está conectada e o webhook configurado |
| Bot responde "Por favor, responda apenas com texto" | O usuário enviou áudio/imagem/figurinha — só aceita texto |
| Bot reiniciou a conversa | Sessão expirou (>24h) ou houve 3 tentativas inválidas |
| Dados não aparecem no Excel | Use o endpoint `/exportar` para baixar — o arquivo persiste entre mensagens mas não entre redeploys |

---

## Fluxo completo de ponta a ponta

```
LinkedIn post
    │
    ▼ clica no link wa.me
WhatsApp abre com mensagem pré-preenchida "Quero me cadastrar como fornecedor"
    │
    ▼ fornecedor envia
Evolution API recebe a mensagem
    │
    ▼ POST /webhook
FastAPI processa → ConversationManager verifica sessão no Supabase
    │
    ▼ SAUDACAO (primeira vez)
Bot responde: "Olá! Qual é a Razão Social da sua empresa?"
    │
    ▼ fornecedor responde com a Razão Social
    ▼ fornecedor informa CNPJ, contato, serviço, estados
    ▼ confirma com "S"
    │
Dados salvos no Excel → session deletada do Supabase
    │
    ▼
Bot: "✅ Cadastro realizado com sucesso!"
```
