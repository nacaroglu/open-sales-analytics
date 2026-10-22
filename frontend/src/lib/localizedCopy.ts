import i18n, { normalizeLocale, type SupportedLocale } from "../i18n";
import type { LocalizationParams } from "./types";

const tr: Record<string, string> = {
  "customers.no_customer_id": "Dosyada customer_id sütunu yok.",
  "customers.no_orders": "Seçili aralıkta sipariş yok.",
  "customers.no_identified_orders": "Seçili aralıkta tanımlanmış müşteriler sipariş vermedi.",
  "customers.no_identified_rows": "Seçili aralıkta tanımlanmış müşteriye ait satır bulunamadı.",
  "customers.no_repeat_customers": "Aralık sonuna kadar iki veya daha fazla sipariş veren aktif tanımlanmış müşteri yok.",
  "customers.no_purchase_intervals": "Seçili aralıkta tekrar sipariş veren tanımlanmış müşteri yok; bu nedenle satın almalar arasındaki süre hesaplanamıyor.",
  "customers.no_acquisition_cohort": "Seçili aralıkla örtüşen ayda edinilmiş tanımlanmış müşteri yok; edinim kohortu bulunmuyor.",
  "customers.no_observed_customer_value": "Seçili aralıkla örtüşen ayda edinilmiş tanımlanmış müşteri yok; gözlemlenecek müşteri değeri bulunmuyor.",
  "customers.zero_historical_value": "Seçili aylarda edinilen tanımlanmış müşterilerin aralık sonuna kadar brüt satışı yok.",
  "customers.no_customers_before_end": "Seçili bitiş tarihine kadar sipariş vermiş tanımlanmış müşteri yok.",
  "customers.concentration.minimum_customers": "Yoğunlaşma analizi için aralıkta en az 10 tanımlanmış müşteri gerekir.",
  "customers.concentration.zero_sales": "Tanımlanmış brüt satış sıfırken yoğunlaşma hesaplanamaz.",
  "customers.projection.requirements_not_met": "Tahmin için gerekli koşullar karşılanmıyor.",
  "customers.projection.missing_customer_id": "Bu tahmini görmek için dosyanıza customer_id sütunu ekleyin.",
  "customers.coverage_below_threshold": "Müşteri analizi için siparişlerin en az %{minimum_coverage_percent} bölümünde customer_id bulunmalıdır. {total_orders} siparişin {identified_orders} tanesinde (%{coverage_percent}) mevcut.",
  "products.no_sales": "Seçili aralıkta satış yapan ürün yok.",
  "products.zero_gross_sales": "Bu aralıktaki brüt satış sıfır.",
  "products.no_comparison_sales": "Seçili aralıklarda satış yapan ürün yok.",
  "products.no_dormant_products": "Seçili aralıkta hareketsiz ürün yok.",
  "products.no_product_pairs": "Seçili aralıkta uygun ürün çifti yok.",
  "products.no_related_products": "Seçili aralıkta uygun ilişkili ürün yok.",
  "products.basket.all_orders_oversized": "Bu aralıktaki tüm siparişler 100'den fazla ürün içeriyor ve sepet analizinin dışında bırakılıyor.",
  "products.basket.minimum_orders": "Sepet analizi için en az 10 sipariş gerekir.",
  "comparison.needs_two_days": "Karşılaştırma için en az iki günlük geçmiş gerekir.",
  "comparison.outside_dataset": "Karşılaştırma için {comparison_start} tarihinden başlayan veri gerekir ancak veri kümesi {dataset_start} tarihinde başlıyor.",
  "products.insufficient_dormancy_history": "Veri, {anchor_date} tarihinden önce {window_days} günden kısa bir süreyi kapsıyor.",
  "customers.rfm.minimum_customers": "RFM için en az {minimum_customers} tanımlanmış müşteri gerekir.",
  "customers.low_coverage": "Yalnızca {total_orders} siparişin {identified_orders} tanesinde (%{coverage_percent}) customer_id var; müşteri sonuçları yalnızca bu siparişleri açıklar.",
  "empty_file": "Dosya boş.",
  "invalid_encoding": "Dosya geçerli UTF-8 metni değil.",
  "malformed_csv": "Dosya CSV olarak okunamadı.",
  "no_data_rows": "Dosyada başlık satırı var ancak veri satırı yok.",
  "errors.invalid_request": "İstek geçerli değil.",
  "errors.upload_disabled": "Bu demoda yüklemeler devre dışı.",
  "errors.capacity_reached": "Sunucu şu anda dolu. Lütfen birkaç dakika sonra yeniden deneyin.",
  "customers.rfm.champions": "Şampiyonlar",
  "customers.rfm.loyal": "Sadık müşteriler",
  "customers.rfm.potential_loyalists": "Potansiyel sadık müşteriler",
  "customers.rfm.needs_attention": "İlgi bekleyenler",
  "customers.rfm.at_risk": "Risk altındakiler",
  "customers.rfm.lost": "Kaybedilenler",
  file_too_large: "Dosya {limit} sınırından büyük.",
  too_many_rows: "Dosyada izin verilen {max_rows} veri satırından fazlası var.",
  missing_column: "Gerekli '{field}' sütunu eksik.",
  duplicate_column: "'{field}' sütunu {count} kez bulunuyor.",
  extra_column: "'{field}' sütunu kullanılmayacak ve yok sayılacak.",
  missing_value: "{field} için değer zorunludur.",
  invalid_date: "Gerçek bir tarih YYYY-MM-DD biçiminde yazılmalıdır; alınan değer '{value}'.",
  future_date: "Sipariş tarihi {value} gelecekte olamaz.",
  invalid_quantity: "1 ile 2.147.483.647 arasında bir tam sayı bekleniyordu; alınan değer '{value}'.",
  invalid_price: "En fazla 14 tam ve 4 ondalık basamak içeren ondalık sayı bekleniyordu; alınan değer '{value}'.",
  negative_price: "Birim fiyat negatif olamaz; alınan değer '{value}'.",
  line_total_too_large: "Miktar × birim fiyat {limit} değerinden küçük olmalıdır; alınan değer {quantity} × {unit_price}.",
  malformed_row: "Satırda {values} değer var, ancak başlıkta {header_values} sütun bulunuyor.",
  duplicate_line: "Bu sipariş ve ürün daha önce {first_row}. satırda görünüyor.",
  customer_id_too_long: "customer_id çok uzun. Karma değer veya UUID gibi opak bir kimlik kullanın. Otomatik kontroller kişisel verilerin her türünü bulamayabilir.",
  customer_id_looks_like_email: "customer_id bir e-posta adresine benziyor. Karma değer veya UUID gibi opak bir kimlik kullanın. Otomatik kontroller kişisel verilerin her türünü bulamayabilir.",
  customer_id_looks_like_phone: "customer_id bir telefon numarasına benziyor. Karma değer veya UUID gibi opak bir kimlik kullanın. Otomatik kontroller kişisel verilerin her türünü bulamayabilir.",
  conflicting_customer_id: "'{order_id}' siparişinde {count} farklı müşteri kimliği var.",
  conflicting_product_name: "'{product_id}' ürününün {count} farklı adı var; ilk ikisi '{first_name}' ve '{second_name}'.",
  zero_price: "{count} satırın birim fiyatı 0.",
  "errors.invalid_range": "Tarih aralığı geçersiz.",
  "errors.internal_error": "Sunucuda bir sorun oluştu.",
  "errors.unknown_error": "Sunucudan beklenmeyen bir yanıt alındı.",
  "errors.network_error": "Sunucuya ulaşılamadı.",
} as const;

const translatedReasons = {
  "customers.no_customer_id": ["Der Datensatz enthält keine customer_id-Spalte.", "В файле нет столбца customer_id.", "El archivo no contiene una columna customer_id.", "文件中没有 customer_id 列。", "ファイルに customer_id 列がありません。"],
  "customers.no_orders": ["Im ausgewählten Zeitraum gibt es keine Bestellungen.", "В выбранном диапазоне нет заказов.", "No hay pedidos en el intervalo seleccionado.", "所选范围内没有订单。", "選択した期間に注文はありません。"],
  "customers.no_identified_orders": ["Im ausgewählten Zeitraum haben keine identifizierten Kunden bestellt.", "В выбранном диапазоне идентифицированные клиенты не совершали заказов.", "Ningún cliente identificado realizó pedidos en el intervalo seleccionado.", "所选范围内已识别客户没有下单。", "選択した期間に識別済み顧客の注文はありません。"],
  "customers.no_identified_rows": ["Im ausgewählten Zeitraum wurden keine Zeilen identifizierter Kunden gefunden.", "В выбранном диапазоне не найдено строк идентифицированных клиентов.", "No se encontraron filas de clientes identificados en el intervalo seleccionado.", "所选范围内未找到已识别客户的记录。", "選択した期間に識別済み顧客の行はありません。"],
  "customers.no_repeat_customers": ["Bis zum Ende des Zeitraums gibt es keine aktiven identifizierten Kunden mit mindestens zwei Bestellungen.", "До конца периода нет активных идентифицированных клиентов с двумя или более заказами.", "No hay clientes identificados activos con dos o más pedidos hasta el final del intervalo.", "截至所选范围结束，没有活跃的已识别客户下过两个或更多订单。", "期間終了までに2回以上注文したアクティブな識別済み顧客はいません。"],
  "customers.no_purchase_intervals": ["Im ausgewählten Zeitraum gibt es keine identifizierten Kunden mit Wiederholungskäufen; daher kann der Abstand zwischen Käufen nicht berechnet werden.", "В выбранном диапазоне нет идентифицированных клиентов с повторными покупками, поэтому интервал между покупками рассчитать нельзя.", "No hay clientes identificados con compras repetidas en el intervalo, por lo que no se puede calcular el tiempo entre compras.", "所选范围内没有已识别客户重复下单，因此无法计算购买间隔。", "選択した期間に識別済みのリピート顧客がいないため、購入間隔を計算できません。"],
  "customers.no_acquisition_cohort": ["Im Monat, der den ausgewählten Zeitraum überschneidet, wurden keine identifizierten Kunden gewonnen; es gibt keine Akquisitionskohorte.", "В месяце, пересекающемся с выбранным диапазоном, нет привлеченных идентифицированных клиентов; когорта привлечения отсутствует.", "No hay clientes identificados adquiridos en el mes que coincide con el intervalo seleccionado; no existe una cohorte de adquisición.", "与所选范围重叠的月份没有新增已识别客户，因此不存在获客队列。", "選択期間と重なる月に獲得した識別済み顧客がいないため、獲得コホートはありません。"],
  "customers.no_observed_customer_value": ["Im Monat, der den ausgewählten Zeitraum überschneidet, wurden keine identifizierten Kunden gewonnen; es gibt keinen beobachtbaren Kundenwert.", "В месяце, пересекающемся с выбранным диапазоном, нет привлеченных идентифицированных клиентов; наблюдаемая ценность клиента отсутствует.", "No hay clientes identificados adquiridos en el mes que coincide con el intervalo seleccionado; no hay valor de cliente observable.", "与所选范围重叠的月份没有新增已识别客户，因此没有可观察的客户价值。", "選択期間と重なる月に獲得した識別済み顧客がいないため、観測可能な顧客価値はありません。"],
  "customers.zero_historical_value": ["Für identifizierte Kunden, die in den ausgewählten Monaten gewonnen wurden, gab es bis zum Ende des Zeitraums keinen Bruttoumsatz.", "У идентифицированных клиентов, привлеченных в выбранные месяцы, до конца периода не было валовых продаж.", "Los clientes identificados adquiridos en los meses seleccionados no generaron ventas brutas hasta el final del intervalo.", "所选月份获客的已识别客户截至范围结束时没有销售总额。", "選択した月に獲得した識別済み顧客は、期間終了までに総売上がありませんでした。"],
  "customers.no_customers_before_end": ["Bis zum ausgewählten Enddatum haben keine identifizierten Kunden bestellt.", "До выбранной даты окончания идентифицированные клиенты не совершали заказов.", "Ningún cliente identificado realizó pedidos hasta la fecha final seleccionada.", "截至所选结束日期，没有已识别客户下单。", "選択した終了日までに注文した識別済み顧客はいません。"],
  "customers.concentration.minimum_customers": ["Für die Konzentrationsanalyse sind mindestens 10 identifizierte Kunden im Zeitraum erforderlich.", "Для анализа концентрации в периоде требуется не менее 10 идентифицированных клиентов.", "El análisis de concentración requiere al menos 10 clientes identificados en el intervalo.", "集中度分析要求此范围内至少有 10 位已识别客户。", "集中度分析には期間内に少なくとも10人の識別済み顧客が必要です。"],
  "customers.concentration.zero_sales": ["Bei null identifiziertem Bruttoumsatz kann keine Konzentration berechnet werden.", "При нулевых валовых продажах идентифицированных клиентов концентрацию рассчитать нельзя.", "No se puede calcular la concentración si las ventas brutas identificadas son cero.", "已识别客户销售总额为零时无法计算集中度。", "識別済み顧客の総売上が0の場合、集中度を計算できません。"],
  "customers.projection.requirements_not_met": ["Die Voraussetzungen für die Prognose sind nicht erfüllt.", "Требования для прогноза не выполнены.", "No se cumplen los requisitos para la proyección.", "未满足预测所需条件。", "予測の要件を満たしていません。"],
  "customers.projection.missing_customer_id": ["Füge deiner Datei eine customer_id-Spalte hinzu, um diese Schätzung zu sehen.", "Добавьте в файл столбец customer_id, чтобы увидеть эту оценку.", "Añade una columna customer_id al archivo para ver esta estimación.", "请在文件中添加 customer_id 列以查看此估算。", "この推定を表示するには、ファイルに customer_id 列を追加してください。"],
  "customers.coverage_below_threshold": ["Für die Kundenanalyse muss customer_id bei mindestens %{minimum_coverage_percent} % der Bestellungen vorhanden sein. Bei {total_orders} Bestellungen ist dies bei {identified_orders} ({coverage_percent} %) der Fall.", "Для анализа клиентов customer_id должен быть как минимум в %{minimum_coverage_percent}% заказов. Он есть в {identified_orders} из {total_orders} заказов ({coverage_percent}%).", "Para analizar clientes, customer_id debe estar presente en al menos el %{minimum_coverage_percent} de los pedidos. Está presente en {identified_orders} de {total_orders} ({coverage_percent}%).", "客户分析要求至少 %{minimum_coverage_percent}% 的订单包含 customer_id。当前 {total_orders} 个订单中有 {identified_orders} 个包含（{coverage_percent}%）。", "顧客分析には、注文の少なくとも %{minimum_coverage_percent}% に customer_id が必要です。{total_orders} 件中 {identified_orders} 件（{coverage_percent}%）にあります。"],
  "products.no_sales": ["Im ausgewählten Zeitraum wurden keine Produkte verkauft.", "В выбранном диапазоне товары не продавались.", "No se vendieron productos en el intervalo seleccionado.", "所选范围内没有售出商品。", "選択した期間に販売された商品はありません。"],
  "products.zero_gross_sales": ["Der Bruttoumsatz in diesem Zeitraum beträgt null.", "Валовые продажи за этот период равны нулю.", "Las ventas brutas en este intervalo son cero.", "此范围内的销售总额为零。", "この期間の総売上は0です。"],
  "products.no_comparison_sales": ["In den ausgewählten Zeiträumen wurden keine Produkte verkauft.", "В выбранных диапазонах товары не продавались.", "No se vendieron productos en los intervalos seleccionados.", "所选期间内没有售出商品。", "選択した期間に販売された商品はありません。"],
  "products.no_dormant_products": ["Im ausgewählten Zeitraum gibt es keine inaktiven Produkte.", "В выбранном диапазоне нет неактивных товаров.", "No hay productos inactivos en el intervalo seleccionado.", "所选范围内没有滞销商品。", "選択した期間に休眠商品はありません。"],
  "products.no_product_pairs": ["Im ausgewählten Zeitraum gibt es keine passenden Produktpaare.", "В выбранном диапазоне нет подходящих пар товаров.", "No hay pares de productos adecuados en el intervalo seleccionado.", "所选范围内没有符合条件的商品组合。", "選択した期間に条件を満たす商品ペアはありません。"],
  "products.no_related_products": ["Im ausgewählten Zeitraum gibt es keine passenden verwandten Produkte.", "В выбранном диапазоне нет подходящих связанных товаров.", "No hay productos relacionados adecuados en el intervalo seleccionado.", "所选范围内没有符合条件的关联商品。", "選択した期間に条件を満たす関連商品はありません。"],
  "products.basket.all_orders_oversized": ["Alle Bestellungen in diesem Zeitraum enthalten mehr als 100 Produkte und werden von der Warenkorbanalyse ausgeschlossen.", "Все заказы в этом диапазоне содержат более 100 товаров и исключаются из анализа корзины.", "Todos los pedidos de este intervalo contienen más de 100 productos y se excluyen del análisis de cesta.", "此范围内所有订单均包含超过 100 件商品，因此被排除在购物篮分析之外。", "この期間のすべての注文に商品が101点以上含まれるため、併売分析から除外されます。"],
  "products.basket.minimum_orders": ["Für die Warenkorbanalyse sind mindestens 10 Bestellungen erforderlich.", "Для анализа корзины требуется не менее 10 заказов.", "El análisis de cesta requiere al menos 10 pedidos.", "购物篮分析至少需要 10 个订单。", "併売分析には少なくとも10件の注文が必要です。"],
  "comparison.needs_two_days": ["Für einen Vergleich werden mindestens zwei Tage Daten benötigt.", "Для сравнения требуется не менее двух дней данных.", "La comparación requiere al menos dos días de datos.", "比较至少需要两天的数据。", "比較には少なくとも2日分のデータが必要です。"],
  "comparison.outside_dataset": ["Für den Vergleich werden Daten ab {comparison_start} benötigt, aber der Datensatz beginnt am {dataset_start}.", "Для сравнения нужны данные начиная с {comparison_start}, но набор данных начинается {dataset_start}.", "La comparación requiere datos desde {comparison_start}, pero el conjunto de datos comienza el {dataset_start}.", "比较需要从 {comparison_start} 开始的数据，但数据集始于 {dataset_start}。", "比較には {comparison_start} からのデータが必要ですが、データセットは {dataset_start} に始まります。"],
  "products.insufficient_dormancy_history": ["Die Daten reichen vor dem {anchor_date} weniger als {window_days} Tage zurück.", "Данные охватывают менее {window_days} дней до {anchor_date}.", "Los datos cubren menos de {window_days} días antes del {anchor_date}.", "数据在 {anchor_date} 之前覆盖不足 {window_days} 天。", "データは {anchor_date} より前を {window_days} 日未満しかカバーしていません。"],
  "customers.rfm.minimum_customers": ["Für RFM sind mindestens {minimum_customers} identifizierte Kunden erforderlich.", "Для RFM требуется не менее {minimum_customers} идентифицированных клиентов.", "RFM requiere al menos {minimum_customers} clientes identificados.", "RFM 至少需要 {minimum_customers} 位已识别客户。", "RFM には少なくとも {minimum_customers} 人の識別済み顧客が必要です。"],
  "customers.low_coverage": ["Nur {identified_orders} von {total_orders} Bestellungen ({coverage_percent} %) enthalten customer_id; Kundenergebnisse beschreiben nur diese Bestellungen.", "Только {identified_orders} из {total_orders} заказов ({coverage_percent}%) содержат customer_id; результаты по клиентам описывают только эти заказы.", "Solo {identified_orders} de {total_orders} pedidos ({coverage_percent}%) tienen customer_id; los resultados de clientes solo describen esos pedidos.", "仅 {total_orders} 个订单中的 {identified_orders} 个（{coverage_percent}%）包含 customer_id；客户结果仅反映这些订单。", "{total_orders} 件中 {identified_orders} 件（{coverage_percent}%）の注文にのみ customer_id があります。顧客分析結果はそれらの注文のみを対象とします。"],
  empty_file: ["Die Datei ist leer.", "Файл пуст.", "El archivo está vacío.", "文件为空。", "ファイルが空です。"],
  invalid_encoding: ["Die Datei ist kein gültiger UTF-8-Text.", "Файл не является корректным текстом UTF-8.", "El archivo no es texto UTF-8 válido.", "文件不是有效的 UTF-8 文本。", "ファイルが有効な UTF-8 テキストではありません。"],
  malformed_csv: ["Die Datei konnte nicht als CSV gelesen werden.", "Не удалось прочитать файл как CSV.", "No se pudo leer el archivo como CSV.", "无法将文件解析为 CSV。", "ファイルを CSV として読み取れませんでした。"],
  no_data_rows: ["Die Datei enthält eine Kopfzeile, aber keine Datenzeilen.", "В файле есть строка заголовка, но нет строк данных.", "El archivo tiene una fila de encabezado, pero no filas de datos.", "文件有标题行，但没有数据行。", "ファイルにはヘッダー行がありますが、データ行がありません。"],
  "errors.invalid_request": ["Die Anfrage ist ungültig.", "Запрос недействителен.", "La solicitud no es válida.", "请求无效。", "リクエストが無効です。"],
  "errors.upload_disabled": ["In dieser Demo sind Uploads deaktiviert.", "В этой демонстрации загрузка файлов отключена.", "Las cargas están desactivadas en esta demo.", "此演示中已禁用上传。", "このデモではアップロードが無効です。"],
  "errors.capacity_reached": ["Der Server ist gerade ausgelastet. Bitte versuche es in einigen Minuten erneut.", "Сервер сейчас перегружен. Повторите попытку через несколько минут.", "El servidor está ocupado. Vuelve a intentarlo en unos minutos.", "服务器当前繁忙。请几分钟后重试。", "現在サーバーが混み合っています。数分後にもう一度お試しください。"],
  "customers.rfm.champions": ["Champions", "Чемпионы", "Campeones", "冠军客户", "チャンピオン"],
  "customers.rfm.loyal": ["Treue Kunden", "Лояльные", "Clientes fieles", "忠诚客户", "ロイヤル顧客"],
  "customers.rfm.potential_loyalists": ["Potenzielle Stammkunden", "Потенциально лояльные", "Leales potenciales", "潜力忠诚客户", "ロイヤル候補"],
  "customers.rfm.needs_attention": ["Benötigen Aufmerksamkeit", "Требуют внимания", "Necesitan atención", "需要关注", "要注意"],
  "customers.rfm.at_risk": ["Abwanderungsgefährdet", "Под угрозой ухода", "En riesgo", "有流失风险", "離反リスク"],
  "customers.rfm.lost": ["Verloren", "Ушедшие", "Perdidos", "已流失客户", "離反顧客"],
  file_too_large: ["Die Datei überschreitet das Limit von {limit}.", "Размер файла превышает лимит {limit}.", "El archivo supera el límite de {limit}.", "文件大小超过 {limit} 限制。", "ファイルサイズが上限 {limit} を超えています。"],
  too_many_rows: ["Die Datei enthält mehr als die zulässigen {max_rows} Datenzeilen.", "В файле больше допустимых {max_rows} строк данных.", "El archivo supera el máximo permitido de {max_rows} filas de datos.", "文件的数据行数超过上限 {max_rows}。", "ファイルのデータ行数が上限 {max_rows} を超えています。"],
  missing_column: ["Die erforderliche Spalte '{field}' fehlt.", "Отсутствует обязательный столбец '{field}'.", "Falta la columna obligatoria '{field}'.", "缺少必需列“{field}”。", "必須列「{field}」がありません。"],
  duplicate_column: ["Die Spalte '{field}' kommt {count}-mal vor.", "Столбец '{field}' встречается {count} раза.", "La columna '{field}' aparece {count} veces.", "列“{field}”出现了 {count} 次。", "列「{field}」が {count} 回あります。"],
  extra_column: ["Die Spalte '{field}' wird nicht verwendet und ignoriert.", "Столбец '{field}' не используется и будет проигнорирован.", "La columna '{field}' no se usará y se ignorará.", "列“{field}”不会使用，将被忽略。", "列「{field}」は使用されず、無視されます。"],
  missing_value: ["Für {field} ist ein Wert erforderlich.", "Для {field} требуется значение.", "Se requiere un valor para {field}.", "{field} 必须有值。", "{field} の値は必須です。"],
  invalid_date: ["Ein gültiges Datum muss im Format YYYY-MM-DD angegeben werden; erhalten: '{value}'.", "Дата должна быть действительной и указана в формате YYYY-MM-DD; получено: '{value}'.", "La fecha debe ser válida y tener formato YYYY-MM-DD; se recibió '{value}'.", "日期必须有效并采用 YYYY-MM-DD 格式；收到“{value}”。", "日付は YYYY-MM-DD 形式の有効な値である必要があります。受信値：「{value}」。"],
  future_date: ["Das Bestelldatum {value} darf nicht in der Zukunft liegen.", "Дата заказа {value} не может быть будущей.", "La fecha del pedido {value} no puede ser futura.", "订单日期 {value} 不能是未来日期。", "注文日 {value} を未来の日付にすることはできません。"],
  invalid_quantity: ["Erwartet wurde eine Ganzzahl von 1 bis 2.147.483.647; erhalten: '{value}'.", "Ожидалось целое число от 1 до 2 147 483 647; получено: '{value}'.", "Se esperaba un entero entre 1 y 2.147.483.647; se recibió '{value}'.", "应为 1 到 2,147,483,647 之间的整数；收到“{value}”。", "1～2,147,483,647 の整数が必要です。受信値：「{value}」。"],
  invalid_price: ["Erwartet wurde eine Dezimalzahl mit höchstens 14 Stellen vor und 4 Stellen nach dem Komma; erhalten: '{value}'.", "Ожидалось десятичное число максимум с 14 цифрами до и 4 после точки; получено: '{value}'.", "Se esperaba un decimal con hasta 14 dígitos enteros y 4 decimales; se recibió '{value}'.", "应为最多 14 位整数和 4 位小数的十进制数；收到“{value}”。", "整数部14桁、小数部4桁以内の数値が必要です。受信値：「{value}」。"],
  negative_price: ["Der Stückpreis darf nicht negativ sein; erhalten: '{value}'.", "Цена за единицу не может быть отрицательной; получено: '{value}'.", "El precio unitario no puede ser negativo; se recibió '{value}'.", "单价不能为负数；收到“{value}”。", "単価を負の値にはできません。受信値：「{value}」。"],
  line_total_too_large: ["Menge × Stückpreis muss kleiner als {limit} sein; erhalten: {quantity} × {unit_price}.", "Количество × цена за единицу должно быть меньше {limit}; получено: {quantity} × {unit_price}.", "Cantidad × precio unitario debe ser menor que {limit}; se recibió {quantity} × {unit_price}.", "数量 × 单价必须小于 {limit}；收到 {quantity} × {unit_price}。", "数量 × 単価は {limit} 未満である必要があります。受信値：{quantity} × {unit_price}。"],
  malformed_row: ["Die Zeile enthält {values} Werte, der Header jedoch {header_values} Spalten.", "В строке {values} значений, а в заголовке {header_values} столбцов.", "La fila tiene {values} valores, pero el encabezado contiene {header_values} columnas.", "此行有 {values} 个值，但标题包含 {header_values} 列。", "行の値は {values} 個ですが、ヘッダーには {header_values} 列あります。"],
  duplicate_line: ["Diese Bestellung und dieses Produkt wurden bereits in Zeile {first_row} gefunden.", "Этот заказ и товар уже встречались в строке {first_row}.", "Este pedido y producto ya aparecieron en la fila {first_row}.", "此订单和商品已在第 {first_row} 行出现。", "この注文と商品はすでに {first_row} 行目にあります。"],
  customer_id_too_long: ["customer_id ist zu lang. Verwende eine opake Kennung wie einen Hash oder eine UUID. Automatische Prüfungen erkennen möglicherweise nicht alle personenbezogenen Daten.", "customer_id слишком длинный. Используйте непрозрачный идентификатор, например хеш или UUID. Автоматическая проверка может не выявить все персональные данные.", "customer_id es demasiado largo. Usa un identificador opaco como un hash o UUID. Las comprobaciones automáticas podrían no detectar todos los datos personales.", "customer_id 过长。请使用哈希值或 UUID 等不透明标识符。自动检查可能无法识别所有个人信息。", "customer_id が長すぎます。ハッシュや UUID などの不透明なIDを使用してください。自動検査ですべての個人情報を検出できるとは限りません。"],
  customer_id_looks_like_email: ["customer_id sieht wie eine E-Mail-Adresse aus. Verwende einen opaken Hash oder eine UUID. Automatische Prüfungen erkennen möglicherweise nicht alle personenbezogenen Daten.", "customer_id похож на адрес электронной почты. Используйте непрозрачный хеш или UUID. Автоматическая проверка может не выявить все персональные данные.", "customer_id parece una dirección de correo. Usa un hash opaco o UUID. Las comprobaciones automáticas podrían no detectar todos los datos personales.", "customer_id 看起来像电子邮件地址。请使用哈希值或 UUID 等不透明标识符。自动检查可能无法识别所有个人信息。", "customer_id がメールアドレスのようです。ハッシュや UUID などの不透明なIDを使用してください。自動検査ですべての個人情報を検出できるとは限りません。"],
  customer_id_looks_like_phone: ["customer_id sieht wie eine Telefonnummer aus. Verwende einen opaken Hash oder eine UUID. Automatische Prüfungen erkennen möglicherweise nicht alle personenbezogenen Daten.", "customer_id похож на номер телефона. Используйте непрозрачный хеш или UUID. Автоматическая проверка может не выявить все персональные данные.", "customer_id parece un número de teléfono. Usa un hash opaco o UUID. Las comprobaciones automáticas podrían no detectar todos los datos personales.", "customer_id 看起来像电话号码。请使用哈希值或 UUID 等不透明标识符。自动检查可能无法识别所有个人信息。", "customer_id が電話番号のようです。ハッシュや UUID などの不透明なIDを使用してください。自動検査ですべての個人情報を検出できるとは限りません。"],
  conflicting_customer_id: ["Die Bestellung '{order_id}' enthält {count} verschiedene Kunden-IDs.", "В заказе '{order_id}' указано {count} разных идентификатора клиента.", "El pedido '{order_id}' contiene {count} identificadores de cliente distintos.", "订单“{order_id}”包含 {count} 个不同的客户 ID。", "注文「{order_id}」に異なる顧客IDが {count} 個あります。"],
  conflicting_product_name: ["Die Produkt-ID '{product_id}' hat {count} verschiedene Namen; die ersten beiden sind '{first_name}' und '{second_name}'.", "У товара '{product_id}' указано {count} разных названия; первые два: '{first_name}' и '{second_name}'.", "El producto '{product_id}' tiene {count} nombres distintos; los dos primeros son '{first_name}' y '{second_name}'.", "商品 ID“{product_id}”有 {count} 个不同名称；前两个是“{first_name}”和“{second_name}”。", "商品ID「{product_id}」に {count} 個の異なる名前があります。最初の2つは「{first_name}」と「{second_name}」です。"],
  zero_price: ["{count} Zeilen haben einen Stückpreis von 0.", "В {count} строках цена за единицу равна 0.", "{count} filas tienen un precio unitario de 0.", "有 {count} 行的单价为 0。", "{count} 行の単価が0です。"],
  "errors.invalid_range": ["Der Datumsbereich ist ungültig.", "Диапазон дат недействителен.", "El intervalo de fechas no es válido.", "日期范围无效。", "日付範囲が無効です。"],
  "errors.internal_error": ["Auf dem Server ist ein Fehler aufgetreten.", "На сервере произошла ошибка.", "Se produjo un error en el servidor.", "服务器发生错误。", "サーバーで問題が発生しました。"],
  "errors.unknown_error": ["Unerwartete Antwort vom Server.", "Получен неожиданный ответ сервера.", "El servidor devolvió una respuesta inesperada.", "服务器返回了意外响应。", "サーバーから予期しない応答がありました。"],
  "errors.network_error": ["Der Server ist nicht erreichbar.", "Не удалось подключиться к серверу.", "No se pudo conectar con el servidor.", "无法连接到服务器。", "サーバーに接続できませんでした。"],
} as const satisfies Record<keyof typeof tr, readonly [string, string, string, string, string]>;

function interpolate(message: string, params: LocalizationParams = {}): string {
  return message.replace(/\{([a-z][a-z0-9_]*)\}/g, (_match, name: string) => String(params[name] ?? `{${name}}`));
}

const localeIndex: Partial<Record<SupportedLocale, number>> = { de: 0, ru: 1, es: 2, "zh-CN": 3, ja: 4 };

export function localizedServerText(code: string | null | undefined, params: LocalizationParams | undefined, fallback: string | null | undefined): string {
  const locale = normalizeLocale(i18n.resolvedLanguage) ?? "en";
  if (!code) return fallback ?? "";
  if (locale === "tr" && code in tr) return interpolate(tr[code], params);
  const index = localeIndex[locale];
  if (index === undefined || !(code in translatedReasons)) return fallback ?? "";
  const message = translatedReasons[code as keyof typeof translatedReasons][index];
  return interpolate(message, params);
}

export function localizedRfmSegment(code: unknown, fallback: unknown): string {
  return localizedServerText(typeof code === "string" ? code : null, undefined, String(fallback ?? ""));
}

const projectionTranslations: Record<string, Partial<Record<SupportedLocale, string>>> = {
  history_months: { tr: "Geçmiş ay sayısı", de: "Monate mit Daten", ru: "Месяцы истории", es: "Meses de historial", "zh-CN": "历史月份", ja: "履歴月数" },
  identified_customers: { tr: "Tanımlanmış müşteriler", de: "Identifizierte Kunden", ru: "Идентифицированные клиенты", es: "Clientes identificados", "zh-CN": "已识别客户", ja: "識別済み顧客" },
  customer_coverage: { tr: "Müşteri kapsamı", de: "Kundenabdeckung", ru: "Охват клиентов", es: "Cobertura de clientes", "zh-CN": "客户覆盖率", ja: "顧客カバー率" },
  mature_cohorts: { tr: "Olgun kohortlar", de: "Ausgereifte Kohorten", ru: "Зрелые когорты", es: "Cohortes maduras", "zh-CN": "成熟队列", ja: "成熟コホート" },
};

export function localizedProjectionCondition(code: string, fallback: string): string {
  const locale = normalizeLocale(i18n.resolvedLanguage) ?? "en";
  return projectionTranslations[code]?.[locale] ?? fallback;
}
