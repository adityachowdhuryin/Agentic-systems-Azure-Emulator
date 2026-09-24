# Zoho Deluge — live invoice (real attach + body paste)

**Primary demo path:** attach a pack `.json` / `.txt` (e.g. `CASE-09_INV-01417.json`).  
**Fallback:** paste the same JSON into the email body.

Band A prefers attachments, then body. No local `CASE-XX` mapping. Unrelated live mail (no pack-shaped invoice) still creates an Invoice Review run; Band B returns `exception:not_an_invoice`. Sales Lead demos use the dashboard Zoho simulator, not live Deluge.

Your Mail IDs (locked):

- `accountId` = `7135116000000008002`
- `folderId` = `7135116000000008014` (inbox)
- Connection = `zoho` — if attach download fails with 401, re-authorize with `ZohoMail.messages.READ` or `ALL`

Replace the ngrok host whenever the tunnel restarts (current example below).

---

## Script B — primary (real attach + body paste)

Copy-paste into Zoho Mail filter Deluge and Save:

```javascript
accountId = "7135116000000008002";
folderId = "7135116000000008014";

messageDetails = zoho.mail.getMessage(mail_messageId,"zoho");
fromAddress = messageDetails.get("FROM");
toAddress = messageDetails.get("TO");
subject = messageDetails.get("SUBJECT");
content = messageDetails.get("CONTENT");

attachmentsOut = List();
try
{
	newAttRaw = messageDetails.get("NEWATT");
	info "NEWATT: " + newAttRaw;
	if(newAttRaw != null && newAttRaw != "")
	{
		attList = List();
		try
		{
			attList = newAttRaw.toJSONList();
		}
		catch (e1)
		{
			info "toJSONList failed, trying cleaned NEWATT: " + e1;
			cleaned = newAttRaw.replaceAll("\\\\","");
			attList = cleaned.toJSONList();
		}
		for each att in attList
		{
			fileName = ifnull(att.get("name"),att.get("fn"));
			attId = ifnull(att.get("id"),att.get("Id"));
			if(fileName == null || attId == null)
			{
				continue;
			}
			lower = fileName.toLowerCase();
			if(!(lower.endsWith(".json") || lower.endsWith(".txt")))
			{
				continue;
			}
			attUrl = "https://mail.zoho.com/api/accounts/" + accountId + "/folders/" + folderId + "/messages/" + mail_messageId + "/attachments/" + attId;
			fileObj = invokeurl
			[
				url :attUrl
				type :GET
				connection:"zoho"
			];
			fileText = "";
			try
			{
				fileText = fileObj.getFileContent();
			}
			catch (e2)
			{
				fileText = fileObj.toString();
			}
			row = Map();
			row.put("filename",fileName);
			row.put("content",fileText);
			attachmentsOut.add(row);
			info "Attached " + fileName + " chars=" + fileText.length();
		}
	}
}
catch (e)
{
	info "Attachment fetch skipped: " + e;
}

payload = Map();
payload.put("messageId",mail_messageId);
payload.put("from",fromAddress);
payload.put("to",toAddress);
payload.put("subject",subject);
payload.put("content",content);
payload.put("attachments",attachmentsOut);

response = invokeurl
[
	url :"https://passage-duplicate-spearhead.ngrok-free.dev/webhook"
	type :POST
	body:payload
	headers:{"Content-Type":"application/json"}
	detailed:true
];
info "Webhook response: " + response;
info "Attachment count: " + attachmentsOut.size();
```

After Save: stay on **Invoice Review**, send mail with only the JSON file attached (body can be “please process”). Bridge should log non-empty attachments; UI auto-selects the run.

---

## Script A — body paste only (fallback)

Use if attach download fails. Paste pack JSON into the email **body**.

```javascript
messageDetails = zoho.mail.getMessage(mail_messageId,"zoho");
fromAddress = messageDetails.get("FROM");
toAddress = messageDetails.get("TO");
subject = messageDetails.get("SUBJECT");
content = messageDetails.get("CONTENT");

payload = Map();
payload.put("messageId",mail_messageId);
payload.put("from",fromAddress);
payload.put("to",toAddress);
payload.put("subject",subject);
payload.put("content",content);
payload.put("attachments",List());

response = invokeurl
[
	url :"https://passage-duplicate-spearhead.ngrok-free.dev/webhook"
	type :POST
	body:payload
	headers:{"Content-Type":"application/json"}
	detailed:true
];
info "Webhook response: " + response;
```

---

## Ops checklist

1. `~/Desktop/webhook` + `ngrok http 8080`  
2. Deluge URL matches current ngrok `…/webhook`  
3. http://127.0.0.1:8080/health · http://127.0.0.1:8000/api/v1/webhooks/zoho-mail/health  
4. Bridge log: `Attachments: N` with N > 0 for file attach  
5. If attach empty: re-auth `"zoho"` connection scopes; check Deluge `info` for NEWATT / Attachment fetch skipped
