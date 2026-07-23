# MSW 5 Thunder Stamper

[繁體中文](README_zh-TW.md)

MSW 5 Thunder Stamper is a Windows desktop tool for placing repeated text or glyph-based authenticity marks at positions defined by a red-point map. It supports an embedded position map, optional external `origin.png` maps, custom PNG glyphs, system fonts, randomized visual effects, multi-process rendering, and transparent PNG export.

Current release: **v1.0.1**

[Download the Windows package](https://github.com/duoduo-88/MSW-5-Thunder-Stamper/releases/latest)

## Features

- Places a code at every detected point in the selected position map.
- Includes an embedded red-point map and can optionally use an external `origin.png`.
- Merges connected red pixels into one placement point by default.
- Uses custom alphanumeric PNG glyphs or a selected `.ttf`/`.otf` system font.
- Supports arbitrary-length text in system-font mode.
- Adjusts scale, glyph opacity, spacing, global and per-character jitter, and X/Y offset.
- Adds glyph noise, edge feathering, colored glow, and glow noise.
- Uses multiple processes and configurable chunk sizes for large point sets.
- Provides dark, white, gray, checkerboard, or custom preview backgrounds without baking the preview background into the output.
- Exports the composed result as PNG.

## Requirements

### Windows package

- Windows 10 or 11
- A program capable of extracting `.7z` archives
- Sufficient memory for the selected image and worker-process count

Extract the latest release archive and run the included executable. A separate Python installation is not required.

### Python source

- Python 3.10 or newer is recommended
- PySide6
- Pillow

Install dependencies:

```powershell
python -m pip install PySide6 Pillow
```

Run the current source file:

```powershell
python "MSW 5 Thunder Stamper v1.0.1 .py"
```

## Basic Workflow

1. Load the PNG, JPEG, or BMP image that will receive the marks.
2. Enter the desired code or text.
3. Choose a placement-map mode:
   - Leave **Prefer embedded red points** enabled to use the built-in map, resized to the loaded image.
   - Disable it to look for `origin.png` beside the loaded image or the script.
4. Choose a text-rendering mode:
   - PNG glyph mode uses files from `glyphs`, the loaded image's folder, or the script folder.
   - System-font mode uses a selected font and may require explicitly choosing a `.ttf` or `.otf` file.
5. Adjust placement, opacity, noise, feathering, glow, CPU-worker, and chunk settings.
6. Select **Generate Watermark** (`生成水印`) and inspect the preview.
7. Select **Save PNG** (`另存PNG`) to export the result.

## Custom PNG Glyphs

The application creates a `glyphs` directory when it starts. In PNG glyph mode:

- Supported lookup characters are letters and digits.
- Filenames are uppercase, for example `A.png`, `B.png`, and `7.png`.
- Input characters are converted to uppercase for lookup.
- Missing glyphs are rendered as a crossed placeholder box.
- Transparent RGBA PNG files are recommended.

Use system-font mode when lowercase distinctions, spaces, punctuation, or other Unicode characters are required.

## Position Maps

The program detects red pixels in a position map and stamps the code around those coordinates. With **Merge nearby red points** enabled, connected red pixels are treated as one component to avoid many overlapping marks from a single dot. An external `origin.png` is resized to the loaded image dimensions when needed.

## Privacy

The source code reads and writes local image and font files only. It does not include an upload, network, or telemetry client.

## Limitations

- Results depend on the placement map, font or glyph quality, and selected parameters.
- PNG glyph mode supports alphanumeric file lookup only; unsupported or missing glyphs use placeholders.
- Automatic system-font file discovery may fail, in which case a `.ttf` or `.otf` file must be selected manually.
- High point counts, large images, many worker processes, and complex glow settings can consume substantial memory and processing time.
- The tool creates a visual marking layer but does not provide cryptographic signing or proof of ownership.

## License

The project source code is licensed under the [MIT License](LICENSE). PySide6, Pillow, and components included in packaged builds retain their own licenses; see [Third-Party Notices](THIRD_PARTY_NOTICES.md).

Copyright (c) 2025 DuoDuo
