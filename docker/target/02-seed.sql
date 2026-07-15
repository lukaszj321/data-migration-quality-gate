INSERT INTO customers (customer_id, full_name, email, country_code, created_at) VALUES
    ('C001', 'Anna Kowalska', 'anna.kowalska@example.test', 'PL', '2024-01-05T09:15:00Z'),
    ('C002', 'Piotr Nowak', 'piotr.nowak@example.test', 'PL', '2024-01-08T10:30:00Z'),
    ('C003', 'Maria Zielinska', 'maria.zielinska@example.test', 'DE', '2024-01-12T14:45:00Z'),
    ('C003', 'Maria Zielinska Duplicate', 'maria.duplicate@example.test', 'DE', '2024-01-12T14:45:00Z'),
    ('C004', 'Jan Wisniewski', 'jan.wisniewski@example.test', 'CZ', '2024-01-17T08:20:00Z'),
    ('C005', 'Ewa Kaminska', 'ewa.kaminska@example.test', 'SK', '2024-01-21T16:05:00Z'),
    ('C006', 'Tomasz Lewandowski', 'tomasz.lewandowski@example.test', 'PL', '2024-01-25T11:40:00Z');

INSERT INTO accounts (account_id, customer_id, account_type, currency, balance, opened_at) VALUES
    ('A001', 'C001', 'checking', 'PLN', 1250.25, '2024-02-01T08:00:00Z'),
    ('A002', 'C001', 'savings', 'EUR', 5400.00, '2024-02-02T08:00:00Z'),
    ('A003', 'C002', 'checking', 'PLN', 780.10, '2024-02-03T08:00:00Z'),
    ('A004', 'C003', 'checking', 'EUR', 240.55, '2024-02-04T08:00:00Z'),
    ('A005', 'C004', 'business', 'CZK', 120000.00, '2024-02-05T08:00:00Z'),
    ('A006', 'C005', 'checking', 'EUR', 610.30, '2024-02-06T08:00:00Z'),
    ('A007', 'C006', 'savings', 'PLN', 9800.99, '2024-02-07T08:00:00Z'),
    ('A008', 'C006', 'checking', 'USD', 312.42, '2024-02-08T08:00:00Z');

INSERT INTO transactions (
    transaction_id, account_id, customer_id, amount, currency, transaction_type, description, occurred_at
) VALUES
    ('T001', 'A001', 'C001', 100.00, 'PLN', 'deposit', 'Opening transfer', '2024-03-01T09:00:00Z'),
    ('T002', 'A001', 'C001', -45.20, 'PLN', 'card_payment', 'Office supplies', '2024-03-02T12:15:00Z'),
    ('T003', 'A002', 'C001', 250.00, 'EUR', 'deposit', 'Savings transfer', '2024-03-03T10:00:00Z'),
    ('T003', 'A002', 'C001', 250.00, 'EUR', 'deposit', 'Duplicate migrated transaction', '2024-03-03T10:00:00Z'),
    ('T004', 'A003', 'C002', -25.00, 'PLN', 'fee', 'Monthly account fee', '2024-03-04T07:30:00Z'),
    ('T005', 'A003', 'C002', 300.00, 'PLN', 'deposit', 'Payroll fragment', '2024-03-05T13:45:00Z'),
    ('T007', 'A004', 'C003', 99.99, 'EUR', 'refund', 'Returned order', '2024-03-07T17:10:00Z'),
    ('T008', 'A005', 'C004', -2500.00, 'CZK', 'wire', 'Vendor invoice', '2024-03-08T11:20:00Z'),
    ('T009', 'A005', 'C004', 15000.00, 'CZK', 'deposit', 'Client payment', '2024-03-09T15:00:00Z'),
    ('T010', 'A006', 'C005', -35.40, 'EUR', 'card_payment', 'Travel', '2024-03-10T12:00:00Z'),
    ('T011', 'A006', 'C005', 500.00, 'EUR', 'deposit', 'Invoice settlement', '2024-03-11T16:30:00Z'),
    ('T012', 'A007', 'C006', -125.00, 'PLN', 'wire', 'Rent share', '2024-03-12T09:45:00Z'),
    ('T013', 'A007', 'C006', 700.00, 'PLN', 'deposit', 'Bonus transfer', '2024-03-13T10:15:00Z'),
    ('T015', 'A008', 'C006', 120.00, 'USD', 'deposit', 'Marketplace payout', '2024-03-15T20:00:00Z'),
    ('T016', 'A002', 'C001', -75.75, 'EUR', 'wire', 'Hotel prepayment', '2024-03-16T06:50:00Z'),
    ('T017', 'A005', 'C004', -400.00, 'CZK', 'fee', 'Service package', '2024-03-17T08:10:00Z'),
    ('T018', 'A001', 'C001', 55.55, 'PLN', 'refund', 'Returned item', '2024-03-18T14:35:00Z'),
    ('T999', 'A999', 'C999', NULL, 'XYZ', 'deposit', NULL, '2024-03-19T10:00:00Z');
