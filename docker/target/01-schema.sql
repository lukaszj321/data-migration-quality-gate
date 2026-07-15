CREATE TABLE customers (
    row_id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL,
    full_name VARCHAR(120),
    email VARCHAR(160),
    country_code VARCHAR(2),
    created_at TIMESTAMPTZ
);

CREATE TABLE accounts (
    row_id BIGSERIAL PRIMARY KEY,
    account_id VARCHAR(32) NOT NULL,
    customer_id VARCHAR(32),
    account_type VARCHAR(30),
    currency VARCHAR(3),
    balance NUMERIC(18,2),
    opened_at TIMESTAMPTZ
);

CREATE TABLE transactions (
    row_id BIGSERIAL PRIMARY KEY,
    transaction_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32),
    customer_id VARCHAR(32),
    amount NUMERIC(18,2),
    currency VARCHAR(3),
    transaction_type VARCHAR(30),
    description VARCHAR(80),
    occurred_at TIMESTAMPTZ
);
