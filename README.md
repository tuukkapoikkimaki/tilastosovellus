# Tilastosovellus

Paikallinen työpöytäsovellus Suomen ja maailman talouden tilastojen selaamiseen.
Tiedot haetaan avoimista rajapinnoista SQLite-tietokantaan (`tilastot.db`), ja
sovellus näyttää ne taulukkona, kuvaajina ja koottuina dashboardeina ilman
internetyhteyttä.

Sovellus on tehty toimimaan Windowsilla, Linuxilla ja macOS:llä.

## Rakenne

| Tiedosto | Tehtävä |
| --- | --- |
| `hae_tilastot.py` | Hakee tilastot netistä ja tallentaa ne tietokantaan `tilastot.db`. |
| `sovellus.py` | Tkinter-käyttöliittymä, joka lukee tilastot paikallisesta tietokannasta. |
| `asetukset.py` | Yhteiset asetukset, kuten tietokannan sijainti. |
| `requirements.txt` | Tarvittavat Python-kirjastot. |

## Tietokanta

Tietokanta tallennetaan käyttäjän datakansioon, ei projektikansioon:

| Käyttöjärjestelmä | Sijainti |
| --- | --- |
| Windows | `%LOCALAPPDATA%\tilastosovellus\tilastot.db` (esim. `C:\Users\<nimi>\AppData\Local\tilastosovellus\`) |
| Linux / macOS | `~/.local/share/tilastosovellus/tilastot.db` (tai `$XDG_DATA_HOME/tilastosovellus/`) |

`hae_tilastot.py` luo kansion tarvittaessa. Tietokantaa ei tallenneta
versionhallintaan, vaan jokainen käyttäjä hakee tiedot itse.

## Tietolähteet

- **Tilastokeskus** (PxWeb-rajapinta): väestö, työttömyys, työtunnit, BKT,
  inflaatio, ulkomaankauppa, kulutus, tuotanto, asuntojen hinnat, vuokrat ja
  kauppamäärät, muuttoliike, asuntotuotanto ja väestöennuste
- **Yahoo Finance** (`yfinance`): pörssi-indeksit (S&P 500, OMX Helsinki 25,
  Nifty 50, Shanghai Composite) sekä kulta, kupari ja maakaasu
- **Eurostat**: inflaation alaerät ja 10 vuoden valtionlainakorot
- **Maailmanpankki**: BKT:n kasvu (USA, Kiina, Intia, EU)
- **FRED**: Brent-raakaöljyn hinta
- **Euroopan keskuspankki (EKP)**: OIS-korot ja 12 kk Euribor

Mikään lähteistä ei vaadi API-avainta. Tilastokeskuksen avoin data on
lisensoitu [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fi)
-lisenssillä; tietoja käytettäessä lähde on mainittava (Tilastokeskus). Muiden
lähteiden tietoja koskevat niiden omat käyttöehdot.

## Asennus

Tarvitaan Python 3.12 tai uudempi sekä Tkinter.

Lataa ensin projekti:

```bash
git clone https://github.com/tuukkapoikkimaki/tilastosovellus.git
cd tilastosovellus
```

Kirjastot kannattaa asentaa virtuaaliympäristöön, jolloin ne eivät sekoitu
koneen muihin Python-kirjastoihin.

### Windows

1. Asenna Python osoitteesta [python.org](https://www.python.org/downloads/).
   Valitse asennuksessa **Add python.exe to PATH**. Tkinter tulee asennuksen
   mukana.
2. Avaa PowerShell tai komentokehote projektikansiossa ja aja:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

   Jos PowerShell estää aktivoinnin (*running scripts is disabled*), aja
   ensin `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` tai käytä
   komentokehotetta (`cmd`).

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Linuxilla Tkinter voi vaatia erillisen paketin, esim. `sudo apt install python3-tk`.

## Käyttö

Aktivoi virtuaaliympäristö ensin (ks. yllä). Aktivoidussa ympäristössä
komento on kaikilla käyttöjärjestelmillä `python`.

1. Hae tilastot tietokantaan:

   ```bash
   python hae_tilastot.py
   ```

   Lopuksi tulostuu yhteenveto onnistuneista
   ja epäonnistuneista hauista. Tietokannan voi luoda myös sovelluksen
   painikkeella **Päivitä tietokanta netistä**.

2. Käynnistä sovellus:

   ```bash
   python sovellus.py
   ```

Sovelluksessa voi:

- valita yksittäisen tilaston tai dashboardin pudotusvalikosta
- rajata aikavälin (*Alkaen* / *Päättyen*)
- tarkastella tietoja taulukkona ja kuvaajana
- päivittää tietokannan suoraan sovelluksesta painikkeella
  **Päivitä tietokanta netistä** (ajaa `hae_tilastot.py`:n taustalla)

### Dashboardit

1. Kansantalous
2. Tuotanto
3. Kuluttajat ja kotitaloudet
4. Ulkomaankauppa
5. Asunnot (Helsinki, Tampere, Turku)
6. Korot ja inflaatio
7. Pörssit
8. BKT:n kasvu globaalisti
9. Öljy ja raaka-aineet

## Uuden tilaston lisääminen

1. Lisää hakumäärittely sopivaan sanakirjaan `hae_tilastot.py`:ssä
   (esim. `TILASTOT`, `PORSSIT`, `EUROSTAT`) ja anna taululle nimi.
2. Lisää näyttönimi ja taulun nimi `sovellus.py`:n `TILASTOT`-sanakirjaan.
3. Halutessasi lisää tilasto johonkin `DASHBOARDIT`-kokonaisuuteen.
4. Aja `python hae_tilastot.py` uudelleen.
