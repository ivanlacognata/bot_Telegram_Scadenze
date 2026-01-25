print("1) test_sheet.py partito")

import googleSheetRead as gs
print("2) import googleSheetRead OK")

data, sheet = gs.export_data()
print("3) export_data() tornata")
print("data =", data)
print("sheet =", sheet)
