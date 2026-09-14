# KrishiSetu Backend (Flask + MySQL)

Replaces the `window.storage` calls in `krishisetu.html` with a real API + database.

## Setup

```bash
pip install -r requirements.txt
mysql -u root -p < schema.sql
export DB_HOST=localhost
export DB_USER=root
export DB_PASSWORD=yourpassword
export DB_NAME=krishisetu
python app.py
```

Server runs at `http://localhost:5000`.

## Endpoints

| Method | Path                     | Purpose                                   |
|--------|--------------------------|--------------------------------------------|
| GET    | /api/config              | Centers, crops, rates, slots, capacity     |
| POST   | /api/bookings            | Create a booking (returns token)           |
| GET    | /api/bookings?phone=     | List a farmer's bookings + queue position  |
| GET    | /api/notifications?phone=| Notification feed for a phone number       |
| GET    | /api/board?center=&date= | Live queue board (now serving, up next)    |
| POST   | /api/admin/login         | Check staff PIN (demo: 1234)               |
| GET    | /api/admin/bookings?center=&date= | Full admin table for a center/date |
| POST   | /api/admin/call-next     | Call the next token in queue               |
| POST   | /api/admin/procure       | Mark a booking as procured (`bookingId`, `qty`) |
| POST   | /api/admin/pay           | Mark a booking as paid (`bookingId`, `amount`)  |

### Example: create a booking

```bash
curl -X POST http://localhost:5000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ramesh Kumar",
    "phone": "9876543210",
    "village": "Ellenabad",
    "cropKey": "wheat",
    "qty": 20,
    "center": "Ellenabad Mandi",
    "date": "2026-09-16",
    "slot": "08:00–09:00"
  }'
```

## Notes

- The PIN check is a placeholder matching the frontend's demo `1234` — swap for real auth (hashed passwords, JWT, etc.) before production.
- `created_at` / `paid_at` are stored as epoch milliseconds to match `Date.now()` in the original JS, so `avgCycleMinutes` math lines up exactly with the frontend's calculation.
- To point `krishisetu.html` at this API instead of `window.storage`, replace `loadState`/`saveState` with `fetch()` calls to these endpoints.
