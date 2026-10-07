# Loona Desktop Pet

![Loona Desktop Pet](social-preview.jpg)

Loona Desktop Pet — питомец, который живёт на рабочем столе Windows. Loona гуляет по экрану, иногда бегает и реагирует на курсор и набор текста. Питомца можно погладить курсором, перетащить или бросить; иногда Loona садится на окна.

## Запустить Loona

Готовая сборка лежит в корне репозитория. Запустите `LoonaDesktopPet.exe` — Python для этого не нужен. Оставьте рядом папки `_internal` и `assets` и файл `VERSION`: без них приложение не запустится.

Настройки и журнал готовой сборки находятся в `%LOCALAPPDATA%\LoonaDesktopPet`.

Хотите запустить Loona из исходников? Откройте папку `Loona-Desktop` и запустите `Start-Loona.cmd`.

## Собрать приложение

Для сборки под Windows x64 нужен Python 3.12. Откройте PowerShell в папке `Loona-Desktop` и выполните:

```powershell
py -3.12 build.py
```

Приложение и ZIP-архив появятся в `dist`. Сборка остаётся локальной и сама ничего не публикует. Подробности — в [инструкции по сборке](Loona-Desktop/BUILDING.md), история изменений — в [CHANGELOG.md](Loona-Desktop/CHANGELOG.md).
