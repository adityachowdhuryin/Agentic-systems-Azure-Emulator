const {
  CloudAdapter,
  ConfigurationBotFrameworkAuthentication,
  CardFactory,
  MessageFactory,
} = require('botbuilder');

function stripMention(text) {
  return String(text || '')
    .replace(/<at>[\s\S]*?<\/at>/gi, '')
    .replace(/&nbsp;/gi, ' ')
    .trim();
}

function channelLabel(activity) {
  const channelData = activity.channelData || {};
  const channel = channelData.channel || {};
  return channel.name || channel.id || activity.channelId || '';
}

function teamLabel(activity) {
  const channelData = activity.channelData || {};
  const team = channelData.team || {};
  return team.name || team.id || '';
}

function isIngestionLogsCommand(text) {
  const normalized = String(text || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return normalized === 'ingestion logs' || normalized === 'ingestion log';
}

function buildAck(bandAStatus, body) {
  if (bandAStatus >= 200 && bandAStatus < 300) {
    const runId = body.run_id || 'unknown';
    const state = body.state || 'UNKNOWN';
    if (body.duplicate) {
      return `Already processed. Existing run ${runId} (${state}).`;
    }
    return `Received. Run ${runId} created (${state}).`;
  }

  const detail = body.detail || body.error || {};
  let message =
    typeof detail === 'string'
      ? detail
      : detail && detail.message
        ? detail.message
        : '';
  if (!message || message === '{}') {
    message =
      Object.keys(body || {}).length === 0
        ? `Band A HTTP ${bandAStatus} with empty body (often timeout/cold start). Please retry in a moment.`
        : JSON.stringify(body);
  }
  if (bandAStatus === 409 && detail.existing_run_id) {
    return `Rejected — lead already has active run ${detail.existing_run_id}.`;
  }
  return `Could not process (HTTP ${bandAStatus}): ${message}`;
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollInvoiceFinding(bandAUrl, runId, { timeoutMs = 240000, intervalMs = 3000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${bandAUrl}/api/v1/invoice/runs/${runId}/finding`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Finding poll error:', error.message);
    }
    await sleep(intervalMs);
  }
  return null;
}

async function handleInvoiceReviewAck(context, bandAUrl, bandABody) {
  const caseId = bandABody.case_id || 'CASE';
  const runId = bandABody.run_id || 'unknown';
  await context.sendActivity(
    MessageFactory.text(
      `Investigating ${caseId}… run ${runId} (door teams). I'll reply when the finding is ready.`
    )
  );
  if (!bandABody.run_id) {
    return;
  }
  const finding = await pollInvoiceFinding(bandAUrl, bandABody.run_id);
  if (finding && finding.verdict) {
    await context.sendActivity(
      MessageFactory.text(
        `${caseId} finding ready — verdict: ${finding.verdict} (${runId}). Open Invoice Review for journal / replay.`
      )
    );
  } else {
    await context.sendActivity(
      MessageFactory.text(
        `${caseId} is still running (${runId}). Check Invoice Review in the dashboard for the finding.`
      )
    );
  }
}

function formatReceivedIst(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(d);
  } catch {
    return '—';
  }
}

function dash(value) {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function ingestionLogsAction(title = 'Ingestion logs') {
  // messageBack is the reliable Teams pattern so the button posts text the bot already handles
  return {
    type: 'Action.Submit',
    title,
    data: {
      action: 'ingestion_logs',
      msteams: {
        type: 'messageBack',
        displayText: title,
        text: 'ingestion logs',
      },
    },
  };
}

function buildWelcomeCard() {
  return {
    type: 'AdaptiveCard',
    $schema: 'http://adaptivecards.io/schemas/adaptive-card.json',
    version: '1.4',
    body: [
      {
        type: 'TextBlock',
        text: 'Band A Sales Bot',
        weight: 'Bolder',
        size: 'Large',
        wrap: true,
      },
      {
        type: 'TextBlock',
        text: 'Send a lead message to create a Band A run, or open the ingestion log for every Teams inbound.',
        wrap: true,
        spacing: 'Small',
      },
    ],
    actions: [ingestionLogsAction('Ingestion logs')],
  };
}

function buildIngestionLogsCard(rows) {
  const body = [
    {
      type: 'TextBlock',
      text: 'Ingestion log',
      weight: 'Bolder',
      size: 'Large',
      wrap: true,
    },
    {
      type: 'TextBlock',
      text: 'Every Teams run and how far it got through Band A — tap Details to expand a run',
      isSubtle: true,
      wrap: true,
      spacing: 'None',
    },
  ];

  if (!rows || rows.length === 0) {
    body.push({
      type: 'TextBlock',
      text: 'No Teams runs yet',
      wrap: true,
      spacing: 'Medium',
      weight: 'Bolder',
    });
  } else {
    rows.slice(0, 25).forEach((row, i) => {
      const detailsId = `details-${i}`;
      const refs = [row.tenant_id, row.owner, row.run_id, row.lead_id]
        .filter((x) => x && x !== '—')
        .join(' · ');
      const sourceLabel =
        row.route && row.route !== '—'
          ? `${dash(row.source)} (${row.route})`
          : dash(row.source);
      const received = formatReceivedIst(row.received_at);
      const meta = [dash(row.phase), dash(row.band_a_stage), received]
        .filter((x) => x && x !== '—')
        .join(' · ');

      const items = [
        {
          type: 'TextBlock',
          text: dash(row.topic),
          weight: 'Bolder',
          wrap: true,
        },
        {
          type: 'TextBlock',
          text: meta || '—',
          size: 'Small',
          wrap: true,
          spacing: 'None',
        },
      ];
      if (refs) {
        items.push({
          type: 'TextBlock',
          text: refs,
          size: 'Small',
          isSubtle: true,
          wrap: true,
          spacing: 'None',
        });
      }
      items.push({
        type: 'Container',
        id: detailsId,
        isVisible: false,
        spacing: 'Small',
        items: [
          {
            type: 'FactSet',
            facts: [
              { title: 'Source', value: sourceLabel },
              { title: 'Band A stage', value: dash(row.band_a_stage) },
              { title: 'State', value: dash(row.phase) },
              { title: 'Spend', value: row.spend == null ? '—' : String(row.spend) },
              { title: 'Received', value: received },
              { title: 'Note', value: dash(row.note) },
            ],
          },
        ],
      });
      items.push({
        type: 'ActionSet',
        spacing: 'Small',
        actions: [
          {
            type: 'Action.ToggleVisibility',
            title: 'Details',
            targetElements: [detailsId],
          },
        ],
      });

      body.push({
        type: 'Container',
        separator: true,
        spacing: 'Medium',
        items,
      });
    });
  }

  return {
    type: 'AdaptiveCard',
    $schema: 'http://adaptivecards.io/schemas/adaptive-card.json',
    version: '1.4',
    body,
    actions: [ingestionLogsAction('Refresh ingestion logs')],
  };
}

async function fetchIngestionLogs(bandAUrl, teamsBridgeKey) {
  const response = await fetch(`${bandAUrl}/api/v1/ingestion-logs?source=teams&limit=25`, {
    method: 'GET',
    headers: {
      'X-Teams-Bridge-Key': teamsBridgeKey,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail || body.error || `HTTP ${response.status}`;
    const message = typeof detail === 'string' ? detail : detail.message || JSON.stringify(detail);
    throw new Error(message);
  }
  return Array.isArray(body.rows) ? body.rows : [];
}

async function sendIngestionLogsCard(context, bandAUrl, teamsBridgeKey) {
  try {
    const rows = await fetchIngestionLogs(bandAUrl, teamsBridgeKey);
    await context.sendActivity(MessageFactory.attachment(CardFactory.adaptiveCard(buildIngestionLogsCard(rows))));
  } catch (error) {
    console.error('Failed to load ingestion logs:', error.message);
    await context.sendActivity(MessageFactory.text(`Could not load ingestion logs: ${error.message}`));
  }
}

function registerTeamsBot(app, { bandAUrl, teamsBridgeKey }) {
  const appId = process.env.MICROSOFT_APP_ID || '';
  const appPassword = process.env.MICROSOFT_APP_PASSWORD || '';
  const tenantId = process.env.MICROSOFT_APP_TENANT_ID || '';
  const appType = process.env.MICROSOFT_APP_TYPE || 'SingleTenant';

  if (!appId || !appPassword) {
    console.log('>>> Teams bot disabled — set MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD in .env');
    app.post('/api/messages', (_req, res) => {
      res.status(503).json({
        error: 'Teams bot not configured. Add MICROSOFT_APP_ID / MICROSOFT_APP_PASSWORD to webhook/.env',
      });
    });
    return;
  }

  const auth = new ConfigurationBotFrameworkAuthentication({
    MicrosoftAppId: appId,
    MicrosoftAppPassword: appPassword,
    MicrosoftAppType: appType,
    MicrosoftAppTenantId: tenantId,
  });
  const adapter = new CloudAdapter(auth);

  adapter.onTurnError = async (context, error) => {
    console.error('Teams bot turn error:', error);
    try {
      await context.sendActivity('Sorry — Band A could not process that message.');
    } catch (sendErr) {
      console.error('Failed to send Teams error reply:', sendErr.message);
    }
  };

  app.post('/api/messages', async (req, res) => {
    await adapter.process(req, res, async (context) => {
      const activity = context.activity;

      // Welcome card when bot is added to a conversation
      if (activity.type === 'conversationUpdate' && Array.isArray(activity.membersAdded)) {
        const botId = activity.recipient && activity.recipient.id;
        const added = activity.membersAdded.some((m) => m.id === botId);
        if (added) {
          await context.sendActivity(
            MessageFactory.attachment(CardFactory.adaptiveCard(buildWelcomeCard()))
          );
        }
        return;
      }

      // Adaptive Card Action.Submit / Action.Execute (Teams often sends invoke)
      const value = activity.value || {};
      const nestedData =
        value.action && typeof value.action === 'object' ? value.action.data || {} : {};
      const submitAction =
        value.action === 'ingestion_logs'
          ? 'ingestion_logs'
          : nestedData.action === 'ingestion_logs'
            ? 'ingestion_logs'
            : null;

      if (activity.type === 'invoke' && submitAction === 'ingestion_logs') {
        await sendIngestionLogsCard(context, bandAUrl, teamsBridgeKey);
        await context.sendActivity({
          type: 'invokeResponse',
          value: { status: 200, body: null },
        });
        return;
      }
      if (submitAction === 'ingestion_logs') {
        await sendIngestionLogsCard(context, bandAUrl, teamsBridgeKey);
        return;
      }

      if (activity.type !== 'message') {
        return;
      }

      const text = stripMention(activity.text);
      if (isIngestionLogsCommand(text) || text.toLowerCase() === 'help') {
        if (text.toLowerCase() === 'help') {
          await context.sendActivity(
            MessageFactory.attachment(CardFactory.adaptiveCard(buildWelcomeCard()))
          );
          return;
        }
        await sendIngestionLogsCard(context, bandAUrl, teamsBridgeKey);
        return;
      }

      const from = activity.from || {};
      const conversation = activity.conversation || {};

      const payload = {
        text,
        from_name: from.name || '',
        from_id: from.aadObjectId || from.id || '',
        channel_id: channelLabel(activity),
        team_id: teamLabel(activity),
        conversation_id: conversation.id || '',
        activity_id: activity.id || '',
        channelData: activity.channelData || {},
        from,
        conversation,
      };

      console.log('\n==================================================');
      console.log(`[${new Date().toLocaleTimeString()}] TEAMS BOT MESSAGE`);
      console.log('==================================================');
      console.log(JSON.stringify(payload, null, 2));
      console.log('==================================================\n');

      let bandAStatus = 500;
      let bandABody = {};
      try {
        const response = await fetch(`${bandAUrl}/api/v1/webhooks/teams`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Teams-Bridge-Key': teamsBridgeKey,
          },
          body: JSON.stringify(payload),
          signal: AbortSignal.timeout(55000),
        });
        bandAStatus = response.status;
        bandABody = await response.json().catch(() => ({}));
        console.log('Band A Teams response:', bandAStatus, bandABody);
      } catch (error) {
        console.error('Failed to forward Teams message to Band A:', error.message);
        const timedOut = error && (error.name === 'TimeoutError' || error.name === 'AbortError');
        bandABody = {
          detail: {
            message: timedOut
              ? 'Timed out waiting for Band A (55s). App may be cold-starting — retry once.'
              : error.message,
          },
        };
      }

      if (bandAStatus >= 200 && bandAStatus < 300 && bandABody.use_case === 'invoice_review') {
        await handleInvoiceReviewAck(context, bandAUrl, bandABody);
      } else {
        await context.sendActivity(MessageFactory.text(buildAck(bandAStatus, bandABody)));
      }
    });
  });

  console.log(`>>> Teams bot listening on http://127.0.0.1:${process.env.PORT || 8080}/api/messages`);
  console.log(`>>> Forwarding to ${bandAUrl}/api/v1/webhooks/teams`);
}

module.exports = {
  registerTeamsBot,
  buildIngestionLogsCard,
  buildWelcomeCard,
  isIngestionLogsCommand,
};
