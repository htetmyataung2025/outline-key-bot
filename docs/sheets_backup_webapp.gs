// H&E VPN — Google Sheets backup receiver (bot update #9).
// Standalone project (script.google.com) — writes into the backup
// spreadsheet by ID, so it does not need to be bound to the sheet.
//
// Setup (owner, one time):
//   1. script.google.com → New project → replace ALL code with this.
//   2. Deploy → New deployment → type "Web app" → Execute as: Me →
//      Who has access: Anyone → Deploy → authorize with your account.
//   3. Copy the Web app URL into the Vercel env var
//      GOOGLE_SHEETS_BACKUP_SCRIPT_URL and redeploy. The SECRET below
//      must match the Vercel env var GOOGLE_SHEETS_BACKUP_SCRIPT_SECRET.
//   If the code is ever edited: Deploy → Manage deployments → edit →
//   Version: "New version" → Deploy (the URL stays the same).
//
// The bot POSTs {secret, tabs: [{title, rows}]}; this script creates any
// missing tab, clears it, and rewrites it from the payload.

const SECRET = "CHANGE_ME"; // must match the Vercel env GOOGLE_SHEETS_BACKUP_SCRIPT_SECRET — never commit the real value
const SHEET_ID = "1pxGSdXA522uMYRAixiXjNCUmIT4QRD9S4Qafzxzob9M";

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.secret !== SECRET) {
      return _json({ ok: false, error: "bad_secret" });
    }
    const ss = SpreadsheetApp.openById(SHEET_ID);
    const wanted = {};
    (body.tabs || []).forEach(function (tab) { wanted[tab.title] = true; });

    const counts = {};
    (body.tabs || []).forEach(function (tab) {
      let sheet = ss.getSheetByName(tab.title);
      if (!sheet) sheet = ss.insertSheet(tab.title);
      sheet.clearContents();
      const rows = tab.rows || [];
      if (rows.length) {
        let width = 0;
        rows.forEach(function (r) { width = Math.max(width, r.length); });
        const grid = rows.map(function (r) {
          const copy = r.slice();
          while (copy.length < width) copy.push("");
          return copy;
        });
        const CHUNK = 1000;
        for (let i = 0; i < grid.length; i += CHUNK) {
          const part = grid.slice(i, i + CHUNK);
          sheet.getRange(i + 1, 1, part.length, width).setValues(part);
        }
      }
      counts[tab.title] = Math.max(0, rows.length - 1);
    });

    // Drop the untouched default tab so the workbook stays clean.
    // Done LAST: a spreadsheet must always keep at least one sheet.
    const starter = ss.getSheetByName("Sheet1");
    if (starter && !wanted["Sheet1"] && ss.getSheets().length > 1 &&
        starter.getDataRange().isBlank()) {
      ss.deleteSheet(starter);
    }
    return _json({ ok: true, counts: counts });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
