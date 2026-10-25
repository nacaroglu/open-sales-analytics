# Architektur

[English](architecture.md) | [Türkçe](architecture.tr-TR.md) | [Deutsch](architecture.de-DE.md) | [Русский](architecture.ru-RU.md) | [Español](architecture.es-ES.md) | [简体中文](architecture.zh-CN.md) | [日本語](architecture.ja-JP.md)

> Maßgeblich für die Richtigkeit dieser Übersetzung ist das [englische Dokument](architecture.md). Synchronisierungsrevision: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

Open Sales Analytics ist eine von FastAPI ausgelieferte React/Vite-Anwendung mit einem einzigen Origin. Das Frontend
bewahrt Datensatzkennung und Bearer-Token im `sessionStorage` eines einzelnen Browser-Tabs auf, sendet Datumsbereich
und Vergleichsauswahl an das Backend und stellt aggregierte Antworten dar. Das Backend ist zwischen Anfragen
zustandslos, abgesehen von einer DuckDB-Datei je Datensatz und einem begrenzten, prozesslokalen Antwortcache.

## Bereiche des Repositorys

| Bereich | Tatsächlicher Pfad | Verantwortung |
| --- | --- | --- |
| API und Lebenszyklus | `backend/app/api/`, `backend/app/auth.py`, `backend/app/cleanup.py` | Upload/Beispielerstellung, Autorisierung, Ablauf, Metadaten und Antwortumschläge |
| Übersicht | `backend/app/analytics/overview/` | Bruttoumsatz, eindeutige Bestellungen, Einheiten, durchschnittlicher Bestellwert, Trends und Vergleiche |
| Produkte | `backend/app/analytics/products/` | Ranglisten, Anteil/Pareto, Wachstum, Inaktivität, Preisverlauf, Bestelldurchdringung und Warenkorbbeziehungen |
| Kunden | `backend/app/analytics/customers/` | Abdeckung, Kundenaggregate, Kohorten, RFM und Projektion |
| Gemeinsame Zeiträume und Verfügbarkeit | `backend/app/analytics/shared/` | Inklusive Datumsfilter, Vergleichszeiträume, Bucket-Auswahl, Verfügbarkeit und Metrikdefinitionen |
| Import und Persistenz | `backend/app/ingest.py`, `backend/app/importer.py`, `backend/app/schema.py` | CSV validieren, Fakten erstellen, Datensatzdatei schreiben und Staging-Daten entfernen |
| Web-UI | `frontend/src/` | Upload, Dashboard-Navigation, zugängliche Zustände, Tabellen und Textalternativen für Diagramme |

Die maßgeblichen Formeln und Zustände der Metriken stehen in `backend/app/analytics/shared/metrics.py`; der
menschenlesbare Katalog ist [_docs/metrics.md](metrics.de-DE.md). Die Produktspezifikation für Phase 3 ist
[_docs/open_sales_analytics_phase_3_spec.md](open_sales_analytics_phase_3_spec.md).

## Datensatzdatei

Jeder Upload wird zu einer privaten DuckDB-Datei unter `DATASET_DIR`. Beim Import werden wiederverwendbare Fakten
einmal berechnet; Abfragen zur Anfragezeit filtern diese Fakten nach dem ausgewählten inklusiven Bereich und
Vergleichszeitraum.

| Tabelle | Spalten | Bedeutung |
| --- | --- | --- |
| `line_items` | `order_id`, `order_date`, `product_id`, `product_name`, `quantity`, `unit_price`, nullable `customer_id` | Validierte Quellzeilen; eine Zeile je Produktposition, mit optionaler undurchsichtiger Kunden-ID |
| `order_facts` | `order_id`, `first_order_date`, `last_order_date`, `line_count`, `units`, `gross_sales` | Eine Zeile je Bestellung und ihre lebenslangen Positions-/Bestellsummen |
| `product_facts` | `product_id`, `product_name`, `first_sale_date`, `last_sale_date`, `lifetime_gross_sales`, `lifetime_units`, `lifetime_orders` | Eine Zeile je Produkt und lebenslange Portfoliofakten |
| `customer_facts` | `customer_id`, `first_order_date`, `acquisition_month`, `first_day_orders`, `last_order_date`, `lifetime_orders`, `lifetime_units`, `lifetime_gross_sales` | Eine Zeile je identifiziertem Kunden; bei Daten mit sechs Spalten nicht vorhanden oder leer |
| `dataset_meta` | `id`, `currency`, `created_at`, `expires_at`, `token_hash`, `row_count`, `has_customer_id`, `identified_orders`, `unidentified_orders`, `total_orders` | Datensatzidentität, Lebenszyklus, datenschutzgerechte Tokenprüfung und Abdeckungszahlen |

Rohe Upload-Bytes werden nur während Validierung/Import zwischengespeichert und nach Abschluss des Imports gelöscht.
Abgeleitete Tabellen werden mit dem Datensatz gelöscht. Kundenfakten enthalten nur pseudonyme IDs und werden nie als
Kundenliste zurückgegeben.

## Anfrageablauf

1. `POST /api/datasets` validiert die mehrteilige CSV, wendet Zeilen- und zeilenübergreifende Regeln an, erstellt die
   DuckDB-Fakten, speichert nur einen SHA-256-Hash des Tokens und gibt Datensatz-ID, einmaliges Token, Metadaten und
   anfängliche Übersicht zurück.
2. `require_dataset` validiert Bearer-Header, Datensatz-ID, Lesbarkeit der Datei, Ablauf und Token, bevor ein
   Modul-Handler läuft. Die Autorisierung erfolgt vor jeder Anfrage, auch bei Cachetreffern.
3. Der Handler bestimmt den inklusiven aktiven Bereich und Vergleichsmodus, erstellt einen Cacheschlüssel und gibt
   entweder einen erfolgreich gecachten JSON-Inhalt zurück oder öffnet den Datensatz schreibgeschützt und berechnet
   die Modulantwort.
4. Die Antwort besteht ausschließlich aus aggregiertem JSON. Der Cache speichert nur erfolgreiche serialisierte
   Inhalte unter einem Schlüssel aus Datensatz-ID, Modul, aktiven Daten, Vergleichsmodus und Moduloptionen.
5. Ablauf, ausdrückliche Löschung und Bereinigung eines Datensatzes machen dessen Cacheeinträge ungültig. Der Cache
   ist prozesslokal, threadsicher, LRU-begrenzt und lässt Einträge zum früheren Zeitpunkt aus eigener TTL und
   Datensatzablauf verfallen.

## API-Oberfläche

Alle Datensatzrouten benötigen `Authorization: Bearer <token>`, außer den öffentlichen Routen für Status,
Konfiguration und Beispieldownload. Das aktive OpenAPI-Schema ist maßgeblich; diese Tabelle wird in
`backend/tests/test_documentation.py` dagegen geprüft.

| Methode | Pfad | Auth | Zweck und wichtigste Optionen |
| --- | --- | --- | --- |
| GET | `/api/health` | Nein | Ältere Statusantwort |
| GET | `/health/live` | Nein | Nur Prozessverfügbarkeit; keine Abhängigkeitsprüfungen |
| GET | `/health/ready` | Nein | Bereitschaft und sichere Dienstidentität |
| GET | `/api/config` | Nein | Öffentlicher Demo-Schalter und Uploadgrenzen; niemals Geheimnisse oder Pfade |
| POST | `/api/datasets` | Nein | Mehrteiliger Upload; Formularfeld `currency` |
| POST | `/api/datasets/sample` | Nein | Mitgeliefertes Beispiel in USD importieren |
| GET | `/api/sample.csv` | Nein | Mitgelieferte Beispiel-CSV herunterladen |
| GET | `/api/datasets/{id}` | Ja | Metadaten, Fähigkeiten, Abdeckung und Ablauf des Datensatzes |
| GET | `/api/datasets/{id}/analytics` | Ja | Ältere Übersichts-Zusammenfassung; optional `start`, `end` |
| DELETE | `/api/datasets/{id}` | Ja | Datensatz löschen und Cache ungültig machen |
| GET | `/api/datasets/{id}/overview` | Ja | Übersichts-KPIs und Trend; `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/products` | Ja | Portfolioanalysen; `start`, `end`, `comparison`, `dormancy_days` |
| GET | `/api/datasets/{id}/products/detail` | Ja | Produktdetails; `product_id`, `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/customers` | Ja | Kundenaggregate und Projektion; `start`, `end`, `comparison` |

## Bereitstellungsform

Das Docker-Image baut das Frontend in einer Node-Stufe, installiert die Backend-Umgebung mit `uv` und führt einen
einzigen FastAPI-Prozess aus. FastAPI liefert die gebaute SPA und `/api` über Port 8000 aus. `DATASET_DIR` sollte ein
privates persistentes Volume sein, wenn Datensätze einen Neustart überstehen müssen; es gibt weder eine gemeinsame
Datenbank noch eine horizontale Skalierungsschicht.
