Warning: truncated output (original token count: 14183)
Total output lines: 733

# open-sales-analytics

[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> Bu çevirinin doğruluk kaynağı [İngilizce belgedir](README.md). Eşitleme revizyonu: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

Open Sales Analytics, kendi sunucunuzda barındırabileceğiniz küçük bir web uygulamasıdır. Tamamlanmış satış satırlarından
oluşan bir CSV yüklersiniz; uygulama değiştirilebilir bir tarih aralığında brüt satışları, siparişleri, birimleri,
ortalama sipariş değerini, satış eğilimini ve en iyi ürünleri gösterir. Brüt satış, seçilen dönemdeki satırlarda
miktarın birim fiyatla çarpımının toplamıdır. İadeler, indirimler, vergiler ve kargo buna dahil değildir.

İçindekiler: [Docker ile çalıştırma](#docker-ile-çalıştırma) | [Yapılandırma](#yapılandırma) |
[Demo adımları](#demo-adımları) | [Sonuçları inceleme](#6-sonuçları-inceleyin) |
[Ürün analitiği](#ürün-analitiği) | [Müşteri analitiği](#müşteri-analitiği) | [Karşılaştırmalar](#karşılaştırmalar) |
[Veri kümesi sözleşmesi](#veri-kümesi-sözleşmesi) | [Para birimleri](#para-birimleri) | [Gizlilik](#gizlilik) |
[Demo modu](#demo-modu) | [Sınırlamalar](#sınırlamalar) | [Yol haritası](#yol-haritası) | [Mimari](#mimari) |
[Geliştirme](#geliştirme) | [Katkıda bulunma](#katkıda-bulunma) | [Lisans](#lisans)

## Docker ile çalıştırma

Yayımlanmış bir imaj yoktur; bu nedenle bu deponun bir checkout'ından bir kez derler, sonra çalıştırırsınız:

```sh
docker build -t open-sales-analytics .
docker run -p 8000:8000 open-sales-analytics
```

<http://localhost:8000> adresini açın. Yükleme ekranını görürsünüz; **Örnek veriyi dene** örnek dosyayla bir panel açar.
`curl http://localhost:8000/api/health`, `{"status":"ok"}` döndürür.

Kapsayıcı root olmayan bir kullanıcıyla (UID 10001) çalışır ve veri kümelerini `/data` içinde tutar
(`DATASET_DIR=/data`). Birim olmadan kapsayıcı kaldırıldığında bunlar kaybolur. Saklamak için `/data` noktasına adlandırılmış
bir birim bağlayın:

```sh
docker run -p 8000:8000 -v osa-data:/data open-sales-analytics
```

Birimle birlikte veri kümeleri, en iyi çaba esasına göre `docker restart` ve kapsayıcının yeniden oluşturulmasından
sonra da kalır; her biri yine `DATASET_TTL_HOURS` sonrasında sona erer. Adlandırılmış birim yerine `/data` noktasına
bir ana makine dizini bağlarsanız, bu dizin kapsayıcının root olmayan kullanıcısı (UID 10001) tarafından yazılabilir
olmalıdır; örneğin `sudo chown 10001 /path/to/dir`.

İmaj kendi durumunu kontrol eder: `docker ps`, başlangıçtan birkaç saniye sonra `healthy`; `/api/health` yanıt vermeyi
bıraktığında `unhealthy` gösterir (her 10 s'de kontrol, 3 s zaman aşımı, 3 başarısızlık, 10 s başlangıç dönemi).
`docker stop`, arka plan temizliğini durdurduktan sonra sunucuyu 0 çıkış koduyla bir saniyeden kısa sürede sonlandırır.
Sunucu kendi istek zaman aşımını ayarlamaz (uvicorn varsayılanları geçerlidir); dolayısıyla çok yavaş bir yükleme ancak
istemci vazgeçtiğinde sona erer.

[Aşağıdaki tablodan](#yapılandırma) bir değişkeni `-e` ile geçirerek ayar sağlayın:

```sh
docker run -p 8000:8000 -e PUBLIC_DEMO_MODE=true open-sales-analytics
```

## Demo adımları

Yeni bir checkout'tan panele kadar, oluşturulmuş örnek verilerle adım adım çalıştırma.
İlk adım [uv](https://docs.astral.sh/uv/) gerektirir; geri kalanlar yalnızca Docker gerektirir.

### 1. Örnek verileri oluşturun

```bash
uv run python backend/scripts/generate_sample.py
```

Bu komut `backend/app/sample/sample_sales.csv` dosyasını yazar. Seed dosyayı belirlenimci yapar; bu yüzden komutu
çalıştıran herkes 6. adımda aynı verileri ve aynı sayıları görür. Dosya imaja kopyalandığı için bunu `docker build`
öncesinde çalıştırın.

İlk satırları kontrol edin:

```bash
head -n 4 backend/app/sample/sample_sales.csv
```

```
order_id,order_date,product_id,product_name,quantity,unit_price,customer_id
ORD-000001,2024-01-01,P001,Ceramic Mug,1,12.00,CUST-6ebe7ed43ba4
ORD-000001,2024-01-01,P002,Travel Tumbler,1,24.00,CUST-6ebe7ed43ba4
ORD-000002,2024-01-01,P001,Ceramic Mug,1,12.00,CUST-c4da5c3ce3f2
```

### 2. İmajı derleyin

```bash
docker build -t open-sales-analytics .
```

### 3. Kapsayıcıyı çalıştırın

```bash
docker run -p 8000:8000 open-sales-analytics
```

Günlük `Uvicorn running on http://0.0.0.0:8000` gösterdiğinde sunucu hazırdır.

### 4. Web arayüzünü açın

<http://localhost:8000> adresini açın. Yükleme ekranı dosya biçimini ve yükleme formunu gösterir.

### 5. Örnek verileri yükleyin

`backend/app/sample/sample_sales.csv` dosyasını seçin, **USD**'yi seçin ve **Yükle** düğmesine tıklayın.
(**Örnek veriyi dene**, aynı dosyayı seçmenizi gerektirmeden içe aktarır.)

![Örnek dosyanın ve USD'nin seçili olduğu yükleme formu](_docs/images/demo-upload.png)

### 6. Sonuçları inceleyin

Panel, verinin 2024-01-01 ile 2025-12-31 arasındaki tam dönemiyle **Genel bakış** ekranında açılır:

| Metrik | Beklenen değer |
| --- | --- |
| Satırlar | 14,397 |
| Brüt satış | $675,816.70 |
| Siparişler | 10,000 |
| Satılan birimler | 24,380 |
| Ortalama sipariş değeri | $67.58 |

![Genel bakış: temel rakamlar, aylık brüt satış eğilimi ve ilk 10 ürün](_docs/images/phase-3/overview.png)

Tam dönem 24 ayı kapsadığından eğilim aylıktır (bkz. [Eğilim kovaları](#eğilim-kovaları)). Her rakamı filtrelemek
için **Başlangıç tarihi** ve **Bitiş tarihi** değerlerini değiştirin; **Sıfırla** tam döneme döner. **Şununla karşılaştır**, önceki dönemi
veya geçen yılın aynı dönemini ekler; veri 2024-01-01 tarihinde başladığı için tam dönemde kullanılamaz.

**Ürünler**; sıralamaları, kümülatif Pareto grafiğiyle brüt satış payını, yükselen ve düşen ürünleri, hareketsiz
ürünleri ve birlikte alınan ürünleri gösterir. Burada 2025, 2024 ile karşılaştırılmıştır
(bkz. [Ürün analitiği](#ürün-analitiği)):

![Ürünler: sıralamalar, Pareto grafiği, yükselen ve düşen ürünler, hareketsizlik ve ürün çiftleri](_docs/images/phase-3/products.png)

Bir ürün adı ayrıntısını açar: brüt satış eğilimi, birim başına ödenen ortalama fiyat, sipariş penetrasyonu ve birlikte
alınan ürünler.

![Ürün ayrıntısı: brüt satış eğilimi, ağırlıklı birim fiyat, sipariş penetrasyonu ve ilişkili ürünler](_docs/images/phase-3/product-detail.png)

**Müşteriler**; kapsamı, temel müşteri rakamlarını, satın almalar arasındaki günleri, kohort elde tutma ısı haritasını,
Geçmiş Müşteri Değerini, Öngörülen 12 Aylık Müşteri Değerini, RFM segmentlerini, satın alma sıklığını ve yoğunlaşmayı
gösterir (bkz. [Müşteri analitiği](#müşteri-analitiği)):

![Müşteriler: kapsam, temel rakamlar, kohort elde tutma ısı haritası, değer, RFM, sıklık ve yoğunlaşma](_docs/images/phase-3/customers.png)

**Başka bir dosya analiz et** bu veri kümesini siler ve yükleme ekranına döner.

## Karşılaştırmalar

Tarih aralığı kartı etkin aralığı önceki dönemle veya geçen yılın aynı dönemiyle karşılaştırabilir. Panel API'ın
döndürdüğü kesin tarihleri gösterir. Karşılaştırma veri kümesinin ilk tarihinden önce başlayacaksa tam aralık
karşılaştırması kullanılamaz. Artık gün karşılaştırmaları karşılaştırma yılındaki Şubat ayının son geçerli gününü
kullanır. Önceki değeri olmayan bir karşılaştırma “Önceki değer yok”; iki sıfır değer “Değişim yok”; yeni ürün “Yeni”;
diğer durumlarda yüzde “Karşılaştırılabilir” olarak gösterilir.

## Ürün analitiği

Aksi belirtilmedikçe tüm ürün rakamları seçilen, iki ucu dahil etkin aralığı kullanır. Para brüt satıştır: indirimler,
iadeler ve maliyetler bu veri kümesi sözleşmesinin dışındadır. Her ürün adı ve kimliği sunucu tarafından sağlanan metin
olarak gösterilir.

| UI etiketi ve anahtar | Formül ve payda | Pencere ve normal olmayan durumlar | Çalışılmış örnek |
| --- | --- | --- | --- |
| Sıralamalar — `gross_sales` | Miktar × birim fiyat toplamı; satılan birimler miktar toplamı; siparişler benzersiz sipariş sayısıdır | Etkin aralık; boş aralıklarda ürün yoktur | 12.50'den 2 birimli satır 25.00 brüt satış katkısı yapar |
| Brüt satış payı — `gross_sales_share` | Ürün brüt satışı / toplam ürün brüt satışı | Etkin aralık; toplam brüt satış sıfırsa yetersiz | 100'ün 15'i %15.00'dır |
| İlk %20 payı — `top_20_percent_share` | En üst %20 ürün sayısının brüt satışı / toplam brüt satış | Etkin aralık; toplam sıfırsa yetersiz | 50/20/15/10/5 değerli beş üründe ilk ürün %50.00'dır |
| %80'e ulaşan ürünler — `products_to_80_percent` | Kümülatif payı %80'e ulaştıran en küçük sıralı ürün sayısı | Etkin aralık; toplam sıfırsa yetersiz | 50+20+15, 3 üründe %80'e ulaşır |
| Kümülatif pay — `cumulative_share` | İşleyen brüt satış / toplam brüt satış | Etkin aralık; toplam sıfırsa kullanılamaz | İlk üç golden ürün %85.00'a ulaşır |
| Ürün büyümesi — `product_growth` | Güncel brüt satış eksi karşılaştırma brüt satışı; yüzde karşılaştırma değerini kullanır | Karşılaştırma dönemi; `Yeni`, `Güncel satış yok`, `Değişim yok` veya kullanılamayan karşılaştırma yanıltıcı yüzdeleri önler | 10'dan 20'ye +10 ve +%100.00'dır |
| Yükselen/düşen sıralaması — `rising_products`, `falling_products` | Mutlak brüt satış değişimine göre sırala | Seçili karşılaştırma; karşılaştırma kullanılamıyorsa kullanılamaz | +10 değişim, +1'lik +%900 değişimin üstünde yer alır |
| Hareketsiz ürünler — `dormancy` | Seçilen 30, 60 veya 90 günlük pencerede satışı olmayan ürünler; önceki toplamlar pencere öncesi satışları kullanır | Seçili aralığın son tarihine dayanır (tam aralıkta veri kümesinin son tarihi), varsayılan 60; yetersiz geçmiş ve sıfır sonuç ayrıdır. Dayanaktan tam N gün önceki satış pencerenin içindedir | Dayanaktan 60 gün önce son satılan ürün 60 günlük pencereye dahildir |
| Ağırlıklı birim fiyat — `weighted_unit_price` | SUM(quantity × unit_price) / SUM(quantity) | Etkin aralık kovaları; satışsız kovalar boşluktur, sıfır fiyat değildir | 10'dan 1 ve 20'den 3 birim 17.50 verir |
| Sipariş penetrasyonu — `order_penetration` | Ürünü içeren benzersiz siparişler / tüm benzersiz siparişler | Etkin aralık; sıfır sipariş sıfır sonuçtur | 200 siparişin 25'i %12.50'dır |
| Destek — `basket_support` | Ortak siparişler / uygun sepet siparişleri | Etkin aralık; en az 10 ortak sipariş ve %0,1 destek gerekir | 10.000 siparişte 10 ortak sipariş %0.10 verir |
| Güven — `basket_confidence` | Ortak siparişler / yönlü ürünü içeren siparişler | Etkin aralık; eşik altındaki çiftler gösterilmez | A→B ve B→A, sipariş sayıları farklı olduğundan farklı olabilir |
| Artış — `basket_lift` | Güven / hedef ürünün desteği | Etkin aralık; eşik altındaki çiftler gösterilmez | Artış, gözlenen çift oranını hedef desteğiyle karşılaştırır |

Paylaşılan kayıt defteri bu anahtarları şöyle etiketler: Brüt satış payı, Kümülatif brüt satış payı, İlk %20 ürün payı,
Brüt satışın %80'ine ulaşan ürünler, Ürün brüt satış büyümesi, Yükselen ürünler, Düşen ürünler, Hareketsiz ürünler,
Ağırlıklı gerçekleşen birim fiyat, Sipariş penetrasyonu, Sepet desteği, Sepet güveni ve Sepet artışı.

Artışları yüksek olsa bile iki sepet eşiğinden birinin altında kalan çiftler gösterilmez. 100'den fazla benzersiz ürünlü
siparişler yalnızca sepet analizinden çıkarılır; tam 100 dahildir ve bu siparişler sıralama, penetrasyon ve brüt satışta
yine sayılır. Products görünümü kaç tanesinin çıkarıldığını bildirir. Fiyat geçmişi yalnızca gerçekleşen fiyat hareketini
anlatır; fiyat esnekliğini ölçmez veya bir fiyat değişiminin satış değişikliğine neden olduğunu göstermez. Küçük tabanlar
baskın olmasın diye yükselme ve düşme mutlak değişimi kullanır. Penetrasyon, destek, güven ve artış benzersiz siparişleri kullanır.

API belgeleri [`/docs`](http://localhost:8000/docs) adresindedir. `GET /api/datasets/{id}/overview` genel bakış KPI'larını
ve eğilimleri; `GET /api/datasets/{id}/products` portföy analizlerini; `GET /api/datasets/{id}/products/detail?product_id=...`
tek bir ürünün ayrıntılı analizlerini döndürür. Veri kümesi uç noktaları veri kümesinin bearer token'ını gerektirir.

## Müşteri analitiği

Müşteri analitiği yalnızca topludur. Tanımlanmış siparişleri açıklar; asla müşteri kimliği, müşteri listesi veya müşteri
başına tutar göstermez. Bir satır seçili son tarihe kadar tam geçmiş olarak açıkça tanımlanmadıkça, etkin raporlama
aralığı başlangıç ve bitiş tarihlerini içerir. Aşağıdaki çalışılmış rakamlar commit edilmiş
`backend/tests/fixtures/customers/golden_customers.csv` fixture'ını kullanır: 2025-01-01 ile 2025-09-30 arasında
20 sipariş, 19 tanımlanmış sipariş, 10 müşteri ve 380.0000 tanımlanmış brüt satış.

| UI etiketi ve anahtar | Formül, pencere ve dayanak | Yetersiz veri ve sıfır sonuç | Çalışılmış örnek |
| --- | --- | --- | --- |
| Müşteri kapsamı — `customer_coverage` | Tanımlanmış benzersiz siparişler / tüm benzersiz siparişler; veri kümesi ve seçili aralık için sipariş başına sayılır | `customer_id` sütunu yoksa kullanılamaz, %50'nin altı gizlenir ve sipariş yoksa kapsam null'dır | Golden fixture'da 19 / 20 = %95.0 |
| Tanımlanmış müşteriler — `identified_customers` | Etkin aralıkta tanımlanmış bir satırı olan benzersiz `customer_id` değerleri; aralık başlangıcı ve sonu dahildir | Tanımlanmış müşteri yoksa `zero_result` ile 0 döner | Golden aralıkta 10 vardır |
| Yeni ve geri dönen müşteri brüt satışı — `new_vs_returning` | Her satırın müşterinin ilk tam geçmiş sipariş tarihinde veya sonrasında olmasına göre `SUM(quantity × unit_price)` bölünür; geçmiş aralık sonuna kadardır | Tanımlanmış satır yoksa `zero_result` ile sıfır para değerleri döner | CUST-01'in 2024-12-15 satın alımı, 2025 satışlarını geri dönen yapar |
| Tekrar satın alma oranı — `repeat_purchase` | Seçili sona kadar en az iki benzersiz siparişi olan etkin müşteriler / etkin tanımlanmış müşteriler; aralık başlangıcından önceki siparişler sayılır | Etkin müşteri yoksa `insufficient_data`; tekrar etmeyen etkin müşteriler tam 0'dır (`zero_result`) | Aynı gün siparişleri benzersiz tarihler değil, benzersiz siparişlerdir |
| Satın almalar arasındaki günler — `days_between_purchases` | Ardışık benzersiz siparişler arasındaki takvim günü aralığının medyanı; sonraki sipariş aralıktaysa aralık dahildir ve aynı gün siparişleri 0 verir | Aralık yoksa medyan null ve `insufficient_data`; sabit kovalar 0, 1-7, 8-14, 15-30, 31-60, 61-90, 91-180, 181-365 ve 366+ | Aynı gün çifti 0 kovasına katkı yapar |
| Kohort elde tutma — `cohort_retention` | Takvim ayı uzaklığına göre elde tutulan müşteriler / tam geçmiş edinme kohortu boyutu; kohortlar seçili sona kadarki tüm geçmişi kullanır | Eksik kohortlar `insufficient_data`; sağ kenar hücresi 0% değil `Henüz gözlemlenmedi` olur | Ay 0, boş olmayan her kohort için %100.0'dır |
| Geçmiş Müşteri Değeri — `historical_customer_value` | Son tarihe kadarki gözlenen tanımlanmış brüt satış / tanımlanmış müşteri sayısı; medyan ortadaki müşteri başına değerdir; kohort eğrileri kümülatif satış kullanır | Kohort yoksa `insufficient_data`; sıfır gözlenen satış sıfır sonuçtur; bu tahmin değil gözlenen veridir | Golden fixture 10 tanımlanmış müşteride 380.0000 değerine sahiptir |
| RFM segmentleri — `rfm` | Güncellik, seçili son tarihten önceki günlerdir; sıklık benzersiz siparişler; parasal değer tanımlanmış brüt satıştır. Her boyut göreli beşte birlik puanlarını ve FM = F + M kullanır | 5'ten az müşteri `insufficient_data`; eşitlikler aynı puanı ve kayıt defterindeki tam puan-segment tablosunu kullanır | Puanlar evrensel kıyaslara değil, bu yüklemeye görelidir |
| RFM segment ayrıntıları — `rfm_drilldown` | Toplu segment brüt satışı ile sabit güncellik (0-30'dan 366+'ya) ve sıklık (1, 2, 3, 4, 5, 6-10, 11-20, 21+) kovaları; müşteri başına satır yoktur | 5'ten az müşteri `insufficient_data`; sıfır brüt satışın payı null'dır | Golden fixture, kimlik eşitlik bozucusu olmadan eşit değerler içerir |
| Satın alma sıklığı — `purchase_frequency` | Sona kadarki benzersiz tanımlanmış siparişlere göre 1, 2, 3, 4, 5, 6-10, 11-20 ve 21+ olarak gruplanan müşteriler | Tanımlanmış müşteri yoksa boş sayılar, null paylar ve `insufficient_data` verir | İki siparişli müşteri 2 kovasındadır |
| Müşteri yoğunlaşması — `concentration` | En üst ondalık dilim brüt satışı / tanımlanmış brüt satış; N müşteri için üst grup, kesimde eşitlik bozucu olmadan `ceil(N / 10)` en büyük aralık satış değerine sahiptir | 10'dan az müşteri veya sıfır tanımlanmış brüt satış `insufficient_data` ve null pay verir | N=10 iken 1000, 500 ve sekiz adet 100 satış 1000 / 2300 = 0.4348 verir |

%50 ve %80 kapsam katmanları dahildir: %50'nin altı gizlenir, %50.0'dan %80 hariç altına kadar düşük kapsam uyarısı,
%80 veya üzeri normaldir. UI görüntülenen yüzdeyi tek ondalığa keser; katman sınırını geçecek biçimde yuvarlamaz. Kapsam
satır değil sipariş düzeyindedir. Sütunsuz dosya %0 değil, kullanılamazdır.

Müşteri kimliği ve kohortlar seçili sona kadarki tam geçmişi kullanır. Aralık başlangıcını ileri almak müşteriyi yeni
olarak yeniden sınıflandırmaz veya kohort üyeliğini değiştirmez. RFM güncelliği ve kohort olgunluğu bugüne değil,
seçili son tarihe dayanır. Kısmi veya gelecekteki kohort hücresi sıfır sonuç değil, **Henüz gözlemlenmedi**'dir.

Yükleme tutarlılık kuralları kesindir: sipariş içindeki boşluklar tek boş olmayan kimlikle doldurulur; iki farklı kimlik
tüm yüklemeyi reddettirir; tümü boş sipariş tanımlanmamış kalır. Varsayılan `customer_id` sınırı 128 karakterdir.
En iyi çaba kontrolleri bariz e-posta adreslerini, bariz telefon numaralarını ve sınırı aşan değerleri reddeder; isimleri,
posta adreslerini, ulusal kimlik numaralarını, tersine çevrilebilir kodlamaları veya sıra dışı telefon biçimlerini tanıyamaz.

Müşteri verileri anonim değil, takma adlıdır. UUID, dahili anahtar veya dosya dışında tutulan gizli salt içeren karma
kullanın. Yanıtlar yalnızca toplu sayılar ve toplamlar içerir: müşteri listesi, arama, indirme veya dışa aktarma yoktur;
müşteri kimlikleri, kohort üyeliği ve RFM kayıtları günlüğe yazılmaz. Müşteri verileri yalnızca veri kümesinin DuckDB
dosyasında yaşar, `DATASET_TTL_HOURS` (varsayılan 24) sonrasında bu dosyayla birlikte veya **Başka bir dosya analiz et** ile
hemen kaldırılır; ham CSV içe aktarmadan sonra silinir. Öngörülen 12 Aylık Müşteri Değeri bu gözlenen ölçü değil, ayrı
bir gelecek metriğidir.

## Yapılandırma

Sunucu başladığında bu ortam değişkenler…4183 tokens truncated…a göreli olduğunu belirtir.

`sections.rfm_drilldown`, `sections.rfm` ile aynı nüfus, girdiler ve segmentlerle, karşılaştırmasız toplu segment
rakamlarını bildirir. Üst düzeyde `customer_count` (N, `sections.rfm` ile aynı), `recency_anchor` (aralık sonu) ve
`gross_sales` (N müşterinin sona kadarki parasal değerlerinin toplamı, para yarımdan yukarı 4 ondalığa yuvarlanır)
döndürür. `segments`, altı segmenti her zaman `sections.rfm` sırasıyla listeler; her biri `customer_count`, `gross_sales`
(üyelerinin parasal değer toplamı), `gross_sales_share` (segment `gross_sales` / üst düzey `gross_sales`; toplam `0`
ise `null`), dayanağa günler için altı sabit kovada `recency_distribution` (`0-30`, `31-60`, `61-90`, `91-180`,
`181-365`, `366+`; `key`, `min_days`, `max_days`, `customer_count`) ve benzersiz siparişler için sekiz sabit kovada
`frequency_distribution` (`1`, `2`, `3`, `4`, `5`, `6-10`, `11-20`, `21+`; `key`, `min_orders`, `max_orders`,
`customer_count`) içerir. Açık kovaların azamisi `null`, boş segmentler ve kovalar `0`'dır. Tek üyeli segment de
müşteri kimliği veya puanı dönmediğinden diğerleri gibi bildirilir. 5'ten az müşteri gerçek `customer_count` ve
`gross_sales`, boş `segments` listesiyle `insufficient_data` verir.

Eksik veya gizlenmiş kapsam her bölümü atlar (`sections` boştur). Uç nokta her zaman `Cache-Control: no-store` döndürür.
Müşteri yanıtları tasarım gereği yalnızca topludur: müşteri kimliği, müşteri düzeyi nesne, arama, ayrıntı, indirme veya
dışa aktarma verisi döndürmez; kimlikler günlüklere yazılmaz.

### Uyarılar

Uyarılar dosyayı reddettirmez. `201` yanıtının `warnings` listesinde ve yükleme ekranında görünürler.

| Kod | Anlam |
| --- | --- |
| `extra_column` | Dosyada altı zorunlu sütundan veya `customer_id`'den biri olmayan, örneğin `note` sütunu vardır. Yok sayılır ve saklanmaz. |
| `zero_price` | Bir veya daha fazla satırın birim fiyatı 0'dır. İçe aktarılır, brüt satış olmadan sipariş ve birim sayılır. |

### Örnek veri

Geçerli bir örnek dosyayı <http://localhost:8000/api/sample.csv> adresinden indirin (yükleme ekranı bunu
**Örnek CSV'yi indir** olarak bağlar). Yükleme ekranındaki **Örnek veriyi dene**, aynı dosyayı yükleme olmadan USD
olarak içe aktarır.

## Eğilim kovaları

Eğilim, brüt satışları takvim kovasına göre gruplar. Ayrıntı düzeyi yalnızca iki sonu da sayılan seçili aralığa bağlıdır:
90 güne kadar günlük, 90 günden fazla ve 730 güne kadar haftalık, daha uzun aralıklar aylıktır. API her kova için
`bucket_start` (kovanın ilk günü) döndürür; kapsam alanı döndürmez.

- Aralık dahildir: başlangıç ve bitiş tarihleri aralığın içindedir.
- Haftalar pazartesiden pazara gider; haftalık kovanın `bucket_start` değeri pazartesidir. Aylar takvim aylarıdır.
- Aralığın kestiği kova (başlangıçtan önce başlayan ilk hafta/ay veya sondan sonra biten son hafta/ay) kısmi dönemdir.
  Grafik bunu aralık ve takvimden hesaplar; dolayısıyla satışsız bir gün de kapsamda sayılır. Tek günlük günlük kova her
  zaman tamdır (veriler yalnızca tarih tutar); hafta veya ayın tek günlük dilimi kısmidir. Tek hafta ya da ay içindeki
  aralık o kovayı kısmi gösterir.
- Kısmi sunum: kısmi hafta veya ay eksen etiketi, `29 Ara haftası` veya ay adı yerine kapsadığı tarihleri (`29–31 Ara`,
  `10–31 Mar 2025`) gösterir; nokta içi boştur; grafik altındaki not bunu belirtir; araç ipucu yılı ve
  `Kısmi dönem: <kapsanan tarihler>` metnini ekler. Tam kovada bunların hiçbiri yoktur.
- Yalnızca aralık içindeki satırlar toplanır; bu yüzden kısmi kova kapsadığı tarihlerin satışını tutar.

## Para birimleri

Para birimi yükleme formunda seçilir: USD, EUR, GBP, TRY, CAD, AUD, JPY, CHF, SEK, PLN. Tutarlar için yalnızca bir
etikettir. Dönüşüm ve döviz kuru yoktur. Başka kodlar `400 invalid_request` ile reddedilir.

## Gizlilik

- Ham CSV, içe aktarma başarıyla veya hatayla biter bitmez silinir.
- Zorunlu sütunlar ve isteğe bağlı `customer_id`, `DATASET_DIR` altında veri kümesi başına bir DuckDB dosyasında özel
  izinlerle saklanır (dosya `0600`, dizinler `0700`).
- Müşteri kimlikleri anonim değil, takma adlı verilerdir. Veri kümesinin 24 saatlik ömrü boyunca tutulurlar. Karma
  kimlik, UUID veya kişisel olmayan dahili anahtar kullanın; e-posta, telefon veya ad gibi doğrudan tanımlayıcı yüklemeyin.
- Müşteri kimliği uzunluk, e-posta ve telefon kontrolleri yalnızca en iyi çaba korumalarıdır. Anonimleştirme veya
  uyumluluk garantisi değildir; otomatik kontroller her tür kişisel veriyi bulamaz.
- Veri kümesi `DATASET_TTL_HOURS` (varsayılan 24) sonrasında, başlangıçta ve her `CLEANUP_INTERVAL_MINUTES` çalışan
  temizlikle veya **Başka bir dosya analiz et** tıklanınca hemen silinir.
- Başarılı modül yanıtları sınırlı, sürece yerel önbellekte `RESPONSE_CACHE_TTL_SECONDS` (varsayılan 300 saniye)
  tutulabilir; yetkilendirme her istekte çalışır, girdiler veri kümesi ve seçeneklerle anahtarlanır, süre sonu veya
  silme önbellek yanıtlarını kaldırır. Önbellek örnekler arasında paylaşılmaz.
- Erişim rastgele bearer token gerektirir. Tarayıcı bunu `sessionStorage` içinde tutar; sekme kapanınca kaybolur.
  Sunucu yalnızca SHA-256 karmasını saklar.
- Eksik veya süresi dolmuş veri kümesi kimliği 404, mevcut veri kümesi için yanlış token 401 döndürür; dolayısıyla durum
  bir kimliğin var olup olmadığını gösterir. Bu kabul edilmiş risktir: kimlikler tahmin edilemeyen rastgele 128 bit
  değerlerdir ve veri kümesi token olmadan okunamaz.
- Günlükler yöntem, yol, durum, süre ve veri kümesi kimliğiyle istek başına bir JSON satırıdır. İsteği izlemek için veri
  kümesi kimliği kasıtlı olarak günlüğe yazılır; sır değildir ve token olmadan kullanılamaz. Günlükler asla token,
  dosya içeriği/adı, ürün adı veya sipariş kimliği içermez. Hata günlükleri istisna mesajlarını değil, istisna sınıfı
  adlarını ve yığın çerçevelerini tutar.
- Başka hizmetlere hiçbir şey gönderilmez.
- Müşteri kimlikleri sağlandığında veri kümesi DuckDB dosyası, tanımlanmış müşteri başına tüm geçmiş ilk/son sipariş
  tarihleri, edinme ayı, benzersiz yaşam boyu siparişler, birimler ve brüt satışla bir `customer_facts` satırı içerir.
  Tanımlanmamış siparişler için satır içermez ve veri kümesiyle sona erer; ayrı paylaşılan veritabanı değildir.

## Demo modu

Barındırılan demo, `PUBLIC_DEMO_MODE=true` ile çalışan herkese açık bir örnektir: ziyaretçiler yalnızca paketlenmiş örnek
verileri inceleyebilir ve dosya yükleyemez. Veri kümeleri diğerleri gibi sona erer (`DATASET_TTL_SECONDS`) ve tek örnek
olarak çalışır. Kendi dosyalarınızı analiz etmek için [kendiniz çalıştırın](#docker-ile-çalıştırma).

`PUBLIC_DEMO_MODE=true`, başka kişilerin dosyalarını almaması gereken herkese açık sunucu içindir:

- `POST /api/datasets`, gövdeyi okumadan 403 `upload_disabled` yanıtı verir.
- **Örnek veriyi dene** ve örnek indirme çalışmaya devam eder.
- Yükleme ekranı yalnızca dosya biçimini ve **Örnek veriyi dene** seçeneğini gösterir; dosya veya para birimi alanı yoktur.
  Yalnız örnek veri kabul ettiğini söyler ve yüklemeler için [Docker ile çalıştırma](#docker-ile-çalıştırma) bölümüne bağlanır.
- `GET /api/config`, ekranın bunu anlamasını sağlayan `{"public_demo_mode":true,...}` değerini döndürür.
- `MAX_DATASETS` herkese açık sunucunun diskini korur: her **Örnek veriyi dene** tıklaması veri kümesi oluşturur; sınırda
  503 `capacity_reached` yanıtı verir.

## Sınırlamalar

- Yalnız bir örnek. Yatay ölçekleme yoktur: veri kümeleri bu örneğin diskindeki dosyalardır.
- Yeniden başlatmadan sonra kalma, yalnızca `DATASET_DIR` birim üzerindeyken ve en iyi çaba esasındadır.
- Hesap ve paylaşım yoktur. Veri kümesine yalnızca tek tarayıcı sekmesinde kalan token'ıyla erişilebilir.
- Dosya başına tek para birimi.
- Müşteri düzeyi listeler, dışa aktarımlar veya aramalar sunulmaz; müşteri rakamları yalnız tanımlanmış siparişleri kapsar.
- Yalnız brüt satış: iade, indirim, vergi veya kargo yoktur.
- Varsayılan 50 MB ve 500.000 satır.
- Telefon, tablet ve masaüstü genişlikleri (360 px ve üzeri); geniş tablolar kendi bölgelerinde kayar (bkz.
  [`_docs/design-system.md`](_docs/design-system.md)).

## Yol haritası

Aşama 3 tamamlandı. [Aşama 3 belirtimindeki](_docs/open_sales_analytics_phase_3_spec.md#20-deferred-roadmap) sonraki adaylar:

- **Aşama 4: yönetilen ürün temeli.** Merkezi uygulama veritabanı, hesaplar, sahiplik, kayıtlı veri kümeleri ve kalıcı paneller.
- **Aşama 4: barındırılan veri alımı.** Hız sınırları, yalıtım, kötüye kullanım kontrolleri ve izlemeyle korunan herkese açık yüklemeler.
- **Aşama 4: finansal sözleşme katmanı.** Net satış, indirim, iade ve marj analitiğiyle isteğe bağlı `discount_amount`, `refund_amount` ve `unit_cost` sütunları.
- **Daha sonra:** Shopify, WooCommerce ve pazar yeri biçim eşleyicileri; çok dosyalı ve çok kanallı veri kümeleri;
  açık gizlilik modeliyle müşteri aktivasyonu ve dışa aktarma; daha büyük eşzamansız içe aktarmalar; yalnızca doğrulanmış
  kullanıcı ihtiyacından sonra tahmin veya anomali algılama.

## Mimari

Recharts kullanan React (Vite) frontend, FastAPI backend ile JSON üzerinden konuşur. Her veri kümesi `DATASET_DIR`
altında bir DuckDB dosyasıdır; doğrulama ve analitik bu dosyada SQL ile yapılır. Standart içe aktarma yeniden kullanılabilir
`order_facts`, `product_facts` ve tanımlanmış müşteri verisi varsa aynı dosyada tam geçmiş `customer_facts` oluşturur.
Süreç içi arka plan görevi süresi dolan veri kümelerini kaldırır. Docker imajı, FastAPI'ın hem API'ı hem derlenmiş
frontend'i aynı origin'den 8000 portunda sunduğu tek kapsayıcıdır. [Aşama 3 mimari kılavuzuna](_docs/architecture.tr-TR.md),
[metrik kataloğuna](_docs/metrics.tr-TR.md), [sürüm kontrol listesi ve kanıt raporuna](_docs/phase-3-release-checklist.md),
[Aşama 3 belirtimine](_docs/open_sales_analytics_phase_3_spec.md) ve [iş listesine](_docs/tasks.md) bakın.

## Geliştirme

Çalışma düzeni: [`_docs/process.md`](_docs/process.md). Test kuralları:
[`_docs/testing-guidelines.md`](_docs/testing-guidelines.md).
Performans temel çizgisi komutları ve sonuçları: [`_docs/benchmarks.md`](_docs/benchmarks.md).

Depo kökünden:

```sh
uv sync
uv run pytest
```

Lint ve tür kontrolleri (CI ile aynı komutlar; `uv sync`, `ruff` ve `mypy` araçlarını geliştirme bağımlılıkları olarak kurar):

```sh
uv run ruff check backend
uv run ruff format --check backend   # `uv run ruff format backend` fixes it
uv run mypy backend/app
```

Bağımlılık taraması (CI `dependency-scan` işiyle aynı iki komut; `uvx`, `pip-audit` aracını proje bağımlılığı yapmadan çalıştırır):

```sh
uv export --locked --no-emit-project --format requirements-txt -o /tmp/requirements.txt
uvx pip-audit@2.10.1 -r /tmp/requirements.txt --no-deps --disable-pip
(cd frontend && npm audit --audit-level=high)
```

Backend'i başlatın (http://127.0.0.1:8000 üzerinde sunar):

```sh
uv run uvicorn app.main:app --app-dir backend
```

Kontrol edin: `curl http://127.0.0.1:8000/api/health`, `{"status":"ok"}` döndürür. Derlenmiş frontend'i Docker
olmadan aynı origin'den sunmak için önce `frontend/` içinde `npm run build` çalıştırın (aşağıya bakın), sonra backend'i
yukarıdaki gibi başlatın ve <http://127.0.0.1:8000> adresini açın.

### Frontend

Node 22 veya yenisini gerektirir. `frontend/` içinden:

```sh
npm ci            # install
npm run dev       # dev server on http://localhost:5173
npm test          # Vitest, single run
npm run lint      # ESLint
npm run typecheck # tsc --noEmit (TypeScript 7)
npm run build     # type check, then the production bundle in frontend/dist
```

`npm run dev`, `/api` isteklerini 8000 portundaki backend'e proxy'ler; dolayısıyla backend'i de başlatın.

### Zorunlu CI kontrolleri

`main` dalıyla birleştirme, GitHub'ın pull request'te tam olarak böyle gösterdiği şu dört kontrolü gerektirmelidir
(Settings, Branches veya Rules, "Require status checks to pass", ardından her adı seçin):

- `Backend (tests, ruff, mypy)`
- `Frontend (tests, lint, type check, build)`
- `Dependency scan (Python, npm) / Dependency scan (Python, npm)`
- `Container (build, smoke, browser tests)`

Bağımlılık taraması `.github/workflows/dependency-scan.yml` yeniden kullanılabilir iş akışını çağırır; GitHub adını
`<calling job> / <called job>` olarak iki kez gösterir. Dal korumasında bu tam iki parçalı adı seçin; düz
`Dependency scan (Python, npm)` bir kontrol çalışmasıyla eşleşmez. `.github/workflows/` içindeki bir işi yeniden
adlandırırsanız bu listeyi ve koruma ayarını aynı değişiklikte güncelleyin; artık olmayan zorunlu kontrol her
birleştirmeyi engeller. Her pull request'te `gh pr checks <number>` ile karşılaştırın.

### Bağımlılık taraması

CI iki kilit dosyasını her pull request'te, `main` dalına her push'ta ve her pazartesi 05:17 UTC'de
(`.github/workflows/dependency-scan-scheduled.yml`) tarar; böylece değişmemiş kilit dosyasına yönelik yeni öneri,
sonraki pull request'i beklemeden çalışmayı kırmızı yapar. İkisi de aynı paylaşılan tanımı,
`.github/workflows/dependency-scan.yml` kullanır; aşağıdaki komutlar ve politika aynıdır. Zamanlanmış çalışma
`contents: read` kullanır, sır içermez ve Actions sekmesinden elle de ("Run workflow") başlatılabilir.

| Ekosistem | Araç ve girdi | CI'ın başarısız olduğu durum |
| --- | --- | --- |
| Python | `uv.lock` üzerinde `pip-audit` (çalışma zamanı ve geliştirme paketleri) | bilinen herhangi bir güvenlik açığı (`pip-audit` önem filtresi içermez) |
| npm | `frontend/package-lock.json` üzerinde `npm audit --audit-level=high` | yüksek ve kritik öneriler; düşük ve orta düzeyler günlükte gösterilir ama başarısız etmez |

Hata veren tarayıcı (ağ yok, bozuk girdi) işi de başarısız eder; adımlarda `|| true` veya `continue-on-error` yoktur.
Yoksayma listesi yoktur. Önerinin henüz düzeltmesi yoksa çıkış yolu, öneri kimliği ve yanındaki gerekçeyle tarama
komutuna istisna sabitleyen (`pip-audit --ignore-vuln ID` veya paketi kaldırma) incelenmiş pull request'tir; sessizce
atlanmaz. Önbellekler yalnız paket indirmelerini ve Playwright tarayıcısını tutar; hiçbir veri kümesi, yükleme, sır veya
DuckDB dosyası önbelleğe alınmaz veya artifact olarak yüklenmez.

Dependabot (`.github/dependabot.yml`) pazartesileri eski Python (`pyproject.toml` kaynaklı `uv.lock`) ve npm
(`frontend/package-lock.json`) bağımlılıkları için, ekosistem başına en fazla 5 açık pull request oluşturur. Dependabot
yalnızca mevcut bağımlılıkları yükseltir; yenisini eklemez. Pull request'leri sır olmadan diğerleriyle aynı CI'ı çalıştırır
(Dependabot pull request'leri salt okunur token alır); böylece bağımlılık taraması, testler, derleme ve tarayıcı paketi
değişen kilit dosyasında çalışır. Diğer değişiklikler gibi inceleyin: sürüm notlarını ve kilit dosyası diff'ini okuyun,
yalnız tüm kontroller yeşilken birleştirin ve ana sürüm yükseltmesinde uygulamayı elle de bir kez çalıştırın. Kırmızı
kontrol pull request'i kapatmak ya da düzeltmek için nedendir; asla birleştirme nedeni değildir.

Başarısız zamanlanmış çalışma, deponun Actions sekmesinde "Dependency scan (scheduled)" adlı kırmızı çalışma olarak
görünür (iş akışı adıyla veya `event:schedule` ile filtreleyin). GitHub depo sahibine e-posta da gönderir: zamanlanmış
iş akışlarında `cron` satırını en son değiştiren kullanıcıyı bilgilendirir; başkası programı düzenlerse bildirim
ayarlarının (Settings, Notifications, Actions) açık olduğunu kontrol edin. Zamanlanmış iş akışları yalnız varsayılan
dalda çalışır ve GitHub 60 gün depo etkinliği olmazsa onları duraklatır; böyle olursa Actions sekmesinden yeniden etkinleştirin.

### Kapsayıcı imajını sabitleme

Karar: `Dockerfile` temel imajları (`node:26`, `python:3.14-slim`) digest ile sabitlenir
(`FROM image:tag@sha256:...`, çok mimarili indeks digest'i). Nedeni: etiket hareket eder; aynı commit'in iki derlemesi
farklı olabilir ve incelenmemiş yukarı akış değişikliği derlemeyi bozabilir veya tehlikeye atabilir. Digest derlemeyi
yinelenebilir ve her temel imaj değişikliğini incelenmiş pull request yapar. Dependabot (`.github/dependabot.yml`
içindeki `docker` girdisi, pazartesileri) etiketi ve digest'i birlikte yükseltir; `docker-smoke` CI işi, birleştirmeden
önce yeni imajda kapsayıcıyı derler ve başlatır. Elle güncellemek için istediğiniz etiketin digest'ini bulun ve `FROM`
satırının iki parçasını değiştirin. `COPY --from=ghcr.io/astral-sh/uv:0.8` ile kopyalanan `uv` imajı şimdilik etiketinde kalır.

### Sabitlenmiş action'lar

`.github/workflows/ci.yml` içindeki `pinned-actions` işi, `.github` altındaki herhangi bir `uses:` yerel yol
(`./.github/workflows/...`) veya `owner/repo@<40 hex characters>` değilse başarısız olur; hata açıklaması dosya ve satırı
belirtir. Sabitlemeleri `uses: owner/repo@<sha> # vX.Y.Z` olarak yazın; Dependabot SHA ve yorumu güncel tutar. Kontrol,
`contents: read` kullanan, sırsız ve `actions/checkout` dışında üçüncü taraf action'ı olmayan shell adımıdır; fork ve
Dependabot pull request'lerinde de çalışır.

### Tarayıcı testi

Küçük Playwright paketi (Chromium, `frontend/e2e/`) temel yolculukları kapsar: Try sample data, geçerli yükleme,
geçersiz yükleme, tarih aralığı ve Reset, Analyze another file, modüller arası müşteri yolculuğu, 360/768/1280 px
duyarlı düzenler ve süresi dolmuş veri kümesi. Tarayıcıyı bir kez kurun (yaklaşık 150 MB, depo dışında saklanır), sonra
`frontend/` içinden çalıştırın:

```sh
npx playwright install chromium
npx playwright install-deps chromium   # Linux only: system libraries, needs sudo; CI runs it too
npm run e2e
```

`npm run e2e` backend'i (8000 portu) ve Vite geliştirme sunucusunu (5173 portu), geçici veri kümesi diziniyle kendi
başlatır ve sonra durdurur. İki port da boş olmalıdır. Çalışan uygulamayı (örneğin kapsayıcıyı) test etmek için
`E2E_BASE_URL` ayarlayın; sunucu başlatılmaz. Süre sonu yolculuğu gerçek süre sonunu sınırlandırılmış yoklamayla
beklediği için uygulama `DATASET_TTL_SECONDS=60` ile çalışmalıdır:

```sh
docker build -t open-sales-analytics .   # from the repository root
docker run -d --name oca -p 8000:8000 -e DATASET_TTL_SECONDS=60 open-sales-analytics
curl -f http://localhost:8000/api/health   # answers {"status":"ok"}; repeat for a few seconds until it does
curl -f http://localhost:8000/d/anything | grep -i '<div id="root"'   # the single-page app
E2E_BASE_URL=http://localhost:8000 npm run e2e
docker rm -f oca
```

Başarısızlıkta iz ve ekran görüntüsü `frontend/test-results/` içine kaydedilir (izi `npx playwright show-trace` ile
açın). `CI` ayarlandığında (GitHub Actions'ta olduğu gibi) iz ağ yanıtlarını içerdiğinden kaydedilmez; CI yalnızca
başarısızlık ekran görüntülerini yükler.

## Katkıda bulunma

Hata bildirimleri, fikirler ve pull request'ler memnuniyetle karşılanır; [`CONTRIBUTING.md`](CONTRIBUTING.tr-TR.md)
belgesine bakın.

## Lisans

[Apache License, Version 2.0](LICENSE) kapsamında lisanslanmıştır.
