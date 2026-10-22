# Metrik kataloğu

[English](metrics.md) | [Türkçe](metrics.tr-TR.md) | [Deutsch](metrics.de-DE.md) | [Русский](metrics.ru-RU.md) | [Español](metrics.es-ES.md) | [简体中文](metrics.zh-CN.md) | [日本語](metrics.ja-JP.md)

> Bu çevirinin doğruluk kaynağı [İngilizce belgedir](metrics.md). Eşitleme revizyonu: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

Bu katalog `backend/app/analytics/shared/metrics.py` dosyasını izler. Tüm aralıklar iki ucu da kapsar. “Kullanılamıyor”
modülün dosya veya karşılaştırma için yanıt veremediği, “yetersiz veri” metriğin eşiğinin karşılanmadığı, “sıfır sonuç”
ise eşleşen satırı olmayan geçerli bir yanıt anlamına gelir. Ölçü her zaman **brüt satış**tır; asla revenue değildir.

| Anahtar | UI adı | Formül / pay | Payda | Pencere, dayanak ve uyarı |
| --- | --- | --- | --- | --- |
| `first_purchase` | İlk satın alma | Tüm geçmişteki en erken sipariş tarihi | — | Yüklenen geçmişin tamamı; tanımlanmış sipariş yoksa kullanılamaz |
| `acquisition_cohort` | Edinme kohortu | İlk satın almayı içeren takvim ayı | — | Tüm geçmiş; ay, ilk günüyle temsil edilir |
| `gross_sales` | Brüt satış | `SUM(quantity × unit_price)` | — | Etkin aralık; satış yoksa 0 döner |
| `orders` | Benzersiz siparişler | `COUNT(DISTINCT order_id)` | — | Etkin aralık; sipariş yoksa 0 döner |
| `units_sold` | Satılan birimler | `SUM(quantity)` | — | Etkin aralık; birim yoksa 0 döner |
| `average_order_value` | Ortalama sipariş değeri | Brüt satış | Benzersiz siparişler | Etkin aralık; sipariş yoksa 0 döner |
| `change_percent` | Yüzde değişim | `(current - comparison) / comparison × 100` | Karşılaştırma değeri | Seçili karşılaştırma; sıfır taban sözel bir durum ve mutlak değişim kullanır |
| `product_revenue_share` | Brüt satış payı | Ürün brüt satışı | Toplam brüt satış | Uyumluluk anahtarı; etkin aralık; toplam sıfırsa kullanılamaz |
| `gross_sales_share` | Brüt satış payı | Ürün brüt satışı | Toplam brüt satış | Etkin aralık; toplam sıfırsa kullanılamaz |
| `cumulative_share` | Kümülatif brüt satış payı | İşleyen ürün brüt satışı | Toplam brüt satış | Azalan ürün sırası; toplam sıfırsa kullanılamaz |
| `top_20_percent_share` | En üst %20 ürün payı | İlk `ceil(0.2 × product_count)` ürünün brüt satışı | Toplam brüt satış | Etkin aralık; toplam sıfırsa kullanılamaz |
| `products_to_80_percent` | Brüt satışın %80'ine ulaşan ürünler | En küçük uygun ürün öneki | Toplam brüt satış | Etkin aralık; toplam sıfırsa kullanılamaz |
| `product_growth` | Ürün brüt satış büyümesi | Güncel brüt satış eksi karşılaştırma brüt satışı | — | Seçili karşılaştırma; taban kullanılamıyorsa kullanılamaz |
| `rising_products` | Yükselen ürünler | Pozitif brüt satış değişimine sahip sayı | — | Seçili karşılaştırma; yalnız renk değil, işaretler ve sözcükler gösterilir |
| `falling_products` | Düşen ürünler | Negatif brüt satış değişimine sahip sayı | — | Seçili karşılaştırma; yalnız renk değil, işaretler ve sözcükler gösterilir |
| `new_products` | Yeni ürünler | Güncelde var, karşılaştırmada yok | — | Seçili karşılaştırma; karşılaştırma yoksa kullanılamaz |
| `no_current_sales_products` | Güncel satışı olmayan ürünler | Karşılaştırmada var, güncelde yok | — | Seçili karşılaştırma; karşılaştırma yoksa kullanılamaz |
| `unchanged_products` | Değişmeyen ürünler | Her iki dönemde de eşit brüt satış | — | Seçili karşılaştırma; karşılaştırma yoksa kullanılamaz |
| `growth_rank_absolute_change` | Ürün büyüme sırası | Mutlak brüt satış değişimine göre sırala | — | Seçili karşılaştırma; küçük tabanlar baskın olmaz |
| `dormancy` | Hareketsiz ürünler | Dayanak eksi son satışın en az pencere kadar olduğu ürünler | — | Dayanak seçili aralığın sonudur; pencere 30, 60 veya 90 gündür; geçmiş yetersiz olabilir |
| `cumulative_revenue_share` | Kümülatif brüt satış payı | Azalan ürün brüt satışının işleyen toplamı | Toplam brüt satış | Uyumluluk anahtarı; etkin aralık; toplam sıfırsa kullanılamaz |
| `weighted_unit_price` | Ağırlıklı gerçekleşen birim fiyat | `SUM(quantity × unit_price)` | `SUM(quantity)` | Günlük/haftalık/aylık etkin aralık kovası; birim yoksa kullanılamaz; esneklik iddiası yoktur |
| `order_penetration` | Sipariş penetrasyonu | Ürünü içeren siparişler | Tüm siparişler | Etkin aralık; sipariş yoksa sıfır sonuç |
| `basket_support` | Sepet desteği | A ve B için ortak siparişler | Uygun sepet siparişleri | En az 10 ortak sipariş ve %0,1 destek; >100 ürünlü siparişler yalnız burada dışlanır |
| `basket_confidence` | Sepet güveni | A ve B için ortak siparişler | Kaynak ürünü içeren siparişler | Aynı sepet eşikleri; yön önemlidir |
| `basket_lift` | Sepet artışı | Yönlü güven | Hedef ürün desteği | Aynı sepet eşikleri; gözlenen çift oranını hedef desteğiyle karşılaştırır |
| `identified_customers` | Tanımlanmış müşteriler | Benzersiz tanımlanmış müşteri kimlikleri | — | Etkin aralık; hiç yoksa sıfır sonuç |
| `customer_coverage` | Müşteri kapsamı | Tanımlanmış benzersiz siparişler | Tüm benzersiz siparişler | Veri kümesi/aralık sipariş kapsamı; <%50 gizlenir, %50–<%80 uyarı, ≥%80 normal |
| `new_vs_returning` | Yeni ve geri dönen müşteri brüt satışı | İlk tam geçmiş sipariş tarihine göre bölünmüş tanımlanmış brüt satış | — | Etkin aralık; ilk sipariş dayanağı tüm geçmişi kullanır |
| `repeat_purchase` | Tekrar satın alma oranı | Son tarihe kadar ≥2 benzersiz siparişi olan etkin müşteriler | Etkin tanımlanmış müşteriler | Aralık başlangıcından önceki siparişler sayılır; etkin müşteri yoksa yetersiz |
| `days_between_purchases` | Satın almalar arasındaki günler | Ardışık tanımlanmış sipariş tarihi aralıklarının medyanı | — | Sonraki sipariş aralıkta olmalı; aynı gün aralığı 0'dır; sabit dahilî kovalar |
| `cohort_retention` | Kohort elde tutma | Kohort/ay uzaklığındaki elde tutulan müşteriler | Tüm geçmiş kohort boyutu | Kesim seçili sondur; gelecek hücreler 0 değil Henüz gözlenmedi der |
| `historical_customer_value` | Geçmiş Müşteri Değeri | Müşteri başına gözlenmiş tanımlanmış brüt satış; müşteri başı değer medyanı | Tanımlanmış müşteriler | Yalnız gözlem, tahmin yok; kohort üyeliği tüm geçmiş edinme ayını kullanır |
| `projected_customer_value` | Öngörülen 12 Aylık Müşteri Değeri | Gözlenen değer artı olgun kohort artış tahmini | Tanımlanmış müşteriler | Yalnız tahmin: 18 aylık geçmiş, 500 müşteri, %70 kapsam, 5 olgun kohort, 12 aylık ufuk |
| `rfm` | RFM segmentleri | Göreli güncellik, sıklık ve parasal beşte birlik puanları; `FM = F + M` | Tanımlanmış müşteriler | Seçili sona kadar; 5'ten azı yetersiz; bu yüklemeye görelidir, kıyas ölçütü değildir |
| `rfm_drilldown` | RFM segment ayrıntıları | Toplu segment sayıları, brüt satış ve sabit dağılımlar | Segment toplamları | Yalnız toplu; müşteri kimliği yok; aynı RFM uyarısı |
| `purchase_frequency` | Satın alma sıklığı | Benzersiz tanımlanmış sipariş sayısına göre gruplanmış müşteriler | Sona kadar tanımlanmış müşteriler | Sabit kovalar 1, 2, 3, 4, 5, 6–10, 11–20, 21+ |
| `concentration` | Müşteri yoğunlaşması | İlk `ceil(N / 10)` müşterinin brüt satışı | Tanımlanmış brüt satış | Etkin aralık; 10'dan az müşteri veya sıfır satış yetersizdir |

Projeksiyon bir tahmindir; garanti ya da nedensellik/kâr ölçüsü değildir. Müşteri kimlikleri takma adlıdır, anonim
değildir; tüm müşteri yanıtları yalnızca topludur ve listeleri, aramayı, dışa aktarımı veya müşteri başına değerleri
açığa çıkarmaz.
