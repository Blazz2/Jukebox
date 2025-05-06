from flask import Flask, render_template, request, jsonify, session
from tinydb import TinyDB, Query
import pygame
import threading
import time
import qrcode
import socket
import os
import atexit
from datetime import datetime, timedelta
import random
import string
from flask_session import Session
import xml.etree.ElementTree as ET
from xml.dom import minidom

app = Flask(__name__)

# nastavitev seje
app.config['SECRET_KEY'] = "skrivni ključ" 
app.config['SESSION_TYPE'] = 'filesystem'

# inicializacija seje
Session(app)

# inicializacija baz za shranjevanje
baza_pesmi = TinyDB('vse_pesmi.json')
baza_privzetih_pesmi = TinyDB('privzete_glasbe.json')
cakalna_vrsta_baza = TinyDB('cakalna_vrsta.json')
trenutna_pesem_baza = TinyDB('trenutna_pesem.json')
vnosi_pesmi = TinyDB('vnos_pesmi.json')
baza_kod = TinyDB('baza_kod.json')

# pot do mape muske
muske_mapa = os.path.join(app.root_path, 'static', 'muske')

# posodobi bazo vseh pesmi ob zagonu
if os.path.exists(muske_mapa):
    # pridobi seznam datotek v mapi in rezultate shrani v množico (set)
    trenutne_datoteke = {datoteka for datoteka in os.listdir(muske_mapa) if datoteka.endswith('.mp3')}
    # pridobi seznam datotek v bazi brez poti do datoteke
    datoteke_v_bazi = {os.path.basename(pesem['datoteka']) for pesem in baza_pesmi.all()}
    
    # odstrani pesmi, ki niso več v mapi
    for pesem in baza_pesmi.all():
        if os.path.basename(pesem['datoteka']) not in trenutne_datoteke:
            baza_pesmi.remove(doc_ids=[pesem.doc_id])
    
    # pridobi največji obstoječi ID v bazi
    max_id = max([pesem['id'] for pesem in baza_pesmi.all()], default=0)
    
    # doda nove pesmi, ki jih še ni v bazi
    for datoteka in trenutne_datoteke:
        if datoteka not in datoteke_v_bazi:
            # razdeli ime datoteke na avtorja in naslov
            ime_brez_koncnice = os.path.splitext(datoteka)[0]
            avtor = "Neznan"
            naslov = ime_brez_koncnice
            
            # preveri, če ime datoteke vsebuje ločilo " - "
            if " - " in ime_brez_koncnice:
                deli = ime_brez_koncnice.split(" - ", 1)
                avtor = deli[0].strip()
                naslov = deli[1].strip()
            
            max_id += 1
            baza_pesmi.insert({
                "id": max_id,
                "naslov": naslov,
                "avtor": avtor,
                "datoteka": os.path.join('muske', datoteka)
            })

# posodobi bazo privzetih pesmi ob zagonu
privzete_pesmi_mapa = os.path.join(app.root_path, 'static', 'privzete_pesmi')
if os.path.exists(privzete_pesmi_mapa):
    # pridobi seznam datotek v mapi
    trenutne_privzete = {datoteka for datoteka in os.listdir(privzete_pesmi_mapa) if datoteka.endswith('.mp3')}
    # pridobi seznam datotek v bazi
    privzete_v_bazi = {os.path.basename(pesem['datoteka']) for pesem in baza_privzetih_pesmi.all()}
    
    # odstrani pesmi, ki niso več v mapi
    for pesem in baza_privzetih_pesmi.all():
        if os.path.basename(pesem['datoteka']) not in trenutne_privzete:
            baza_privzetih_pesmi.remove(doc_ids=[pesem.doc_id])
    
    # pridobi največji obstoječi ID v bazi privzetih pesmi
    max_privzeti_id = max([pesem['id'] for pesem in baza_privzetih_pesmi.all()], default=0)
    
    # dodaj nove pesmi, ki jih še ni v bazi
    for datoteka in trenutne_privzete:
        if datoteka not in privzete_v_bazi:
            # razdeli ime datoteke na avtorja in naslov
            ime_brez_koncnice = os.path.splitext(datoteka)[0]
            avtor = "Neznan"
            naslov = ime_brez_koncnice
            
            # preveri, če ime datoteke vsebuje ločilo " - "
            if " - " in ime_brez_koncnice:
                deli = ime_brez_koncnice.split(" - ", 1)
                avtor = deli[0].strip()
                naslov = deli[1].strip()
            
            max_privzeti_id += 1
            baza_privzetih_pesmi.insert({
                "id": max_privzeti_id,
                "naslov": naslov,
                "avtor": avtor,
                "datoteka": os.path.join('privzete_pesmi', datoteka)
            })

# napolni bazo, ko se program začne
if not trenutna_pesem_baza.all():
    trenutna_pesem_baza.insert({"id": 0, "naslov": "Ni trenutne pesmi", "avtor": "", "datoteka": ""})

# napolni 6x, da bo tabela vedno imela 6 vrstic
cakalna_vrsta_baza.truncate()
for _ in range(6):
    cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": ""})

def generiraj_kodo():
    # generira naključno 4 mestno kodo
    return ''.join(random.choices(string.digits, k=3))

# inicializacija pygame mixerja za predvajanje zvoka
pygame.mixer.init()

# funkcija za zapis v XML datoteko
def zapis_v_xml(pesem, datum):
    xml_datoteka = 'predvajane_pesmi.xml'
    
    # če datoteka že obstaja, jo naloži, sicer ustvari novo strukturo
    if os.path.exists(xml_datoteka):
        tree = ET.parse(xml_datoteka)
        root = tree.getroot()
    else:
        root = ET.Element("predvajane_pesmi")
    
    # ustvari nov vnos za pesem
    vnos = ET.SubElement(root, "pesem")
    ET.SubElement(vnos, "datum").text = datum
    ET.SubElement(vnos, "avtor").text = pesem['avtor']
    ET.SubElement(vnos, "naslov").text = pesem['naslov']
    
    # zapiše XML datoteko z lepim formatiranjem
    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="    ")
    with open(xml_datoteka, "w", encoding="utf-8") as f:
        f.write(xmlstr)

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

    # preveri ali obstaja veljavna koda
    kode = Query()
    trenuten_cas = datetime.now()
    veljavna_koda = baza_kod.get(kode.iztekla > trenuten_cas.isoformat())
    if not veljavna_koda:
        # generira novo kodo in jo shrani v bazo
        nova_koda = generiraj_kodo()
        iztekla = trenuten_cas + timedelta(minutes=3)
        baza_kod.truncate()
        baza_kod.insert({"koda": nova_koda, "iztekla": iztekla.isoformat()})
        koda = nova_koda
    else:
        koda = veljavna_koda['koda']

    cakalna_vrsta = cakalna_vrsta_baza.all()
    trenutna = trenutna_pesem_baza.all()
    trenutna_pesem = trenutna[0]['naslov']
    
    # naključna izbira pesmi iz privzetih pesmi ob zagonu, če ni izbrane
    if trenutna_pesem == "Ni trenutne pesmi" and baza_privzetih_pesmi.all():
        nakljucna_pesem = random.choice(baza_privzetih_pesmi.all())
        cakalna_vrsta_baza.update({
            "id": nakljucna_pesem["id"],
            "naslov": nakljucna_pesem["naslov"],
            "avtor": nakljucna_pesem["avtor"],
            "datoteka": nakljucna_pesem["datoteka"]
        }, doc_ids=[cakalna_vrsta[0].doc_id])
        threading.Thread(target=predvajaj_naslednjo).start()

    return render_template("index.html", slika="qr_slika.png", cakalna_vrsta=cakalna_vrsta, trenutna_pesem=trenutna_pesem, koda=koda)

@app.route("/pesmi", methods=["GET", "POST"])
def pesmi():
    # uporabnik vnese kodo
    if request.method == "POST":
        uporabniska_koda = request.form['koda']
        kode = Query()
        trenutni_cas = datetime.now()
        pravilna_koda = baza_kod.get((kode.koda == uporabniska_koda) & (kode.iztekla > trenutni_cas.isoformat()))

        if not pravilna_koda:
            return render_template("pesmi.html", napaka="Koda je napačna ali je potekla.", pesmi=[], prikazi_vnos_kode=True)
        
        # shrani kodo skupaj s časom, če je veljavna 
        session['uporabniska_koda'] = uporabniska_koda
        session['cas_kode'] = trenutni_cas.isoformat()
        # pošlje bazo vseh pesmi za predvajanje
        pesmi = sorted(baza_pesmi.all(), key=lambda x: x['naslov'].lower())
        return render_template("pesmi.html", pesmi=pesmi, prikazi_vnos_kode=False)
    # GET zahteva prikazuje formo za vnos kode
    return render_template("pesmi.html", pesmi=[], prikazi_vnos_kode=True)

@app.route("/v_cakalno_vrsto", methods=["POST"])
def shrani():
    # pridobi pesem iz baze in jo zamenja z "Ni izbrane pesmi" v čakalni vrsti
    pesem = Query()
    data = request.get_json()
    pesem_id = int(data['id'])
    uporabniska_koda = data.get('koda')

    # preveri ali je koda še veljavna (3 minute od vnosa) 
    cas_kode = session.get('cas_kode')
    if not cas_kode or not uporabniska_koda:
        return jsonify({"error": "Koda je napačna ali je potekla."}), 400

    try:
        cas_kode = datetime.fromisoformat(cas_kode)
        trenutni_cas = datetime.now()
        if trenutni_cas > cas_kode + timedelta(minutes=3):
            return jsonify({"error": "Koda je potekla (3 minute). Počakaj na novo kodo"}), 400
    except ValueError:
        return jsonify({"error": "Neveljaven čas seje."}), 400
    
    # preveri ali je uporabnik že dodal pesem z to kodo
    uporabljene_kode = session.get('uporabljene_kode', [])
    if uporabniska_koda in uporabniska_koda in uporabljene_kode:
        return jsonify({"error": "S to kodo si že izbral pesem. Počakaj na novo kodo"}), 429

    # doda pesem v čakalno vrsto
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
            # preveri ali je uporabnik že uporabil kodo
            uporabljene_kode.append(uporabniska_koda)
            session['uporabljene_kode'] = uporabljene_kode
            # počisti sejo za naslednjo kodo
            session.pop('uporabniska_koda', None)
            session.pop('cas_kode', None)
            # za predvajanje naslednje pesmi ko se trenutna konča
            if not pygame.mixer.music.get_busy():
                threading.Thread(target=predvajaj_naslednjo).start()
            return jsonify({"message": f"Pesem '{izbrana_pesem['naslov']}' dodana v čakalno vrsto."})
        else:
            return jsonify({"error": "Čakalna vrsta je polna"}), 400     
    return jsonify({"error": "Pesem ni najdena"}), 404

def predvajaj_naslednjo():
    while True:
        cakalna_vrsta = cakalna_vrsta_baza.all()
        if not cakalna_vrsta:
            break
        # pot do datoteke pesmi
        pesem = cakalna_vrsta[0]
        relativna_pot = pesem["datoteka"]
        absolutna_pot = os.path.join(app.root_path, 'static', relativna_pot)
        # doda izbrano pesem v trenutno pesem bazo in izbriše prejšnjo
        try:
            pygame.mixer.music.load(absolutna_pot)
            trenutna_pesem_baza.truncate()  
            trenutna_pesem_baza.insert({
                "id": pesem["id"],
                "naslov": pesem["naslov"],
                "avtor": pesem["avtor"],
                "datoteka": pesem["datoteka"]
            })
            # zapis predvajane pesmi v XML
            datum = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            zapis_v_xml(pesem, datum)
            # predvaja pesem in jo odstrani iz čakalne vrste
            pygame.mixer.music.play()
            cakalna_vrsta_baza.remove(doc_ids=[pesem.doc_id])
            # napolni tabelo z "Ni izbrane pesmi" da bo vedno 6 vrstic
            while len(cakalna_vrsta_baza.all()) < 6:
                cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": ""})
            
            while pygame.mixer.music.get_busy():
                time.sleep(1)
        except pygame.error:
            # v primeru napake pri nalaganju pesmi, jo odstrani in nadaljuje
            cakalna_vrsta_baza.remove(doc_ids=[pesem.doc_id])
            continue
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
    # dobi naslov pesmi, ki ga je vnesel uporabnik in ga shranil v bazo
    pesem = request.form['pesem']
    vnosi_pesmi.insert({"pesem": pesem})
    return render_template("zabelezeno.html")

@app.route("/prepozno")
def prepozno():
    # pokaze to spletno stran, ce je zmanjkalo casa
    return render_template("prepozno.html")

def izprazni_bazo():
    # za izbrisanje baz ko se program ugasne
    cakalna_vrsta_baza.truncate()
    trenutna_pesem_baza.truncate()
    vnosi_pesmi.truncate()
    baza_kod.truncate()

# izvede izprazni_bazo() ko se program ugasne
atexit.register(izprazni_bazo)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)