# Katkıda Bulunma

[English](CONTRIBUTING.md) | [Türkçe](CONTRIBUTING.tr-TR.md) | [Deutsch](CONTRIBUTING.de-DE.md) | [Русский](CONTRIBUTING.ru-RU.md) | [Español](CONTRIBUTING.es-ES.md) | [简体中文](CONTRIBUTING.zh-CN.md) | [日本語](CONTRIBUTING.ja-JP.md)

> Bu çevirinin doğruluk kaynağı [İngilizce belgedir](CONTRIBUTING.md). Eşitleme revizyonu: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

Open Sales Analytics'e yardım ettiğiniz için teşekkürler. Hata bildirimleri, fikirler ve pull request'ler memnuniyetle karşılanır.

## Hata bildirme veya özellik isteme

**Bug report** ya da **Feature request** şablonuyla bir issue açın. Bir hata için, hatayı gösteren mümkün olan en küçük CSV
en yararlısıdır. Asla gerçek müşteri verisi eklemeyin: uydurma sipariş ve müşteri kimlikleri kullanın. Bir güvenlik
sorununu herkese açık bir issue'da değil, Security sekmesindeki GitHub **Report a vulnerability** düğmesi aracılığıyla
özel olarak bildirin.

## Çalışmalar nasıl düzenlenir

- Çalışmalar, her seferinde bir tane olmak üzere GitHub issue'larıyla takip edilir. Bir issue; hedefini, kabul
  kriterlerini, kapsam dışı olanları ve kısıtlarını belirtir ([`_docs/task-template.md`](_docs/task-template.md)).
- Issue'nun adını taşıyan bir dalda çalışın; örneğin `feature/issue-42-short-name`. Asla `main` dalına commit atmayın.
- Her issue için bir pull request açılır. İncelemeden ve gerekli CI kontrolleri geçtikten sonra birleştirilir.

Sürecin tamamı [`_docs/process.md`](_docs/process.md) belgesindedir.

## Kurulum

[uv](https://docs.astral.sh/uv/) ve Node 22 ya da daha yenisine ihtiyacınız vardır.

```sh
uv sync                    # backend and dev tools
(cd frontend && npm ci)    # frontend
```

README'deki [Geliştirme](README.tr-TR.md#geliştirme) bölümü backend ve frontend'in nasıl çalıştırılacağını açıklar.

## Pull request açmadan önce

CI'ın çalıştırdığı kontrolleri çalıştırın:

```sh
uv run pytest
uv run ruff check backend
uv run ruff format --check backend
uv run mypy backend/app
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Kullanıcı yolculuğundaki bir değişiklik için tarayıcı testlerini de çalıştırın (`frontend/` içinde `npm run e2e`;
bkz. [Tarayıcı testi](README.tr-TR.md#tarayıcı-testi)).

## Kurallar

- **Testler.** Yeni davranış testlerle birlikte gelir. Önce [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md)
  belgesini okuyun.
- **UI.** UI'a dokunan her şey [`_docs/design-system.md`](_docs/design-system.md) belgesine uyar. Belgenin kapsamadığı
  bir desen, aynı değişiklikte bu belgeye bir satır olarak eklenir.
- **Bağımlılıklar.** Bir bağımlılık eklemeden önce issue'da sorun. Bağımlılıklar `pyproject.toml` ve
  `frontend/package.json` içinde tanımlanır.
- **Terimler.** Ölçü her zaman "gross sales"tir; asla "revenue" değildir.
- **Gizlilik.** Hiçbir şey token'ları, dosya içeriklerini veya müşteri kimliklerini günlüğe yazamaz ya da gösteremez
  (bkz. [Gizlilik](README.tr-TR.md#gizlilik)).

## Lisans

Katkıda bulunarak katkılarınızın [Apache License 2.0](LICENSE) kapsamında lisanslanmasını kabul edersiniz.
