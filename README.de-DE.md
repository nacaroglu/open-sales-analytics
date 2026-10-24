# open-sales-analytics

[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> Maßgeblich für die Richtigkeit dieser Übersetzung ist das [englische Dokument](README.md). Synchronisierungsrevision: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

Open Sales Analytics ist eine kleine, selbst gehostete Webanwendung. Du lädst eine CSV mit abgeschlossenen
Verkaufspositionen hoch; sie zeigt Bruttoumsatz, Bestellungen, Einheiten, durchschnittlichen Bestellwert, einen
Verkaufstrend und die erfolgreichsten Produkte für einen veränderbaren Datumsbereich. Der Bruttoumsatz ist die Summe
aus Menge mal Stückpreis über alle Positionen im gewählten Zeitraum. Er enthält keine Erstattungen, Rabatte, Steuern
oder Versandkosten.

Inhalt: [Mit Docker ausführen](#mit-docker-ausführen) | [Konfiguration](#konfiguration) |
[Demo-Anleitung](#demo-anleitung) | [Ergebnisse untersuchen](#6-ergebnisse-untersuchen) |
[Produktanalysen](#produktanalysen) | [Kundenanalysen](#kundenanalysen) | [Vergleiche](#vergleiche) |
[Datensatzvertrag](#datensatzvertrag) | [Währungen](#währungen) | [Datenschutz](#datenschutz) |
[Demo-Modus](#demo-modus) | [Einschränkungen](#einschränkungen) | [Roadmap](#roadmap) | [Architektur](#architektur) |
[Entwicklung](#entwicklung) | [Mitwirken](#mitwirken) | [Lizenz](#lizenz)

## Mit Docker ausführen

Es gibt kein veröffentlichtes Image. Baue es daher einmal aus einem Checkout dieses Repositorys und führe es aus:

```sh
docker build -t open-sales-analytics .
docker run -p 8000:8000 open-sales-analytics
```

Öffne <http://localhost:8000>. Du siehst den Uploadbildschirm; **Beispieldaten ausprobieren** öffnet ein Dashboard mit der
Beispieldatei. `curl http://localhost:8000/api/health` gibt `{"status":"ok"}` zurück.

Der Container läuft als Nicht-root-Benutzer (UID 10001) und speichert Datensätze in `/data` (`DATASET_DIR=/data`).
Ohne Volume gehen sie beim Entfernen des Containers verloren. Binde zum Beibehalten ein benanntes Volume unter
`/data` ein:

```sh
docker run -p 8000:8000 -v osa-data:/data open-sales-analytics
```

Mit dem Volume überstehen Datensätze nach bestem Bemühen `docker restart` und eine Neuerstellung des Containers;
jeder läuft weiterhin nach `DATASET_TTL_HOURS` ab. Wenn du statt eines benannten Volumes ein Hostverzeichnis unter
`/data` einbindest, muss der Nicht-root-Benutzer des Containers (UID 10001) darin schreiben können, zum Beispiel mit
`sudo chown 10001 /path/to/dir`.

Das Image prüft sich selbst: `docker ps` zeigt einige Sekunden nach dem Start `healthy` und `unhealthy`, wenn
`/api/health` nicht mehr antwortet (Prüfung alle 10 s, 3 s Timeout, 3 Fehlschläge, 10 s Startfrist). `docker stop`
beendet den Server nach dem Stoppen der Hintergrundbereinigung in weniger als einer Sekunde mit Exitcode 0. Der Server
setzt kein eigenes Anfrage-Timeout (uvicorn-Standardwerte gelten); ein sehr langsamer Upload endet also erst, wenn der
Client aufgibt.

Übergib eine Einstellung mit `-e` und einer Variable aus der [folgenden Tabelle](#konfiguration):

```sh
docker run -p 8000:8000 -e PUBLIC_DEMO_MODE=true -e OSA_ENVIRONMENT=production -e OSA_VERSION=20261024-123456-abc1234 open-sales-analytics
```

## Demo-Anleitung

Ein schrittweiser Ablauf mit erzeugten Beispieldaten, vom frischen Checkout bis zum Dashboard.
Schritt 1 benötigt [uv](https://docs.astral.sh/uv/); danach wird nur Docker benötigt.

### 1. Beispieldaten erzeugen

```bash
uv run python backend/scripts/generate_sample.py
```

Dies schreibt `backend/app/sample/sample_sales.csv`. Der Seed macht die Datei deterministisch, sodass alle dieselben
Daten und Zahlen in Schritt 6 erhalten. Führe den Befehl vor `docker build` aus: Die Datei wird in das Image kopiert.

Prüfe die ersten Zeilen:

```bash
head -n 4 backend/app/sample/sample_sales.csv
```

```
order_id,order_date,product_id,product_name,quantity,unit_price,customer_id
ORD-000001,2024-01-01,P001,Ceramic Mug,1,12.00,CUST-6ebe7ed43ba4
ORD-000001,2024-01-01,P002,Travel Tumbler,1,24.00,CUST-6ebe7ed43ba4
ORD-000002,2024-01-01,P001,Ceramic Mug,1,12.00,CUST-c4da5c3ce3f2
```

### 2. Image bauen

```bash
docker build -t open-sales-analytics .
```

### 3. Container ausführen

```bash
docker run -p 8000:8000 open-sales-analytics
```

Der Server ist bereit, wenn das Protokoll `Uvicorn running on http://0.0.0.0:8000` anzeigt.

### 4. Weboberfläche öffnen

Öffne <http://localhost:8000>. Der Uploadbildschirm zeigt Dateiformat und Uploadformular.

### 5. Beispieldaten hochladen

Wähle `backend/app/sample/sample_sales.csv`, dann **USD**, und klicke **Hochladen**.
(**Beispieldaten ausprobieren** importiert dieselbe Datei ohne Auswahl.)

![Uploadformular mit ausgewählter Beispieldatei und USD](_docs/images/demo-upload.png)

### 6. Ergebnisse untersuchen

Das Dashboard öffnet **Übersicht** mit dem gesamten Datenzeitraum vom 2024-01-01 bis 2025-12-31:

| Metrik | Erwarteter Wert |
| --- | --- |
| Zeilen | 14,397 |
| Bruttoumsatz | $675,816.70 |
| Bestellungen | 10,000 |
| Verkaufte Einheiten | 24,380 |
| Durchschnittlicher Bestellwert | $67.58 |

![Übersicht: Kennzahlen, monatlicher Bruttoumsatztrend und die 10 besten Produkte](_docs/images/phase-3/overview.png)

Der gesamte Zeitraum umfasst 24 Monate, daher ist der Trend monatlich (siehe [Trend-Buckets](#trend-buckets)). Ändere
**Startdatum** und **Enddatum**, um alle Zahlen zu filtern; **Zurücksetzen** stellt den gesamten Zeitraum wieder her.
**Vergleichen mit** ergänzt den vorherigen Zeitraum oder denselben Zeitraum des Vorjahres; für den gesamten Zeitraum ist
dies nicht verfügbar, da die Daten am 2024-01-01 beginnen.

**Produkte** zeigt Ranglisten, den Bruttoumsatzanteil mit kumuliertem Pareto-Diagramm, steigende und fallende Produkte,
inaktive Produkte und gemeinsam gekaufte Produkte, hier für 2025 gegenüber 2024
(siehe [Produktanalysen](#produktanalysen)):

![Produkte: Ranglisten, Pareto-Diagramm, steigende und fallende Produkte, Inaktivität und Produktpaare](_docs/images/phase-3/products.png)

Ein Produktname öffnet seine Details: Bruttoumsatztrend, durchschnittlich bezahlter Stückpreis,
Bestelldurchdringung und gemeinsam gekaufte Produkte.

![Produktdetails: Bruttoumsatztrend, gewichteter Stückpreis, Bestelldurchdringung und verwandte Produkte](_docs/images/phase-3/product-detail.png)

**Kunden** zeigt Abdeckung, Kundenkennzahlen, Tage zwischen Käufen, die Kohortenbindungs-Heatmap, den Historischen
Kundenwert, den Prognostizierten 12-Monats-Kundenwert, RFM-Segmente, Kaufhäufigkeit und Konzentration
(siehe [Kundenanalysen](#kundenanalysen)):

![Kunden: Abdeckung, Kennzahlen, Kohortenbindungs-Heatmap, Wert, RFM, Häufigkeit und Konzentration](_docs/images/phase-3/customers.png)

**Weitere Datei analysieren** löscht diesen Datensatz und kehrt zum Uploadbildschirm zurück.

## Vergleiche

Die Datumsbereichskarte kann den aktiven Bereich mit dem vorherigen Zeitraum oder demselben Zeitraum des Vorjahres
vergleichen. Das Dashboard zeigt die exakten, von der API zurückgegebenen Daten. Ein Vergleich des gesamten Bereichs
ist nicht verfügbar, wenn er vor dem ersten Datum des Datensatzes beginnen würde. Schaltjahresvergleiche verwenden den
letzten gültigen Februartag des Vergleichsjahres. Ein Vergleich ohne vorherigen Wert heißt „No prior value“, zwei
Nullwerte „Keine Änderung“, ein neues Produkt „Neu“; andernfalls wird der Prozentsatz als „Vergleichbar“ angezeigt.

## Produktanalysen

Soweit nicht anders angegeben, verwenden alle Produktzahlen den ausgewählten inklusiven aktiven Bereich. Geldwerte
sind Bruttoumsatz; Rabatte, Erstattungen und Kosten liegen außerhalb dieses Datensatzvertrags. Jeder Produktname und
jede ID werden als vom Server gelieferter Text angezeigt.

| UI-Bezeichnung und Schlüssel | Formel und Nenner | Fenster und nicht normale Zustände | Rechenbeispiel |
| --- | --- | --- | --- |
| Ranglisten — `gross_sales` | Summe aus Menge × Stückpreis; verkaufte Einheiten sind Mengensumme; Bestellungen sind eindeutige Bestellanzahl | Aktiver Bereich; leere Bereiche enthalten keine Produkte | Eine Position mit 2 Einheiten zu 12.50 trägt 25.00 Bruttoumsatz bei |
| Bruttoumsatzanteil — `gross_sales_share` | Produktbruttoumsatz / gesamter Produktbruttoumsatz | Aktiver Bereich; unzureichend, wenn Gesamtbruttoumsatz null ist | 15 von 100 sind 15.00 % |
| Anteil der besten 20 % — `top_20_percent_share` | Bruttoumsatz der besten 20 % der Produktanzahl / Gesamtbruttoumsatz | Aktiver Bereich; unzureichend, wenn Gesamtsumme null ist | Fünf Produkte mit 50/20/15/10/5: das erste sind 50.00 % |
| Produkte bis 80 % — `products_to_80_percent` | Kleinste geordnete Produktanzahl, deren kumulierter Anteil 80 % erreicht | Aktiver Bereich; unzureichend, wenn Gesamtsumme null ist | 50+20+15 erreicht 80 % bei 3 Produkten |
| Kumulierter Anteil — `cumulative_share` | Laufender Bruttoumsatz / Gesamtbruttoumsatz | Aktiver Bereich; nicht verfügbar, wenn Gesamtsumme null ist | Die ersten drei golden Produkte erreichen 85.00 % |
| Produktwachstum — `product_growth` | Aktueller minus Vergleichsbruttoumsatz; Prozentsatz verwendet Vergleichswert | Vergleichszeitraum; `Neu`, `Kein aktueller Umsatz`, `Keine Änderung` oder nicht verfügbarer Vergleich vermeiden irreführende Prozente | 10 auf 20 sind +10 und +100.00 % |
| Rang steigender/fallender Produkte — `rising_products`, `falling_products` | Rang nach absoluter Bruttoumsatzänderung | Gewählter Vergleich; nicht verfügbar, wenn Vergleich nicht verfügbar | Änderung +10 liegt über einer Änderung +1 mit +900 % |
| Inaktive Produkte — `dormancy` | Produkte ohne Verkauf im ausgewählten 30-, 60- oder 90-Tage-Fenster; frühere Summen nutzen Verkäufe vor dem Fenster | Am Ende des gewählten Bereichs verankert (beim Gesamtbereich letztes Datensatzdatum), Standard 60; unzureichende Historie und Nullergebnis sind verschieden. Ein Verkauf genau N Tage vor dem Anker liegt im Fenster | Ein zuletzt 60 Tage vor dem Anker verkauftes Produkt ist im 60-Tage-Fenster enthalten |
| Gewichteter Stückpreis — `weighted_unit_price` | SUM(quantity × unit_price) / SUM(quantity) | Buckets des aktiven Bereichs; Buckets ohne Verkäufe sind Lücken, keine Nullpreise | 1 Einheit zu 10 plus 3 zu 20 ergibt 17.50 |
| Bestelldurchdringung — `order_penetration` | Eindeutige Bestellungen mit Produkt / alle eindeutigen Bestellungen | Aktiver Bereich; null Bestellungen ist ein Nullergebnis | 25 von 200 Bestellungen sind 12.50 % |
| Support — `basket_support` | Gemeinsame Bestellungen / geeignete Warenkorbbestellungen | Aktiver Bereich; mindestens 10 gemeinsame Bestellungen und 0,1 % Support erforderlich | 10 gemeinsame von 10.000 ergeben 0.10 % |
| Konfidenz — `basket_confidence` | Gemeinsame Bestellungen / Bestellungen mit gerichtetem Produkt | Aktiver Bereich; Paare unter Schwelle werden nicht gezeigt | A→B und B→A können wegen unterschiedlicher Bestellzahlen abweichen |
| Lift — `basket_lift` | Konfidenz / Support des Zielprodukts | Aktiver Bereich; Paare unter Schwelle werden nicht gezeigt | Lift vergleicht beobachtete Paarrate mit Ziel-Support |

Die gemeinsame Registry bezeichnet diese Schlüssel als: Bruttoumsatzanteil, kumulierter Bruttoumsatzanteil, Anteil
der besten 20 % der Produkte, Produkte bis 80 % des Bruttoumsatzes, Wachstum des Produktbruttoumsatzes, steigende
Produkte, fallende Produkte, inaktive Produkte, gewichteter realisierter Stückpreis, Bestelldurchdringung,
Warenkorb-Support, Warenkorb-Konfidenz und Warenkorb-Lift.

Paare unter einer der Warenkorbschwellen werden auch bei hohem Lift nicht angezeigt. Bestellungen mit mehr als 100
eindeutigen Produkten werden nur aus der Warenkorbanalyse ausgeschlossen; genau 100 sind enthalten, und diese
Bestellungen zählen weiterhin in Ranglisten, Durchdringung und Bruttoumsatz. Die Products-Ansicht meldet die Anzahl
ausgeschlossener Bestellungen. Der Preisverlauf beschreibt nur realisierte Preisbewegungen; er misst keine
Preiselastizität und belegt keine Ursache zwischen Preis- und Verkaufsänderung. Steigend/fallend verwendet absolute
Änderungen, damit winzige Basiswerte nicht dominieren. Durchdringung, Support, Konfidenz und Lift verwenden eindeutige Bestellungen.

Die API-Dokumentation ist unter [`/docs`](http://localhost:8000/docs) verfügbar. `GET /api/datasets/{id}/overview`
liefert Übersichts-KPIs und Trends; `GET /api/datasets/{id}/products` die Portfolioanalysen; und
`GET /api/datasets/{id}/products/detail?product_id=...` Detailanalysen eines Produkts. Datensatz-Endpunkte benötigen
das Bearer-Token des Datensatzes.

## Kundenanalysen

Kundenanalysen sind ausschließlich aggregiert. Sie beschreiben identifizierte Bestellungen und zeigen niemals eine
Kunden-ID, Kundenliste oder einen Betrag je Kunde. Der aktive Berichtsbereich enthält Start- und Enddatum, sofern eine
Zeile nicht ausdrücklich als vollständige Historie bis zum gewählten Enddatum beschrieben ist. Die folgenden
Rechenwerte verwenden das eingecheckte Fixture `backend/tests/fixtures/customers/golden_customers.csv`: 20 Bestellungen,
19 identifizierte Bestellungen, 10 Kunden und 380.0000 identifizierten Bruttoumsatz vom 2025-01-01 bis 2025-09-30.

| UI-Bezeichnung und Schlüssel | Formel, Fenster und Anker | Unzureichende Daten und Nullergebnis | Rechenbeispiel |
| --- | --- | --- | --- |
| Kundenabdeckung — `customer_coverage` | Eindeutige identifizierte Bestellungen / alle eindeutigen Bestellungen; je Bestellung für Datensatz und gewählten Bereich gezählt | Ohne Spalte `customer_id` nicht verfügbar, unter 50 % unterdrückt, und ohne Bestellungen ist Abdeckung null | 19 / 20 = 95.0 % im golden Fixture |
| Identifizierte Kunden — `identified_customers` | Eindeutige `customer_id`-Werte mit identifizierter Position im aktiven Bereich; Start und Ende inklusiv | Kein identifizierter Kunde ergibt 0 mit `zero_result` | Der golden Bereich hat 10 |
| Bruttoumsatz neuer gegenüber wiederkehrenden Kunden — `new_vs_returning` | `SUM(quantity × unit_price)` danach aufgeteilt, ob jede Position am ersten Bestelldatum des Kunden in der Gesamthistorie oder danach liegt; Historie bis Bereichsende | Keine identifizierten Zeilen ergeben Nullgeldwerte mit `zero_result` | Der Kauf von CUST-01 am 2024-12-15 macht seine Verkäufe 2025 wiederkehrend |
| Wiederkaufsrate — `repeat_purchase` | Aktive Kunden mit mindestens zwei eindeutigen Bestellungen bis zum gewählten Ende / aktive identifizierte Kunden; Bestellungen vor Bereichsbeginn zählen | Keine aktiven Kunden ist `insufficient_data`; aktive Kunden ohne Wiederkauf sind exakt 0 (`zero_result`) | Bestellungen am selben Tag sind eindeutige Bestellungen, nicht eindeutige Daten |
| Tage zwischen Käufen — `days_between_purchases` | Median der Kalendertage zwischen aufeinanderfolgenden eindeutigen Bestellungen; ein Intervall zählt, wenn seine spätere Bestellung im Bereich liegt; gleiche Tage ergeben 0 | Kein Intervall hat null Median und `insufficient_data`; feste Buckets sind 0, 1-7, 8-14, 15-30, 31-60, 61-90, 91-180, 181-365 und 366+ | Ein Paar am selben Tag zählt zu Bucket 0 |
| Kohortenbindung — `cohort_retention` | Gebundene Kunden / Kohortengröße der Akquisition aus Gesamthistorie, je Kalendermonatsversatz; Kohorten nutzen gesamte Historie bis zum gewählten Ende | Fehlende Kohorten sind `insufficient_data`; rechte Randzelle ist `Noch nicht beobachtet`, niemals 0 % | Monat 0 ist für jede nicht leere Kohorte 100.0 % |
| Historischer Kundenwert — `historical_customer_value` | Beobachteter identifizierter Bruttoumsatz bis Enddatum / identifizierte Kundenanzahl; Median ist mittlerer Wert je Kunde; Kohortenkurven nutzen kumulierte Verkäufe | Keine Kohorte ist `insufficient_data`; null beobachteter Umsatz ist Nullergebnis; dies sind Beobachtungen, keine Prognose | Das golden Fixture hat 380.0000 über 10 identifizierte Kunden |
| RFM-Segmente — `rfm` | Aktualität sind Tage vor gewähltem Enddatum; Häufigkeit sind eindeutige Bestellungen; Geldwert ist identifizierter Bruttoumsatz. Jede Dimension nutzt relative Quintilswerte und FM = F + M | Weniger als 5 Kunden ist `insufficient_data`; Gleichstände nutzen denselben Wert und die vollständige Wert-zu-Segment-Tabelle der Registry | Werte sind relativ zu diesem Upload, keine universellen Benchmarks |
| RFM-Segmentdetails — `rfm_drilldown` | Aggregierter Segmentbruttoumsatz plus feste Buckets für Aktualität (0-30 bis 366+) und Häufigkeit (1, 2, 3, 4, 5, 6-10, 11-20, 21+); keine Zeilen je Kunde | Weniger als 5 Kunden ist `insufficient_data`; null Bruttoumsatz hat null Anteil | Das golden Fixture enthält Gleichstände ohne ID-Tiebreak |
| Kaufhäufigkeit — `purchase_frequency` | Nach eindeutigen identifizierten Bestellungen bis zum gewählten Ende in 1, 2, 3, 4, 5, 6-10, 11-20 und 21+ gruppierte Kunden | Keine identifizierten Kunden ergibt leere Zählungen, null Anteile und `insufficient_data` | Kunde mit zwei Bestellungen ist in Bucket 2 |
| Kundenkonzentration — `concentration` | Bruttoumsatz des obersten Dezils / identifizierter Bruttoumsatz; für N Kunden enthält die Spitzengruppe die `ceil(N / 10)` größten Bereichsumsätze, ohne Tiebreak am Schnitt | Weniger als 10 Kunden oder null identifizierter Bruttoumsatz ist `insufficient_data` mit null Anteil | Bei N=10 ergeben Umsätze 1000, 500 und achtmal 100 den Wert 1000 / 2300 = 0.4348 |

Die Stufen für 50 % und 80 % sind inklusiv: Unter 50 % wird verborgen, 50.0 % bis ausschließlich 80 % zeigt eine
Warnung bei geringer Abdeckung, ab 80 % ist normal. Die UI schneidet den angezeigten Prozentsatz auf eine Dezimalstelle
ab; sie rundet nicht über eine Stufengrenze. Abdeckung gilt je Bestellung, nicht je Position. Eine Datei ohne Spalte
ist nicht verfügbar statt 0 %.

Kundenidentität und Kohorten nutzen die Gesamthistorie bis zum gewählten Enddatum. Ein späterer Bereichsbeginn stuft
einen Kunden nicht als neu ein und ändert keine Kohortenzugehörigkeit. RFM-Aktualität und Kohortenreife sind am
gewählten Enddatum verankert, nie an heute. Eine teilweise oder zukünftige Kohortenzelle ist **Noch nicht beobachtet**,
kein Nullergebnis.

Die Konsistenzregeln beim Upload sind exakt: Leere Werte innerhalb einer Bestellung werden aus ihrer einzigen nicht
leeren ID ergänzt; zwei verschiedene IDs lehnen den gesamten Upload ab; eine vollständig leere Bestellung bleibt
nicht identifiziert. Die Standardgrenze für `customer_id` ist 128 Zeichen. Die Best-Effort-Prüfungen lehnen
offensichtliche E-Mail-Adressen, offensichtliche Telefonnummern und Werte über der Grenze ab; Namen, Postanschriften,
nationale ID-Nummern, umkehrbare Codierungen oder ungewöhnliche Telefonnummern können sie nicht erkennen.

Kundendaten sind pseudonym, nicht anonym. Verwende UUID oder internen Schlüssel oder einen Hash mit geheimem Salt
außerhalb der Datei. Antworten enthalten nur aggregierte Zählungen und Summen: Es gibt keine Kundenliste, Suche,
Downloads oder Exporte; Kunden-IDs, Kohortenzugehörigkeit und RFM-Datensätze werden nicht protokolliert. Kundendaten
liegen nur in der DuckDB-Datei des Datensatzes, werden mit ihr nach `DATASET_TTL_HOURS` (standardmäßig 24) oder sofort
mit **Weitere Datei analysieren** entfernt, und die rohe CSV wird nach dem Import gelöscht. Der Prognostizierte
12-Monats-Kundenwert ist eine separate zukünftige Metrik und nicht dieser beobachtete Wert.

## Konfiguration

Der Server liest beim Start diese Umgebungsvariablen. Jede Variable ist optional.

| Variable | Typ | Standard | Wirkung |
| --- | --- | --- | --- |
| `DATASET_DIR` | path | `./tmp_datasets` (`/data` im Docker-Image) | Verzeichnis mit einer DuckDB-Datei je Datensatz. Wird bei Bedarf mit privaten Berechtigungen erstellt. |
| `DATASET_TTL_HOURS` | integer > 0 | `24` | Stunden bis zum Ablauf und Löschen eines Datensatzes. |
| `DATASET_TTL_SECONDS` | integer > 0 | unset | Nur für Tests. Wenn gesetzt, Lebensdauer in Sekunden statt `DATASET_TTL_HOURS`. Browser-Tests verwenden dies für einen echten Ablauf. In Produktion nicht setzen. |
| `MAX_UPLOAD_BYTES` | integer > 0 | `52428800` (50 MB) | Größter akzeptierter Upload in Bytes. Eine größere Datei wird mit `file_too_large` abgelehnt. |
| `MAX_ROWS` | integer > 0 | `500000` | Höchste Anzahl Datenzeilen (Kopfzeile zählt nicht) in einem Upload. Mehr wird mit `too_many_rows` abgelehnt. |
| `CUSTOMER_ID_MAX_LENGTH` | integer > 0 | `128` | Maximale Unicode-Zeichenanzahl einer nicht leeren `customer_id`; längere Werte werden mit `customer_id_too_long` abgelehnt. |
| `CLEANUP_INTERVAL_MINUTES` | integer > 0 | `15` | Intervall, in dem der Server abgelaufene Datensätze entfernt (auch einmal beim Start). |
| `PUBLIC_DEMO_MODE` | boolean | `false` | `true` deaktiviert Uploads; siehe [Demo-Modus](#demo-modus). |
| `MAX_DATASETS` | integer > 0 | `200` | Höchste Anzahl nicht abgelaufener Datensätze auf dem Server. Ein weiterer (Upload oder **Beispieldaten ausprobieren**) gibt 503 `capacity_reached` zurück, bis einer abläuft oder gelöscht wird. |
| `RESPONSE_CACHE_MAX_ENTRIES` | integer >= 0 | `256` | Höchste Anzahl gecachter Overview/Product-Antworten in diesem Prozess. `0` deaktiviert den Antwortcache. |
| `RESPONSE_CACHE_TTL_SECONDS` | integer > 0 | `300` | Maximale Lebensdauer einer gecachten Overview/Product-Antwort; der Datensatzablauf hat immer Vorrang. |
| `OSA_ENVIRONMENT` | `development` or `production` | `development` | Laufzeitumgebung. Andere Werte verhindern den Start. |
| `OSA_VERSION` | string | `local` | Lesbare Version. CI setzt die Build-Version; mit `docker run -e` überschreibbar. |

Boolesche Werte akzeptieren `true`/`false`, `1`/`0` und `yes`/`no` unabhängig von Groß-/Kleinschreibung
(`on`/`off`, `t`/`f` und `y`/`n` funktionieren ebenfalls).

Ein ungültiger Wert lässt den Server den Start mit einem Fehler verweigern, der die Variable nennt. Ungültig bedeutet:
keine Zahl, null oder negativ, Dezimalzahl wie `1.5`, leere Zeichenfolge oder boolescher Wert außerhalb der obigen
Schreibweisen. Beispielsweise beendet sich `MAX_ROWS=0 uv run uvicorn app.main:app --app-dir backend` mit
`MAX_ROWS  Input should be greater than 0`.

## Datensatzvertrag

Eine Zeile ist eine Produktposition in einer abgeschlossenen Bestellung. Die Datei muss diese sechs Pflichtspalten
und eine optionale Spalte enthalten (dieselbe Tabelle steht auf dem Uploadbildschirm). Bedeutung und Datenschutzgrenzen
von `customer_id` stehen unter [Kundenanalysen](#kundenanalysen):

| Spalte | Typ | Regel |
| --- | --- | --- |
| `order_id` | String | Erforderlich und nicht leer. Wird zur Zählung eindeutiger Bestellungen verwendet. |
| `order_date` | Date | Erforderliches ISO-Kalenderdatum im Format `YYYY-MM-DD`. Darf nicht in der Zukunft liegen. |
| `product_id` | String | Erforderlich und nicht leer. Identifiziert das Produkt. |
| `product_name` | String | Erforderlich und nicht leer. Eine `product_id` muss innerhalb eines Uploads genau einem Namen entsprechen. |
| `quantity` | Integer | Erforderlich und größer als null. Null und negative Mengen sind ungültig. |
| `unit_price` | Decimal | Erforderlich und nicht negativ. Ein Nullpreis wird mit Warnung akzeptiert; ein negativer Preis ist ungültig. |
| `customer_id` | String | Optional. Darf leer sein; bis zu `CUSTOMER_ID_MAX_LENGTH` Unicode-Zeichen (standardmäßig 128); verwende Hash-ID, UUID oder nicht personenbezogenen internen Schlüssel. Niemals E-Mail-Adresse, Telefonnummer, Name oder andere direkte Kennung. |

Regeln auf Dateiebene:

- UTF-8, kommagetrennt, eine Kopfzeile. Die Kopfzeile ist in Fehlerberichten Zeile 1, die erste Datenzeile also Zeile 2.
- Spaltennamen werden nach Entfernen äußerer Leerzeichen verglichen. Die Reihenfolge ist egal. Eine Spalte außerhalb
  der sechs Pflichtspalten und `customer_id` wird mit Warnung (`extra_column`) ignoriert.
- `(order_id, product_id)` ist eindeutig: Dasselbe Produkt erscheint höchstens einmal je Bestellung.
- Ein Name je `product_id` in der gesamten Datei.
- Innerhalb einer Bestellung werden leere `customer_id`-Werte aus der einzigen nicht leeren ID ergänzt; widersprüchliche
  IDs lehnen den Upload ab, Bestellungen mit ausschließlich leeren Werten bleiben nicht identifiziert.
- Eine Währung je Upload, ausgewählt im Uploadformular (siehe [Währungen](#währungen)).
- Jede ungültige Zeile lehnt die gesamte Datei ab. Nichts wird gespeichert.
- Standardmäßig höchstens 50 MB und 500.000 Zeilen (`MAX_UPLOAD_BYTES` und `MAX_ROWS`).
- Mengen sind Ganzzahlen bis 2.147.483.647. Preise sind einfache Dezimalzahlen (kein Währungssymbol, kein
  Tausendertrennzeichen) mit höchstens 14 Stellen vor und 4 nach dem Punkt.

### Ein gültiges Beispiel

Speichere dies als `example.csv`. Es hat drei Positionen und zwei Bestellungen; Bestellung `A-1001` hat zwei Positionen.

```csv
order_id,order_date,product_id,product_name,quantity,unit_price
A-1001,2025-03-01,P-10,Ceramic Mug,2,12.50
A-1001,2025-03-01,P-20,Travel Tumbler,1,24.00
A-1002,2025-03-02,P-10,Ceramic Mug,1,12.50
```

Eine optionale `customer_id` kann enthalten sein; leere Zellen sind erlaubt:

```csv
order_id,order_date,product_id,product_name,quantity,unit_price,customer_id
A-1001,2025-03-01,P-10,Ceramic Mug,2,12.50,CUST-007
A-1001,2025-03-01,P-20,Travel Tumbler,1,24.00,
```

Importiere die Datei bei auf Port 8000 laufender Anwendung über die API:

```sh
curl -F currency=USD -F file=@example.csv http://localhost:8000/api/datasets
```

Die Antwort ist `201` mit `"warnings":[]`, einer `dataset_id`, einem `token` und der ersten Zusammenfassung. Der
Bruttoumsatz beträgt hier 61.50 aus 2 Bestellungen und 4 Einheiten.

### Ungültige Beispiele

Jedes ist eine kleine Änderung an der gültigen Datei. Die Anwendung antwortet mit `422`, dem Fehlercode
`validation_failed` und einer Fehlerliste; der `code` jedes Fehlers steht in dieser Tabelle. Jeder Fehler enthält auch
Zeilennummer und Spalte.

| Änderung an der gültigen Datei | Fehler-`code` | Zeile |
| --- | --- | --- |
| `unit_price` aus der Kopfzeile (und den letzten Wert jeder Zeile) entfernen | `missing_column` | keine (Dateiebene) |
| Datum `2025-03-02` in `2025-13-02` ändern | `invalid_date` | 4 |
| Menge der letzten Zeile von `1` auf `0` ändern | `invalid_quantity` | 4 |
| Letzte Zeile wiederholen | `duplicate_line` | 5 |

### Fehlercodes

Der Bericht listet die ersten 100 Fehler auf und nennt die Gesamtzahl (`error_count`).

| Code | Ursache |
| --- | --- |
| `file_too_large` | Datei ist größer als `MAX_UPLOAD_BYTES`. |
| `empty_file` | Datei ist leer. |
| `invalid_encoding` | Datei ist kein gültiges UTF-8. |
| `malformed_csv` | Datei kann nicht als CSV gelesen werden (zum Beispiel ein einzelnes Feld länger als 131.072 Zeichen). |
| `too_many_rows` | Mehr als `MAX_ROWS` Datenzeilen. |
| `no_data_rows` | Es gibt eine Kopfzeile, aber keine Datenzeilen. |
| `missing_column` | Eine der sechs Pflichtspalten fehlt in der Kopfzeile. |
| `duplicate_column` | Eine Pflichtspalte erscheint mehrfach in der Kopfzeile. |
| `missing_value` | Ein Pflichtwert ist leer. |
| `invalid_date` | `order_date` ist kein echtes Datum in Schreibweise `YYYY-MM-DD`. |
| `future_date` | `order_date` liegt nach heute (UTC). |
| `invalid_quantity` | `quantity` ist keine Ganzzahl von 1 bis 2.147.483.647. |
| `invalid_price` | `unit_price` ist keine einfache Dezimalzahl mit höchstens 14 Stellen vor und 4 nach dem Punkt. |
| `negative_price` | `unit_price` ist kleiner als null. |
| `line_total_too_large` | `quantity × unit_price` ist 100.000.000.000.000 oder mehr und liegt außerhalb des exakten Dezimalbereichs für Bruttoumsatz. |
| `malformed_row` | Die Zeile hat eine andere Anzahl Werte als die Kopfzeile. |
| `duplicate_line` | Dieselbe `order_id` und `product_id` stehen in einer früheren Zeile. |
| `conflicting_product_name` | Eine `product_id` hat mehr als einen `product_name`. |
| `conflicting_customer_id` | Eine Bestellung hat mehr als eine nicht leere `customer_id`. |
| `customer_id_too_long` | Eine nicht leere `customer_id` überschreitet `CUSTOMER_ID_MAX_LENGTH` Unicode-Zeichen. |
| `customer_id_looks_like_email` | Eine nicht leere `customer_id` entspricht der offensichtlichen E-Mail-Heuristik. |
| `customer_id_looks_like_phone` | Eine nicht leere `customer_id` entspricht der offensichtlichen Telefon-Heuristik. |

Die drei Prüfungen für `customer_id` sind eine Best-Effort-Leitplanke, keine Anonymisierung oder Compliance-Garantie.
Die E-Mail-Prüfung sucht überall im Wert nach `[^@\s]+@[^@\s]+\.[A-Za-z]{2,}`. Die Telefonprüfung erlaubt nur
Ziffern, Leerzeichen, `+ - . ( )`, verlangt 7–15 Ziffern sowie entweder ein führendes `+`, sichtbare Leerzeichen/
Klammern oder mindestens zwei `-`/`.`-Trenner. Diese Heuristiken haben bewusst bekannte Lücken: Eine rein numerische
Telefonnummer wie `05321234567` wird akzeptiert, während Zifferngruppen mit zwei Bindestrichen wie `2024-01-000123`
abgelehnt werden. Eine akzeptierte ID ist dadurch nicht anonym.

Eine Anfrage kann auch vor dem Lesen der Datei scheitern: Eine Währung außerhalb der Liste ergibt `400 invalid_request`.

### Kundenabdeckung

Wenn `customer_id` vorhanden ist, wird die Abdeckung einmal beim Import auf Bestellebene berechnet, nachdem leere IDs
aus einer anderen Position derselben Bestellung ergänzt wurden:

`identified distinct orders / all distinct orders`

Dies ist kein Zeilenprozentsatz; eine identifizierte Bestellung mit fünf Positionen zählt einmal. Datensatzmetadaten
melden Zählungen und gerundetes Verhältnis, während die Stufe aus exakten Ganzzahlzählungen über den gesamten Datensatz
bestimmt wird:

- unter 50 %: `suppressed`; Kundenanalysen sind nicht verfügbar;
- 50 % bis unter 80 %: `warning`; Kundenanalysen sind mit Warnung über geringe Abdeckung verfügbar;
- 80 % oder mehr: `normal`; Kundenanalysen sind normal verfügbar.

Dateien ohne `customer_id` haben die Stufe `missing` und `coverage: null` statt Null-Prozent-Abdeckung.
Abdeckungsmetadaten enthalten nur Zählungen und nie Kundenkennungen. Die Abdeckung eines Datumsbereichs verwendet
dieselbe Formel auf Bestellebene mit inklusiven Bestelldaten; ein leerer Bereich hat Nullzählungen und `coverage: null`.
Die Stufe basiert weiter auf dem gesamten Datensatz; Datumsfilter lassen das Customers-Modul nicht erscheinen oder verschwinden.

### Customers-API

`GET /api/datasets/{id}/customers` ist durch Bearer-Token geschützt und akzeptiert dieselben optionalen
Abfrageparameter `start`, `end` und `comparison` wie die Endpunkte der Module Overview und Products. Ohne Parameter
verwendet es den gesamten Datensatz und den Standardvergleich `previous_period`. Ungültige, umgekehrte oder außerhalb
liegende Daten ergeben `400 invalid_range`; ein unbekannter Vergleich `400 invalid_request`. Fehlende oder fehlerhafte
Zugangsdaten ergeben `401 unauthorized` mit `WWW-Authenticate: Bearer`; ein unbekannter, abgelaufener oder gelöschter
Datensatz ergibt `404 not_found`.

Die typisierte Antwort enthält `module`, `range`, `comparison`, `currency`, `availability`, `coverage` und `sections`.
`coverage.dataset` ist die gespeicherte Abdeckung des gesamten Datensatzes; `coverage.range` die inklusive Abdeckung
des ausgewählten Bereichs. Beide enthalten Stufe, gerundetes Abdeckungsverhältnis und Zählungen identifizierter,
nicht identifizierter und gesamter Bestellungen. Bei normaler oder warning-Abdeckung meldet
`sections.identified_customers` die eindeutigen identifizierten Kunden mit Aktivität im inklusiven Bereich sowie
gemeinsamen Vergleichswert und Änderungsfelder. Eine leere aktive Population ist `zero_result`.
`sections.new_vs_returning` teilt den identifizierten Bruttoumsatz im Bereich in Neukundenumsatz (Positionen am ersten
Kaufdatum des Kunden) und Umsatz wiederkehrender Kunden (spätere Positionen) mit denselben Vergleichsfeldern;
die Klassifizierung verwendet stets `first_order_date` aus der Gesamthistorie des ganzen Uploads, sodass ein späterer
Bereichsbeginn einen wiederkehrenden Kunden nie zu einem neuen macht.

`sections.days_between_purchases` meldet Wiederbestellungszeitpunkte nur für den aktuellen Bereich (keine
Vergleichsfelder). Die eindeutigen Bestellungen jedes identifizierten Kunden werden nach ihrer ersten Position datiert
und sortiert; jedes aufeinanderfolgende Paar ist ein Intervall in Kalendertagen, zwei Bestellungen am selben Tag
ergeben `0`. Ein Intervall zählt, wenn seine spätere Bestellung im inklusiven Bereich liegt, auch wenn die frühere vor
Bereichsbeginn liegt; Bestellungen nach dem Bereichsende werden ignoriert. Der Abschnitt gibt `median_days` (Mittelwert
der beiden mittleren Werte bei gerader Anzahl, kann also auf `.5` enden; kein mean wird gemeldet), `interval_count`,
`contributing_customers` und neun feste `buckets` (`0`, `1-7`, `8-14`, `15-30`, `31-60`, `61-90`, `91-180`,
`181-365`, `366+` days) zurück, jeweils mit `interval_count` und `share` aller Intervalle. Ohne enthaltenes Intervall
sind Median und alle Anteile `null`, der Zustand ist `insufficient_data`.

`sections.cohort_retention` ist eine monatliche Bindungsmatrix nach Akquisitionskohorte nur für den aktuellen Bereich
(keine Vergleichsfelder). Die Kohorte eines Kunden ist der Monat seiner ersten Bestellung in der Gesamthistorie;
Zeilen sind die Kohortenmonate vom Monat des Bereichsbeginns bis zum Monat des Bereichsendes, älteste zuerst, sodass
eine Änderung nur des Starts keine Zeile ändert. Das Bereichsende ist der `data_cutoff`: Kunden, die danach erstmals
auftreten, sind keine Mitglieder, und spätere Aktivität wird ignoriert; Aktivität vor dem Start zählt weiter. Jede
Zeile hat `cohort_month` (`YYYY-MM`), `cohort_size`, `complete_months` und `cells`; Monat `N` (0 = Akquisitionsmonat)
enthält `retained_count` (Mitglieder mit identifizierter Position in diesem Kalendermonat) und `retention`
(`retained_count / cohort_size`). Der `state` jeder Zelle ist `complete` (ganzer Monat am oder vor Stichtag), `partial`
(Monat enthält den Stichtag; bisherige Zählung) oder `not_observed` (Monat beginnt nach Stichtag; Werte sind `null`,
nie `0`). Zeilen werden auf die Breite der ältesten Kohorte aufgefüllt. Ohne überlappende Kohorte ist `rows` leer und
der Zustand `insufficient_data`.

`sections.historical_customer_value` meldet beobachteten Historischen Kundenwert (bereits beobachteter Bruttoumsatz,
keine Prognose) nur für den aktuellen Bereich. Seine Population sind die Mitglieder der `cohort_retention`-Zeilen;
der Wert eines Kunden ist sein identifizierter Bruttoumsatz am oder vor `data_cutoff` (Bereichsende), einschließlich
Verkäufen vor Bereichsbeginn. Zurückgegeben werden `customer_count`, `average` (Gesamtwert / `customer_count`) und
`median` (Mittelwert der beiden mittleren Werte bei gerader Anzahl), Geld halb-auf auf 4 Dezimalstellen gerundet.
`rows` spiegelt `cohort_retention`-Zeilen und Zellzustände; `value_per_customer` jeder Zelle = kumulierter Bruttoumsatz
der Kohorte bis Ende von Monat `N` (am Stichtag gedeckelt) / `cohort_size` (`null` bei `not_observed`). `all_cohorts`
ist ein Punkt je Monatsversatz über Kohorten mit `complete`-Zelle (`value_per_customer`, `contributing_cohorts`; `null`
und `0`, wenn keine vollständig ist). Ohne Kohorte ist der Zustand `insufficient_data`; Mitglieder mit Gesamtwert 0
ergeben `zero_result` mit Werten `0.0000`.

`sections.rfm` meldet RFM-Segmentzählungen nur für den aktuellen Bereich ohne Vergleich. Seine Population
(`customer_count`, N) sind identifizierte Kunden mit identifizierter Bestellung am oder vor Bereichsende; ihre gesamte
identifizierte Aktivität bis zum Ende zählt, der Bereichsbeginn hat keine Wirkung. Aktualität sind Tage von der letzten
identifizierten Position eines Kunden bis zum `recency_anchor` (Bereichsende), Häufigkeit sind eindeutige Bestellungen,
Geldwert ist Bruttoumsatz. Jede Dimension wird aus dem Kundenrang mit 1–5 bewertet:
`floor(5 × (2 × worse + ties) / (2 × N)) + 1`; `worse` zählt Kunden mit strikt schlechterem Wert, `ties` solche mit
demselben Wert. Gleiche Werte erhalten denselben Score, eine konstante Dimension erhält 3. Mit `FM = F + M` benennt
die erste passende Regel das Segment: Champions (R ≥ 4, FM ≥ 8), Loyal (R ≥ 3, FM ≥ 6), Potential Loyalists
(R ≥ 4, FM ≤ 5), Needs Attention (R = 3, FM ≤ 5), At Risk (R ≤ 2, FM ≥ 6), Lost (R ≤ 2, FM ≤ 5). `segments` listet
immer alle sechs in dieser Reihenfolge mit `customer_count` und `share`; Scores je Kunde verlassen das Backend nie.
Weniger als 5 Kunden ergeben leere `segments` und `insufficient_data`. Ein fester `note` sagt, dass Segmente relativ
zum Kundenbestand dieses Uploads und keine universellen Benchmarks sind.

`sections.rfm_drilldown` meldet aggregierte Zahlen je RFM-Segment mit derselben Population, denselben Eingaben und
Segmenten wie `sections.rfm` und ohne Vergleich. Auf oberster Ebene gibt es `customer_count` (N, wie in
`sections.rfm`), `recency_anchor` (Bereichsende) und `gross_sales` (summierter Geldwert aller N Kunden bis zum Ende,
halb-auf auf 4 Dezimalstellen gerundet). `segments` listet stets alle sechs Segmente in der Reihenfolge von
`sections.rfm`; jedes hat `customer_count`, `gross_sales` (Geldwertsumme der Mitglieder), `gross_sales_share`
(Segment-`gross_sales` / oberste `gross_sales`, `null` bei Gesamtsumme `0`), eine `recency_distribution` über sechs
feste Buckets von Tagen zum Anker (`0-30`, `31-60`, `61-90`, `91-180`, `181-365`, `366+`; `key`, `min_days`,
`max_days`, `customer_count`) und eine `frequency_distribution` über acht feste Buckets eindeutiger Bestellungen
(`1`, `2`, `3`, `4`, `5`, `6-10`, `11-20`, `21+`; `key`, `min_orders`, `max_orders`, `customer_count`). Offene Buckets
haben ein Maximum `null`, leere Segmente und Buckets sind `0`. Ein Segment mit einem Mitglied wird wie jedes andere
gemeldet, da keine Kundenkennung oder kein Score zurückgegeben wird. Weniger als 5 Kunden ergibt `insufficient_data`
mit echten `customer_count` und `gross_sales` sowie leerer `segments`-Liste.

Fehlende oder unterdrückte Abdeckung lässt jeden Abschnitt aus (`sections` ist leer). Der Endpunkt gibt immer
`Cache-Control: no-store` zurück. Kundenantworten sind absichtlich ausschließlich aggregiert: Sie enthalten keine
Kundenkennungen, Objekte je Kunde, Suche, Details, Downloads oder Exportdaten; Kennungen werden nicht protokolliert.

### Warnungen

Warnungen lehnen die Datei nicht ab. Sie erscheinen in der `warnings`-Liste der `201`-Antwort und im Uploadbildschirm.

| Code | Bedeutung |
| --- | --- |
| `extra_column` | Datei hat eine Spalte außerhalb der sechs Pflichtspalten und `customer_id`, zum Beispiel `note`. Sie wird ignoriert und nicht gespeichert. |
| `zero_price` | Eine oder mehrere Positionen haben Stückpreis 0. Sie werden importiert und zählen als Bestellungen und Einheiten, ohne Bruttoumsatz. |

### Beispieldaten

Lade eine gültige Beispieldatei unter <http://localhost:8000/api/sample.csv> herunter (der Uploadbildschirm verlinkt
sie als **Beispiel-CSV herunterladen**). **Beispieldaten ausprobieren** auf dem Uploadbildschirm importiert dieselbe Datei ohne Upload in USD.

## Trend-Buckets

Der Trend gruppiert Bruttoumsatz nach Kalender-Bucket. Die Granularität hängt nur vom gewählten Bereich einschließlich
beider Enddaten ab: bis 90 Tage täglich, über 90 bis 730 Tage wöchentlich, länger monatlich. Die API gibt je Bucket
`bucket_start` (erster Tag des Buckets) und kein Abdeckungsfeld zurück.

- Der Bereich ist inklusiv: Start- und Enddatum gehören dazu.
- Wochen laufen Montag bis Sonntag; `bucket_start` eines Wochen-Buckets ist sein Montag. Monate sind Kalendermonate.
- Ein vom Bereich angeschnittener Bucket (erste Woche/Monat beginnt vor Start oder letzte endet nach Ende) ist ein
  Teilzeitraum. Das Diagramm ermittelt dies aus Bereich und Kalender; ein Tag ohne Verkäufe zählt daher als abgedeckt.
  Ein eintägiger Tages-Bucket ist immer vollständig (Daten enthalten nur Daten); ein eintägiger Ausschnitt aus Woche
  oder Monat ist teilweise. Ein Bereich innerhalb einer Woche oder eines Monats zeigt den Bucket als teilweise.
- Darstellung eines Teilzeitraums: Die Achsenbeschriftung einer teilweisen Woche/eines Monats zeigt die abgedeckten
  Daten (`29–31. Dez.`, `10–31. März 2025`) statt `Woche ab 29. Dez.` oder Monatsname, der Punkt ist hohl, ein Hinweis unter
  dem Diagramm erklärt dies, und der Tooltip ergänzt Jahr und `Teilzeitraum: <abgedeckte Daten>`. Ein vollständiger
  Bucket hat nichts davon.
- Nur Zeilen im Bereich werden summiert; ein teilweiser Bucket enthält also Verkäufe der abgedeckten Daten.

## Währungen

Die Währung wird im Uploadformular gewählt: USD, EUR, GBP, TRY, CAD, AUD, JPY, CHF, SEK, PLN. Sie ist nur eine
Beschriftung der Beträge. Es gibt weder Umrechnung noch Wechselkurs. Andere Codes werden mit `400 invalid_request` abgelehnt.

## Datenschutz

- Die rohe CSV wird unmittelbar nach Ende des Imports gelöscht, bei Erfolg und Fehler.
- Pflichtspalten und optionale `customer_id` werden in einer DuckDB-Datei je Datensatz unter `DATASET_DIR` mit privaten
  Berechtigungen gespeichert (`0600` für Datei, `0700` für Verzeichnisse).
- Kunden-IDs sind pseudonyme, keine anonymen Daten. Sie werden für die 24-stündige Lebensdauer des Datensatzes
  gespeichert. Verwende Hash-ID, UUID oder nicht personenbezogenen internen Schlüssel; lade nie direkte Kennungen wie
  E-Mail-Adresse, Telefonnummer oder Name hoch.
- Prüfungen von Kunden-ID-Länge, E-Mail und Telefon sind nur Best-Effort-Leitplanken. Sie sind keine Anonymisierung oder
  Compliance-Garantie; automatische Prüfungen finden nicht jede Art personenbezogener Daten.
- Ein Datensatz wird nach `DATASET_TTL_HOURS` (standardmäßig 24) durch eine Bereinigung beim Start und danach alle
  `CLEANUP_INTERVAL_MINUTES` oder sofort beim Klick auf **Weitere Datei analysieren** gelöscht.
- Erfolgreiche Modulantworten können für `RESPONSE_CACHE_TTL_SECONDS` (standardmäßig 300 Sekunden) in einem begrenzten,
  prozesslokalen Cache bleiben; Autorisierung läuft bei jeder Anfrage, Einträge werden nach Datensatz und Optionen
  geschlüsselt, Ablauf oder Löschung entfernt gecachte Antworten. Der Cache wird nicht zwischen Instanzen geteilt.
- Zugriff benötigt ein zufälliges Bearer-Token. Der Browser hält es im `sessionStorage`, es verschwindet beim Schließen
  des Tabs. Der Server speichert nur einen SHA-256-Hash davon.
- Eine fehlende oder abgelaufene Datensatz-ID ergibt 404, ein falsches Token für einen vorhandenen Datensatz 401; der
  Status verrät also, ob eine ID existiert. Dies ist ein akzeptiertes Risiko: IDs sind zufällige, nicht erratbare
  128-Bit-Werte, und ein Datensatz bleibt ohne Token unlesbar.
- Pro Anfrage gibt es eine JSON-Protokollzeile mit Methode, Pfad, Status, Dauer und Datensatz-ID. Die Datensatz-ID wird
  absichtlich protokolliert, um eine Anfrage verfolgen zu können; sie ist kein Geheimnis und ohne Token nutzlos.
  Protokolle enthalten nie Tokens, Dateiinhalte, Dateinamen, Produktnamen oder Bestell-IDs. Fehlerprotokolle enthalten
  Namen von Exception-Klassen und Stackframes, niemals Exception-Nachrichten.
- Nichts wird an andere Dienste gesendet.
- Wenn Kunden-IDs geliefert werden, enthält die DuckDB-Datei des Datensatzes außerdem `customer_facts`: eine Zeile je
  identifiziertem Kunden mit ersten/letzten Bestelldaten der Gesamthistorie, Akquisitionsmonat, eindeutigen lebenslangen
  Bestellungen, Einheiten und Bruttoumsatz. Sie enthält keine Zeilen für nicht identifizierte Bestellungen, läuft mit
  dem Datensatz ab und ist keine separate gemeinsame Datenbank.

## Demo-Modus

Eine gehostete Demo ist eine öffentliche Instanz mit `PUBLIC_DEMO_MODE=true`: Besucher können nur die mitgelieferten
Beispieldaten untersuchen und keine Datei hochladen. Ihre Datensätze laufen wie alle anderen ab (`DATASET_TTL_SECONDS`),
und sie läuft als einzelne Instanz. Um eigene Dateien zu analysieren, [führe sie selbst aus](#mit-docker-ausführen).

`PUBLIC_DEMO_MODE=true` ist für einen öffentlichen Server, der keine Dateien anderer Personen annehmen soll:

- `POST /api/datasets` antwortet ohne Lesen des Inhalts mit 403 `upload_disabled`.
- **Beispieldaten ausprobieren** und der Beispieldownload funktionieren weiter.
- Der Uploadbildschirm zeigt nur Dateiformat und **Beispieldaten ausprobieren**, kein Datei- oder Währungsfeld. Er erklärt, dass
  nur Beispieldaten akzeptiert werden, und verlinkt für Uploads [Mit Docker ausführen](#mit-docker-ausführen).
- `GET /api/config` gibt `{"public_demo_mode":true,...}` zurück; daran erkennt es der Bildschirm.
- `MAX_DATASETS` schützt den Datenträger eines öffentlichen Servers: Jeder Klick auf **Beispieldaten ausprobieren** erstellt einen
  Datensatz, und an der Grenze antwortet er mit 503 `capacity_reached`.

## Einschränkungen

- Nur eine Instanz. Keine horizontale Skalierung: Datensätze sind Dateien auf dem Datenträger dieser Instanz.
- Überleben eines Neustarts nach bestem Bemühen und nur, wenn `DATASET_DIR` auf einem Volume liegt.
- Keine Konten und keine Freigabe. Ein Datensatz ist nur mit seinem Token erreichbar, das in einem Browser-Tab bleibt.
- Eine Währung je Datei.
- Keine Kundenlisten, Exporte oder Suchen; Kundenzahlen umfassen nur identifizierte Bestellungen.
- Nur Bruttoumsatz: keine Erstattungen, Rabatte, Steuern oder Versandkosten.
- Standardmäßig 50 MB und 500.000 Zeilen.
- Telefon-, Tablet- und Desktopbreiten (ab 360 px); breite Tabellen scrollen in ihrem eigenen Bereich (siehe
  [`_docs/design-system.md`](_docs/design-system.md)).

## Roadmap

Phase 3 ist abgeschlossen. Die nächsten Kandidaten aus der
[Spezifikation für Phase 3](_docs/open_sales_analytics_phase_3_spec.md#20-deferred-roadmap):

- **Phase 4: Grundlage für ein verwaltetes Produkt.** Zentrale Anwendungsdatenbank, Konten, Eigentum, gespeicherte
  Datensätze und persistente Dashboards.
- **Phase 4: gehostete Datenaufnahme.** Geschützte öffentliche Uploads mit Ratenbegrenzung, Isolation,
  Missbrauchskontrollen und Überwachung.
- **Phase 4: finanzielle Vertragsschicht.** Optionale Spalten `discount_amount`, `refund_amount` und `unit_cost` mit
  Analysen für Nettoumsatz, Rabatte, Erstattungen und Marge.
- **Später:** Format-Mapper für Shopify, WooCommerce und Marktplätze; Datensätze über mehrere Dateien und Kanäle;
  Kundenaktivierung und Export mit ausdrücklichem Datenschutzmodell; größere asynchrone Importe; Prognosen oder
  Anomalieerkennung erst nach validiertem Nutzerbedarf.

## Architektur

Ein React-(Vite-)Frontend mit Recharts spricht über JSON mit einem FastAPI-Backend. Jeder Datensatz ist eine
DuckDB-Datei unter `DATASET_DIR`; Validierung und Analysen sind SQL auf dieser Datei. Der kanonische Import erstellt
wiederverwendbare `order_facts`, `product_facts` und bei identifizierten Kundendaten `customer_facts` aus der
Gesamthistorie in derselben Datei. Eine prozessinterne Hintergrundtask entfernt abgelaufene Datensätze. Das Docker-Image
ist ein einzelner Container, in dem FastAPI API und gebautes Frontend vom selben Origin über Port 8000 ausliefert.
Siehe [Architekturleitfaden für Phase 3](_docs/architecture.de-DE.md), [Metrikkatalog](_docs/metrics.de-DE.md),
[Release-Checkliste und Nachweisbericht](_docs/phase-3-release-checklist.md),
[Spezifikation für Phase 3](_docs/open_sales_analytics_phase_3_spec.md) und [Backlog](_docs/tasks.md).

## Entwicklung

Organisation der Arbeit: [`_docs/process.md`](_docs/process.md). Testkonventionen:
[`_docs/testing-guidelines.md`](_docs/testing-guidelines.md).
Befehle und Ergebnisse der Performance-Basislinie: [`_docs/benchmarks.md`](_docs/benchmarks.md).

Vom Repository-Stammverzeichnis:

```sh
uv sync
uv run pytest
```

Lint- und Typprüfungen (dieselben Befehle wie in CI; `uv sync` installiert `ruff` und `mypy` als Entwicklungsabhängigkeiten):

```sh
uv run ruff check backend
uv run ruff format --check backend   # `uv run ruff format backend` fixes it
uv run mypy backend/app
```

Abhängigkeitsscan (dieselben zwei Befehle wie im CI-Job `dependency-scan`; `uvx` führt `pip-audit` aus, ohne es zur
Projektabhängigkeit zu machen):

```sh
uv export --locked --no-emit-project --format requirements-txt -o /tmp/requirements.txt
uvx pip-audit@2.10.1 -r /tmp/requirements.txt --no-deps --disable-pip
(cd frontend && npm audit --audit-level=high)
```

Backend starten (unter http://127.0.0.1:8000):

```sh
uv run uvicorn app.main:app --app-dir backend
```

Prüfung: `curl http://127.0.0.1:8000/api/health` gibt `{"status":"ok"}` zurück. Um das gebaute Frontend ohne Docker
vom selben Origin auszuliefern, führe zuerst `npm run build` in `frontend/` aus (siehe unten), starte dann das Backend
wie oben und öffne <http://127.0.0.1:8000>.

### Frontend

Benötigt Node 22 oder neuer. In `frontend/`:

```sh
npm ci            # install
npm run dev       # dev server on http://localhost:5173
npm test          # Vitest, single run
npm run lint      # ESLint
npm run typecheck # tsc --noEmit (TypeScript 7)
npm run build     # type check, then the production bundle in frontend/dist
```

`npm run dev` leitet `/api` an das Backend auf Port 8000 weiter; starte daher auch das Backend.

### Erforderliche CI-Checks

Das Zusammenführen in `main` soll diese vier Checks erfordern, exakt wie GitHub sie auf einem Pull Request anzeigt
(Settings, Branches oder Rules, „Require status checks to pass“, dann jeden Namen auswählen):

- `Backend (tests, ruff, mypy)`
- `Frontend (tests, lint, type check, build)`
- `Dependency scan (Python, npm) / Dependency scan (Python, npm)`
- `Container (build, smoke, browser tests)`

Der Abhängigkeitsscan ist ein Aufruf des wiederverwendbaren Workflows `.github/workflows/dependency-scan.yml`; GitHub
zeigt den Namen daher zweimal als `<calling job> / <called job>`. Wähle in der Branch Protection diesen vollständigen,
doppelten Namen; das einfache `Dependency scan (Python, npm)` passt zu keinem Checklauf. Wenn du einen Job unter
`.github/workflows/` umbenennst, aktualisiere Liste und Schutzregel in derselben Änderung, denn ein nicht mehr
existierender erforderlicher Check blockiert jede Zusammenführung. Vergleiche auf einem Pull Request mit
`gh pr checks <number>`.

### Abhängigkeitsscans

CI scannt beide Lockfiles bei jedem Pull Request und jedem Push auf `main` sowie jeden Montag um 05:17 UTC
(`.github/workflows/dependency-scan-scheduled.yml`), sodass eine neue Meldung zu unverändertem Lockfile einen Lauf rot
macht, ohne auf den nächsten Pull Request zu warten. Beide rufen dieselbe Definition
`.github/workflows/dependency-scan.yml` auf; Befehle und Richtlinie unten sind damit identisch. Der geplante Lauf hat
`contents: read`, keine Secrets und kann im Actions-Tab auch manuell („Run workflow“) gestartet werden.

| Ökosystem | Werkzeug und Eingabe | Lässt CI fehlschlagen bei |
| --- | --- | --- |
| Python | `pip-audit` über `uv.lock` (Laufzeit- und Entwicklungspakete) | jeder bekannten Sicherheitslücke (`pip-audit` hat keinen Schweregradfilter) |
| npm | `npm audit --audit-level=high` über `frontend/package-lock.json` | hohen und kritischen Meldungen; niedrige und mittlere erscheinen im Protokoll, schlagen aber nicht fehl |

Ein Scannerfehler (kein Netzwerk, schlechte Eingabe) lässt den Job ebenfalls scheitern; Schritte enthalten weder
`|| true` noch `continue-on-error`. Es gibt keine Ignorierliste. Hat eine Meldung noch keine Korrektur, ist der Ausweg
ein geprüfter Pull Request, der im Scanbefehl eine Ausnahme mit Meldungs-ID und Begründung daneben festschreibt
(`pip-audit --ignore-vuln ID` oder Paket entfernen); niemals ein stilles Überspringen. Caches enthalten nur
Paketdownloads und den Playwright-Browser; keine Datensätze, Uploads, Secrets oder DuckDB-Dateien werden gecacht oder
als Artefakt hochgeladen.

Dependabot (`.github/dependabot.yml`) öffnet montags Pull Requests für veraltete Python- (`uv.lock` aus
`pyproject.toml`) und npm-Abhängigkeiten (`frontend/package-lock.json`), höchstens 5 offene je Ökosystem. Dependabot
aktualisiert nur vorhandene Abhängigkeiten und fügt nie neue hinzu. Seine Pull Requests führen dieselbe CI wie alle
anderen aus, ohne Secrets (Dependabot-Pull-Requests erhalten ein schreibgeschütztes Token); Scan, Tests, Build und
Browser-Suite laufen also gegen das geänderte Lockfile. Prüfe sie wie jede Änderung: Lies Release Notes und Lockfile-
Diff, führe nur bei grünen Checks zusammen, und starte bei einem Major-Upgrade die Anwendung einmal manuell. Ein roter
Check ist ein Grund, den Pull Request zu schließen oder zu korrigieren, niemals ihn zusammenzuführen.

Ein fehlgeschlagener geplanter Lauf erscheint als roter Lauf „Dependency scan (scheduled)“ im Actions-Tab des
Repositorys (nach Workflowname oder `event:schedule` filtern). GitHub mailt auch dem Repositoryinhaber: Bei geplanten
Workflows wird der Benutzer benachrichtigt, der zuletzt die `cron`-Zeile geändert hat. Ändert jemand anderes den Plan,
prüfe dessen Benachrichtigungseinstellungen (Settings, Notifications, Actions). Geplante Workflows laufen nur auf dem
Standardbranch und werden von GitHub nach 60 Tagen ohne Repositoryaktivität pausiert; aktiviere sie dann im Actions-Tab erneut.

### Container-Images pinnen

Entscheidung: Die Basisimages im `Dockerfile` (`node:26`, `python:3.14-slim`) sind per Digest gepinnt
(`FROM image:tag@sha256:...`, der Multiarchitektur-Index-Digest). Grund: Ein Tag bewegt sich, zwei Builds desselben
Commits könnten sich unterscheiden, und eine ungeprüfte vorgelagerte Änderung könnte den Build brechen oder
kompromittieren. Ein Digest macht den Build reproduzierbar und jede Basisimage-Änderung zu einem geprüften Pull Request.
Dependabot (`docker`-Eintrag in `.github/dependabot.yml`, montags) aktualisiert Tag und Digest zusammen, und der
CI-Job `docker-smoke` baut und startet den Container auf dem neuen Image vor dem Zusammenführen. Ermittle für ein
manuelles Update den Digest des gewünschten Tags und ersetze beide Teile der `FROM`-Zeile. Das mit
`COPY --from=ghcr.io/astral-sh/uv:0.8` kopierte `uv`-Image bleibt vorerst bei seinem Tag.

### Gepinnte Actions

Der Job `pinned-actions` in `.github/workflows/ci.yml` schlägt fehl, wenn ein `uses:` unter `.github` weder lokaler
Pfad (`./.github/workflows/...`) noch `owner/repo@<40 hex characters>` ist; die Fehlerannotation nennt Datei und Zeile.
Schreibe Pins als `uses: owner/repo@<sha> # vX.Y.Z`; Dependabot hält SHA und Kommentar aktuell. Der Check ist ein
Shellschritt mit `contents: read`, ohne Secret und ohne Drittanbieter-Action außer `actions/checkout`; er läuft daher
auch auf Pull Requests aus Forks und von Dependabot.

### Browser-Test

Eine kleine Playwright-Suite (Chromium, `frontend/e2e/`) deckt die Hauptabläufe ab: Try sample data, gültiger Upload,
ungültiger Upload, Datumsbereich und Reset, Analyze another file, modulübergreifender Kundenablauf, responsive Layouts
bei 360/768/1280 px und ein abgelaufener Datensatz. Installiere den Browser einmal (etwa 150 MB, außerhalb des
Repositorys gespeichert) und führe ihn dann in `frontend/` aus:

```sh
npx playwright install chromium
npx playwright install-deps chromium   # Linux only: system libraries, needs sudo; CI runs it too
npm run e2e
```

`npm run e2e` startet Backend (Port 8000) und Vite-Entwicklungsserver (Port 5173) mit temporärem Datensatzverzeichnis
selbst und stoppt sie danach. Beide Ports müssen frei sein. Setze `E2E_BASE_URL`, um eine bereits laufende Anwendung
(zum Beispiel den Container) zu testen; dann wird kein Server gestartet. Diese Anwendung muss mit
`DATASET_TTL_SECONDS=60` laufen, weil der Ablauf-Test mit begrenztem Polling auf einen echten Ablauf wartet:

```sh
docker build -t open-sales-analytics .   # from the repository root
docker run -d --name oca -p 8000:8000 -e DATASET_TTL_SECONDS=60 open-sales-analytics
curl -f http://localhost:8000/api/health   # answers {"status":"ok"}; repeat for a few seconds until it does
curl -f http://localhost:8000/d/anything | grep -i '<div id="root"'   # the single-page app
E2E_BASE_URL=http://localhost:8000 npm run e2e
docker rm -f oca
```

Bei einem Fehler werden Trace und Screenshot in `frontend/test-results/` gespeichert (Trace mit
`npx playwright show-trace` öffnen). Wenn `CI` gesetzt ist (wie in GitHub Actions), wird kein Trace aufgenommen, weil
er Netzwerkantworten enthält; CI lädt nur Fehlerscreenshots hoch.

## Mitwirken

Fehlerberichte, Ideen und Pull Requests sind willkommen; siehe [`CONTRIBUTING.md`](CONTRIBUTING.de-DE.md).

## Lizenz

Lizenziert unter der [Apache License, Version 2.0](LICENSE).
