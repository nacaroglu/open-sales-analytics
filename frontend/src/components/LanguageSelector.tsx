import { useTranslation } from "react-i18next";
import { normalizeLocale, setLocale, type SupportedLocale } from "../i18n";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700";

export default function LanguageSelector() {
  const { t, i18n } = useTranslation();
  const locale = normalizeLocale(i18n.resolvedLanguage) ?? "en";
  return (
    <label className="block text-sm font-medium text-slate-900">
      {t("common.language")}
      <select
        aria-label={t("common.language")}
        value={locale}
        onChange={(event) => void setLocale(event.target.value as SupportedLocale)}
        className={`mt-1 block h-10 rounded-md border border-slate-500 bg-white px-3 text-base text-slate-900 ${FOCUS}`}
      >
        <option value="en">English</option>
        <option value="tr">Türkçe</option>
        <option value="de">Deutsch</option>
        <option value="ru">Русский</option>
        <option value="es">Español</option>
        <option value="zh-CN">简体中文</option>
        <option value="ja">日本語</option>
      </select>
    </label>
  );
}
