===== 🎯 Scopo della cartella =====

Questa cartella contiene script di test utilizzati per verificare il corretto funzionamento delle integrazioni tra:
Google Sheets API (Domain-Wide Delegation)
Accesso ai Gantt ufficiali JEToP
Parsing dei servizi e delle scadenze
Configurazione del foglio di controllo
Questi script sono stati utilizzati durante la fase di sviluppo e debugging iniziale del bot.

⚠️ Non sono necessari per l’esecuzione del bot in produzione.

===============================
📁 Struttura dei file di test
===============================

1️⃣ test_domain.py

|🔎 Scopo |

Verificare che:
 Il Service Account sia configurato correttamente
 La Domain-Wide Delegation funzioni
 L’impersonificazione dell’utente Jetop sia corretta
 Le API Google rispondano correttamente

|🔬 Cosa testa |

Lettura del file JSON del Service Account
Creazione credenziali delegate
Accesso API Sheets
Assenza errore unauthorized_client

|✅ Output atteso |

Se tutto funziona correttamente:
 type: service_account
 client_email: bot-scadenze@...
 has_private_key: True
 DATA:
 [ ... ]

2️⃣ test_sheet.py

|🔎 Scopo |

Verificare la lettura del foglio di configurazione principale.

|🔬 Cosa testa |

Accesso al file CONFIG_SPREADSHEET_ID
Lettura range Foglio1!A2:D
Parsing delle colonne:

 Nome

 ChatId

 Giorni_avviso

 Gantt

|✅ Output atteso |

Numero corretto di righe lette dal file di configurazione.

Esempio:

Progetti letti: 3

3️⃣ test_gantt.py

|🔎 Scopo |

Verificare che il bot riesca a:
 Accedere a un Gantt ufficiale
 Leggere le righe corrette
 Interpretare correttamente:

 Area

 Nome servizio

 Durata

 Scadenza

|🔬 Cosa testa |

Estrazione dello spreadsheetId dal link

Lettura range GANTT!B9:E...

Parsing delle date

Parsing delle durate

Gestione righe “sporche”

|✅ Output atteso |
Servizi letti dal gantt: X
Primi 5: [...]

=============================
🧪 Quando usare questi test 
=============================

Utilizzare questi script nei seguenti casi:

 Nuovo Service Account
 Cambio dominio Google Workspace
 Modifica permessi API
 Errore unauthorized_client
 Errore 400 Google Sheets
 Gantt che improvvisamente non viene letto
 Migrazione del bot su nuovo server

=========================
🚀 Come eseguire i test 
=========================

Assicurarsi di:
 Attivare il virtual environment:
 source venv/bin/activate     # Linux / Mac
 venv\Scripts\activate        # Windows
 Eseguire lo script desiderato:
 python test_domain.py
 python test_sheet.py
 python test_gantt.py