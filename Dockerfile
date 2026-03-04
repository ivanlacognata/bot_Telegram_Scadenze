#Usa un'immagine Python ufficiale
FROM python:3.11-slim

#Imposta la directory di lavoro
WORKDIR /app

#Copia requirements
COPY requirements.txt .

#Installa le dipendenze
RUN pip install --no-cache-dir -r requirements.txt

#Copia tutto il progetto
COPY . .

#Comando di avvio
CMD ["python", "-u", "src/main.py"]