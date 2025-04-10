from flask import Flask, render_template, request, jsonify
from tinydb import TinyDB, Query
import pygame
import threading
import time
import qrcode
import socket
import os
import atexit

app = Flask(__name__)
# inicializacija baz
baza_pesmi = TinyDB('vse_glasbe.json')
cakalna_vrsta_baza = TinyDB('cakalna_vrsta.json')
trenutna_pesem_baza = TinyDB('trenutna_pesem.json')
vnosi_pesmi = TinyDB('vnos_pesmi.json')


# napolni bazo, ko se prorgram začne
if not trenutna_pesem_baza.all():
    trenutna_pesem_baza.insert({"id": 0, "naslov": "Ni trenutne pesmi", "avtor": "", "datoteka": ""})

# napolni 10x, da bo tabela vedno imela 10 vrstic
if len(cakalna_vrsta_baza.all()) < 11:
    for x in range(5 - len(cakalna_vrsta_baza.all())):
        cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": ""})


# inicializacija pygame mixerja za predvajanje zvoka
pygame.mixer.init()  

@app.route("/")
def zacetna_stran():
    # generiranje QR kode z lokalnim IP-jem in prikaz tabele z čakalno vrsto ter trenutno pesmijo 
    static_mapa = os.path.join(os.path.dirname(__file__), 'static')
    qr_pot = os.path.join(static_mapa, 'qr_slika.png')
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    url = f'http://{local_ip}:5000/pesmi'
    qr = qrcode.make(url)
    qr.save(qr_pot)
    cakalna_vrsta = cakalna_vrsta_baza.all()
    trenutna = trenutna_pesem_baza.all()
    trenutna_pesem = trenutna[0]['naslov']
    return render_template("index.html", slika="qr_slika.png", cakalna_vrsta=cakalna_vrsta, trenutna_pesem=trenutna_pesem)

@app.route("/pesmi")
def pesmi():
    # pošlje bazo vseh pesmi za predvajanje
    pesmi = sorted(baza_pesmi.all(), key=lambda x: x['naslov'].lower())
    return render_template("pesmi.html", pesmi=pesmi)

@app.route("/v_cakalno_vrsto", methods=["POST"])
def shrani():
    # pridobi pesem iz baze in jo zamenja z "Ni izbrane pesmi" v čakalni vrsti
    pesem = Query()
    data = request.get_json()
    pesem_id = int(data['id'])
    izbrana_pesem = baza_pesmi.get(pesem.id == pesem_id)
    if izbrana_pesem:
        dodana_pesem = {
            "id": izbrana_pesem["id"],
            "naslov": izbrana_pesem["naslov"],
            "avtor": izbrana_pesem["avtor"],
            "datoteka": izbrana_pesem["datoteka"]
        }
        cakalna_vrsta = cakalna_vrsta_baza.search(pesem.naslov == "Ni izbrane pesmi")
        if cakalna_vrsta:
            cakalna_vrsta_baza.update(dodana_pesem, doc_ids=[cakalna_vrsta[0].doc_id])
        else:
            return jsonify({"error": "Čakalna vrsta je polna"}), 400
        # za predvajanje naslednje pesmi ko se trenutna konča
        if not pygame.mixer.music.get_busy():
            threading.Thread(target=predvajaj_naslednjo).start() # thread je potreben, da se pesem predvaja v ozadju, AI
        return jsonify({"message": f"Pesem '{izbrana_pesem['naslov']}' dodana v čakalno vrsto."})
    return jsonify({"error": "Pesem ni najdena"}), 404

def predvajaj_naslednjo():
    
    while True:
        cakalna_vrsta = cakalna_vrsta_baza.all()
        if not cakalna_vrsta:
            break
        # po vsakem koncu pesmi se napolni tabelo z "Ni izbrane pesmi" da bo vedno 10 vrstic
        if len(cakalna_vrsta_baza.all()) < 11:
            for x in range(6 - len(cakalna_vrsta_baza.all())):
                cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": ""})
        # pot do datoteke pesmi
        pesem = cakalna_vrsta[0]
        relativna_pot = pesem["datoteka"]
        absolutna_pot = os.path.join(app.root_path, 'static', relativna_pot)
        #doda izbrano pesem v trenutno pesem bazo in izbriše prejšnjo
        pygame.mixer.music.load(absolutna_pot)
        trenutna_pesem_baza.truncate()  
        trenutna_pesem_baza.insert({
            "id": pesem["id"],
            "naslov": pesem["naslov"],
            "avtor": pesem["avtor"],
            "datoteka": pesem["datoteka"]
        })
        # predvaja pesem in jo odstrani iz čakalne vrste
        pygame.mixer.music.play()
        cakalna_vrsta_baza.remove(doc_ids=[pesem.doc_id]) 

        while pygame.mixer.music.get_busy():
            time.sleep(1)
        # po končani pesmi se izpiše "Ni trenutne pesmi" v tabeli
        if not pygame.mixer.music.get_busy():
            trenutna_pesem_baza.truncate()
            trenutna_pesem_baza.insert({"id": 0, "naslov": "Ni trenutne pesmi", "avtor": "", "datoteka": ""})

@app.route("/zabelezeno")
def zabelezeno():
    # za prikaz strani potem, ko uporabnik izbere pesem
    return render_template("zabelezeno.html")


@app.route("/dodaj_pesem", methods=["POST"])
def dodaj_pesem():
    pesem = request.form['pesem']
    vnosi_pesmi.insert({"pesem": pesem})
    return render_template("zabelezeno.html")

@app.route("/prepozno")
def prepozno():
    return render_template("prepozno.html")

def izprazni_bazo():
    # za izbrisanje baz ko se program ugasne
    cakalna_vrsta_baza.truncate()
    trenutna_pesem_baza.truncate()
    vnosi_pesmi.truncate()
# izvede izprazni_bazo() ko se program ugasne
atexit.register(izprazni_bazo)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)