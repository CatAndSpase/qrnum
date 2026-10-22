# qrnum

Генератор QR-кодов для WB PVZ (`encoded_scanned_code`) по алгоритму из `WB_Point_Terminal.exe` (PyQt6/PyInstaller).

## Формат

- `scanned_code` (11-значный номер) -> `encoded_scanned_code` = `*` + base64
- payload: 6 байт
  - `raw[:5]` = `scanned_code` в big-endian (5 байт)
  - `raw[5]` = `(verhoeff(s[:mid]) << 4) | verhoeff(s[mid:])`, где `s = str(scanned_code)`, `mid = len(s)//2`
- чек-сумма считается по **Verhoeff** с таблицами как в оригинальной программе
- QR генерится из `encoded_scanned_code`

## Установка

```bash
cd ~/Projects/qrnum
python3 -m venv .venv
.venv/bin/pip install segno pillow zxing-cpp
```

## Использование

```bash
# сгенерировать код и QR
./qrnum 51828566893

# без звёздочки
./qrnum 51828566893 --no-star

# искать в кэше БД точек
./qrnum 51828566893 --db

# пересобрать кэш из sqlite
./qrnum --rebuild

# проверить соответствие алгоритма БД
./qrnum --check
```

## Как найдено

Алгоритм вытащен из распакованного `WB_Point_Terminal.exe`:
- `PYZ.pyz_extracted/app/features/printing/cell_print.pyc`
  - `_decode_wb_qr_code()` — декодирование из QR
  - `_compute_checksum_byte()` — расчёт 2х полунбиблов через Verhoeff
  - `_verhoeff()` + `_VERHOEFF_D/_P/_INV`
- Соответствие: `12311/12313`. 2 записи в БД имеют легаси-формат без 6-байтового Verhoeff-пэйлоада (`*/8MOGAh`, `*wtj+a93`) — в текущей версии терминала не генерятся.

## Файлы

- `qrnum.py` — CLI
- `.venv/` — зависимости
- `out/` — сгенерированные QR
- `~/Library/Caches/qrnum/pairs.json` — кэш пар из точечных БД
