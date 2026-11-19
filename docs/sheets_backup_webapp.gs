// H&E VPN — Google Sheets backup receiver (bot update #9).
//
// Setup (owner, one time):
//   1. Open the backup spreadsheet → Extensions → Apps Script.
//   2. Replace ALL existing code with this file's contents.
//   3. Set SECRET below to the same value as the Vercel env var
//      GOOGLE_SHEETS_BACKUP_SCRIPT_SECRET.
//   4. Deploy → New deployment → type "Web app" → Execute as: Me →
//      Who has access: Anyone → Deploy → authorize with your account.
//   5. Copy the Web app URL into the Vercel env var
//      GOOGLE_SHEETS_BACKUP_SCRIPT_URL and redeploy.
//
// The bot POSTs {secret, tabs: [{title, rows}]}; this script creates any
// missing tab, clears it, and rewrites it from the payload. It only ever
// touches the spreadsheet it is bound to.

const SECRET = "CHANGE_ME";

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.secret !== SECRET) {
      return _json({ ok: false, error: "bad_secret" });
    }
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const wanted = {};
    (body.tabs || []).forEach(function (tab) { wanted[tab.title] = true; });

    // Drop the untouched default tab so the workbook stays clean.
    const starter = ss.getSheetByName("Sheet1");
    if (starter && !wanted["Sheet1"] && starter.getDataRange().isBlank()) {
      ss.deleteSheet(starter);
    }

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
