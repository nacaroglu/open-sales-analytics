# Metrikkatalog

[English](metrics.md) | [Türkçe](metrics.tr-TR.md) | [Deutsch](metrics.de-DE.md) | [Русский](metrics.ru-RU.md) | [Español](metrics.es-ES.md) | [简体中文](metrics.zh-CN.md) | [日本語](metrics.ja-JP.md)

> Maßgeblich für die Richtigkeit dieser Übersetzung ist das [englische Dokument](metrics.md). Synchronisierungsrevision: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

Dieser Katalog folgt `backend/app/analytics/shared/metrics.py`. Alle Bereiche sind inklusiv. „Nicht verfügbar“ bedeutet,
dass das Modul für die Datei oder den Vergleich keine Antwort liefern kann; „unzureichende Daten“, dass der
Schwellenwert der Metrik nicht erreicht ist; ein „Nullergebnis“ ist eine gültige Antwort ohne passende Zeilen. Die
Kennzahl ist immer **Bruttoumsatz**, niemals Revenue.

| Schlüssel | UI-Name | Formel / Zähler | Nenner | Fenster, Anker und Einschränkung |
| --- | --- | --- | --- | --- |
| `first_purchase` | Erster Kauf | Frühestes Bestelldatum in der gesamten Historie | — | Gesamte hochgeladene Historie; keine identifizierte Bestellung bedeutet nicht verfügbar |
| `acquisition_cohort` | Akquisitionskohorte | Kalendermonat des ersten Kaufs | — | Gesamte Historie; der Monat wird durch seinen ersten Tag dargestellt |
| `gross_sales` | Bruttoumsatz | `SUM(quantity × unit_price)` | — | Aktiver Bereich; ohne Verkäufe wird 0 zurückgegeben |
| `orders` | Eindeutige Bestellungen | `COUNT(DISTINCT order_id)` | — | Aktiver Bereich; ohne Bestellungen wird 0 zurückgegeben |
| `units_sold` | Verkaufte Einheiten | `SUM(quantity)` | — | Aktiver Bereich; ohne Einheiten wird 0 zurückgegeben |
| `average_order_value` | Durchschnittlicher Bestellwert | Bruttoumsatz | Eindeutige Bestellungen | Aktiver Bereich; ohne Bestellungen wird 0 zurückgegeben |
| `change_percent` | Prozentuale Änderung | `(current - comparison) / comparison × 100` | Vergleichswert | Gewählter Vergleich; Nullbasis verwendet einen Textstatus und absolute Änderung |
| `product_revenue_share` | Bruttoumsatzanteil | Produktbruttoumsatz | Gesamtbruttoumsatz | Kompatibilitätsschlüssel; aktiver Bereich; bei Gesamtsumme null nicht verfügbar |
| `gross_sales_share` | Bruttoumsatzanteil | Produktbruttoumsatz | Gesamtbruttoumsatz | Aktiver Bereich; bei Gesamtsumme null nicht verfügbar |
| `cumulative_share` | Kumulierter Bruttoumsatzanteil | Laufender Produktbruttoumsatz | Gesamtbruttoumsatz | Absteigende Produktreihenfolge; bei Gesamtsumme null nicht verfügbar |
| `top_20_percent_share` | Anteil der besten 20 % der Produkte | Bruttoumsatz der ersten `ceil(0.2 × product_count)` Produkte | Gesamtbruttoumsatz | Aktiver Bereich; bei Gesamtsumme null nicht verfügbar |
| `products_to_80_percent` | Produkte bis 80 % des Bruttoumsatzes | Kleinster qualifizierender Produktpräfix | Gesamtbruttoumsatz | Aktiver Bereich; bei Gesamtsumme null nicht verfügbar |
| `product_growth` | Wachstum des Produktbruttoumsatzes | Aktueller minus Vergleichsbruttoumsatz | — | Gewählter Vergleich; nicht verfügbar, wenn Basis nicht verfügbar |
| `rising_products` | Steigende Produkte | Anzahl mit positiver Bruttoumsatzänderung | — | Gewählter Vergleich; Zeichen und Wörter werden gezeigt, nicht nur Farbe |
| `falling_products` | Fallende Produkte | Anzahl mit negativer Bruttoumsatzänderung | — | Gewählter Vergleich; Zeichen und Wörter werden gezeigt, nicht nur Farbe |
| `new_products` | Neue Produkte | Aktuell vorhanden, im Vergleich nicht | — | Gewählter Vergleich; ohne Vergleich nicht verfügbar |
| `no_current_sales_products` | Produkte ohne aktuelle Verkäufe | Im Vergleich vorhanden, aktuell nicht | — | Gewählter Vergleich; ohne Vergleich nicht verfügbar |
| `unchanged_products` | Unveränderte Produkte | Gleicher Bruttoumsatz in beiden Zeiträumen | — | Gewählter Vergleich; ohne Vergleich nicht verfügbar |
| `growth_rank_absolute_change` | Produktrang nach Wachstum | Rang nach absoluter Bruttoumsatzänderung | — | Gewählter Vergleich; winzige Basiswerte dominieren nicht |
| `dormancy` | Inaktive Produkte | Produkte, bei denen Anker minus letzter Verkauf mindestens dem Fenster entspricht | — | Anker ist Ende des gewählten Bereichs; Fenster 30, 60 oder 90 Tage; Historie kann unzureichend sein |
| `cumulative_revenue_share` | Kumulierter Bruttoumsatzanteil | Laufender absteigender Produktbruttoumsatz | Gesamtbruttoumsatz | Kompatibilitätsschlüssel; aktiver Bereich; bei Gesamtsumme null nicht verfügbar |
| `weighted_unit_price` | Gewichteter realisierter Stückpreis | `SUM(quantity × unit_price)` | `SUM(quantity)` | Täglicher/wöchentlicher/monatlicher Bucket im aktiven Bereich; ohne Einheiten nicht verfügbar; keine Elastizitätsaussage |
| `order_penetration` | Bestelldurchdringung | Bestellungen mit Produkt | Alle Bestellungen | Aktiver Bereich; ohne Bestellungen Nullergebnis |
| `basket_support` | Warenkorb-Support | Gemeinsame Bestellungen für A und B | Geeignete Warenkorbbestellungen | Mindestens 10 gemeinsame Bestellungen und 0,1 % Support; Bestellungen mit >100 Produkten nur hier ausgeschlossen |
| `basket_confidence` | Warenkorb-Konfidenz | Gemeinsame Bestellungen für A und B | Bestellungen mit Ausgangsprodukt | Gleiche Warenkorbschwellen; Richtung ist relevant |
| `basket_lift` | Warenkorb-Lift | Gerichtete Konfidenz | Support des Zielprodukts | Gleiche Warenkorbschwellen; vergleicht beobachtete Paarrate mit Ziel-Support |
| `identified_customers` | Identifizierte Kunden | Eindeutige identifizierte Kunden-IDs | — | Aktiver Bereich; keine ergeben ein Nullergebnis |
| `customer_coverage` | Kundenabdeckung | Identifizierte eindeutige Bestellungen | Alle eindeutigen Bestellungen | Bestellabdeckung für Datensatz/Bereich; <50 % unterdrückt, 50–<80 % Warnung, ≥80 % normal |
| `new_vs_returning` | Bruttoumsatz neuer gegenüber wiederkehrenden Kunden | Identifizierter Bruttoumsatz, geteilt nach erstem Bestelldatum der Gesamthistorie | — | Aktiver Bereich; Anker der ersten Bestellung nutzt vollständige Historie |
| `repeat_purchase` | Wiederkaufsrate | Aktive Kunden mit ≥2 eindeutigen Bestellungen bis zum Ende | Aktive identifizierte Kunden | Bestellungen vor Bereichsbeginn zählen; ohne aktive Kunden unzureichend |
| `days_between_purchases` | Tage zwischen Käufen | Median der Intervalle aufeinanderfolgender identifizierter Bestelldaten | — | Spätere Bestellung muss im Bereich liegen; Intervall am selben Tag ist 0; feste inklusive Buckets |
| `cohort_retention` | Kohortenbindung | Gebundene Kunden in Kohorte/Monatsversatz | Größe der Kohorte aus vollständiger Historie | Stichtag ist gewähltes Ende; zukünftige Zellen heißen Noch nicht beobachtet, niemals 0 |
| `historical_customer_value` | Historischer Kundenwert | Beobachteter identifizierter Bruttoumsatz je Kunde; Median des Werts je Kunde | Identifizierte Kunden | Nur beobachtet, keine Prognose; Kohortenzugehörigkeit nutzt Akquisitionsmonat aus Gesamthistorie |
| `projected_customer_value` | Prognostizierter 12-Monats-Kundenwert | Beobachteter Wert plus inkrementelle Schätzung reifer Kohorten | Identifizierte Kunden | Nur Schätzung: 18 Monate Historie, 500 Kunden, 70 % Abdeckung, 5 reife Kohorten, 12-Monats-Horizont |
| `rfm` | RFM-Segmente | Relative Quintilswerte für Aktualität, Häufigkeit und Geldwert; `FM = F + M` | Identifizierte Kunden | Bis zum gewählten Ende; weniger als 5 unzureichend; relativ zu diesem Upload, kein Benchmark |
| `rfm_drilldown` | RFM-Segmentdetails | Aggregierte Segmentzahlen, Bruttoumsatz und feste Verteilungen | Segmentsummen | Nur aggregiert; keine Kunden-IDs; gleiche RFM-Einschränkung |
| `purchase_frequency` | Kaufhäufigkeit | Nach Anzahl eindeutiger identifizierter Bestellungen gruppierte Kunden | Identifizierte Kunden bis Ende | Feste Buckets 1, 2, 3, 4, 5, 6–10, 11–20, 21+ |
| `concentration` | Kundenkonzentration | Bruttoumsatz der obersten `ceil(N / 10)` Kunden | Identifizierter Bruttoumsatz | Aktiver Bereich; weniger als 10 Kunden oder Umsatz null ist unzureichend |

Die Projektion ist eine Schätzung, keine Garantie und keine Kausalitäts-/Gewinnkennzahl. Kunden-IDs sind pseudonym,
nicht anonym; alle Kundenantworten sind ausschließlich aggregiert und legen keine Listen, Suche, Exporte oder Werte je
Kunde offen.
