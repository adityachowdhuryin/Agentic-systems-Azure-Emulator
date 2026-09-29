# Zoho Deluge — live invoice (Azure + local)

**Primary demo path:** attach a pack `.json` / `.txt` (e.g. `CASE-09_INV-01417.json`).  
**Fallback:** paste the same JSON into the email body.

Band A prefers attachments, then body. Unrelated live mail still creates an Invoice Review run; Band B returns `exception:not_an_invoice`.

Your Mail IDs (locked):

- `accountId` = `7135116000000008002`
- `folderId` = `7135116000000008014` (inbox)
- Connection = `zoho` — if attach download fails with 401, re-authorize with `ZohoMail.messages.READ` or `ALL`

## Azure (preferred — no ngrok)

Point Deluge straight at banda HTTPS. Header `X-Mail-Bridge-Key` must match the ACA env (`local-mail-bridge-key` unless rotated).

```
https://banda.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/api/v1/webhooks/zoho-mail
```

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
	url :"https://banda.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/api/v1/webhooks/zoho-mail"
	type :POST
	body:payload
	headers:{"Content-Type":"application/json","X-Mail-Bridge-Key":"local-mail-bridge-key"}
	detailed:true
];
info "Webhook response: " + response;
info "Attachment count: " + attachmentsOut.size();
```

After Save: stay on **Invoice Review**, send mail with only the JSON file attached (body can be “please process”). UI auto-selects the run on the Azure dashboard.

---

## Script A — body paste only (fallback)

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
	url :"https://banda.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/api/v1/webhooks/zoho-mail"
	type :POST
	body:payload
	headers:{"Content-Type":"application/json","X-Mail-Bridge-Key":"local-mail-bridge-key"}
	detailed:true
];
info "Webhook response: " + response;
```

---

## Local (optional — ngrok + Desktop bridge)

Only if developing against localhost:

1. `~/Desktop/webhook` + `ngrok http 8080`
2. Deluge URL = `https://<ngrok-host>/webhook` (bridge adds the mail key)
3. http://127.0.0.1:8080/health · http://127.0.0.1:8000/api/v1/webhooks/zoho-mail/health
