<div align="center">

<img src="assets/banner.svg" alt="DF Translator" width="100%">

<br>

[![Скачать](https://img.shields.io/badge/%E2%AC%87%EF%B8%8F%20%D0%A1%D0%BA%D0%B0%D1%87%D0%B0%D1%82%D1%8C-DFTranslator.exe-22c58b?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/persephonemajestic/df-translator/releases/latest/download/DFTranslator.exe)

[![Версия](https://img.shields.io/github/v/release/persephonemajestic/df-translator?style=flat-square&color=22c58b&label=версия)](https://github.com/persephonemajestic/df-translator/releases/latest)
[![Скачиваний](https://img.shields.io/github/downloads/persephonemajestic/df-translator/total?style=flat-square&color=2b3442&label=скачиваний)](https://github.com/persephonemajestic/df-translator/releases)
![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-2b3442?style=flat-square&logo=windows&logoColor=white)

**Нажмите кнопку — переведите экран или выделенный текст.**<br>
Названия квестов, цели, награды и интерфейс — по лору игры.

</div>

---

## Установка

1. Нажмите **«Скачать»** выше (или возьмите `DFTranslator.exe` в [релизах](https://github.com/persephonemajestic/df-translator/releases/latest)).
2. Запустите файл — откроется панель управления, а значок **译** появится в трее.
3. В игре включите режим **«Окно без рамки»**.

Установщик не нужен: это один файл. Дальше программа **обновляется сама**.

> Первый запуск может занять до минуты (распаковка и загрузка OCR). Windows SmartScreen может предупредить о неподписанном файле: **«Подробнее» → «Выполнить в любом случае»**.

## Как пользоваться

| Клавиши | Действие |
|---|---|
| `Ctrl` `Alt` `T` | перевести весь экран |
| `Ctrl` `Alt` `R` | выделить область мышью и перевести |
| `Ctrl` `Alt` `C` | убрать перевод |
| `Ctrl` `Alt` `M` | режим: поверх игры ⇄ отдельная панель |

Сочетания меняются в панели управления. Зелёная точка у плашки — перевод из лор-глоссария, жёлтая — машинный, его стоит проверять.

## Возможности

- **Лор-перевод:** все 333 квеста, цели, награды и интерфейс (Нулевая плотина, Хаавк, GTI и др.).
- **Весь экран или область** — по горячей клавише или кнопкой в панели.
- **Панель управления:** горячие клавиши, движок перевода (Google, DeepL, Claude), вид плашек, OCR.
- **Два режима показа:** плашки поверх игры или отдельное окно на втором мониторе.
- **Свой глоссарий:** правьте термины в `glossary_user.json` (папка настроек открывается из панели).

## Античит ACE

Программа **не внедряется в игру и не читает её память**: только снимает экран, распознаёт текст и показывает отдельное окно. Горячие клавиши — штатные средства Windows, без хуков. Гарантий это не даёт; самый осторожный вариант — режим **«Отдельная панель»** на втором мониторе.

<details>
<summary>Для разработчика</summary>

Новая версия: `git tag v1.0.1 && git push origin v1.0.1` — Actions соберёт один `DFTranslator.exe` и опубликует релиз; у пользователей он подтянется сам. Текст релиза берётся из `RELEASE_NOTES.md` и показывается в программе как «Что нового».

Запуск из исходников: `pip install -r requirements.txt`, затем `python run_app.py`.

</details>

<sub>Данные квестов — [kkrb.net](https://www.kkrb.net) (автор Key725). Неофициальный проект, не связан с издателем игры.</sub>
