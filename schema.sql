-- KrishiSetu database schema
CREATE DATABASE IF NOT EXISTS krishisetu CHARACTER SET utf8mb4;
USE krishisetu;

-- Purchase centers (matches CENTERS array in frontend)
CREATE TABLE IF NOT EXISTS centers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE
);

-- Crops with procurement rate (matches CROP_KEYS / RATES)
CREATE TABLE IF NOT EXISTS crops (
    crop_key VARCHAR(30) PRIMARY KEY,
    name VARCHAR(60) NOT NULL,
    rate_per_qtl DECIMAL(10, 2) NOT NULL
);

-- One counter per center+date, tracks the token queue (matches getCounter())
CREATE TABLE IF NOT EXISTS counters (
    center VARCHAR(120) NOT NULL,
    booking_date DATE NOT NULL,
    now_serving INT NOT NULL DEFAULT 0,
    next_token INT NOT NULL DEFAULT 1,
    PRIMARY KEY (center, booking_date)
);

-- Farmer bookings (matches the `booking` object built in wireBook())
CREATE TABLE IF NOT EXISTS bookings (
    id VARCHAR(80) PRIMARY KEY,
    token INT NOT NULL,
    name VARCHAR(120) NOT NULL,
    phone VARCHAR(10) NOT NULL,
    village VARCHAR(120) NOT NULL,
    crop_key VARCHAR(30) NOT NULL,
    qty DECIMAL(10, 2) NOT NULL,
    center VARCHAR(120) NOT NULL,
    booking_date DATE NOT NULL,
    slot VARCHAR(20) NOT NULL,
    status ENUM('booked', 'progress', 'procured', 'paid') NOT NULL DEFAULT 'booked',
    procured_qty DECIMAL(10, 2) DEFAULT NULL,
    payment_amount DECIMAL(12, 2) DEFAULT NULL,
    created_at BIGINT NOT NULL,   -- epoch millis, same as Date.now() in the frontend
    paid_at BIGINT DEFAULT NULL,
    CONSTRAINT fk_booking_crop FOREIGN KEY (crop_key) REFERENCES crops(crop_key),
    INDEX idx_center_date (center, booking_date),
    INDEX idx_center_date_slot (center, booking_date, slot),
    INDEX idx_phone (phone),
    INDEX idx_center_date_status (center, booking_date, status)
);

-- Per-phone notification feed (matches STATE.notifications[phone])
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone VARCHAR(10) NOT NULL,
    message VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_phone_created (phone, created_at)
);

-- Seed data matching the frontend's CENTERS / RATES constants
INSERT IGNORE INTO centers (name) VALUES
    ('Ellenabad Mandi'),
    ('Sirsa Grain Market'),
    ('Fatehabad APMC Yard');

INSERT IGNORE INTO crops (crop_key, name, rate_per_qtl) VALUES
    ('wheat',     'Wheat',     2275.00),
    ('paddy',     'Paddy',     2183.00),
    ('cotton',    'Cotton',    7121.00),
    ('mustard',   'Mustard',   5650.00),
    ('bajra',     'Bajra',     2500.00),
    ('sugarcane', 'Sugarcane',  340.00);
