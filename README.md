# Data Migration Quality Gate

Data Migration Quality Gate to narzędzie CLI pełniące rolę bramki jakości migracji, czyli `quality gate`, dla migracji danych pomiędzy dwiema bazami PostgreSQL. Porównuje bazę źródłową z bazą docelową, wykonuje zestaw kontroli jakości i zwraca decyzję wdrożeniową: `ALLOW`, `REVIEW` albo `BLOCK`.

Projekt jest aktualnie na etapie Milestone 2A. Implementuje działający pionowy fragment: walidację konfiguracji YAML, połączenie z dwiema bazami PostgreSQL, osiem kontroli jakości, czytelne podsumowanie CLI, raport JSON oraz kody wyjścia przydatne w automatyzacji.

## Spis treści

- [Problem biznesowy](#problem-biznesowy)
- [Dla kogo jest to narzędzie](#dla-kogo-jest-to-narzędzie)
- [Jak działa narzędzie](#jak-działa-narzędzie)
- [Diagram przepływu](#diagram-przepływu)
- [Aktualny zakres](#aktualny-zakres)
- [Dostępne kontrole](#dostępne-kontrole)
- [Dane demonstracyjne](#dane-demonstracyjne)
- [Kontrolowane błędy target](#kontrolowane-błędy-target)
- [Wymagania](#wymagania)
- [Uruchomienie baz](#uruchomienie-baz)
- [Instalacja](#instalacja)
- [Konfiguracja YAML](#konfiguracja-yaml)
- [Walidacja konfiguracji](#walidacja-konfiguracji)
- [Uruchomienie gate](#uruchomienie-gate)
- [Statusy decyzje i kody wyjścia](#statusy-decyzje-i-kody-wyjścia)
- [Raport JSON](#raport-json)
- [Testy i quality gates](#testy-i-quality-gates)
- [Struktura projektu](#struktura-projektu)
- [Ograniczenia Milestone 2A](#ograniczenia-milestone-2a)
- [Planowane kolejne kontrole](#planowane-kolejne-kontrole)

[↑ Powrót do spisu treści](#spis-treści)

---

## Problem biznesowy

Migracja danych rzadko kończy się na prostym skopiowaniu rekordów. Zespół musi wiedzieć, czy dane w bazie docelowej są kompletne, czy nie pojawiły się nadmiarowe rekordy, czy logiczne klucze migracyjne nie zostały zdublowane oraz czy podstawowe reguły domenowe nadal są spełnione.

Sama liczba rekordów nie wystarcza. Tabela docelowa może mieć tyle samo wierszy co tabela źródłowa, a mimo to zawierać inne rekordy: część danych może zniknąć, część może pojawić się nadmiarowo, a część może łamać relacje logiczne albo dopuszczalne wartości.

Data Migration Quality Gate automatyzuje te kontrole i zwraca wynik, który można wykorzystać przed decyzją o wdrożeniu migracji.

[↑ Powrót do spisu treści](#spis-treści)

---

## Dla kogo jest to narzędzie

Projekt jest przeznaczony dla osób pracujących z migracjami danych i walidacją jakości danych:

- inżynierów danych,
- developerów odpowiedzialnych za migracje,
- analityków QA,
- release managerów,
- zespołów utrzymujących systemy z bazami PostgreSQL.

README zakłada znajomość podstaw SQL, migracji danych lub inżynierii danych. Nie wymaga znajomości wewnętrznej struktury tego repozytorium.

[↑ Powrót do spisu treści](#spis-treści)

---

## Jak działa narzędzie

Narzędzie czyta `migration.yaml`, waliduje konfigurację przez Pydantic, pobiera connection stringi ze zmiennych środowiskowych i wykonuje skonfigurowane kontrole dla tabel `customers`, `accounts` oraz `transactions`.

Baza źródłowa reprezentuje dane przed migracją. Baza docelowa reprezentuje wynik migracji. Obie bazy są uruchamiane lokalnie przez Docker Compose jako oddzielne usługi:

- `source-db`, baza `source_db`, port hosta `5433`,
- `target-db`, baza `target_db`, port hosta `5434`.

Każda tabela ma techniczny klucz `row_id`. Kontrole migracyjne używają natomiast logicznych kluczy domenowych skonfigurowanych w YAML, takich jak `customer_id`, `account_id` i `transaction_id`.

[↑ Powrót do spisu treści](#spis-treści)

---

## Diagram przepływu

```mermaid
flowchart LR
    A[(Źródłowy PostgreSQL)] --> C[Kontrole jakości danych]
    B[(Docelowy PostgreSQL)] --> C
    D[Konfiguracja YAML] --> C
    C --> E[Wyniki kontroli]
    E --> F[PASS / WARN / FAIL]
    E --> G[Raport JSON]
    F --> H[ALLOW / REVIEW / BLOCK]
```

[↑ Powrót do spisu treści](#spis-treści)

---

## Aktualny zakres

Milestone 2A obejmuje:

- CLI `data-quality-gate`,
- walidację konfiguracji YAML,
- połączenie z dwiema bazami PostgreSQL,
- osiem kontroli jakości danych,
- agregację wyników do `PASS`, `WARN` albo `FAIL`,
- decyzję wdrożeniową `ALLOW`, `REVIEW` albo `BLOCK`,
- raport JSON w katalogu `reports/`,
- testy jednostkowe i integracyjne,
- lokalne środowisko demonstracyjne w Docker Compose.

Wersja aplikacji pozostaje `0.1.0`. Wersja schematu raportu JSON pozostaje `0.1`.

[↑ Powrót do spisu treści](#spis-treści)

---

## Dostępne kontrole

### `row_count`

Porównuje liczbę rekordów w tabeli źródłowej i docelowej.

Wykrywa różnicę w liczbie wierszy. Zwraca `PASS`, gdy liczby są równe, oraz `FAIL`, gdy są różne. Ta kontrola jest szybkim sygnałem, ale nie dowodzi poprawności migracji.

### `missing_keys`

Wykrywa logiczne klucze obecne w bazie źródłowej, ale nieobecne w bazie docelowej.

Pomaga znaleźć brakujące rekordy po migracji. Zwraca `PASS`, gdy niczego nie brakuje, oraz `FAIL`, gdy co najmniej jeden klucz źródłowy nie występuje w target.

### `unexpected_keys`

Wykrywa logiczne klucze obecne tylko w bazie docelowej.

Pokazuje nadmiarowe rekordy, które nie mają odpowiednika w source. Zwraca `PASS`, gdy takich rekordów nie ma, oraz `WARN`, gdy występują. W tym projekcie nadmiarowy rekord wymaga przeglądu, ale sam w sobie nie blokuje migracji tak jak `FAIL`.

### `duplicate_keys`

Wykrywa duplikaty logicznych kluczy migracyjnych osobno w source i target.

Pomaga znaleźć sytuacje, w których ten sam `customer_id`, `account_id` albo `transaction_id` występuje więcej niż raz. Zwraca `PASS`, gdy nie ma duplikatów, oraz `FAIL`, gdy duplikaty występują w którejkolwiek bazie.

### `schema_match`

Porównuje strukturę tabeli source i target.

Sprawdza obecność kolumn, typ danych, długość pól znakowych, precision i scale dla `NUMERIC` oraz nullability. Nie porównuje nazw constraintów, indeksów, kolejności fizycznej kolumn ani wartości domyślnych. Zwraca `PASS`, gdy schemat jest zgodny dla kontrolowanych kolumn, oraz `FAIL`, gdy znajdzie istotną niezgodność schematu.

### `null_check`

Sprawdza kolumny oznaczone w YAML jako `not_null: true`.

Kontrola działa osobno dla source i target. Wykrywa niedozwolone wartości `NULL` w kolumnach wymaganych logicznie. Zwraca `PASS`, gdy nie ma takich wartości, oraz `FAIL`, gdy pojawi się co najmniej jeden niedozwolony `NULL`.

### `allowed_values`

Sprawdza kolumny z listą `allowed_values`.

Porównanie jest dokładne i case-sensitive. `NULL` nie jest naruszeniem tej kontroli, bo obsługuje go `null_check`. Zwraca `PASS`, gdy wszystkie niepuste wartości są dozwolone, oraz `FAIL`, gdy source albo target zawiera wartość spoza listy.

### `referential_integrity`

Sprawdza logiczną integralność referencyjną wewnątrz tej samej bazy.

Dla relacji skonfigurowanych przez `references` kontrola sprawdza, czy wartość w tabeli child istnieje w tabeli parent. Nie porównuje relacji source bezpośrednio z target. `NULL` w child jest ignorowany przez tę kontrolę i powinien być obsłużony przez `null_check`. Zwraca `PASS`, gdy relacje są poprawne, oraz `FAIL`, gdy występują orphan records.

[↑ Powrót do spisu treści](#spis-treści)

---

## Dane demonstracyjne

Docker Compose uruchamia dwie deterministycznie seedowane bazy PostgreSQL. Source zawiera spójny zestaw danych demonstracyjnych:

- 6 klientów w `customers`,
- 8 kont w `accounts`,
- 18 transakcji w `transactions`.

Target symuluje wynik migracji z kontrolowanymi błędami demonstracyjnymi. Błędy są celowe, powtarzalne i opisane w tabeli poniżej.

Target celowo nie ma constraintów `UNIQUE` ani fizycznych FK blokujących te błędy. Dzięki temu baza może przyjąć niepoprawny wynik migracji, a narzędzie może wykryć problemy po fakcie. To odzwierciedla częsty wzorzec pracy z obszarem landing/staging podczas migracji.

[↑ Powrót do spisu treści](#spis-treści)

---

## Kontrolowane błędy target

| Problem | Tabela | Rekord lub kolumna | Wykrywająca kontrola |
| ------- | ------ | ------------------ | -------------------- |
| Brakująca transakcja po migracji | `transactions` | `T006` | `missing_keys` |
| Brakująca transakcja po migracji | `transactions` | `T014` | `missing_keys` |
| Nadmiarowa transakcja w target | `transactions` | `T999` | `unexpected_keys` |
| Duplikat logicznego klucza transakcji | `transactions` | `transactions.T003` | `duplicate_keys` |
| Duplikat logicznego klucza klienta | `customers` | `customers.C003` | `duplicate_keys` |
| Niedozwolony `NULL` | `transactions` | `transactions.T999.amount = NULL` | `null_check` |
| Niedozwolona waluta | `transactions` | `transactions.T999.currency = XYZ` | `allowed_values` |
| Orphan do nieistniejącego konta | `transactions` | `T999.account_id = A999` | `referential_integrity` |
| Orphan do nieistniejącego klienta | `transactions` | `T999.customer_id = C999` | `referential_integrity` |
| Różnica schematu | `transactions` | source `description VARCHAR(255)`, target `description VARCHAR(80)` | `schema_match` |

Dodatkowo target zawiera dane przydatne dla przyszłych kontroli, których Milestone 2A jeszcze nie implementuje: zmienioną kwotę dla `T004` i skrócony opis dla `T010`.

[↑ Powrót do spisu treści](#spis-treści)

---

## Wymagania

Do uruchomienia projektu lokalnie potrzebne są:

- Python 3.12,
- PostgreSQL uruchamiany przez Docker Compose,
- Docker Compose,
- pakiet instalowany z `pyproject.toml`.

Główne biblioteki i narzędzia developerskie:

- SQLAlchemy Core,
- psycopg,
- Pydantic,
- PyYAML,
- pytest,
- pytest-cov,
- Ruff,
- mypy.

Projekt nie używa SQLAlchemy ORM, FastAPI, Reacta, Pandas, Celery, Redis, Kubernetes ani usług chmurowych.

[↑ Powrót do spisu treści](#spis-treści)

---

## Uruchomienie baz

Uruchom świeże środowisko baz:

```powershell
docker compose down --volumes --remove-orphans
docker compose up -d
docker compose ps
```

Po starcie oba serwisy powinny być `healthy`:

- `source-db`,
- `target-db`.

Connection stringi nie są zapisywane w `migration.yaml`. Ustaw je przez zmienne środowiskowe:

```powershell
$env:DQG_SOURCE_DB_URL="postgresql+psycopg://dqg_demo:dqg_demo_password@localhost:5433/source_db"
$env:DQG_TARGET_DB_URL="postgresql+psycopg://dqg_demo:dqg_demo_password@localhost:5434/target_db"
```

Wartości są demonstracyjne. Prawdziwego pliku `.env` nie należy commitować.

[↑ Powrót do spisu treści](#spis-treści)

---

## Instalacja

Zainstaluj projekt w trybie editable:

```powershell
python -m pip install -e ".[dev]"
```

Sprawdź entry point:

```powershell
data-quality-gate --version
```

Oczekiwany wynik:

```text
data-quality-gate 0.1.0
```

[↑ Powrót do spisu treści](#spis-treści)

---

## Konfiguracja YAML

Plik `migration.yaml` definiuje nazwę migracji, aliasy baz danych, limit próbek oraz listę tabel i kontroli.

Fragment konfiguracji dla `transactions`:

```yaml
tables:
  transactions:
    primary_key: transaction_id
    checks:
      - row_count
      - missing_keys
      - unexpected_keys
      - duplicate_keys
      - schema_match
      - null_check
      - allowed_values
      - referential_integrity

    columns:
      transaction_id:
        not_null: true
      account_id:
        not_null: true
        references:
          table: accounts
          column: account_id
      customer_id:
        not_null: true
        references:
          table: customers
          column: customer_id
      amount:
        not_null: true
      currency:
        not_null: true
        allowed_values:
          - PLN
          - EUR
          - USD
          - CZK
      occurred_at:
        not_null: true
```

Walidacja konfiguracji odrzuca między innymi:

- nieobsługiwane nazwy kontroli,
- duplikaty kontroli w jednej tabeli,
- `sample_limit < 1`,
- pustą listę `allowed_values`,
- duplikaty w `allowed_values`,
- referencję do nieistniejącej tabeli albo kolumny,
- `null_check` bez żadnej kolumny `not_null: true`,
- `allowed_values` bez żadnej skonfigurowanej listy wartości,
- `referential_integrity` bez żadnej relacji `references`,
- `schema_match` bez konfiguracji kolumn.

[↑ Powrót do spisu treści](#spis-treści)

---

## Walidacja konfiguracji

Walidacja sprawdza wyłącznie YAML i nie łączy się z bazami:

```powershell
data-quality-gate validate migration.yaml
```

Przykładowy rzeczywisty output:

```text
Configuration is valid: migration.yaml
```

Błąd konfiguracji zwraca kod wyjścia `3` i jest wypisywany bez pełnego tracebacka.

[↑ Powrót do spisu treści](#spis-treści)

---

## Uruchomienie gate

Uruchom pełną walidację migracji:

```powershell
data-quality-gate run migration.yaml
```

Przykładowy rzeczywisty output dla danych demonstracyjnych:

```text
Migration: legacy-payments-to-new-payments
Status: FAIL

Checks: 23
Passed: 14
Warnings: 1
Failed: 8

Deployment decision: BLOCK
JSON report: reports/legacy-payments-to-new-payments-<run-id>.json
```

Zawartość tego bloku pozostaje po angielsku, ponieważ aplikacja faktycznie wypisuje komunikaty CLI po angielsku.

[↑ Powrót do spisu treści](#spis-treści)

---

## Statusy decyzje i kody wyjścia

Statusy kontroli:

- `PASS` oznacza, że dana kontrola nie znalazła problemu.
- `WARN` oznacza wynik wymagający przeglądu, ale niekoniecznie blokujący migrację.
- `FAIL` oznacza błąd blokujący.

Agregacja statusu migracji:

- jeśli istnieje co najmniej jeden `FAIL`, wynik końcowy to `FAIL`,
- jeśli nie ma `FAIL`, ale istnieje co najmniej jeden `WARN`, wynik końcowy to `WARN`,
- jeśli wszystkie kontrole mają `PASS`, wynik końcowy to `PASS`.

Decyzja wdrożeniowa:

| Status | Decyzja | Znaczenie |
| ------ | ------- | --------- |
| `PASS` | `ALLOW` | Migracja może przejść dalej. |
| `WARN` | `REVIEW` | Migracja wymaga przeglądu. |
| `FAIL` | `BLOCK` | Migracja powinna zostać zablokowana. |

Kody wyjścia:

| Kod | Znaczenie |
| --- | --------- |
| `0` | `PASS` |
| `1` | `WARN` |
| `2` | `FAIL` |
| `3` | niepoprawna konfiguracja |
| `4` | błąd techniczny albo błąd połączenia z bazą |

[↑ Powrót do spisu treści](#spis-treści)

---

## Raport JSON

Po każdym technicznie udanym uruchomieniu `run` narzędzie zapisuje raport JSON w katalogu `reports/`.

Raport zawiera:

- `schema_version`, obecnie `0.1`,
- `summary`,
- `failed_checks`,
- pełną listę `results`.

Model `CheckResult` zachowuje stały publiczny kontrakt:

- `check_name`,
- `table`,
- `status`,
- `discrepancy_count`,
- `message`,
- `sample_records`,
- `duration_ms`.

Milestone 2A dodaje nowe wartości `check_name`, ale nie zmienia struktury raportu. Raport nie zawiera haseł, connection stringów ani surowych danych uwierzytelniających.

Przykładowy fragment wyniku `schema_match`:

```json
{
  "check_name": "schema_match",
  "table": "transactions",
  "status": "FAIL",
  "discrepancy_count": 1,
  "sample_records": [
    {
      "column": "description",
      "issue": "length_mismatch",
      "source": "varchar(255) NULL",
      "target": "varchar(80) NULL"
    }
  ]
}
```

Przykładowy fragment wyniku `referential_integrity`:

```json
{
  "check_name": "referential_integrity",
  "table": "transactions",
  "status": "FAIL",
  "sample_records": [
    {
      "database": "target",
      "primary_key": "T999",
      "column": "account_id",
      "value": "A999",
      "referenced_table": "accounts",
      "referenced_column": "account_id"
    }
  ]
}
```

[↑ Powrót do spisu treści](#spis-treści)

---

## Testy i quality gates

Podstawowe komendy jakości:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy data_quality_gate
.\.venv\Scripts\python.exe -m pytest -m "not integration" -W error `
  --cov=data_quality_gate `
  --cov-branch `
  --cov-report=term-missing `
  --cov-fail-under=85
```

Testy integracyjne wymagają działających kontenerów PostgreSQL i ustawionych zmiennych `DQG_SOURCE_DB_URL` oraz `DQG_TARGET_DB_URL`:

```powershell
.\.venv\Scripts\python.exe -m pytest -m integration
```

[↑ Powrót do spisu treści](#spis-treści)

---

## Struktura projektu

Najważniejsze elementy repozytorium:

```text
compose.yaml
Dockerfile
pyproject.toml
README.md
migration.yaml
docker/
  source/
  target/
data_quality_gate/
  cli.py
  config.py
  database.py
  engine.py
  models.py
  reporting.py
  checks/
tests/
reports/
```

Katalog `reports/` przechowuje raporty runtime, ale pliki JSON z raportami są ignorowane przez Git. W repozytorium pozostaje tylko `reports/.gitkeep`.

[↑ Powrót do spisu treści](#spis-treści)

---

## Ograniczenia Milestone 2A

To nie jest wersja produkcyjna. Aktualny zakres świadomie pomija:

- `column_comparison`,
- `numeric_tolerance`,
- `checksum`,
- raport HTML,
- GitHub Actions,
- publikację na GitHub,
- tagi i release.

Projekt nie wykonuje jeszcze pełnego porównania wartości wszystkich kolumn. Koncentruje się na kontrolach strukturalnych, kluczach logicznych, podstawowych regułach domenowych i integralności referencyjnej.

[↑ Powrót do spisu treści](#spis-treści)

---

## Planowane kolejne kontrole

Naturalne kolejne kroki to:

- `column_comparison` do porównywania wartości kolumn między source i target,
- `numeric_tolerance` do porównań liczbowych z tolerancją,
- `checksum` do szybkiego porównywania większych zbiorów danych,
- raport HTML jako wygodniejsza forma przeglądu wyników.

Te elementy nie są jeszcze zaimplementowane i nie powinny być traktowane jako gotowa funkcjonalność.

[↑ Powrót do spisu treści](#spis-treści)
