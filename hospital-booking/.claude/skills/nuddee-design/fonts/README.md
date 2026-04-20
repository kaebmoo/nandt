# Fonts

NudDee uses **Sarabun** (weights 300 / 400 / 600 / 700) loaded from Google Fonts in every template:

```html
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap" rel="stylesheet">
```

The repo does **not** ship local TTF/WOFF2 files for Sarabun. If you need an offline/embedded copy:

1. Download from https://fonts.google.com/specimen/Sarabun
2. Drop `Sarabun-Light.ttf`, `Sarabun-Regular.ttf`, `Sarabun-SemiBold.ttf`, `Sarabun-Bold.ttf` into this folder
3. Register them via `@font-face` in your stylesheet (see `colors_and_type.css` for the CDN import, swap for local URLs).

**Substitution flagged:** we're relying on Google Fonts CDN. If you want local fonts, please supply them.
