# Tilastosovellus

Paikallinen työpöytäsovellus Suomen ja maailman talouden tilastojen selaamiseen.
Tiedot haetaan avoimista rajapinnoista SQLite-tietokantaan (`tilastot.db`), ja
sovellus näyttää ne taulukkona, kuvaajina ja koottuina dashboardeina ilman
internetyhteyttä.

## Rakenne

| Tiedosto | Tehtävä |
| --- | --- |
| `hae_tilastot.py` | Hakee tilastot netistä ja tallentaa ne tietokantaan `tilastot.db`. |
| `sovellus.py` | Tkinter-käyttöliittymä, joka lukee tilastot paikallisesta tietokannasta. |
| `asetukset.py` | Yhteiset asetukset, kuten tietokannan sijainti. |
| `requirements.txt` | Tarvittavat Python-kirjastot. |
| `*.png` | Esimerkkikuvaajia (väestö, työttömyys, työtunnit, ulkomaankauppa). |

## Tietokanta

Tietokanta sijaitsee käyttäjän datakansiossa XDG-käytännön mukaisesti:

```
~/.local/share/tilastosovellus/tilastot.db
```

Jos ympäristömuuttuja `XDG_DATA_HOME` on asetettu, käytetään kansiota
`$XDG_DATA_HOME/tilastosovellus/`. `hae_tilastot.py` luo kansion
tarvittaessa.

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

Mikään lähteistä ei vaadi API-avainta.

## Asennus

Tarvitaan Python 3.12 (tai uudempi) ja Tkinter.

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

Linuxilla Tkinter voi vaatia erillisen paketin, esim. `sudo apt install python3-tk`.

## Käyttö

1. Hae tilastot tietokantaan:

   ```bash
   python hae_tilastot.py
   ```

   Lopuksi tulostuu yhteenveto onnistuneista ja epäonnistuneista hauista.

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
