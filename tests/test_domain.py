from googleSheetRead import export_data


import json
with open("service_account.json", "r", encoding="utf-8") as f:
    j = json.load(f)

data, sheet_api, service = export_data()
