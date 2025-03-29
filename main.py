from flask import Flask, request, jsonify, render_template
import qrcode
import io
import base64
import json
import pygame
import time
import threading

app = Flask(__name__)

pygame.mixer.init() #inicializiraj pygame mixerja za predvajanje zvoka

@app.route("/")
def qr():
    # Generiranje QR kode
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data("http://127.0.0.1:5000/pesem")  # Dodaj URL v QR kodo
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")  # Ustvari sliko QR kode
    img_buffer = io.BytesIO()  # Pomnilnik za sliko
    img.save(img_buffer, format="PNG")  # Shrani sliko v pomnilnik
    img_niz = base64.b64encode(img_buffer.getvalue()).decode("utf-8")  # Prekodi v base64 za HTML

    # Preberi čakalno vrsto iz datoteke
    with open("cakalna_vrsta.json", "r") as datoteka:
        vsebina = datoteka.read().strip()
        if vsebina:
            cakalna_vrsta = json.loads(vsebina)
        else:
            cakalna_vrsta = []

    # Renderiranje začetne strani z QR kodo in čakalno vrsto
    return render_template('index.html', qr_code=img_niz, cakalna_vrsta=cakalna_vrsta)


@app.route("/pesem")
def prikazi_pesmi():
    with open("vse_pesmi.json", "r") as datoteka:
        pesmi = json.load(datoteka) # Prebere vse pesmi iz JSON datoteke
    return render_template("pesem.html", pesmi=pesmi)

@app.route("/predvajaj/<int:pesem_id>", methods=['POST']) 
def predvajaj_pesmi(pesem_id):
    with open("vse_pesmi.json", "r", encoding="utf-8") as datoteka:
        vse_pesmi = json.load(datoteka) # Prebere vse pesmi iz baze vseh pesmi

    with open('cakalna_vrsta.json', 'r', encoding='utf-8') as cilj_datoteka:
        vsebina = cilj_datoteka.read().strip() # prebere vsebino datoteke iz baze cakalne vrste 
        if vsebina:
            cakalna_vrsta = json.loads(vsebina) # pretvori v JSON
        else:
            cakalna_vrsta = [] # če je prazna naredi seznam

    izbrana_pesem = None
    for pesem in vse_pesmi:
        if pesem["id"] == pesem_id:
            izbrana_pesem = pesem # gre skozi vse pesmi in izbere tisto ki ima enak id kot izbrana pesem
            break  

    if izbrana_pesem:
        cakalna_vrsta.append(izbrana_pesem) # doda izbrano pesem v čakalno vrsto

    
    with open("cakalna_vrsta.json", "w", encoding="utf-8") as datoteka:
        json.dump(cakalna_vrsta, datoteka, indent=4, ensure_ascii=False) # Shrani posodobljeno čakalno vrsto, ascii je zato da shrani tudi šumnike

    
    if not pygame.mixer.music.get_busy(): # če se nič ne predvaja
        threading.Thread(target=predvajaj_naslednjo).start() # Začni predvajati naslednjo pesem v čakalni vrsti, thread je potreben, da se ne blokira Flask server, AI

    return jsonify({"message": f"Pesem '{izbrana_pesem['naslov']}' dodana v čakalno vrsto."})

def predvajaj_naslednjo():
    while True:
        with open("cakalna_vrsta.json", "r", encoding="utf-8") as datoteka:
            vsebina = datoteka.read().strip()
            if vsebina:
                cakalna_vrsta = json.loads(vsebina)
            else:
                cakalna_vrsta = []

        if not cakalna_vrsta:
            return jsonify({"message": "Čakalna vrsta je prazna."})

        
        pesem = cakalna_vrsta[0] # pesem je prva iz čakalne vrste
        
        
        cakalna_vrsta.pop(0) # Odstrani to pesem iz čakalne vrste
        with open("cakalna_vrsta.json", "w", encoding="utf-8") as datoteka:
            json.dump(cakalna_vrsta, datoteka, indent=4, ensure_ascii=False) # Shrani posodobljeno čakalno vrsto

        
        pygame.mixer.music.load(pesem["datoteka"]) # naloži pesem iz baze pesmi v čakalni vrsti
        pygame.mixer.music.play() # Predvaja to pesem

        # Čakaj na konec pesmi
        while pygame.mixer.music.get_busy(): # get_busy preveri ali se pesem predvaja
            time.sleep(1)  # počaka sekundo in ponovno preveri

        # pesem je končana, počaka sekundo pred predvajanjem naslednje pesmi
        time.sleep(1)
        pygame.mixer.music.stop()  # Prepreči morebitne napake pri ponovnem predvajanju

        
        if len(cakalna_vrsta) > 0: # Preveri, če je v čakalni vrsti še kaj pesmi in nato zažene funkcijo za predvajanje naslednje pesmi
            predvajaj_naslednjo()

@app.route("/hvala")
def hvala():
    return render_template("hvala.html")


if __name__ == "__main__":
    app.run(debug=True)
