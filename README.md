# ZKTeco Control de Asistencia

Seguimiento de asistencia para dispositivos ZKTeco (K30/ID) con interfaz gráfica
Qt (PySide6), base de datos SQLite local y exportación a Excel.

## Uso desde el código fuente

```bash
uv sync
uv run zkteco-ui          # interfaz gráfica
uv run zkteco --help      # CLI
```

## Compilar un ejecutable único

El proyecto usa **PyInstaller** en modo *onefile* para producir un binario
autocontenido (incluye Qt, la app y sus recursos).

### Local (cualquier plataforma)

```bash
uv sync --group dev
uv run --group dev pyinstaller zkteco-ui.spec --noconfirm
```

El ejecutable queda en `dist/`:

| Plataforma  | Archivo                      |
|-------------|------------------------------|
| Windows     | `dist/ZKTecoController.exe`  |
| Linux       | `dist/ZKTecoController`      |
| macOS       | `dist/ZKTecoController`      |

> Compilar *para* Windows debe hacerse **en** Windows (PyInstaller no cruza
> plataformas). Pulsa "Run workflow" en la pestaña Actions del repositorio para
> que GitHub lo compile en `windows-latest` y publica el `.exe`.

### Automatizado con GitHub Actions

El workflow [`.github/workflows/build-windows.yml`](.github/workflows/build-windows.yml):

1. Se dispara manualmente (**Actions → Build Windows EXE → Run workflow**)
   o al publicar una etiqueta `v*`.
2. Instala Python 3.13, `uv` y las dependencias (incluye PyInstaller).
3. Compila `dist/ZKTecoController.exe`.
4. Sube el `.exe` como artifact; si la ejecución vino de un tag `v*`, crea/actualiza
   un GitHub Release adjuntando el binario.

## Configuración del dispositivo

La IP/puerto del lector se configuran en la app (icono ⚙). Firma de huella:
registro manual en el dispositivo (la app solo crea usuario con nombre + ID y
muestra las instrucciones).