import i18n from "i18next";
import { initReactI18next } from "react-i18next";

export const supportedLocales = ["en", "tr"] as const;
export type SupportedLocale = (typeof supportedLocales)[number];
export const LOCALE_STORAGE_KEY = "osa.locale";

const en = {
  common: {
    language: "Language", english: "English", turkish: "Türkçe", loading: "Loading…",
    updating: "Updating…", retry: "Retry", reset: "Reset", error: "Error", warning: "Warning",
    success: "Success", unavailable: "Unavailable", insufficient: "Insufficient data",
    notEnough: "Not enough data", showValues: "Show values", period: "Period", currency: "Currency",
    rows: "Rows", expires: "Expires", startDate: "Start date", endDate: "End date",
    comparison: "Comparison", previousPeriod: "Previous period", previousYear: "Same period last year",
    overview: "Overview", products: "Products", customers: "Customers", grossSales: "Gross sales",
    orders: "Orders", unitsSold: "Units sold", averageOrderValue: "Average order value",
    analyzeAnother: "Analyze another file", dismiss: "Dismiss", estimate: "Estimate",
    currentPeriod: "Current period", comparisonPeriod: "Comparison period", rank: "Rank",
    product: "Product", code: "Code", share: "Share", field: "Field", reason: "Reason", file: "File",
    yes: "Yes", no: "No", partial: "partial", month: "Month", average: "Average", median: "Median",
    column: "Column", type: "Type", rule: "Rule", fileFormat: "File format", startAnalysis: "Start an analysis",
    compareWith: "Compare with", comparisonUnavailable: "Comparison unavailable", cohort: "Cohort",
    cohortSize: "Cohort size", mature: "Mature", monthsObserved: "Months observed", observed: "Observed",
    projected: "Projected (estimate)", horizon: "12-month horizon", totalEstimate: "12-month total (estimate)",
    selectCurrency: "Select a currency", dashboardSections: "Dashboard sections", customerAvailability: "Customer availability",
    lowCoverage: "Low coverage", datasetValue: "this dataset", met: "Met", notMet: "Not met", notAvailable: "not available",
    extra: {
      back: "Back", date: "Date", daily: "Daily", weekly: "Weekly", monthly: "Monthly",
      change: "Change", changePercent: "Change %", percentageChange: "Percentage change",
      grossSalesNow: "Gross sales now", grossSalesBefore: "Gross sales before", unitsChange: "Units change", ordersChange: "Orders change",
      noChange: "No change", noCurrentSales: "No current sales", distinctOrders: "Distinct orders",
      confidenceAB: "Confidence A→B", confidenceBA: "Confidence B→A", confidenceFrom: "Confidence from product", confidenceTo: "Confidence to product",
      observedValue: "Observed value per customer", weightedPrice: "Weighted unit price", purchaseFrequencyTable: "Purchase frequency table",
      daysTable: "Days between purchases table", historicalTable: "Historical Customer Value table",
      rfmRecency: "RFM recency distribution", rfmFrequency: "RFM frequency distribution",
      under10: "Under 10%", notReliable: "Not enough data for a reliable estimate",
      projectionHelp: "Estimate of average gross sales per customer in their first 12 months, based on how earlier customer groups behaved. It is not a guarantee of future sales and does not include costs, discounts or refunds.",
      expiredTitle: "This dataset has expired or was deleted", expiredSentence: "Upload a file or try the sample data again.",
      unauthorizedTitle: "This dataset cannot be opened from this browser session", unauthorizedSentence: "Datasets can only be opened in the tab where they were created.",
      badRange: "The selected date range is not valid for this dataset", unavailableSection: "This section is not available.",
      uploadFailed: "Something went wrong — your file was not imported", sampleFailed: "Something went wrong — the sample data could not be loaded",
      uploadDisabledHint: "You can still use Try sample data.", noOrders: "No orders in the selected range.",
      startBeforeEnd: "Start date must be on or before end date", unavailableSuffix: "(unavailable)",
      previousPeriodLower: "previous period", previousYearLower: "same period last year",
      dataUpTo: "Data up to", basedOn: "based on", matureCohort: "mature cohort", matureCohorts: "mature cohorts",
      toFix: "to fix.", showingFirst: "Showing the first", rejectedPrefix: "The file was rejected and nothing was imported:",
      warningExplanation: "These are not the reason the file was rejected. Fix the errors above.",
      excludedOrders: "orders with more than 100 distinct products were left out of this analysis only.",
      grossDaily: "Gross sales — daily", grossWeekly: "Gross sales — weekly", grossMonthly: "Gross sales — monthly",
      grossPerMonth: "Gross sales per month", partialPeriod: "Partial period", over75: "75% and over", up: "up", down: "down", versus: "vs",
      thisDataset: "this dataset:", customers: "customers", months: "months",
      expiresInLessMinute: "Expires in less than a minute", expiresMinute_one: "Expires in {{count}} minute",
      expiresMinute_other: "Expires in {{count}} minutes", expiresHour_one: "Expires in {{count}} hour",
      expiresHour_other: "Expires in {{count}} hours", expiresDay_one: "Expires in {{count}} day",
      expiresDay_other: "Expires in {{count}} days",
      fileRejected: "The file was rejected and nothing was imported:", errorsToFix: "to fix.",
      warningsNotReason: "These are not the reason the file was rejected. Fix the errors above.",
      rankBy: "Rank by", shareOfSales: "Share of gross sales", top20Products: "Top 20% of products:",
      productsFor80: "Products to reach 80% of gross sales:", noProductOutperforms: "No product sold more than in the comparison period",
      noProductUnderperforms: "No product sold less than in the comparison period", inactiveFor: "Inactive for",
      noSaleInDays: "No sale in the", daysUpTo: "days up to", endOfRange: "the end of the selected range",
      pairsNeed: "Pairs need at least", sharedOrders: "shared orders and at least", support: "support.",
      distinctProducts: "distinct products were left out of this analysis only.",
      productNotFound: "Product not found", allProducts: "All products", averagePricePaid: "Average price paid per unit",
      realizedPriceHelp: "Shows how the realised price moved; it does not show that price changes caused sales changes.",
      orderPenetration: "Order penetration", ofOrders: "of orders", period: "Period",
      grossSalesTrend: "Gross sales trend",
      projectedCustomerValue: "Projected 12-Month Customer Value", projectionTable: "Projected 12-Month Customer Value table",
      projectionDescription: "Estimate of average gross sales per customer in their first 12 months, based on how earlier customer groups behaved. It is not a guarantee of future sales and does not include costs, discounts or refunds.",
      addCustomerIdForEstimate: "Add a customer_id column to your file to see this estimate.",
      notReliableEstimate: "Not enough data for a reliable estimate", observedSoFar: "Observed so far",
      projectedEstimate: "Projected (estimate)", total12Estimate: "12-month total (estimate)",
      monthsObserved: "Months observed", mature: "Mature", observed: "Observed", cohort: "Cohort",
      validationReport: "Validation report", errors: "Errors", warnings: "Warnings", row: "Row", field: "Field",
      reason: "Reason", code: "Code", file: "File", retentionTable: "Cohort retention table",
      cohortSize: "Cohort size", notYetObserved: "Not yet observed", retentionShade: "Shading, retention:",
      estimate: "Estimate", notAvailable: "not available", month: "Month", rfmDrilldown: "RFM segment drill-down",
    },
  },
  upload: {
    title: "Upload sales data", file: "CSV file", choose: "Choose CSV file", noFile: "No file selected",
    currency: "Currency", upload: "Upload", sample: "Try sample data", download: "Download sample CSV",
    processing: "Processing…", help: "Select a CSV file and currency to continue.", contract: "Dataset contract",
    requiredColumns: "Required columns", column: "Column", type: "Type", rule: "Rule",
    validation: "Validation report", errors: "Errors", warnings: "Warnings", row: "Row",
    format: "File format", start: "Start an analysis", extraColumns: "Extra columns are ignored.",
    invalidWhole: "If any row is invalid, the whole file is rejected.",
    stringType: "String", dateType: "Date", integerType: "Integer", decimalType: "Decimal",
    orderRule: "Required and non-empty. Used for distinct order counting.",
    dateRule: "Required ISO calendar date in YYYY-MM-DD format. Must not be in the future.",
    productRule: "Required and non-empty. Identifies the product.",
    quantityRule: "Required and greater than zero. Zero and negative quantities are invalid.",
    priceRule: "Required and non-negative. A zero price is accepted with a warning; a negative price is invalid.",
    customerRule: "Optional. Blank is allowed; use a hashed identifier, UUID or non-personal internal key (never an email, phone number or name).",
    productNameRule: "Required and non-empty. One product_id must map to exactly one name within an upload.",
    intro: "Upload a CSV of completed sales lines and see gross sales, orders and top products.",
    demoIntro: "This demo accepts sample data only. Click Try sample data to see gross sales, orders and top products.",
    formatHelp: "One row is one product line within one completed order. The file must have these six required columns plus one optional column.",
    chooseFile: "Choose file", nativeNoFile: "No file chosen", selfHosted: "Uploads are available in the self-hosted version.",
    runDocker: "Run it yourself with Docker",
  },
  dashboard: {
    dateRange: "Date range", keyFigures: "Key figures", salesTrend: "Sales trend", topProducts: "Top products",
    noSales: "No sales in this range", noSalesSelected: "No sales in the selected range",
    noProducts: "No products sold in this range", goUpload: "Go to the upload screen",
    customerCoverage: "Customer coverage", identifiedOrders: "Identified orders",
    unidentifiedOrders: "Unidentified orders", customerAnalyticsUnavailable: "Customer analytics is unavailable",
    readContract: "Read the Dataset contract", customerAnalyses: "Customer analyses", productAnalyses: "Product analyses",
    dismissNotice: "Dismiss notice", dismissSuccess: "Dismiss success notice", customerHidden: "Customer analytics is hidden: coverage below 50%",
  },
  products: {
    rankings: "Rankings", rankBy: "Rank by", grossSalesShare: "Share of gross sales",
    risingFalling: "Rising and falling products", rising: "Rising", falling: "Falling",
    dormant: "Dormant products", inactiveFor: "Inactive for", boughtTogether: "Bought together",
    productA: "Product A", productB: "Product B", sharedOrders: "Shared orders", support: "Support",
    lift: "Lift", allProducts: "All products", productDetail: "Product detail", grossSalesTrend: "Gross sales trend",
    averagePrice: "Average price paid per unit", penetration: "Order penetration", lastSale: "Last sale",
    daysInactive: "Days inactive", earlierGrossSales: "Earlier gross sales", earlierOrders: "Earlier orders",
    cumulativeShare: "Cumulative share", noSales: "No sales", productNotFound: "Product not found",
    noMore: "No product sold more than in the comparison period", noLess: "No product sold less than in the comparison period",
    noPair: "No product pair meets the thresholds in this range", noRelated: "No related product meets the thresholds in this range",
    noUnits: "No units of this product sold in this range", averageUnit: "Average price per unit",
    rankingKey: "Products ranked by gross sales, left to right. Solid line: cumulative share of gross sales. Dashed line: 80% of gross sales.",
    reach80: "Products to reach 80% of gross sales:", top20: "Top 20% of products:",
    realisedPrice: "Shows how the realised price moved; it does not show that price changes caused sales changes.", newProduct: "New",
  },
  customers: {
    keyFigures: "Customer key figures", identified: "Identified customers",
    newGrossSales: "New-customer gross sales", returningGrossSales: "Returning-customer gross sales",
    repeatRate: "Repeat-purchase rate", medianDays: "Median days between purchases",
    daysBetween: "Days between purchases", intervals: "Intervals", bucket: "Bucket",
    cohortRetention: "Cohort retention", historicalValue: "Historical Customer Value",
    projectedValue: "Projected 12-Month Customer Value", rfm: "RFM segments", segment: "Segment",
    purchaseFrequency: "Purchase frequency", concentration: "Customer concentration",
    topDecile: "Top-decile share", recency: "Recency", frequency: "Frequency", cohorts: "Cohorts",
    notObserved: "Not yet observed", retentionKey: "Retention shading key", drilldown: "RFM segment drill-down",
    identifiedGrossSales: "Identified gross sales", observedSoFar: "Observed so far",
    projectionTable: "Projected 12-Month Customer Value table", rfmTable: "RFM segments table",
    repeatRateLabel: "Repeat-purchase rate", shading: "Shading, retention:",
    historicalHelp: "Observed gross sales per identified customer. Not a prediction.",
    rfmHelp: "Segments are relative to the customers in this upload, not universal benchmarks.",
    rfmRules: "RFM score rules",
    rfmRulesHelp: "Recency, frequency and monetary scores are relative quintiles; ties receive the same score, and the first matching segment rule applies.", cohortRetentionTable: "Cohort retention table",
  },
  errors: {
    load: "Something went wrong loading this data", section: "Something went wrong showing this section",
    request: "The request is not valid.", server: "Something went wrong on the server.",
  },
} as const;

type SameKeys<T> = { [K in keyof T]: T[K] extends string ? string : SameKeys<T[K]> };

const tr = {
  common: {
    language: "Dil", english: "English", turkish: "Türkçe", loading: "Yükleniyor…", updating: "Güncelleniyor…",
    retry: "Yeniden dene", reset: "Sıfırla", error: "Hata", warning: "Uyarı", success: "Başarılı",
    unavailable: "Kullanılamıyor", insufficient: "Yetersiz veri", notEnough: "Yeterli veri yok",
    showValues: "Değerleri göster", period: "Dönem", currency: "Para birimi", rows: "Satırlar",
    expires: "Sona erme", startDate: "Başlangıç tarihi", endDate: "Bitiş tarihi", comparison: "Karşılaştırma",
    previousPeriod: "Önceki dönem", previousYear: "Geçen yılın aynı dönemi", overview: "Genel bakış",
    products: "Ürünler", customers: "Müşteriler", grossSales: "Brüt satış", orders: "Siparişler",
    unitsSold: "Satılan adet", averageOrderValue: "Ortalama sipariş değeri", analyzeAnother: "Başka bir dosya analiz et",
    dismiss: "Kapat", estimate: "Tahmin", currentPeriod: "Geçerli dönem", comparisonPeriod: "Karşılaştırma dönemi",
    rank: "Sıra", product: "Ürün", code: "Kod", share: "Pay", field: "Alan", reason: "Neden", file: "Dosya",
    yes: "Evet", no: "Hayır", partial: "kısmi", month: "Ay", average: "Ortalama", median: "Medyan",
    column: "Sütun", type: "Tür", rule: "Kural", fileFormat: "Dosya biçimi", startAnalysis: "Analiz başlat",
    compareWith: "Şununla karşılaştır", comparisonUnavailable: "Karşılaştırma kullanılamıyor", cohort: "Kohort",
    cohortSize: "Kohort büyüklüğü", mature: "Olgun", monthsObserved: "Gözlemlenen ay", observed: "Gözlemlenen",
    projected: "Tahmini", horizon: "12 aylık ufuk", totalEstimate: "12 aylık toplam (tahmin)",
    selectCurrency: "Para birimi seç", dashboardSections: "Panel bölümleri", customerAvailability: "Müşteri kullanılabilirliği",
    lowCoverage: "Düşük kapsam", datasetValue: "bu veri kümesi", met: "Karşılandı", notMet: "Karşılanmadı", notAvailable: "kullanılamıyor",
    extra: {
      back: "Geri", date: "Tarih", daily: "Günlük", weekly: "Haftalık", monthly: "Aylık",
      change: "Değişim", changePercent: "Değişim %", percentageChange: "Yüzde değişim",
      grossSalesNow: "Güncel brüt satış", grossSalesBefore: "Önceki brüt satış", unitsChange: "Birim değişimi", ordersChange: "Sipariş değişimi",
      noChange: "Değişim yok", noCurrentSales: "Güncel satış yok", distinctOrders: "Farklı siparişler",
      confidenceAB: "Güven A→B", confidenceBA: "Güven B→A", confidenceFrom: "Üründen güven", confidenceTo: "Ürüne güven",
      observedValue: "Müşteri başına gözlemlenen değer", weightedPrice: "Ağırlıklı birim fiyat", purchaseFrequencyTable: "Satın alma sıklığı tablosu",
      daysTable: "Satın almalar arasındaki günler tablosu", historicalTable: "Geçmiş Müşteri Değeri tablosu",
      rfmRecency: "RFM güncellik dağılımı", rfmFrequency: "RFM sıklık dağılımı",
      under10: "%10'un altında", notReliable: "Güvenilir bir tahmin için yeterli veri yok",
      projectionHelp: "Önceki müşteri gruplarının davranışına dayalı olarak müşterilerin ilk 12 ayındaki ortalama brüt satış tahmini. Gelecekteki satışların garantisi değildir ve maliyet, indirim veya iadeleri içermez.",
      expiredTitle: "Bu veri kümesinin süresi dolmuş veya silinmiş", expiredSentence: "Bir dosya yükleyin veya örnek veriyi yeniden deneyin.",
      unauthorizedTitle: "Bu veri kümesi bu tarayıcı oturumunda açılamıyor", unauthorizedSentence: "Veri kümeleri yalnızca oluşturuldukları sekmede açılabilir.",
      badRange: "Seçili tarih aralığı bu veri kümesi için geçerli değil", unavailableSection: "Bu bölüm kullanılamıyor.",
      uploadFailed: "Bir sorun oluştu — dosyanız içe aktarılmadı", sampleFailed: "Bir sorun oluştu — örnek veri yüklenemedi",
      uploadDisabledHint: "Örnek veriyi dene seçeneğini kullanmaya devam edebilirsiniz.", noOrders: "Seçili aralıkta sipariş yok.",
      startBeforeEnd: "Başlangıç tarihi bitiş tarihinden sonra olamaz", unavailableSuffix: "(kullanılamıyor)",
      previousPeriodLower: "önceki dönem", previousYearLower: "geçen yılın aynı dönemi",
      dataUpTo: "Veri tarihi", basedOn: "dayanak", matureCohort: "olgun kohort", matureCohorts: "olgun kohort",
      toFix: "düzeltilmeli.", showingFirst: "İlk kayıtlar gösteriliyor:", rejectedPrefix: "Dosya reddedildi ve hiçbir şey içe aktarılmadı:",
      warningExplanation: "Dosyanın reddedilme nedeni bunlar değildir. Yukarıdaki hataları düzeltin.",
      excludedOrders: "100'den fazla farklı ürün içeren sipariş yalnızca bu analizin dışında bırakıldı.",
      grossDaily: "Brüt satış — günlük", grossWeekly: "Brüt satış — haftalık", grossMonthly: "Brüt satış — aylık",
      grossPerMonth: "Aylık brüt satış", partialPeriod: "Kısmi dönem", over75: "%75 ve üzeri", up: "artış", down: "düşüş", versus: "karşılaştırma",
      thisDataset: "bu veri kümesi:", customers: "müşteri", months: "ay", fileRejected: "Dosya reddedildi ve hiçbir şey içe aktarılmadı:", errorsToFix: "düzeltilmeli.",
      expiresInLessMinute: "Bir dakikadan kısa süre içinde sona erer", expiresMinute_one: "{{count}} dakika içinde sona erer",
      expiresMinute_other: "{{count}} dakika içinde sona erer", expiresHour_one: "{{count}} saat içinde sona erer",
      expiresHour_other: "{{count}} saat içinde sona erer", expiresDay_one: "{{count}} gün içinde sona erer",
      expiresDay_other: "{{count}} gün içinde sona erer",
      warningsNotReason: "Bunlar dosyanın reddedilme nedeni değildir. Yukarıdaki hataları düzeltin.", rankBy: "Sıralama ölçütü", shareOfSales: "Brüt satış payı",
      top20Products: "Ürünlerin en yüksek %20'si:", productsFor80: "Brüt satışın %80'ine ulaşan ürün sayısı:",
      noProductOutperforms: "Karşılaştırma döneminden daha fazla satan ürün yok", noProductUnderperforms: "Karşılaştırma döneminden daha az satan ürün yok",
      inactiveFor: "Hareketsizlik süresi", noSaleInDays: "Şu sürede satış yok:", daysUpTo: "gün, bitiş tarihi", endOfRange: "seçili aralığın sonu",
      pairsNeed: "Ürün çiftleri için en az", sharedOrders: "ortak sipariş ve en az", support: "destek gerekir.",
      distinctProducts: "farklı ürün yalnızca bu analizin dışında bırakıldı.",
      productNotFound: "Ürün bulunamadı", allProducts: "Tüm ürünler", averagePricePaid: "Birim başına ortalama ödenen fiyat",
      realizedPriceHelp: "Gerçekleşen fiyatın değişimini gösterir; fiyat değişimlerinin satış değişimine neden olduğunu göstermez.",
      orderPenetration: "Sipariş penetrasyonu", ofOrders: "siparişin", period: "Dönem",
      grossSalesTrend: "Brüt satış eğilimi",
      projectedCustomerValue: "Tahmini 12 Aylık Müşteri Değeri", projectionTable: "Tahmini 12 Aylık Müşteri Değeri tablosu",
      projectionDescription: "Önceki müşteri gruplarının davranışına dayalı olarak müşterilerin ilk 12 ayındaki ortalama brüt satış tahmini. Gelecekteki satışların garantisi değildir ve maliyet, indirim veya iadeleri içermez.",
      addCustomerIdForEstimate: "Bu tahmini görmek için dosyanıza customer_id sütunu ekleyin.", notReliableEstimate: "Güvenilir bir tahmin için yeterli veri yok",
      observedSoFar: "Şimdiye kadar gözlemlenen", projectedEstimate: "Tahmini", total12Estimate: "12 aylık toplam (tahmin)",
      monthsObserved: "Gözlemlenen ay", mature: "Olgun", observed: "Gözlemlenen", cohort: "Kohort",
      validationReport: "Doğrulama raporu", errors: "Hatalar", warnings: "Uyarılar", row: "Satır", field: "Alan",
      reason: "Neden", code: "Kod", file: "Dosya", retentionTable: "Kohort elde tutma tablosu",
      cohortSize: "Kohort büyüklüğü", notYetObserved: "Henüz gözlemlenmedi", retentionShade: "Gölgelendirme, elde tutma:",
      estimate: "Tahmin", notAvailable: "kullanılamıyor", month: "Ay", rfmDrilldown: "RFM segment ayrıntısı",
    },
  },
  upload: {
    title: "Satış verisi yükle", file: "CSV dosyası", choose: "CSV dosyası seç", noFile: "Dosya seçilmedi",
    currency: "Para birimi", upload: "Yükle", sample: "Örnek veriyi dene", download: "Örnek CSV'yi indir",
    processing: "İşleniyor…", help: "Devam etmek için bir CSV dosyası ve para birimi seçin.",
    contract: "Veri kümesi sözleşmesi", requiredColumns: "Gerekli sütunlar", column: "Sütun", type: "Tür", rule: "Kural",
    validation: "Doğrulama raporu", errors: "Hatalar", warnings: "Uyarılar", row: "Satır",
    format: "Dosya biçimi", start: "Analiz başlat", extraColumns: "Ek sütunlar yok sayılır.",
    invalidWhole: "Herhangi bir satır geçersizse dosyanın tamamı reddedilir.",
    stringType: "Metin", dateType: "Tarih", integerType: "Tam sayı", decimalType: "Ondalık",
    orderRule: "Zorunlu ve boş olamaz. Farklı siparişleri saymak için kullanılır.",
    dateRule: "YYYY-AA-GG biçiminde zorunlu ISO takvim tarihi. Gelecekte olamaz.",
    productRule: "Zorunlu ve boş olamaz. Ürünü tanımlar.",
    quantityRule: "Zorunlu ve sıfırdan büyük. Sıfır ve negatif miktarlar geçersizdir.",
    priceRule: "Zorunlu ve negatif olamaz. Sıfır fiyat uyarıyla kabul edilir; negatif fiyat geçersizdir.",
    customerRule: "İsteğe bağlıdır. Boş olabilir; karma kimlik, UUID veya kişisel olmayan dahili anahtar kullanın (e-posta, telefon numarası ya da ad kullanmayın).",
    productNameRule: "Zorunlu ve boş olamaz. Bir product_id, yükleme içinde tam olarak bir ada karşılık gelmelidir.",
    intro: "Tamamlanan satış satırlarını içeren bir CSV yükleyin; brüt satışları, siparişleri ve en iyi ürünleri görün.",
    demoIntro: "Bu demo yalnızca örnek veriyi kabul eder. Brüt satışları, siparişleri ve en iyi ürünleri görmek için Örnek veriyi dene'ye tıklayın.",
    formatHelp: "Her satır, tamamlanmış bir siparişteki bir ürün satırıdır. Dosyada altı zorunlu sütun ile bir isteğe bağlı sütun bulunmalıdır.",
    chooseFile: "Dosya seç", nativeNoFile: "Dosya seçilmedi", selfHosted: "Yüklemeler kendi sunucunuzda çalışan sürümde kullanılabilir.",
    runDocker: "Docker ile kendiniz çalıştırın",
  },
  dashboard: {
    dateRange: "Tarih aralığı", keyFigures: "Temel göstergeler", salesTrend: "Satış eğilimi", topProducts: "En iyi ürünler",
    noSales: "Bu aralıkta satış yok", noSalesSelected: "Seçili aralıkta satış yok",
    noProducts: "Bu aralıkta satılan ürün yok", goUpload: "Yükleme ekranına git", customerCoverage: "Müşteri kapsamı",
    identifiedOrders: "Tanımlanan siparişler", unidentifiedOrders: "Tanımlanamayan siparişler",
    customerAnalyticsUnavailable: "Müşteri analitiği kullanılamıyor", readContract: "Veri kümesi sözleşmesini oku",
    customerAnalyses: "Müşteri analizleri", productAnalyses: "Ürün analizleri",
    dismissNotice: "Bildirimi kapat", dismissSuccess: "Başarı bildirimini kapat", customerHidden: "Müşteri analizi gizli: kapsam %50'nin altında",
  },
  products: {
    rankings: "Sıralamalar", rankBy: "Sıralama ölçütü", grossSalesShare: "Brüt satış payı",
    risingFalling: "Yükselen ve düşen ürünler", rising: "Yükselen", falling: "Düşen", dormant: "Hareketsiz ürünler",
    inactiveFor: "Hareketsizlik süresi", boughtTogether: "Birlikte alınanlar", productA: "Ürün A", productB: "Ürün B",
    sharedOrders: "Ortak siparişler", support: "Destek", lift: "Kaldıraç", allProducts: "Tüm ürünler",
    productDetail: "Ürün ayrıntısı", grossSalesTrend: "Brüt satış eğilimi", averagePrice: "Birim başına ortalama ödenen fiyat",
    penetration: "Sipariş penetrasyonu", lastSale: "Son satış", daysInactive: "Hareketsiz gün", earlierGrossSales: "Önceki brüt satış",
    earlierOrders: "Önceki siparişler", cumulativeShare: "Kümülatif pay", noSales: "Satış yok", productNotFound: "Ürün bulunamadı",
    noMore: "Karşılaştırma döneminden daha fazla satan ürün yok", noLess: "Karşılaştırma döneminden daha az satan ürün yok",
    noPair: "Bu aralıkta eşikleri karşılayan ürün çifti yok", noRelated: "Bu aralıkta eşikleri karşılayan ilişkili ürün yok",
    noUnits: "Bu aralıkta bu üründen satılan birim yok", averageUnit: "Birim başına ortalama fiyat",
    rankingKey: "Ürünler brüt satışa göre soldan sağa sıralanır. Düz çizgi: brüt satışın kümülatif payı. Kesikli çizgi: brüt satışın %80'i.",
    reach80: "Brüt satışın %80'ine ulaşan ürün sayısı:", top20: "Ürünlerin en yüksek %20'si:",
    realisedPrice: "Gerçekleşen fiyatın değişimini gösterir; fiyat değişimlerinin satış değişimine neden olduğunu göstermez.", newProduct: "Yeni",
  },
  customers: {
    keyFigures: "Müşteri temel göstergeleri", identified: "Tanımlanan müşteriler", newGrossSales: "Yeni müşteri brüt satışı",
    returningGrossSales: "Geri dönen müşteri brüt satışı", repeatRate: "Tekrar satın alma oranı",
    medianDays: "Satın almalar arasındaki medyan gün", daysBetween: "Satın almalar arasındaki günler",
    intervals: "Aralıklar", bucket: "Grup", cohortRetention: "Kohort elde tutma", historicalValue: "Geçmiş Müşteri Değeri",
    projectedValue: "Tahmini 12 Aylık Müşteri Değeri", rfm: "RFM segmentleri", segment: "Segment",
    purchaseFrequency: "Satın alma sıklığı", concentration: "Müşteri yoğunlaşması", topDecile: "Üst ondalık payı",
    recency: "Güncellik", frequency: "Sıklık", cohorts: "Kohortlar", notObserved: "Henüz gözlemlenmedi",
    retentionKey: "Elde tutma gölgelendirme anahtarı", drilldown: "RFM segment ayrıntısı",
    identifiedGrossSales: "Tanımlanan brüt satış", observedSoFar: "Şimdiye kadar gözlemlenen",
    projectionTable: "Tahmini 12 Aylık Müşteri Değeri tablosu", rfmTable: "RFM segmentleri tablosu",
    repeatRateLabel: "Tekrar satın alma oranı", shading: "Gölgelendirme, elde tutma:",
    historicalHelp: "Tanımlanmış müşteri başına gözlemlenen brüt satış. Tahmin değildir.",
    rfmHelp: "Segmentler evrensel ölçütlere değil, bu yüklemedeki müşterilere göredir.",
    rfmRules: "RFM puanlama kuralları",
    rfmRulesHelp: "Güncellik, sıklık ve parasal puanlar göreli beşte birlik dilimlerdir; eşit değerler aynı puanı alır ve ilk eşleşen segment kuralı uygulanır.", cohortRetentionTable: "Kohort elde tutma tablosu",
  },
  errors: {
    load: "Bu veri yüklenirken bir sorun oluştu", section: "Bu bölüm gösterilirken bir sorun oluştu",
    request: "İstek geçerli değil.", server: "Sunucuda bir sorun oluştu.",
  },
} satisfies SameKeys<typeof en>;

export const resources = { en: { translation: en }, tr: { translation: tr } } as const;

export function normalizeLocale(value: string | null | undefined): SupportedLocale | null {
  if (!value) return null;
  const base = value.trim().toLowerCase().split("-")[0];
  return supportedLocales.includes(base as SupportedLocale) ? (base as SupportedLocale) : null;
}

export function resolveInitialLocale(storage?: Pick<Storage, "getItem"> | null,
  languages: readonly string[] = typeof navigator === "undefined" ? [] : navigator.languages): SupportedLocale {
  let selectedStorage = storage;
  if (selectedStorage === undefined && typeof window !== "undefined") {
    try { selectedStorage = window.localStorage; } catch { selectedStorage = null; }
  }
  let saved: SupportedLocale | null = null;
  try { saved = normalizeLocale(selectedStorage?.getItem(LOCALE_STORAGE_KEY)); } catch { /* use browser language */ }
  if (saved) return saved;
  for (const language of languages) {
    const locale = normalizeLocale(language);
    if (locale) return locale;
  }
  return "en";
}

const initialLocale = resolveInitialLocale();
void i18n.use(initReactI18next).init({
  resources, lng: initialLocale, fallbackLng: "en", supportedLngs: [...supportedLocales],
  interpolation: { escapeValue: false }, returnNull: false,
  missingKeyHandler: import.meta.env.DEV
    ? (_languages, namespace, key) => {
        throw new Error(`Missing i18n resource: ${namespace}:${key}`);
      }
    : undefined,
});
document.documentElement.lang = initialLocale;
i18n.on("languageChanged", (language) => {
  const locale = normalizeLocale(language) ?? "en";
  document.documentElement.lang = locale;
  try { localStorage.setItem(LOCALE_STORAGE_KEY, locale); } catch { /* language switching still works */ }
});

export async function setLocale(locale: SupportedLocale): Promise<void> {
  await i18n.changeLanguage(locale);
}

export const englishToKey = new Map<string, string>();
function collect(value: object, prefix = "") {
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof child === "string") englishToKey.set(child, path);
    else collect(child, path);
  }
}
collect(en);

export default i18n;
