# Mimari

[English](architecture.md) | [Türkçe](architecture.tr-TR.md) | [Deutsch](architecture.de-DE.md) | [Русский](architecture.ru-RU.md) | [Español](architecture.es-ES.md) | [简体中文](architecture.zh-CN.md) | [日本語](architecture.ja-JP.md)

> Bu çevirinin doğruluk kaynağı [İngilizce belgedir](architecture.md). Eşitleme revizyonu: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

Open Sales Analytics, FastAPI tarafından sunulan tek kaynaklı bir React/Vite uygulamasıdır. Frontend, veri kümesi
tanımlayıcısını ve bearer token'ını tek bir tarayıcı sekmesinin `sessionStorage` alanında tutar; tarih aralığı ve
karşılaştırma seçimlerini backend'e gönderir ve toplu yanıtları işler. Backend, her veri kümesi için bir DuckDB dosyası
ve sınırlandırılmış, sürece yerel yanıt önbelleği dışında istekler arasında durum tutmaz.

## Depo alanları

| Alan | Gerçek yol | Sorumluluk |
| --- | --- | --- |
| API ve yaşam döngüsü | `backend/app/api/`, `backend/app/auth.py`, `backend/app/cleanup.py` | Yükleme/örnek oluşturma, yetkilendirme, süre sonu, meta veriler ve yanıt zarfları |
| Genel bakış | `backend/app/analytics/overview/` | Brüt satış, benzersiz siparişler, birimler, ortalama sipariş değeri, eğilimler ve karşılaştırmalar |
| Ürünler | `backend/app/analytics/products/` | Sıralamalar, pay/Pareto, büyüme, hareketsizlik, fiyat geçmişi, penetrasyon ve sepet ilişkisi |
| Müşteriler | `backend/app/analytics/customers/` | Kapsam, müşteri toplamları, kohortlar, RFM ve projeksiyon |
| Paylaşılan dönemler ve kullanılabilirlik | `backend/app/analytics/shared/` | Dahilî tarih filtreleri, karşılaştırma dönemleri, kova seçimi, kullanılabilirlik ve metrik tanımları |
| İçe aktarma ve kalıcılık | `backend/app/ingest.py`, `backend/app/importer.py`, `backend/app/schema.py` | CSV doğrulama, olguları oluşturma, veri kümesi dosyasını yazma ve hazırlama verilerini kaldırma |
| Web UI | `frontend/src/` | Yükleme, panel gezinmesi, erişilebilir durumlar, tablolar ve grafiklerin metin alternatifleri |

Yetkili metrik formülleri ve durumları `backend/app/analytics/shared/metrics.py` içindedir; insan tarafından okunabilir
katalog [_docs/metrics.md](metrics.tr-TR.md) belgesidir. Aşama 3 ürün belirtimi
[_docs/open_sales_analytics_phase_3_spec.md](open_sales_analytics_phase_3_spec.md) belgesidir.

## Veri kümesi dosyası

Her yükleme, `DATASET_DIR` altında özel bir DuckDB dosyasına dönüşür. İçe aktarma yeniden kullanılabilir olguları bir
kez hesaplar; istek zamanındaki sorgular bu olguları seçili dahilî aralığa ve karşılaştırma dönemine göre filtreler.

| Tablo | Sütunlar | Anlam |
| --- | --- | --- |
| `line_items` | `order_id`, `order_date`, `product_id`, `product_name`, `quantity`, `unit_price`, nullable `customer_id` | Doğrulanmış kaynak satırlar; isteğe bağlı opak müşteri kimliğiyle ürün satırı başına bir kayıt |
| `order_facts` | `order_id`, `first_order_date`, `last_order_date`, `line_count`, `units`, `gross_sales` | Sipariş başına bir kayıt ve yaşam boyu satır/sipariş toplamları |
| `product_facts` | `product_id`, `product_name`, `first_sale_date`, `last_sale_date`, `lifetime_gross_sales`, `lifetime_units`, `lifetime_orders` | Ürün başına bir kayıt ve yaşam boyu portföy olguları |
| `customer_facts` | `customer_id`, `first_order_date`, `acquisition_month`, `first_day_orders`, `last_order_date`, `lifetime_orders`, `lifetime_units`, `lifetime_gross_sales` | Tanımlanmış müşteri başına bir kayıt; altı sütunlu verilerde yoktur veya boştur |
| `dataset_meta` | `id`, `currency`, `created_at`, `expires_at`, `token_hash`, `row_count`, `has_customer_id`, `identified_orders`, `unidentified_orders`, `total_orders` | Veri kümesi kimliği, yaşam döngüsü, gizliliği koruyan token doğrulaması ve kapsam sayıları |

Ham yükleme baytları yalnızca doğrulama/içe aktarma sırasında hazırlanır ve içe aktarma tamamlandığında silinir. Türetilmiş
tablolar veri kümesiyle birlikte silinir. Müşteri olguları yalnızca takma adlı kimlikler içerir ve asla müşteri listesi
olarak döndürülmez.

## İstek akışı

1. `POST /api/datasets` çok parçalı CSV'yi doğrular, satır ve satırlar arası kuralları uygular, DuckDB olgularını
   oluşturur, yalnızca SHA-256 token karmasını saklar ve veri kümesi kimliğini, tek kullanımlık token'ı, meta verileri
   ve ilk genel bakışı döndürür.
2. `require_dataset`, bir modül işleyicisi çalışmadan önce bearer başlığını, veri kümesi kimliğini, dosya
   okunabilirliğini, süre sonunu ve token'ı doğrular. Yetkilendirme, önbellek isabetleri dahil her istekten önce yapılır.
3. İşleyici dahilî etkin aralığı ve karşılaştırma modunu çözümler, bir önbellek anahtarı oluşturur ve ya başarıyla
   önbelleğe alınmış JSON gövdesini döndürür ya da veri kümesini salt okunur açıp modül yanıtını hesaplar.
4. Yanıt yalnızca toplu JSON'dur. Önbellek yalnızca başarılı serileştirilmiş gövdeleri; veri kümesi kimliği, modül,
   etkin tarihler, karşılaştırma modu ve modül seçeneklerini içeren bir anahtarla saklar.
5. Veri kümesinin süresinin dolması, açıkça silinmesi ve temizlik taraması veri kümesinin önbellek girdilerini geçersiz
   kılar. Önbellek sürece yereldir, iş parçacığı güvenlidir, LRU ile sınırlandırılmıştır ve girdileri kendi TTL'si ile
   veri kümesi süre sonundan erken olanında sona erdirir.

## API yüzeyi

Herkese açık sağlık, yapılandırma ve örnek indirme rotaları dışında tüm veri kümesi rotaları
`Authorization: Bearer <token>` gerektirir. Canlı OpenAPI şeması yetkili kaynaktır; bu tablo
`backend/tests/test_documentation.py` tarafından ona göre kontrol edilir.

| Yöntem | Yol | Yetki | Amaç ve ana seçenekler |
| --- | --- | --- | --- |
| GET | `/api/health` | Hayır | Canlılık kontrolü |
| GET | `/api/config` | Hayır | Herkese açık demo bayrağı ve yükleme sınırları; asla sırlar veya yollar değil |
| POST | `/api/datasets` | Hayır | Çok parçalı yükleme; `currency` form alanı |
| POST | `/api/datasets/sample` | Hayır | Paketlenmiş örneği USD olarak içe aktar |
| GET | `/api/sample.csv` | Hayır | Paketlenmiş örnek CSV'yi indir |
| GET | `/api/datasets/{id}` | Evet | Veri kümesi meta verileri, yetenekleri, kapsamı ve süre sonu |
| GET | `/api/datasets/{id}/analytics` | Evet | Eski genel bakış özeti; isteğe bağlı `start`, `end` |
| DELETE | `/api/datasets/{id}` | Evet | Veri kümesini sil ve önbelleğini geçersiz kıl |
| GET | `/api/datasets/{id}/overview` | Evet | Genel bakış KPI'ları ve eğilim; `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/products` | Evet | Portföy analitiği; `start`, `end`, `comparison`, `dormancy_days` |
| GET | `/api/datasets/{id}/products/detail` | Evet | Ürün ayrıntısı; `product_id`, `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/customers` | Evet | Müşteri toplamları ve projeksiyon; `start`, `end`, `comparison` |

## Dağıtım yapısı

Docker imajı frontend'i bir Node aşamasında derler, backend ortamını `uv` ile kurar ve tek bir FastAPI süreci
çalıştırır. FastAPI, derlenmiş SPA'yı ve `/api`yi 8000 portundan sunar. Veri kümelerinin yeniden başlatmadan sonra
kalması gerektiğinde `DATASET_DIR` özel bir kalıcı birim olmalıdır; paylaşılan bir veritabanı ya da yatay ölçekleme
katmanı yoktur.
