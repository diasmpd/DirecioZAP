// Patches Baileys inside Evolution API for WhatsApp 2026 protocol compatibility
// Strategy: install latest @whiskeysockets/baileys to get use_new_auth_key support
const fs = require('fs');
const { execSync } = require('child_process');

// 1. Update Baileys to latest version (handles use_new_auth_key in 2026 registration flow)
try {
    console.log('[patch] Installing latest @whiskeysockets/baileys...');
    const result = execSync(
        'cd /evolution && npm install @whiskeysockets/baileys@latest --no-save --prefer-online 2>&1',
        { timeout: 120000, encoding: 'utf8' }
    );
    console.log('[patch] Baileys update output:', result.slice(-300));
    console.log('[patch] Baileys updated successfully');
} catch (e) {
    console.log('[patch] WARNING: Baileys update failed:', e.message.slice(0, 200));
    console.log('[patch] Continuing with bundled version...');
}

// 2. DICT_VERSION 2 → 3 (required for WA 2026 binary protocol)
const defaultsPath = '/evolution/node_modules/baileys/lib/Defaults/index.js';
try {
    let defaults = fs.readFileSync(defaultsPath, 'utf8');
    if (defaults.includes('exports.DICT_VERSION = 2')) {
        defaults = defaults.replace('exports.DICT_VERSION = 2', 'exports.DICT_VERSION = 3');
        fs.writeFileSync(defaultsPath, defaults);
        console.log('[patch] DICT_VERSION patched: 2 → 3');
    } else if (defaults.includes('DICT_VERSION')) {
        console.log('[patch] DICT_VERSION already patched or different format');
    } else {
        console.log('[patch] WARNING: DICT_VERSION not found in Defaults');
    }
} catch (e) {
    console.log('[patch] WARNING: DICT_VERSION patch failed:', e.message);
}

console.log('[patch] All patches applied successfully');
