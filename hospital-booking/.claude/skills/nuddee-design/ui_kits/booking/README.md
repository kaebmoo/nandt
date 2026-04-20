# NudDee Booking UI Kit

Recreation of the patient-facing + hospital-admin booking flow, plus the public marketing landing, as reusable JSX components.

Open **index.html** to see an interactive click-through prototype that cycles:

1. Marketing landing (hero + features + pricing)
2. Patient picks event type
3. Patient picks date + time
4. Patient fills in details
5. Booking success

## Files

- `index.html` — loads React + Babel, boots `App.jsx`
- `App.jsx` — router / screen switcher
- `Chrome.jsx` — sticky top nav + footer shared across screens
- `Landing.jsx` — marketing landing page (hero, features, pricing)
- `EventTypes.jsx` — grid of appointment types for the hospital
- `DateTimePicker.jsx` — calendar + time-slot grid
- `BookingForm.jsx` — customer details form
- `BookingSuccess.jsx` — confirmation page with animated check
- `ui.jsx` — shared primitives (Button, Card, Input, Label, Field)
- `icons.jsx` — inline Heroicon SVGs

All visuals come directly from `flask_app/app/templates/` in kaebmoo/nandt.
