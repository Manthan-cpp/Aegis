# Phase 1 beginner guide

## What you can try

1. Start the frontend from the `frontend` folder with `npm run dev`.
2. Open `http://localhost:3000`.
3. Use it like an ordinary calculator. For example, `12 + 3 × 4 =` shows `24`.
4. Enter `2580` and press `=`. The calculator becomes the Aegis private screen without changing the URL.
5. Press `Escape` or click `Quick exit`. The private screen disappears immediately.

## What “client-side” means here

The calculator and unlock check run in the browser. There is no backend request
in Phase 1, and no PIN is sent over the network. The current demo code is
`2580`; a valid 4–6 digit replacement can be set in the browser console with:

```js
localStorage.setItem("aegis.unlock-code", "7391")
```

This is intentionally convenient for a demo, not secure authentication. Anyone
who can inspect the browser can discover or change it. Phase 6 will move the
setting behind authentication and store it per account.

## The three files to understand first

- `frontend/app/(stealth)/page.tsx` is the shell. It decides whether to show the calculator or Aegis.
- `frontend/app/(stealth)/calculator.tsx` contains the calculator buttons, keyboard support, arithmetic parser, and hidden-code check.
- `frontend/app/(main)/main-app.tsx` is the first real Aegis screen. The SOS, companion, and legal cards are intentionally visual placeholders until their phases begin.

The backend is unchanged in Phase 1 because this feature does not need a
server yet. That keeps the first backend concepts for Phase 2 focused: an API
endpoint, a request body, and a service that performs one job.
