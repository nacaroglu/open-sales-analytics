import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import i18n, { englishToKey, normalizeLocale } from "../i18n";
import { formatDay } from "../lib/format";

const textSources = new WeakMap<Text, { source: string; lastTranslation: string }>();
const attributeSources = new WeakMap<Element, Map<string, { source: string; lastTranslation: string }>>();
const ATTRIBUTES = ["aria-label", "title", "placeholder"] as const;

const turkishPatterns: [RegExp, (...matches: string[]) => string][] = [
  [/^Your data is ready\. The figures below are from the uploaded dataset\.$/, () => "Verileriniz hazır. Aşağıdaki rakamlar yüklenen veri kümesindendir."],
  [/^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$/, (start, end) => `${start}–${end}`],
  [/^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2}) compared with (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2}) \((previous period|same period last year)\)$/, (start, end, compareStart, compareEnd, mode) => `${start}–${end}, ${compareStart}–${compareEnd} ile karşılaştırıldı (${mode === "previous period" ? "önceki dönem" : "geçen yılın aynı dönemi"})`],
  [/^(.+) of orders \((.+) of (.+)\)$/, (coverage, selected, total) => `Siparişlerin ${coverage} kadarı (${selected}/${total})`],
  [/^(.+) of orders$/, (coverage) => `${coverage} siparişin`],
  [/^Expires in less than a minute$/, () => "Bir dakikadan kısa süre içinde sona erer"],
  [/^Expires in (\d+) minute(?:s)?$/, (n) => `${n} dakika içinde sona erer`],
  [/^Expires in (\d+) hour(?:s)?$/, (n) => `${n} saat içinde sona erer`],
  [/^Expires in (\d+) day(?:s)?$/, (n) => `${n} gün içinde sona erer`],
  [/^(\d+) days$/, (n) => `${n} gün`],
  [/^Month (\d+)$/, (n) => `Ay ${n}`],
  [/^(\d+) customers$/, (n) => `${n} müşteri`],
  [/^Median: (.+) days$/, (value) => `Medyan: ${value} gün`],
  [/^(.+) drill-down$/, (segment) => `${segment} ayrıntısı`],
  [/^No product has been inactive for (\d+) days$/, (n) => `${n} gündür hareketsiz ürün yok`],
  [/^No sale in the (\d+) days up to (.+), the end of the selected range$/, (n, date) => `Seçili aralığın sonu olan ${date} tarihine kadarki ${n} günde satış yok`],
  [/^Top (\d+) products? by gross sales from (.+) to (.+)$/, (n, start, end) => `${start}–${end} arasında brüt satışa göre ilk ${n} ürün`],
  [/^Cumulative share of gross sales over (\d+) products ranked by gross sales, from (.+) to (.+)$/, (n, start, end) => `${start}–${end} arasında brüt satışa göre sıralanmış ${n} ürünün kümülatif brüt satış payı`],
  [/^(Daily|Weekly|Monthly) gross sales from (.+) to (.+)$/, (period, start, end) => `${start}–${end} arasında ${period === "Daily" ? "günlük" : period === "Weekly" ? "haftalık" : "aylık"} brüt satış`],
  [/^Gross sales per (day|week|month) from (.+) to (.+)$/, (period, start, end) => `${start}–${end} arasında ${period === "day" ? "günlük" : period === "week" ? "haftalık" : "aylık"} brüt satış`],
  [/^Weighted unit price per (day|week|month) from (.+) to (.+)$/, (period, start, end) => `${start}–${end} arasında ${period === "day" ? "günlük" : period === "week" ? "haftalık" : "aylık"} ağırlıklı birim fiyat`],
  [/^Week of (.+)$/, (date) => `${date} haftası`],
  [/^In the selected range: (.+) of (.+) orders have a customer ID \((.+)\)\.$/, (identified, total, coverage) => `Seçili aralıkta ${total} siparişin ${identified} tanesinde müşteri kimliği var (${coverage}).`],
  [/^Low coverage: based on (.+) of orders\.$/, (coverage) => `Düşük kapsam: siparişlerin ${coverage} kadarına dayanır.`],
  [/^(.+) state$/, (metric) => `${translateOwnedText(metric)} durumu`],
  [/^Bar chart of days between purchase interval buckets from (.+) to (.+)$/, (start, end) => `${start}–${end} arasındaki satın alma aralığı gün gruplarının çubuk grafiği`],
  [/^Line chart of observed gross sales per identified customer by cohort age from (.+) to (.+)$/, (start, end) => `${start}–${end} arasında kohort yaşına göre kimliği belirlenmiş müşteri başına gözlemlenen brüt satış çizgi grafiği`],
  [/^Start date must be between (.+) and (.+)$/, (min, max) => `Başlangıç tarihi ${min} ile ${max} arasında olmalıdır`],
  [/^End date must be between (.+) and (.+)$/, (min, max) => `Bitiş tarihi ${min} ile ${max} arasında olmalıdır`],
  [/^The file is larger than the (.+) limit\.$/, (limit) => `Dosya ${limit} sınırından büyük.`],
  [/^(.+) orders with more than 100 distinct products were left out of this analysis only\.$/, (count) => `100'den fazla farklı ürün içeren ${count} sipariş yalnızca bu analizin dışında bırakıldı.`],
  [/^(.+) of orders \((.+) of (.+)\)$/, (coverage, selected, total) => `Siparişlerin ${coverage} kadarı (${selected}/${total})`],
  [/^(.+) to (.+) compared with (.+) to (.+) \((.+)\)$/, (a, b, c, d, mode) => `${a}–${b}, ${c}–${d} ile karşılaştırıldı (${mode === "previous period" ? "önceki dönem" : "geçen yılın aynı dönemi"})`],
];

const dynamicRules: [string, RegExp][] = [
  ["success", /^Your data is ready\. The figures below are from the uploaded dataset\.$/],
  ["dateRange", /^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$/],
  ["comparisonRange", /^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2}) compared with (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2}) \((previous period|same period last year)\)$/],
  ["comparisonWindow", /^\((\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2}), (previous period|same period last year)\)$/],
  ["orderCoverage", /^(.+) of orders \((.+) of (.+)\)$/],
  ["ordersOnly", /^(.+) of orders$/],
  ["expiresMinute", /^Expires in (\d+) minute(?:s)?$/],
  ["expiresHour", /^Expires in (\d+) hour(?:s)?$/],
  ["expiresDay", /^Expires in (\d+) day(?:s)?$/],
  ["days", /^(\d+) days$/],
  ["month", /^Month (\d+)$/],
  ["customers", /^(\d+) customers$/],
  ["medianDays", /^Median: (.+) days$/],
  ["drilldown", /^(.+) drill-down$/],
  ["noDormant", /^No product has been inactive for (\d+) days$/],
  ["noSaleEnd", /^No sale in the (\d+) days up to (.+), the end of the selected range$/],
  ["topProducts", /^Top (\d+) products? by gross sales from (.+) to (.+)$/],
  ["pareto", /^Cumulative share of gross sales over (\d+) products ranked by gross sales, from (.+) to (.+)$/],
  ["dailyGross", /^(Daily|Weekly|Monthly) gross sales from (.+) to (.+)$/],
  ["grossPer", /^Gross sales per (day|week|month) from (.+) to (.+)$/],
  ["weightedPrice", /^Weighted unit price per (day|week|month) from (.+) to (.+)$/],
  ["weekOf", /^Week of (.+)$/],
  ["identifiedCoverage", /^In the selected range: (.+) of (.+) orders have a customer ID \((.+)\)\.$/],
  ["lowCoverage", /^Low coverage: based on (.+) of orders\.$/],
  ["metricState", /^(.+) state$/],
  ["barChart", /^Bar chart of days between purchase interval buckets from (.+) to (.+)$/],
  ["lineChart", /^Line chart of observed gross sales per identified customer by cohort age from (.+) to (.+)$/],
  ["startBetween", /^Start date must be between (.+) and (.+)$/],
  ["endBetween", /^End date must be between (.+) and (.+)$/],
  ["fileTooLarge", /^The file is larger than the (.+) limit\.$/],
  ["excluded", /^(.+) orders with more than 100 distinct products were left out of this analysis only\.$/],
  ["comparisonSentence", /^(.+) to (.+) compared with (.+) to (.+) \((.+)\)$/],
];

const dynamicTemplates: Record<"de" | "ru" | "es" | "zh-CN" | "ja", Record<string, string>> = {
  de: {
    success: "Deine Daten sind bereit. Die folgenden Zahlen stammen aus dem hochgeladenen Datensatz.",
    dateRange: "{0} bis {1}", comparisonRange: "{0} bis {1} im Vergleich zu {2} bis {3} ({4})", comparisonWindow: "({0} bis {1}, {2})",
    orderCoverage: "{0} der Bestellungen ({1} von {2})", ordersOnly: "{0} der Bestellungen",
    expiresMinute: "Läuft in {0} Minuten ab", expiresHour: "Läuft in {0} Stunden ab", expiresDay: "Läuft in {0} Tagen ab",
    days: "{0} Tage", month: "Monat {0}", customers: "{0} Kunden", medianDays: "Median: {0} Tage",
    drilldown: "Details zu {0}", noDormant: "Seit {0} Tagen ist kein Produkt inaktiv",
    noSaleEnd: "Keine Verkäufe in den {0} Tagen bis zum Ende des ausgewählten Zeitraums ({1})",
    topProducts: "Top {0} Produkte nach Bruttoumsatz von {1} bis {2}", pareto: "Kumulierter Bruttoumsatzanteil der {0} nach Bruttoumsatz sortierten Produkte von {1} bis {2}",
    dailyGross: "Bruttoumsatz {0} von {1} bis {2}", grossPer: "Bruttoumsatz pro {0} von {1} bis {2}", weightedPrice: "Gewichteter Stückpreis pro {0} von {1} bis {2}",
    weekOf: "Woche ab {0}", identifiedCoverage: "Im ausgewählten Zeitraum haben {0} von {1} Bestellungen eine Kunden-ID ({2}).",
    lowCoverage: "Geringe Abdeckung: basiert auf {0} der Bestellungen.", metricState: "Status: {0}",
    barChart: "Balkendiagramm der Kaufabstandsgruppen von {0} bis {1}", lineChart: "Liniendiagramm des beobachteten Bruttoumsatzes pro identifiziertem Kunden nach Kohortenalter von {0} bis {1}",
    startBetween: "Das Startdatum muss zwischen {0} und {1} liegen", endBetween: "Das Enddatum muss zwischen {0} und {1} liegen",
    fileTooLarge: "Die Datei überschreitet das Limit von {0}.", excluded: "{0} Bestellungen mit mehr als 100 verschiedenen Produkten wurden nur aus dieser Analyse ausgeschlossen.",
    comparisonSentence: "{0} bis {1} im Vergleich zu {2} bis {3} ({4})",
  },
  ru: {
    success: "Данные готовы. Ниже показаны значения из загруженного набора данных.",
    dateRange: "{0} — {1}", comparisonRange: "{0} — {1} по сравнению с {2} — {3} ({4})", comparisonWindow: "({0} — {1}, {2})",
    orderCoverage: "{0} заказов ({1} из {2})", ordersOnly: "{0} заказов",
    expiresMinute: "Истекает через {0} мин.", expiresHour: "Истекает через {0} ч", expiresDay: "Истекает через {0} дн.",
    days: "{0} дн.", month: "Месяц {0}", customers: "Клиентов: {0}", medianDays: "Медиана: {0} дн.",
    drilldown: "Подробнее о сегменте «{0}»", noDormant: "За последние {0} дн. неактивных товаров нет",
    noSaleEnd: "Нет продаж за {0} дн. до конца выбранного периода ({1})",
    topProducts: "Топ-{0} товаров по валовым продажам с {1} по {2}", pareto: "Накопленная доля валовых продаж для {0} товаров, ранжированных по продажам, с {1} по {2}",
    dailyGross: "Валовые продажи ({0}) с {1} по {2}", grossPer: "Валовые продажи за {0} с {1} по {2}", weightedPrice: "Средневзвешенная цена за {0} с {1} по {2}",
    weekOf: "Неделя с {0}", identifiedCoverage: "В выбранном диапазоне у {0} из {1} заказов есть ID клиента ({2}).",
    lowCoverage: "Низкий охват: данные есть для {0} заказов.", metricState: "Состояние: {0}",
    barChart: "Столбчатая диаграмма интервалов между покупками с {0} по {1}", lineChart: "Линейный график наблюдаемых валовых продаж на идентифицированного клиента по возрасту когорты с {0} по {1}",
    startBetween: "Дата начала должна быть между {0} и {1}", endBetween: "Дата окончания должна быть между {0} и {1}",
    fileTooLarge: "Размер файла превышает лимит {0}.", excluded: "{0} заказов с более чем 100 разными товарами исключены только из этого анализа.",
    comparisonSentence: "{0} — {1} по сравнению с {2} — {3} ({4})",
  },
  es: {
    success: "Tus datos están listos. Las cifras siguientes corresponden al conjunto de datos cargado.",
    dateRange: "{0} a {1}", comparisonRange: "{0} a {1} frente a {2} a {3} ({4})", comparisonWindow: "({0} a {1}, {2})",
    orderCoverage: "{0} de los pedidos ({1} de {2})", ordersOnly: "{0} de los pedidos",
    expiresMinute: "Caduca en {0} minutos", expiresHour: "Caduca en {0} horas", expiresDay: "Caduca en {0} días",
    days: "{0} días", month: "Mes {0}", customers: "{0} clientes", medianDays: "Mediana: {0} días",
    drilldown: "Detalle de {0}", noDormant: "No hay productos inactivos desde hace {0} días",
    noSaleEnd: "Sin ventas en los {0} días hasta el final del intervalo seleccionado ({1})",
    topProducts: "Los {0} productos principales por ventas brutas de {1} a {2}", pareto: "Porcentaje acumulado de ventas brutas de {0} productos ordenados por ventas, de {1} a {2}",
    dailyGross: "Ventas brutas {0} de {1} a {2}", grossPer: "Ventas brutas por {0} de {1} a {2}", weightedPrice: "Precio unitario ponderado por {0} de {1} a {2}",
    weekOf: "Semana del {0}", identifiedCoverage: "En el intervalo seleccionado, {0} de {1} pedidos tienen ID de cliente ({2}).",
    lowCoverage: "Cobertura baja: se basa en {0} de los pedidos.", metricState: "Estado: {0}",
    barChart: "Gráfico de barras de intervalos entre compras de {0} a {1}", lineChart: "Gráfico de líneas de ventas brutas observadas por cliente identificado según la antigüedad de cohorte, de {0} a {1}",
    startBetween: "La fecha de inicio debe estar entre {0} y {1}", endBetween: "La fecha de fin debe estar entre {0} y {1}",
    fileTooLarge: "El archivo supera el límite de {0}.", excluded: "{0} pedidos con más de 100 productos distintos se excluyeron solo de este análisis.",
    comparisonSentence: "{0} a {1} frente a {2} a {3} ({4})",
  },
  "zh-CN": {
    success: "数据已准备就绪。以下数字来自已上传的数据集。",
    dateRange: "{0} 至 {1}", comparisonRange: "{0} 至 {1}，与 {2} 至 {3} 比较（{4}）", comparisonWindow: "（{0} 至 {1}，{2}）",
    orderCoverage: "占订单的 {0}（{1}/{2}）", ordersOnly: "占订单的 {0}",
    expiresMinute: "将在 {0} 分钟后过期", expiresHour: "将在 {0} 小时后过期", expiresDay: "将在 {0} 天后过期",
    days: "{0} 天", month: "第 {0} 月", customers: "{0} 位客户", medianDays: "中位数：{0} 天",
    drilldown: "{0}细分详情", noDormant: "过去 {0} 天没有不活跃商品",
    noSaleEnd: "截至所选范围结束日期 {1}，过去 {0} 天没有销售",
    topProducts: "{1} 至 {2} 销售总额排名前 {0} 的商品", pareto: "{1} 至 {2} 按销售总额排序的 {0} 种商品的累计销售占比",
    dailyGross: "{1} 至 {2} 的{0}销售总额", grossPer: "{1} 至 {2} 每{0}销售总额", weightedPrice: "{1} 至 {2} 每{0}加权单价",
    weekOf: "{0}所在周", identifiedCoverage: "所选范围内 {1} 个订单中有 {0} 个包含客户 ID（{2}）。",
    lowCoverage: "覆盖率低：仅基于 {0} 的订单。", metricState: "{0}状态",
    barChart: "{0} 至 {1} 购买间隔分组柱状图", lineChart: "{0} 至 {1} 按队列年龄统计的已识别客户人均实际销售总额折线图",
    startBetween: "开始日期必须介于 {0} 和 {1} 之间", endBetween: "结束日期必须介于 {0} 和 {1} 之间",
    fileTooLarge: "文件超过 {0} 的大小限制。", excluded: "{0} 个包含超过 100 种不同商品的订单仅从此分析中排除。",
    comparisonSentence: "{0} 至 {1}，与 {2} 至 {3} 比较（{4}）",
  },
  ja: {
    success: "データの準備ができました。以下の数値はアップロードされたデータセットのものです。",
    dateRange: "{0}～{1}", comparisonRange: "{0}～{1} と {2}～{3} の比較（{4}）", comparisonWindow: "（{0}～{1}、{2}）",
    orderCoverage: "注文の{0}（{1}/{2}）", ordersOnly: "注文の{0}",
    expiresMinute: "{0}分後に期限切れ", expiresHour: "{0}時間後に期限切れ", expiresDay: "{0}日後に期限切れ",
    days: "{0}日", month: "{0}か月目", customers: "顧客数：{0}", medianDays: "中央値：{0}日",
    drilldown: "{0}の詳細", noDormant: "過去{0}日間に非アクティブな商品はありません",
    noSaleEnd: "選択期間の終了日（{1}）までの{0}日間に売上はありません",
    topProducts: "{1}～{2}の総売上上位{0}商品", pareto: "{1}～{2}の総売上順上位{0}商品の累積割合",
    dailyGross: "{1}～{2}の{0}総売上", grossPer: "{1}～{2}の{0}あたり総売上", weightedPrice: "{1}～{2}の{0}あたり加重平均単価",
    weekOf: "{0}の週", identifiedCoverage: "選択期間の{1}件中{0}件に顧客IDがあります（{2}）。",
    lowCoverage: "カバー率が低いため、注文の{0}のみを基にしています。", metricState: "{0}の状態",
    barChart: "{0}～{1}の購入間隔区分の棒グラフ", lineChart: "{0}～{1}のコホート経過月別・識別済み顧客あたり実績総売上の折れ線グラフ",
    startBetween: "開始日は{0}から{1}の間にしてください", endBetween: "終了日は{0}から{1}の間にしてください",
    fileTooLarge: "ファイルサイズが上限 {0} を超えています。", excluded: "異なる商品が100点を超える注文{0}件は、この分析からのみ除外されました。",
    comparisonSentence: "{0}～{1} と {2}～{3} の比較（{4}）",
  },
};

function translateDynamic(locale: "de" | "ru" | "es" | "zh-CN" | "ja", source: string): string | undefined {
  for (const [key, pattern] of dynamicRules) {
    const match = source.match(pattern);
    const template = dynamicTemplates[locale][key];
    if (match && template) {
      const values = match.slice(1).map((value) => {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
        const date = new Date(`${value}T00:00:00Z`);
        return Number.isNaN(date.getTime()) ? value : formatDay(date, true);
      });
      const periods: Record<string, Record<string, string>> = {
        de: { Daily: "täglich", Weekly: "wöchentlich", Monthly: "monatlich", day: "Tag", week: "Woche", month: "Monat", "previous period": "vorheriger Zeitraum", "same period last year": "gleicher Zeitraum im Vorjahr" },
        ru: { Daily: "ежедневно", Weekly: "еженедельно", Monthly: "ежемесячно", day: "день", week: "неделю", month: "месяц", "previous period": "предыдущий период", "same period last year": "тот же период прошлого года" },
        es: { Daily: "diarias", Weekly: "semanales", Monthly: "mensuales", day: "día", week: "semana", month: "mes", "previous period": "período anterior", "same period last year": "mismo período del año pasado" },
        "zh-CN": { Daily: "每日", Weekly: "每周", Monthly: "每月", day: "天", week: "周", month: "月", "previous period": "上一期间", "same period last year": "去年同期" },
        ja: { Daily: "日別", Weekly: "週別", Monthly: "月別", day: "日", week: "週", month: "月", "previous period": "前の期間", "same period last year": "前年同期" },
      };
      if (["dailyGross", "comparisonRange", "comparisonWindow", "comparisonSentence"].includes(key)) {
        const valueIndex = key === "dailyGross" ? 0 : values.length - 1;
        values[valueIndex] = periods[locale][values[valueIndex]] ?? values[valueIndex];
      } else if (key === "grossPer" || key === "weightedPrice") {
        values[0] = periods[locale][values[0]] ?? values[0];
      }
      return template.replace(/\{(\d+)\}/g, (_token, index: string) => values[Number(index)] ?? "");
    }
  }
  return undefined;
}

export function translateOwnedText(source: string): string {
  const locale = normalizeLocale(i18n.resolvedLanguage) ?? "en";
  if (locale === "en") return source;
  const key = englishToKey.get(source);
  if (key) return i18n.t(key);
  if (locale !== "tr") return translateDynamic(locale, source) ?? source;
  for (const [pattern, replacement] of turkishPatterns) {
    const match = source.match(pattern);
    if (match) return replacement(...match.slice(1));
  }
  return source;
}

function translateTextNode(node: Text, preserveSource: boolean = false): void {
  const parent = node.parentElement;
  if (!parent || parent.closest("[data-i18n-ignore], [data-i18n-data]")) return;
  if (parent.classList.contains("font-mono")) return;
  const productDetail = parent.closest('section[aria-label="Product detail"], section[aria-label="Ürün ayrıntısı"]');
  if (productDetail && (parent.matches("h2") || parent.classList.contains("font-mono"))) return;
  const current = node.data;
  const previous = textSources.get(node);
  const source = previous !== undefined && (preserveSource || current === previous.lastTranslation) ? previous.source : current;
  const leading = source.match(/^\s*/)?.[0] ?? "";
  const trailing = source.match(/\s*$/)?.[0] ?? "";
  const trimmed = source.trim();
  if (!trimmed) return;
  const translated = `${leading}${translateOwnedText(trimmed)}${trailing}`;
  textSources.set(node, { source, lastTranslation: translated });
  if (node.data !== translated) node.data = translated;
}

function translateElement(element: Element, preserveSource: boolean = false): void {
  if (element.closest("[data-i18n-ignore]")) return;
  let sources = attributeSources.get(element);
  if (!sources) { sources = new Map(); attributeSources.set(element, sources); }
  for (const attribute of ATTRIBUTES) {
    const current = element.getAttribute(attribute);
    if (current === null) continue;
    const previous = sources.get(attribute);
    const source = previous !== undefined && (preserveSource || current === previous.lastTranslation) ? previous.source : current;
    const translated = translateOwnedText(source);
    sources.set(attribute, { source, lastTranslation: translated });
    if (current !== translated) element.setAttribute(attribute, translated);
  }
  for (const child of element.childNodes) if (child instanceof Text) translateTextNode(child, preserveSource);
}

function walk(root: Element, preserveSource: boolean = false): void {
  translateElement(root, preserveSource);
  for (const element of root.querySelectorAll("*")) translateElement(element, preserveSource);
}

export default function LocalizedUi({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const { i18n: instance } = useTranslation();
  useEffect(() => {
    if (!root.current) return;
    let applying = false;
    const apply = () => {
      if (!root.current || applying) return;
      applying = true; walk(root.current); applying = false;
    };
    apply();
    const observer = new MutationObserver(() => queueMicrotask(apply));
    observer.observe(root.current, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: [...ATTRIBUTES] });
    const languageChanged = () => {
      if (!root.current || applying) return;
      applying = true; walk(root.current, true); applying = false;
    };
    instance.on("languageChanged", languageChanged);
    return () => { observer.disconnect(); instance.off("languageChanged", languageChanged); };
  }, [instance]);
  return <div ref={root} className="contents">{children}</div>;
}
