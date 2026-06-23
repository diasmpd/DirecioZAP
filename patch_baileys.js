// Patches Baileys inside Evolution API for WhatsApp 2026 protocol compatibility
const fs = require('fs');

// 1. DICT_VERSION 2 → 3
const defaultsPath = '/evolution/node_modules/baileys/lib/Defaults/index.js';
let defaults = fs.readFileSync(defaultsPath, 'utf8');
if (defaults.includes('exports.DICT_VERSION = 2')) {
    defaults = defaults.replace('exports.DICT_VERSION = 2', 'exports.DICT_VERSION = 3');
    fs.writeFileSync(defaultsPath, defaults);
    console.log('[patch] DICT_VERSION patched: 2 → 3');
} else {
    console.log('[patch] DICT_VERSION already patched');
}

// 2. Add use_new_auth_key handler to socket.js
const socketPath = '/evolution/node_modules/baileys/lib/Socket/socket.js';
let socket = fs.readFileSync(socketPath, 'utf8');

if (!socket.includes("CB:use_new_auth_key")) {
    const anchor = "ws.on('CB:ib,,downgrade_webclient'";
    const idx = socket.indexOf(anchor);
    if (idx !== -1) {
        const handler = `    ws.on('CB:use_new_auth_key', (node) => {
        logger.info({ attrs: node.attrs }, 'use_new_auth_key received - acking and continuing');
        try {
            sendNode({ tag: 'ack', attrs: { id: node.attrs.id || '0', class: 'use_new_auth_key', to: 's.whatsapp.net' } });
        } catch (e) {
            logger.warn({ e: e.message }, 'use_new_auth_key ack failed (non-fatal)');
        }
    });\n    `;
        socket = socket.slice(0, idx) + handler + socket.slice(idx);
        fs.writeFileSync(socketPath, socket);
        console.log('[patch] use_new_auth_key handler added to socket.js');
    } else {
        console.log('[patch] ERROR: anchor not found in socket.js');
    }
} else {
    console.log('[patch] use_new_auth_key handler already present');
}

// 3. Log CB:failure details for debugging
if (!socket.includes('WA_FAILURE_DEBUG')) {
    socket = fs.readFileSync(socketPath, 'utf8');
    const failureAnchor = "ws.on('CB:failure', (node) => {";
    const fidx = socket.indexOf(failureAnchor);
    if (fidx !== -1) {
        const after = socket.indexOf('\n', fidx) + 1;
        const logLine = `        logger.error({ attrs: node.attrs }, 'WA_FAILURE_DEBUG');\n`;
        socket = socket.slice(0, after) + logLine + socket.slice(after);
        fs.writeFileSync(socketPath, socket);
        console.log('[patch] CB:failure debug logging added');
    }
}

console.log('[patch] All patches applied successfully');
