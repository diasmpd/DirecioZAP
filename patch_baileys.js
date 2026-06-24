// Patches Baileys inside Evolution API for WhatsApp 2026 protocol compatibility
const fs = require('fs');

// 1. DICT_VERSION 2 → 3 (required for WA 2026 binary protocol)
const defaultsPath = '/evolution/node_modules/baileys/lib/Defaults/index.js';
let defaults = fs.readFileSync(defaultsPath, 'utf8');
if (defaults.includes('exports.DICT_VERSION = 2')) {
    defaults = defaults.replace('exports.DICT_VERSION = 2', 'exports.DICT_VERSION = 3');
    fs.writeFileSync(defaultsPath, defaults);
    console.log('[patch] DICT_VERSION patched: 2 → 3');
} else {
    console.log('[patch] DICT_VERSION already patched or not found');
}

// 2. Suppress the use_new_auth_key disconnect: swallow the node silently so
//    Baileys does not throw, allowing WA to complete the QR handshake.
const socketPath = '/evolution/node_modules/baileys/lib/Socket/socket.js';
let socket = fs.readFileSync(socketPath, 'utf8');

if (!socket.includes("CB:use_new_auth_key")) {
    const anchor = "ws.on('CB:ib,,downgrade_webclient'";
    const idx = socket.indexOf(anchor);
    if (idx !== -1) {
        // Register handler that swallows the node WITHOUT sending any ACK.
        // Sending an ACK with wrong key data causes WA to drop the connection.
        const handler = `    ws.on('CB:use_new_auth_key', (node) => {
        logger.info({ attrs: node.attrs }, 'use_new_auth_key received - swallowing (no ack)');
    });\n    `;
        socket = socket.slice(0, idx) + handler + socket.slice(idx);
        fs.writeFileSync(socketPath, socket);
        console.log('[patch] use_new_auth_key swallow handler added');
    } else {
        console.log('[patch] WARNING: anchor not found in socket.js — handler skipped');
    }
} else {
    console.log('[patch] use_new_auth_key handler already present');
}

console.log('[patch] All patches applied successfully');
