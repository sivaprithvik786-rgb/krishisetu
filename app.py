"""
KrishiSetu backend API
-----------------------
Flask + MySQL backend for the KrishiSetu procurement-slot-booking frontend
(krishisetu.html). It replaces the browser-side window.storage calls with
real persistence, and mirrors the exact fields/statuses the frontend uses:

    booking: id, token, name, phone, village, cropKey, qty, center, date,
             slot, status(booked|progress|procured|paid),
             procuredQty, paymentAmount, createdAt, paidAt

Run:
    pip install -r requirements.txt
    mysql -u root -p < schema.sql
    export DB_PASSWORD=yourpassword   # and any other config.py env vars
    python app.py
"""
import re
import time
import uuid
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql

from config import SLOT_CAPACITY, AVG_MIN_PER_FARMER, SLOTS, ADMIN_PIN
from db import get_cursor

app = Flask(__name__)
CORS(app)  # allow the static HTML frontend (served from anywhere) to call this API

PHONE_RE = re.compile(r"^[0-9]{10}$")


# ---------------------------------------------------------------- helpers --
def bad_request(message, code=400):
    return jsonify({"error": message}), code


def now_ms():
    return int(time.time() * 1000)


def serialize_booking(row):
    """Convert a DB row into the exact shape the frontend expects."""
    return {
        "id": row["id"],
        "token": row["token"],
        "name": row["name"],
        "phone": row["phone"],
        "village": row["village"],
        "cropKey": row["crop_key"],
        "qty": float(row["qty"]),
        "center": row["center"],
        "date": row["booking_date"].isoformat(),
        "slot": row["slot"],
        "status": row["status"],
        "procuredQty": float(row["procured_qty"]) if row["procured_qty"] is not None else None,
        "paymentAmount": float(row["payment_amount"]) if row["payment_amount"] is not None else None,
        "createdAt": row["created_at"],
        "paidAt": row["paid_at"],
    }


def get_or_create_counter(cur, center, date_str):
    cur.execute(
        "SELECT center, booking_date, now_serving, next_token FROM counters "
        "WHERE center=%s AND booking_date=%s FOR UPDATE",
        (center, date_str),
    )
    row = cur.fetchone()
    if row:
        return row
    cur.execute(
        "INSERT INTO counters (center, booking_date, now_serving, next_token) "
        "VALUES (%s, %s, 0, 1)",
        (center, date_str),
    )
    return {"center": center, "booking_date": date_str, "now_serving": 0, "next_token": 1}


def add_notification(cur, phone, message):
    cur.execute(
        "INSERT INTO notifications (phone, message) VALUES (%s, %s)",
        (phone, message),
    )


# --------------------------------------------------------------- config ---
@app.route("/api/config", methods=["GET"])
def get_config():
    with get_cursor() as cur:
        cur.execute("SELECT name FROM centers ORDER BY id")
        centers = [r["name"] for r in cur.fetchall()]
        cur.execute("SELECT crop_key, name, rate_per_qtl FROM crops")
        crops = {r["crop_key"]: {"name": r["name"], "rate": float(r["rate_per_qtl"])} for r in cur.fetchall()}
    return jsonify({
        "centers": centers,
        "crops": crops,
        "slots": SLOTS,
        "slotCapacity": SLOT_CAPACITY,
    })


# -------------------------------------------------------------- bookings --
@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    village = (data.get("village") or "").strip()
    crop_key = data.get("cropKey")
    qty = data.get("qty")
    center = data.get("center")
    date_str = data.get("date")  # expects "YYYY-MM-DD"
    slot = data.get("slot")

    if not all([name, village, crop_key, center, date_str, slot]) or qty is None:
        return bad_request("Missing required field(s): name, phone, village, cropKey, qty, center, date, slot")
    if not PHONE_RE.match(phone):
        return bad_request("Phone must be exactly 10 digits")
    try:
        qty = float(qty)
        if qty <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return bad_request("qty must be a positive number")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return bad_request("date must be in YYYY-MM-DD format")

    with get_cursor(commit=True) as cur:
        # Validate crop and slot exist
        cur.execute("SELECT 1 FROM crops WHERE crop_key=%s", (crop_key,))
        if not cur.fetchone():
            return bad_request(f"Unknown cropKey: {crop_key}")
        if slot not in SLOTS:
            return bad_request(f"Unknown slot: {slot}")

        # Enforce slot capacity (matches SLOT_CAPACITY check in wireBook())
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM bookings WHERE center=%s AND booking_date=%s AND slot=%s",
            (center, date_str, slot),
        )
        if cur.fetchone()["cnt"] >= SLOT_CAPACITY:
            return bad_request(f"Slot {slot} at {center} on {date_str} is full. Please choose another time.", 409)

        counter = get_or_create_counter(cur, center, date_str)
        token = counter["next_token"]

        booking_id = f"{center}-{date_str}-{token}-{uuid.uuid4().hex[:8]}"
        created_at = now_ms()

        cur.execute(
            """INSERT INTO bookings
               (id, token, name, phone, village, crop_key, qty, center,
                booking_date, slot, status, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'booked',%s)""",
            (booking_id, token, name, phone, village, crop_key, qty, center,
             date_str, slot, created_at),
        )

        # Advance / create the counter row
        cur.execute(
            "INSERT INTO counters (center, booking_date, now_serving, next_token) "
            "VALUES (%s, %s, 0, %s) "
            "ON DUPLICATE KEY UPDATE next_token = %s",
            (center, date_str, token + 1, token + 1),
        )

        add_notification(cur, phone, f"Token #{token} — {center}, {date_str}, {slot}")

        position = token - counter["now_serving"]
        wait_min = max(0, position - 1) * AVG_MIN_PER_FARMER

    return jsonify({
        "token": token,
        "bookingId": booking_id,
        "center": center,
        "date": date_str,
        "slot": slot,
        "estimatedWaitMinutes": wait_min,
    }), 201


@app.route("/api/bookings", methods=["GET"])
def get_bookings_by_phone():
    phone = request.args.get("phone", "").strip()
    if not PHONE_RE.match(phone):
        return bad_request("Provide a valid 10-digit phone number as ?phone=")

    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM bookings WHERE phone=%s ORDER BY created_at DESC",
            (phone,),
        )
        rows = cur.fetchall()

        results = []
        for row in rows:
            booking = serialize_booking(row)
            if row["status"] == "booked":
                cur.execute(
                    "SELECT now_serving FROM counters WHERE center=%s AND booking_date=%s",
                    (row["center"], row["booking_date"]),
                )
                counter_row = cur.fetchone()
                now_serving = counter_row["now_serving"] if counter_row else 0
                cur.execute(
                    "SELECT COUNT(*) AS ahead FROM bookings "
                    "WHERE center=%s AND booking_date=%s AND status='booked' AND token < %s",
                    (row["center"], row["booking_date"], row["token"]),
                )
                ahead = cur.fetchone()["ahead"]
                booking["farmersAhead"] = ahead
                booking["estimatedWaitMinutes"] = ahead * AVG_MIN_PER_FARMER
                booking["nowServing"] = now_serving
            results.append(booking)

    return jsonify(results)


# ---------------------------------------------------------- notifications --
@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    phone = request.args.get("phone", "").strip()
    if not PHONE_RE.match(phone):
        return bad_request("Provide a valid 10-digit phone number as ?phone=")

    with get_cursor() as cur:
        cur.execute(
            "SELECT message, created_at FROM notifications "
            "WHERE phone=%s ORDER BY created_at DESC LIMIT 50",
            (phone,),
        )
        rows = cur.fetchall()

    return jsonify([
        {"text": r["message"], "at": r["created_at"].isoformat()} for r in rows
    ])


# ---------------------------------------------------------------- board ----
@app.route("/api/board", methods=["GET"])
def get_board():
    center = request.args.get("center")
    date_str = request.args.get("date")
    if not center or not date_str:
        return bad_request("center and date query params are required")

    with get_cursor() as cur:
        cur.execute(
            "SELECT now_serving FROM counters WHERE center=%s AND booking_date=%s",
            (center, date_str),
        )
        counter_row = cur.fetchone()
        now_serving = counter_row["now_serving"] if counter_row else 0

        cur.execute(
            "SELECT * FROM bookings WHERE center=%s AND booking_date=%s AND status='booked' "
            "ORDER BY token ASC LIMIT 10",
            (center, date_str),
        )
        up_next = [serialize_booking(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT status, COUNT(*) AS cnt FROM bookings "
            "WHERE center=%s AND booking_date=%s GROUP BY status",
            (center, date_str),
        )
        status_counts = {r["status"]: r["cnt"] for r in cur.fetchall()}

    total = sum(status_counts.values())
    waiting = status_counts.get("booked", 0)
    completed = status_counts.get("paid", 0)

    return jsonify({
        "nowServing": now_serving,
        "upNext": up_next,
        "totalBookingsToday": total,
        "currentlyWaiting": waiting,
        "completedAndPaid": completed,
        "slotCapacity": SLOT_CAPACITY,
    })


# ---------------------------------------------------------------- admin ----
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin", ""))
    if pin == ADMIN_PIN:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Incorrect PIN"}), 401


@app.route("/api/admin/bookings", methods=["GET"])
def admin_bookings():
    center = request.args.get("center")
    date_str = request.args.get("date")
    if not center or not date_str:
        return bad_request("center and date query params are required")

    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM bookings WHERE center=%s AND booking_date=%s ORDER BY token ASC",
            (center, date_str),
        )
        rows = [serialize_booking(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT now_serving FROM counters WHERE center=%s AND booking_date=%s",
            (center, date_str),
        )
        counter_row = cur.fetchone()
        now_serving = counter_row["now_serving"] if counter_row else 0

        waiting = sum(1 for r in rows if r["status"] == "booked")
        paid_rows = [r for r in rows if r["status"] == "paid"]
        if paid_rows:
            avg_ms = sum(r["paidAt"] - r["createdAt"] for r in paid_rows) / len(paid_rows)
            avg_cycle_min = round(avg_ms / 60000)
        else:
            avg_cycle_min = None

    return jsonify({
        "rows": rows,
        "nowServing": now_serving,
        "stillWaiting": waiting,
        "completedToday": len(paid_rows),
        "avgCycleMinutes": avg_cycle_min,
    })


@app.route("/api/admin/call-next", methods=["POST"])
def call_next():
    data = request.get_json(silent=True) or {}
    center = data.get("center")
    date_str = data.get("date")
    if not center or not date_str:
        return bad_request("center and date are required")

    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT * FROM bookings WHERE center=%s AND booking_date=%s AND status='booked' "
            "ORDER BY token ASC LIMIT 1 FOR UPDATE",
            (center, date_str),
        )
        next_booking = cur.fetchone()
        if not next_booking:
            return jsonify({"message": "No farmers waiting"}), 200

        cur.execute("UPDATE bookings SET status='progress' WHERE id=%s", (next_booking["id"],))
        cur.execute(
            "INSERT INTO counters (center, booking_date, now_serving, next_token) "
            "VALUES (%s, %s, %s, 1) "
            "ON DUPLICATE KEY UPDATE now_serving = %s",
            (center, date_str, next_booking["token"], next_booking["token"]),
        )
        add_notification(cur, next_booking["phone"], f"Token #{next_booking['token']} — {center}")

    return jsonify({"token": next_booking["token"], "bookingId": next_booking["id"]})


@app.route("/api/admin/procure", methods=["POST"])
def mark_procured():
    data = request.get_json(silent=True) or {}
    booking_id = data.get("bookingId")
    qty = data.get("qty")
    if not booking_id or qty is None:
        return bad_request("bookingId and qty are required")
    try:
        qty = float(qty)
        if qty <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return bad_request("qty must be a positive number")

    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM bookings WHERE id=%s", (booking_id,))
        booking = cur.fetchone()
        if not booking:
            return bad_request("Booking not found", 404)

        cur.execute(
            "UPDATE bookings SET status='procured', procured_qty=%s WHERE id=%s",
            (qty, booking_id),
        )
        cur.execute("SELECT name FROM crops WHERE crop_key=%s", (booking["crop_key"],))
        crop_row = cur.fetchone()
        crop_name = crop_row["name"] if crop_row else booking["crop_key"]
        add_notification(cur, booking["phone"], f"{crop_name} — {qty} qtl — {booking['center']}")

    return jsonify({"ok": True})


@app.route("/api/admin/pay", methods=["POST"])
def mark_paid():
    data = request.get_json(silent=True) or {}
    booking_id = data.get("bookingId")
    amount = data.get("amount")
    if not booking_id or amount is None:
        return bad_request("bookingId and amount are required")
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return bad_request("amount must be a positive number")

    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM bookings WHERE id=%s", (booking_id,))
        booking = cur.fetchone()
        if not booking:
            return bad_request("Booking not found", 404)

        paid_at = now_ms()
        cur.execute(
            "UPDATE bookings SET status='paid', payment_amount=%s, paid_at=%s WHERE id=%s",
            (amount, paid_at, booking_id),
        )
        add_notification(cur, booking["phone"], f"₹{amount:,.0f} — #{booking['token']}")

    return jsonify({"ok": True})


# --------------------------------------------------------------- errors ----
@app.errorhandler(pymysql.MySQLError)
def handle_mysql_error(e):
    app.logger.exception("MySQL error")
    return jsonify({"error": "Database error", "detail": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
