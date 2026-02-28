from googleSheetRead import export_data
from gantt_reader import read_services_deadlines

data, sheet_api, service = export_data()
print("Progetti letti:", len(data))

gantt_url = data[0]["Gantt"]
services = read_services_deadlines(service, gantt_url, worksheet_title="GANTT")  # se il tab non è GANTT, cambia qui

print("Servizi letti dal gantt:", len(services))
print("Primi 5:", services[:5])
