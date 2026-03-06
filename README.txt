===== 🤖 Bot Scadenze JEToP =====

Bot Telegram per il monitoraggio automatico delle scadenze dei servizi nei Gantt ufficiali JEToP.

Il bot legge:
 Un foglio di configurazione centrale (Google Sheets)
 - I Gantt ufficiali dei progetti
 - I topic (forum) dei gruppi Telegram
E invia automaticamente promemoria di scadenza nelle aree corrette.

|🎯 Obiettivo del progetto |

Automatizzare l'invio di promemoria delle scadenze:
 Per progetto -> per area (IT, Marketing, Sales, ecc.) -> nei topic Telegram corrispondenti
 Con logica personalizzabile dei giorni di avviso

============================
🏗 Architettura del sistema
============================

Google Workspace (JEToP)
│
├── Foglio CONFIG
│       ├── Nome progetto
│       ├── ChatId gruppo Telegram
│       ├── Giorni_avviso
│       └── Link Gantt
│
├── Gantt ufficiali
│       ├── Aree
│       ├── Servizi
│       ├── Durata
│       └── Scadenza
│
└── Service Account (Domain Wide Delegation)
        └── Impersonificazione utente JEToP

↓

📂 Struttura del progetto
bot-scadenze/
│
├── main.py
├── googleSheetRead.py
├── gantt_reader.py
├── topic_registry.py
├── topic_map.json
├── service_account_official.json (NON versionato)
│
├── test/ (facoltativa)
│
├── requirements.txt
└── README.md

====================================
🔎 Descrizione dei file principali
====================================

|🧠 main.py |

È il cuore del bot.

Responsabilità:
 Avvia il bot Telegram
 Schedula il job giornaliero
 Legge configurazione
 Legge i Gantt
 Calcola giorni rimanenti
 Decide se inviare messaggi
 Invia nei topic corretti
 Auto-registra e aggiorna topic

|📄 googleSheetRead.py |

Gestisce:
 Autenticazione Google API
 Domain-Wide Delegation
 Lettura del foglio CONFIG
 Parsing delle colonne
Ritorna:
 Lista progetti + service API

|📊 gantt_reader.py |

Legge ogni Gantt e ritorna:
 (area, nome_servizio, durata_giorni, data_scadenza)
Gestisce:
 Parsing date seriali Google
 Parsing date stringa (dd/mm, dd/mm/yyyy)
 Interpretazione prossima occorrenza
 Riconoscimento righe AREA
 Ignora righe sporche

|🧵 topic_registry.py |

Salva in topic_map.json la mappatura:
 chat_id → area → thread_id
Supporta:
 Creazione automatica topic
 Rinomina topic
 Scrittura atomica (anti-corruzione file)

==============================
📅 Logica di invio notifiche
==============================

Per ogni servizio:
 Calcolo:
 days_left = deadline - today
 Invio se:
 days_left ∈ thresholds
 Dove thresholds include:
 - metà durata
 - giorno prima (1)
 - giorno stesso (0)
 - giorno dopo (-1)
 - giorni personalizzati dal foglio config -> per inserire giorni personalizzati, 
   scrivere numeri separati da virgole

Esempio:
Giorni_avviso = 7,5,4
Il bot invierà a:
7 giorni prima
5 giorni prima
4 giorni prima
metà durata
1 giorno prima
giorno stesso
giorno dopo

Duplicati nello stesso giorno → NON inviati (uso set).

===========================
🧵 Topic Telegram (Forum)
===========================

Il bot supporta gruppi con topic.

Funzionamento:
 Quando viene creato un topic → auto-registrato
 Quando viene rinominato → aggiornato nel JSON
 Se area non mappata → messaggio nel generale

Il bot deve avere:
 - Permesso di leggere messaggi
 - Permesso di leggere eventi di servizio
 - Essere amministratore (consigliato)

Il bot deve far parte del gruppo per funzionare.

Il bot può inviare i messaggi in due modalità, in base al valore della cella
"Topic_Destinazione" dell'excel:

////Topic_Destinazione non vuoto////
 Tutti i messaggi verranno inviati nel topic il cui nome corrisponde a quello
 inserito nella cella, indipendentemente dal nome dell'area (messaggio unico in un solo topic).

 Se il topic con quel nome non esiste, i messaggi verranno inviati in General.

////Topic_Destinazione vuoto////
 Comportamento di default: il bot legge il nome dell'area dal Gantt e manda gli
 avvisi dei relativi servizi nel topic con lo stesso nome (messaggi separati per topic).

 ↓⚠️IMPORTANTE⚠️↓
 Il nome del topic del gruppo deve essere uguale al nome dell'area nel gantt di riferimento

/////Esempio (con Topic_Destinazione vuoto)/////
Gantt progetto → 
||IT||
programmare una pagina 
||M&C||
Creare contenuti social
||Sales||
Gestire contratti
||Catering||
Prenotare cannoli [meglio se ricotta]

Topic gruppo telegram →
General
IT
M&C
Sales&Partnership

Messaggi inviati:
IT → programmare una pagina 
M&C → Creare contenuti social
General → Gestire contratti ("Sales" è diverso da "Sales&Partnership"! -> messaggio in General)
General → Prenotare cannoli [meglio se ricotta] (Non esiste un topic chiamato "Catering"! -> messaggio in General)
///////////////////

==================================================
🔐 Configurazione Google (Domain Wide Delegation)
==================================================

Necessario:
 Creare progetto su Google Cloud
Abilitare:
 Google Sheets API
 Google Drive API
 Creare Service Account
 Abilitare Domain-Wide Delegation
 Autorizzare in Admin Console con scope:

 https://www.googleapis.com/auth/spreadsheets
 https://www.googleapis.com/auth/drive

Impostare email impersonata in:
 googleSheetRead.py → IMPERSONATED_USER

============================================
💬Ricavare la ChatId da mettere nell'excel
============================================

Telegram può essere poco intuitivo da questo punto di vista, un metodo semplice
per ricavare l'id da mettere in ChatId nell'excel è il seguente:
 - Inviare un messaggio nella chat (o in un topic della chat)
 - Tasto destro sul messaggio → Copia link messaggio

Il link del messaggio ha questo formato:
 https://t.me/c/XXXXXXXXXX/Y/Z
 Dove:
  - XXXXXXXXXX è l'internal chat id
  - Y è l'id del topic
  - Z è l'id del messaggio nel topic (assente se il gruppo non ha topic)

Per ricavare il chatId (unica cosa che serve fornire al bot):
 - Copiare l'internal chat id
 - Aggiungere il prefisso -100

/////Esempio/////

Gruppo TEDx2030 → topic qualsiasi
- Link del messaggio: https://t.me/c/1234567890/5/1
- Chat id = -1001234567890
- Inserire nell'excel alla riga TEDx2030, nella colonna ChatId → -1001234567890

///////////////////

==========================================
📊 Requisiti formato Gantt (obbligatorio)
==========================================

Perché il bot possa leggere correttamente un Gantt, tutti i Gantt devono mantenere 
lo stesso formato (stessa struttura di colonne e celle).
Se il formato cambia (colonne spostate, celle diverse, tab rinominata, ecc.) il bot potrebbe:
 - leggere 0 servizi
 - assegnare aree sbagliate
 - non inviare avvisi anche se le scadenze ci sono

Si è preso come riferimento standard il Gantt Portfolio.

|✅ Tab e colonne richieste |

Il bot legge per default il tab (worksheet) chiamato:
GANTT (valore di default worksheet_title="GANTT" in read_services_deadlines)

Dentro al tab, il bot legge solo queste colonne:
 Colonna B → Nome Area oppure Nome Servizio
 Colonna D → Durata in giorni (numero)
 Colonna E → Scadenza (data)

Nota: la colonna del nome servizio deve essere B. Se viene spostata, 
bisogna aggiornare gantt_reader.py.

|▶️ Da che riga parte a leggere |

Il bot inizia a scorrere il Gantt a partire da:
 start_row = 9 (default)

Quindi legge da:
 B9 fino a E(end_row) dove:
 end_row = start_row + max_rows - 1
 max_rows = 1200 (default)

In altre parole, legge questo range:
 GANTT!B9:E1208 (se max_rows=1200)

Se nel Gantt i dati partono da una riga diversa, bisogna modificare start_row.

|🧠 Come interpreta le righe del Gantt |

Il bot scorre riga per riga e decide se quella riga è:
 (1) Riga vuota
 Se B, D, E sono vuote → la riga viene ignorata.

 (2) Header (“Nome area”)
 Se in colonna B trova testo "Nome area" (case-insensitive) → la riga viene ignorata.

 (3) Riga AREA (titolo sezione)
 Una riga viene considerata un “titolo area” se:
  - B non è vuota (es. IT, M&C, D&V...)
  - D è vuota (durata mancante)
  - E è vuota (scadenza mancante)

  Esempio:

  B	D	E
  -------------------
  IT		
  -------------------

  Quando il bot trova una riga così:
   - aggiorna la variabile current_area = "IT"
   - tutte le righe servizio successive vengono associate a 
     quell’area finché non trova una nuova riga area.

  Se un Gantt non ha una riga area valida, il bot usa come fallback:
  Generale"

 (4) Riga SERVIZIO (task valida)

 Una riga viene considerata un servizio valido se:
  - B ha un nome servizio
  - D contiene un numero (durata giorni)
  - E contiene una data (scadenza)

  Esempio:

        B	                D	  E
  -------------------------------------
  Pagina portfolio	11	25/02
  -------------------------------------

 Per ogni servizio il bot salva:
  - area (current_area)
  - nome servizio (col B)
  - durata giorni (col D)
  - scadenza (col E)

|📅 Formato della scadenza (colonna E) |

La scadenza può essere scritta nel Gantt in vari modi; il bot gestisce automaticamente:
 ✅ Date seriali Google (valori numerici interni)
 ✅ dd/mm/yyyy 
 ✅ dd/mm/yy
 ✅ dd/mm (senza anno)

---------------------
Caso dd/mm senza anno
---------------------

Se manca l’anno (es. 25/02), il bot interpreta la scadenza come prossima occorrenza:
 - prova con 25/02 nell’anno corrente
 - se quella data è già passata → usa l’anno successivo

Questo evita che la scadenza venga letta come “nel passato” quando il foglio mostra solo giorno/mese.

🧩 Nota: la data di inizio (F9)

Il bot legge anche la cella:

F9 (data inizio progetto)

Attualmente viene letta per robustezza/controlli futuri, 
ma la logica di invio avvisi si basa sulla scadenza 
in colonna E e sul calcolo di days_left.

|✅ Checklist “Gantt compatibile” |

Prima di inserire un Gantt nel foglio CONFIG, assicurarsi che:
 - esista un tab chiamato GANTT (o il default venga aggiornato nel codice)
 - i servizi partano da riga 9 (o aggiornare start_row)
 - colonna B = nome area o nome servizio
 - colonna D = durata numerica (giorni)
 - colonna E = scadenza (data)
 - le righe area abbiano SOLO la colonna B valorizzata (D/E vuote)

=================
🚀 Installazione
=================

1️⃣ Clonare repo
 git clone <repo>
 cd bot-scadenze

2️⃣ Creare virtual environment
 python -m venv venv

Attivazione:

Windows:
 venv\Scripts\activate

Mac/Linux:
 source venv/bin/activate

3️⃣ Installare dipendenze
 pip install -r requirements.txt

Se manca job queue:
 pip install "python-telegram-bot[job-queue]"

4️⃣ Inserire credenziali

Mettere nella root:
 service_account_official.json

⚠️ Non committare su GitHub (sono informazioni sensibili)

5️⃣ Avvio bot
 python main.py

Output atteso:
 Scheduler attivo: invio giornaliero alle HH:MM (Europe/Rome)
 ⚙️ Configurazione foglio CONFIG

 Colonne:

 Nome	ChatId	Giorni_avviso	Gantt

 ChatId: ID gruppo Telegram (es: -100XXXXXXXXXX)

 Giorni_avviso:

 7,5,4

 oppure vuoto.

================
🧪 Debug & Test
================

Cartella test/ contiene:
 test_domain.py
 test_sheet.py
 test_gantt.py

Utili per:
 verificare permessi Google
 verificare parsing Gantt
 debug API

=============
🛡 Sicurezza
=============

Non committare:
 service_account_official.json
 topic_map.json
 file credenziali

Inserire in .gitignore

==================
👨‍💻 Riconoscimenti
==================

Progetto sviluppato per JEToP
Autori principali: 
- La Cognata Vincenzo Ivan
- Coero-Borga Agnese 
Manutenzione futura: area IT
Data creazione: Febbraio 2026
Se si assistono a bug o malfunzionamenti, fare presente per avere la possibilità di correggere.