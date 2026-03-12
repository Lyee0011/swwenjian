# CLAUDE.md

## Project Overview

This is **数据可视化 - 百分比图标生成器** (Data Visualization - Percentage Icon Generator), a single-page web application that generates visual percentage-based icon grids. Users can configure percentages, icons, colors, grid layouts, and export the result as an image.

## Repository Structure

```
/
├── AlternateGothic2-BT.ttf   # Custom font – AlternateGothic2 BT
├── ChillDINGothic_Std.otf    # Custom font – ChillDIN Gothic Standard
└── CLAUDE.md                  # This file
```

**Note:** The main `index.html` was previously part of the repo but has been deleted (see commit history). It was a self-contained 770-line HTML file with embedded CSS and JavaScript — no build system or bundler is used.

## Tech Stack

- **HTML/CSS/JavaScript** — single-file, no framework
- **Google Fonts** — Noto Sans SC, DM Sans (loaded via `@import`)
- **html2canvas** — dynamically loaded from CDN for PNG export
- **Custom fonts** — TTF/OTF files in the repo root, referenced via `@font-face`

## Key Conventions

- **Language:** UI text is in Chinese (Simplified). Keep UI strings in Chinese unless asked otherwise.
- **Single-file architecture:** All markup, styles, and scripts live in one `index.html`. Do not split into separate files unless explicitly requested.
- **No build tools:** There is no `package.json`, bundler, or build step. The app runs by opening the HTML file directly in a browser.
- **Dark theme:** The UI uses a dark background (`#0a0a0f`) with light text. Maintain this aesthetic.
- **Inline styles/scripts:** CSS is in a `<style>` block, JS is in a `<script>` block at the end of the body. No external CSS/JS files.

## Application Features

- Percentage input (0–100) with a visual icon grid
- Configurable icon picker (emoji-based) with custom icon support
- Accent color picker with preset swatches
- Multiple grid layout options (e.g., 10×10, 5×20)
- Background image upload with overlay
- Title and subtitle text editing
- PNG export via html2canvas

## Development Workflow

1. Edit `index.html` directly
2. Open in a browser to preview (no server required, though a local server avoids CORS issues with font loading)
3. No tests, linters, or CI are configured

## Git Conventions

- Default branch: `master`
- Commits use short descriptive messages
- Font files are committed as binary assets in the repo root
