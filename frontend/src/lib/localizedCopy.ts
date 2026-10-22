import i18n, { normalizeLocale } from "../i18n";
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
};

function interpolate(message: string, params: LocalizationParams = {}): string {
  return message.replace(/\{([a-z][a-z0-9_]*)\}/g, (_match, name: string) => String(params[name] ?? `{${name}}`));
}

export function localizedServerText(code: string | null | undefined, params: LocalizationParams | undefined, fallback: string | null | undefined): string {
  if (normalizeLocale(i18n.resolvedLanguage) !== "tr" || !code || !tr[code]) return fallback ?? "";
  return interpolate(tr[code], params);
}

export function localizedRfmSegment(code: unknown, fallback: unknown): string {
  return localizedServerText(typeof code === "string" ? code : null, undefined, String(fallback ?? ""));
}

const projectionTr: Record<string, string> = {
  history_months: "Geçmiş ay sayısı",
  identified_customers: "Tanımlanmış müşteriler",
  customer_coverage: "Müşteri kapsamı",
  mature_cohorts: "Olgun kohortlar",
};

export function localizedProjectionCondition(code: string, fallback: string): string {
  return normalizeLocale(i18n.resolvedLanguage) === "tr" ? (projectionTr[code] ?? fallback) : fallback;
}
