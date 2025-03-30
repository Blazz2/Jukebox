from flask import Flask, request, jsonify, render_template
import qrcode
import io # delo z vzhodno-izhodnimi podatki v pomnilniku
import base64 # za kodiranje binarnih podatkov (slik) v base64 format za HTML
from tinydb import TinyDB, Query
import pygame # za predvajanje zvoka
import time 
import threading # za izvajanje več nalog hkrati
import os

app = Flask(__name__)

pygame.mixer.init() # inicializacija pygame mixerja za predvajanje zvoka

# inicializacija tinydb baz
baza_pesmi = TinyDB('vse_pesmi.json')  # baza za vse pesmi
cakalna_vrsta_baza = TinyDB('cakalna_vrsta.json')  # baza za čakalno vrsto


@app.route("/")
def qr():
    # generiranje qr kode
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data("http://192.168.0.23:5000/pesem")  # dodaj url v qr kodo
    qr.make(fit=True) # za prilagajanje qr kode
    img = qr.make_image(fill_color="black", back_color="white")  # ustvari sliko qr kode
    img_buffer = io.BytesIO()  # pomnilnik za sliko
    img.save(img_buffer, format="PNG")  # shrani sliko v pomnilnik
    img_niz = base64.b64encode(img_buffer.getvalue()).decode("utf-8")  # spremeni v base64 za html

    
    cakalna_vrsta = cakalna_vrsta_baza.all()  # pridobi vse pesmi iz čakalne vrste

    
    return render_template('index.html', qr_code=img_niz, cakalna_vrsta=cakalna_vrsta)

@app.route("/pesem")
def prikazi_pesmi():
    pesmi = baza_pesmi.all()  # prebere vse pesmi iz baze vseh pesmi
    return render_template("pesem.html", pesmi=pesmi)

@app.route("/predvajaj/<int:pesem_id>", methods=['POST']) 
def predvajaj_pesmi(pesem_id):
    pesem = Query() # Query objekt za iskanje pesmi
    izbrana_pesem = baza_pesmi.get(pesem.id == pesem_id)  # gre skozi vse pesmi in izbere tisto, ki ima enak id kot izbrana pesem

    if izbrana_pesem:
        # naredi podatke za pesem, ki jo je uporabnik izbral
        nova_pesem = {
            "id": izbrana_pesem["id"],
            "naslov": izbrana_pesem["naslov"],
            "avtor": izbrana_pesem["avtor"],
            "datoteka": izbrana_pesem["datoteka"]
        }
        cakalna_vrsta_baza.insert(nova_pesem)  # doda izbrano pesem v čakalno vrsto
        
        if not pygame.mixer.music.get_busy():  # če se nič ne predvaja
            threading.Thread(target=predvajaj_naslednjo).start()  # začni predvajati naslednjo pesem v čakalni vrsti, thread je potreben, da se ne blokira flask server, AI

        return jsonify({"message": f"pesem '{izbrana_pesem['naslov']}' dodana v čakalno vrsto."})
    
    return jsonify({"error": "pesem ni najdena"}), 404

def predvajaj_naslednjo():
    while True:
        cakalna_vrsta = cakalna_vrsta_baza.all()  # prebere vsebino iz baze čakalne vrste
        
        if not cakalna_vrsta:  # če je prazna
            return jsonify({"message": "čakalna vrsta je prazna."})

        pesem = cakalna_vrsta[0]  # pesem je prva iz čakalne vrste
        
        

        cakalna_vrsta_baza.remove(doc_ids=[cakalna_vrsta[0].doc_id]) # odstrani to pesem iz čakalne vrste
        
        pygame.mixer.music.load(pesem["datoteka"])  # naloži pesem iz baze pesmi v čakalni vrsti
        pygame.mixer.music.play()  # predvaja to pesem


        while pygame.mixer.music.get_busy():  # get_busy preveri ali se pesem predvaja
            time.sleep(1)  # počaka sekundo in ponovno preveri

        
        time.sleep(1) # počaka sekundo pred predvajanjem naslednje pesmi
        pygame.mixer.music.stop()  # prepreči morebitne napake pri ponovnem predvajanju


        if cakalna_vrsta_baza.all():  # če je v čakalni vrsti še kaj pesmi, nadaljuje z naslednjo
            continue
        else:
            break

@app.route("/hvala")
def hvala():
    return render_template("hvala.html")

if __name__ == "__main__":
    # omogoči dostop iz vseh ip-jev za lokalno omrežje
    app.run(host='0.0.0.0', port=5000, debug=True)