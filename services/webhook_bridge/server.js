require('dotenv').config();
const express = require('express');
const { registerTeamsBot } = require('./teamsBot');

const app = express();
const PORT = Number(process.env.PORT || 8080);
const BAND_A_URL = process.env.BAND_A_URL || 'http://127.0.0.1:8000';
const MAIL_BRIDGE_KEY = process.env.MAIL_BRIDGE_KEY || 'local-mail-bridge-key';
const TEAMS_BRIDGE_KEY = process.env.TEAMS_BRIDGE_KEY || 'local-teams-bridge-key';

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    band_a_url: BAND_A_URL,
    teams_bot_configured: Boolean(process.env.MICROSOFT_APP_ID && process.env.MICROSOFT_APP_PASSWORD),
  });
});

function normalizePayload(body) {
  if (typeof body === 'string') {
    try {
      return JSON.parse(body);
    } catch {
      // Deluge Map.toString() looks like: {key=value, key2=value2}
      if (body.startsWith('{') && body.includes('=')) {
        const obj = {};
        for (const part of body.slice(1, -1).split(',')) {
          const eq = part.indexOf('=');
          if (eq > 0) {
            obj[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
          }
        }
        return obj;
      }
      return { raw: body };
    }
  }
  if (Buffer.isBuffer(body)) {
    return normalizePayload(body.toString('utf8'));
  }
  return body || {};
}

function parseMultipart(raw, contentType) {
  const boundaryMatch = contentType.match(/boundary=([^;]+)/);
  if (!boundaryMatch) return { raw };

  const boundary = boundaryMatch[1].trim();
  const obj = {};
  const parts = raw.split(`--${boundary}`);

  for (const part of parts) {
    const nameMatch = part.match(/name="([^"]+)"/);
    if (!nameMatch) continue;
    const chunks = part.split(/\r?\n\r?\n/);
    if (chunks.length < 2) continue;
    const value = chunks.slice(1).join('\n').replace(/\r?\n--?\s*$/, '').trim();
    obj[nameMatch[1]] = value;
  }

  return obj;
}

function parseBody(rawBody, contentType = '') {
  const raw = Buffer.isBuffer(rawBody) ? rawBody.toString('utf8') : String(rawBody || '');

  // Deluge sometimes labels multipart as application/json, or sends raw multipart body
  if (raw.trimStart().startsWith('--') && raw.includes('Content-Disposition')) {
    const boundary = raw.trimStart().slice(2).split(/\r?\n/)[0];
    return parseMultipart(raw, `multipart/form-data; boundary=${boundary}`);
  }

  if (contentType.includes('application/json')) {
    const parsed = normalizePayload(raw);
    // JSON-wrapped raw multipart string
    if (parsed.raw && String(parsed.raw).trimStart().startsWith('--')) {
      const inner = String(parsed.raw);
      const boundary = inner.trimStart().slice(2).split(/\r?\n/)[0];
      return parseMultipart(inner, `multipart/form-data; boundary=${boundary}`);
    }
    return parsed;
  }
  if (contentType.includes('application/x-www-form-urlencoded')) {
    return Object.fromEntries(new URLSearchParams(raw));
  }
  if (contentType.includes('multipart/form-data')) {
    return parseMultipart(raw, contentType);
  }
  return normalizePayload(raw);
}

// JSON for Bot Framework (must be registered before the raw Zoho webhook parser)
app.use('/api/messages', express.json({ limit: '2mb' }));
registerTeamsBot(app, { bandAUrl: BAND_A_URL, teamsBridgeKey: TEAMS_BRIDGE_KEY });

// Raw body parser — Zoho Deluge may send JSON, form-urlencoded, or multipart
app.post('/webhook', express.raw({ type: '*/*', limit: '10mb' }), async (req, res) => {
  const contentType = req.headers['content-type'] || '';
  const payload = parseBody(req.body, contentType);

  const attachmentCount = Array.isArray(payload.attachments) ? payload.attachments.length : 0;
  console.log('\n==================================================');
  console.log(`[${new Date().toLocaleTimeString()}] ZOHO MAIL WEBHOOK RECEIVED`);
  console.log(`Content-Type: ${contentType}`);
  console.log(`Attachments: ${attachmentCount}`);
  console.log('==================================================');
  // Avoid dumping huge base64 bodies in the terminal
  const logPayload = { ...payload };
  if (Array.isArray(logPayload.attachments)) {
    logPayload.attachments = logPayload.attachments.map((a) => ({
      filename: a && a.filename,
      content_chars: a && a.content != null ? String(a.content).length : 0,
    }));
  }
  console.log(JSON.stringify(logPayload, null, 2));
  console.log('==================================================\n');

  try {
    // Forward full payload including attachments[].content for live invoice extract
    const bandAResponse = await fetch(`${BAND_A_URL}/api/v1/webhooks/zoho-mail`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Mail-Bridge-Key': MAIL_BRIDGE_KEY,
      },
      body: JSON.stringify(payload),
    });

    const bandABody = await bandAResponse.json().catch(() => ({}));
    console.log('Band A response:', bandAResponse.status, bandABody);

    return res.status(200).json({
      status: 'received',
      forwarded: true,
      band_a_status: bandAResponse.status,
      band_a: bandABody,
    });
  } catch (error) {
    console.error('Failed to forward to Band A:', error.message);
    return res.status(200).json({
      status: 'received',
      forwarded: false,
      error: error.message,
    });
  }
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n>>> Zoho Mail webhook bridge running on http://0.0.0.0:${PORT}/webhook`);
  console.log(`>>> Forwarding to ${BAND_A_URL}/api/v1/webhooks/zoho-mail`);
  console.log(`>>> Teams messaging endpoint: http://0.0.0.0:${PORT}/api/messages\n`);
});
