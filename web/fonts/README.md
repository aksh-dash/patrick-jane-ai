# Fonts

The interface asks for **SF Pro** (display) and **SF Mono** (everything else).
Apple's licence doesn't allow redistributing them, so they aren't in this repo.

## If you're on a Mac
Nothing to do. `local('SF Pro Display')` / `local('SF Mono')` in
`../css/fonts.css` picks up the installed system fonts automatically.

## If you're on Windows (or want the exact faces)
1. Download the free developer packages from Apple:
   - https://developer.apple.com/fonts/  → "SF Pro" and "SF Mono"
2. Install them, **or** drop these files into this folder:

```
SF-Pro-Display-Regular.otf
SF-Pro-Display-Medium.otf
SF-Pro-Display-Semibold.otf
SF-Mono-Regular.otf
SF-Mono-Medium.otf
```

Reload the page — no code changes needed.

## If you do neither
The stack falls back to Segoe UI Variable Display and Cascadia Mono / Consolas.
Metrics are close enough that the layout doesn't shift; the letterforms are just
slightly less Apple.
