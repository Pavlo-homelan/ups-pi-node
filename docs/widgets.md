# UPS Widget Packages

Пользовательские виджеты устанавливаются из ZIP-пакетов, похожих по идее на установку плагинов из ZIP в Kodi. Пакет может содержать манифест, CSS и локальные assets.

Важное ограничение: пользовательский виджет меняет внешний вид общего безопасного HTML-шаблона UPS. Портал не выполняет HTML или JavaScript из пакета.

## Выбор Виджета

1. Откройте страницу `System`.
2. В блоке `UPS widget` выберите вариант из выпадающего списка.
3. Встроенные варианты находятся в группе `Built-in`.
4. Установленные ZIP-виджеты появляются в группе `Custom`.

Выбор сохраняется в браузере через `localStorage` и применяется сразу.

## Установка Из ZIP

1. Откройте страницу `System`.
2. В блоке `UPS widget` нажмите выбор файла.
3. Выберите `.zip` пакет виджета.
4. Нажмите `Install from ZIP`.
5. После установки виджет появится в выпадающем списке.

Ограничения пакета:

- только `.zip`;
- общий размер ZIP до 2 MB;
- распакованный размер до 2 MB;
- максимум 40 файлов;
- CSS должен быть в UTF-8;
- запрещены `@import`, `javascript:`, `data:`, внешние `http://` и `https://` ссылки;
- разрешенные типы файлов: `.json`, `.xml`, `.css`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.woff`, `.woff2`, `.ttf`, `.otf`.

Файлы сохраняются в `instance/widgets/`. Путь можно переопределить переменной окружения `UPS_PI_NODE_WIDGETS_DIR`.

## Структура ZIP

Рекомендуемый формат:

```text
my-widget.zip
└── my-widget/
    ├── widget.json
    ├── style.css
    └── assets/
        ├── background.png
        └── display.woff2
```

Допускается архив без общей корневой папки:

```text
my-widget.zip
├── widget.json
├── style.css
└── assets/
    ├── background.png
    └── display.woff2
```

## widget.json

Минимальный манифест:

```json
{
  "id": "my-widget",
  "name": "My Widget",
  "version": "1.0.0",
  "author": "User",
  "stylesheet": "style.css"
}
```

Поля:

- `id`: стабильный идентификатор пакета. На устройстве он будет сохранен как `user-my-widget`;
- `name`: имя в выпадающем списке;
- `version`: версия, отображается в списке установленных виджетов;
- `author`: автор;
- `stylesheet`: путь к главному CSS внутри ZIP.

Если `widget.json` отсутствует, портал попробует найти единственный `.css` файл в архиве и использует имя ZIP как имя виджета.

## addon.xml

Для более Kodi-похожего формата можно использовать `addon.xml`:

```xml
<addon id="my-widget" name="My Widget" version="1.0.0" provider-name="User">
  <extension point="ups-pi-node.widget" stylesheet="style.css" />
</addon>
```

`widget.json` имеет приоритет над `addon.xml`, если в пакете есть оба файла.

## Подключение Assets

CSS может ссылаться на файлы из пакета относительными путями:

```css
.ups-widget {
  background:
    linear-gradient(rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.35)),
    url("assets/background.png") center / cover;
}
```

Не используйте внешние URL. Все картинки и шрифты должны лежать внутри ZIP.

## Подключение Шрифтов

Пользовательские шрифты можно положить в ZIP и подключить через `@font-face`:

```css
@font-face {
  font-family: "WidgetDisplay";
  src: url("assets/display.woff2") format("woff2");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}

.ups-widget {
  font-family: "WidgetDisplay", "Segoe UI", sans-serif;
}
```

Рекомендуемый формат для веба — `woff2`. Также поддерживаются `woff`, `ttf` и `otf`, если они лежат внутри ZIP.

## HTML Шаблон

CSS применяется к общей структуре:

```html
<div class="card ups-widget">
  <div class="widget-head">
    <span class="widget-label">Power</span>
    <h2 id="status-title" data-live="state">CHARGE</h2>
    <div class="status-chip">
      <span id="ac-status" data-live="ac">AC OK</span>
    </div>
  </div>

  <div class="widget-body">
    <div class="widget-visual">
      <div id="battery-gauge" class="battery-gauge">
        <div class="battery-gauge-core">
          <strong id="battery-percent-widget" data-live="percent">100%</strong>
          <span>Battery</span>
        </div>
      </div>

      <div class="battery-can">
        <div class="battery-cap"></div>
        <div class="battery-can-fill"></div>
        <strong data-live="percent">100%</strong>
      </div>
    </div>

    <div class="widget-metrics">
      <div class="widget-metric">
        <span>Voltage</span>
        <strong id="val-v" data-live="voltage">12.60V</strong>
      </div>
      <div class="widget-metric">
        <span>Current</span>
        <strong id="val-i" data-live="current">620mA</strong>
      </div>
    </div>
  </div>

  <div class="oled-readout">...</div>
  <div class="radial-hub">...</div>
  <div class="battery-container widget-bar">
    <div id="battery-bar" class="battery-bar"></div>
  </div>
  <div class="widget-foot">...</div>
</div>
```

## Live-Поля

JavaScript обновляет элементы по `data-live`:

- `state`: состояние питания, например `CHARGE`;
- `ac`: `AC OK` или `AC LOST`;
- `percent`: заряд батареи;
- `voltage`: напряжение;
- `current`: ток;
- `cpu`: температура CPU;
- `ram`: использование RAM.

Не удаляйте все live-поля через CSS. Можно скрывать ненужные блоки, но хотя бы один набор данных должен оставаться видимым.

## CSS-Переменные

Глобальные переменные темы:

```css
--bg
--card
--surface
--surface-strong
--track
--text
--muted
--border
--green
--red
--yellow
--cyan
```

Динамические переменные батареи:

```css
--battery-level
--battery-color
```

`--battery-level` приходит в процентах, например `74%`. `--battery-color` зависит от состояния UPS.

## Минимальный ZIP-Виджет

`widget.json`:

```json
{
  "id": "yellow-ring",
  "name": "Yellow Ring",
  "version": "1.0.0",
  "stylesheet": "style.css"
}
```

`style.css`:

```css
.ups-widget {
  --yellow: #ffe04a;
  --cyan: #38dfff;
  --green: #78ff5c;
  border-color: rgba(255, 224, 74, 0.4);
  border-radius: 18px;
  background:
    radial-gradient(circle at 50% 36%, rgba(255, 224, 74, 0.18), transparent 42%),
    linear-gradient(145deg, #111815, #070b0c);
  box-shadow: 0 0 26px rgba(255, 224, 74, 0.16), var(--shadow);
}

.ups-widget .battery-gauge {
  background:
    conic-gradient(var(--battery-color) 0 var(--battery-level), #222 var(--battery-level) 100%);
}

.ups-widget .widget-metric strong {
  color: var(--cyan);
}
```

## Удаление

На странице `System` установленные ZIP-виджеты отображаются под формой установки. Нажмите `Delete` рядом с нужным виджетом.

## Где Лежит Код

- шаблон виджета: `app/templates/_ups_card_widget.html`;
- встроенные стили: `app/static/css/style.css`;
- выбор и подгрузка CSS: `app/static/js/theme.js`;
- установка и хранение ZIP-пакетов: `app/services/widgets.py`;
- маршруты установки, удаления и выдачи файлов пакета: `app/routes.py`.

## Dashboard Widgets

The main dashboard has its own removable widgets. They are managed on the
`System` page in the `Dashboard widgets` block.

Built-in dashboard widgets:

- `ups-main`: the current skin-based UPS card that uses the ZIP widget CSS.
- `ups-overview`: a wider UPS overview card inspired by the initial `rpi2w-ups`
  battery panel.
- `cpu-temp`: CPU temperature.
- `ram-usage`: RAM usage.
- `wifi-status`: local UI Wi-Fi status. It is not included in Zabbix or Home
  Assistant integration metrics.

The `ups-overview` widget uses a separate template:
`app/templates/_dashboard_widget_ups_overview.html`. It is intentionally
separate from `app/templates/_ups_card_widget.html`, so it can be removed or
changed without affecting ZIP-based UPS widget skins.
