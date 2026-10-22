import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import i18n, { englishToKey, normalizeLocale } from "../i18n";

const textSources = new WeakMap<Text, string>();
const attributeSources = new WeakMap<Element, Map<string, string>>();
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

export function translateOwnedText(source: string): string {
  if ((normalizeLocale(i18n.resolvedLanguage) ?? "en") === "en") return source;
  const key = englishToKey.get(source);
  if (key) return i18n.t(key);
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
  const previousSource = textSources.get(node);
  const previousTranslation = previousSource === undefined ? undefined : translateOwnedText(previousSource);
  const source = previousSource !== undefined && (preserveSource || current === previousTranslation) ? previousSource : current;
  textSources.set(node, source);
  const leading = source.match(/^\s*/)?.[0] ?? "";
  const trailing = source.match(/\s*$/)?.[0] ?? "";
  const trimmed = source.trim();
  if (!trimmed) return;
  const translated = `${leading}${translateOwnedText(trimmed)}${trailing}`;
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
    const source = previous !== undefined && (preserveSource || current === translateOwnedText(previous)) ? previous : current;
    sources.set(attribute, source);
    const translated = translateOwnedText(source);
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
