---

# 🤖 Delivery Instruction PDF Processor — Code Documentation

---

## 📌 Overview

This script automates the extraction of **Delivery Instruction (DI) data from PDF files** and stores the parsed records into a **MySQL database hosted on Railway**. It handles duplicate detection at both the DI and part level, ensuring clean, non-redundant data insertion.

---

## ⚙️ Configuration & Dependencies

### Environment Variables
Loaded from `Railway_Connection.env`:

| Variable | Purpose |
| --- | --- |
| `DB_USER` | Database username |
| `DB_PASSWORD` | Database password |
| `DB_HOST` | Database host address |
| `DB_PORT` | Database port |
| `DB_NAME` | Target database name |

> 💡 **Tip:** Keep your `.env` file secure and never commit it to version control.

### Dependencies

| Library | Usage |
| --- | --- |
| `pandas` | Data manipulation and DataFrame operations |
| `tabula` | Extracting tables from PDF files |
| `pypdf` | PDF reading support |
| `openpyxl` | Excel file handling |
| `re` | Regex pattern matching for parsing |
| `glob` | File path pattern matching |
| `sqlalchemy` | Database engine and ORM types |
| `tabulate` | Pretty-printing tables to console |
| `dotenv` | Loading environment variables from `.env` |
| `tkinter` | GUI folder selection dialog |

---

## 🏗️ Architecture

The script is structured into **3 main classes** and **1 entry point function**:

```
PDFParser          → Reads and cleans raw PDF data
DatabaseManager    → Handles DB connection and insertion
DIProcessor        → Orchestrates the full pipeline
select_folder()    → GUI folder picker (entry point)
```

---

## 🔧 Class: `PDFParser`

> Responsible for reading a DI PDF file and returning a clean, structured DataFrame.

---

### `parse(pdf_path)`

The main method that coordinates the full PDF extraction pipeline.

**Steps:**
1. Extracts all tables from the PDF using `tabula`
2. Flattens table content into a single text string
3. Extracts header fields via regex
4. Parses individual part rows
5. Cleans and returns a structured DataFrame

**Extracted Header Fields:**

| Field | Regex Pattern | Example |
| --- | --- | --- |
| `di_no` | `DI No: XXXXXXXXX` | `123456789` |
| `issue_date` | `Issue Date: DD-MMM-YYYY` | `01-Jan-2025` |
| `delivery_date` | `Delivery Date: DD-MMM-YYYY` | `05-Jan-2025` |
| `plant_loc` | `PLANT LOCATION: XX` | `PLANT A1` |

**Output DataFrame Columns:**

| Column | Type | Description |
| --- | --- | --- |
| `di_no` | str | Delivery Instruction number |
| `issue_date` | date | Date DI was issued |
| `delivery_date` | date | Scheduled delivery date |
| `plant_loc` | str | Plant location |
| `part_no` | str | Shortened part number |
| `part_name` | str | Cleaned part description |
| `packaging_qty` | int | Quantity per package |
| `no_of_cards` | int | Number of Kanban cards |
| `total_qty` | int | `packaging_qty × no_of_cards` |
| `kanban_no` | list | List of 10-digit Kanban numbers |

---

### `_find(pattern, text)`

> Utility regex helper. Returns the first capture group match or `None`.

---

### `_extract_parts(df, di_no, issue_date, delivery_date, plant_location)`

> Iterates through DataFrame rows to detect and extract part records.

**Detection Patterns:**

| Pattern Type | Regex | Example Match |
| --- | --- | --- |
| Preferred part no. | `[A-Z]-\d{3,4}` | `P-703`, `H-2704` |
| Fallback part no. | `[A-Z0-9]+-\d+[A-Z0-9-]*` | `JOON-001`, `JH-00H5` |
| Kanban number | `\b\d{10}\b` | `1234567890` |
| Qty pattern | `(\d+)\s+(\d+)\s+([\d.]+)` | `10 5 50.0` |

**Logic:**
- When a part number is detected in a row, the previous part record is saved and a new one begins
- Kanban numbers from subsequent rows are collected and attached to the current part
- The last part is appended after the loop ends

---

### `_assemble_record(...)`

> Builds a single dictionary record for one part, computing `total_qty = packaging_qty × no_of_cards`.

---

### `_shorten_part_no(pn)`

> Normalizes part numbers to a short `X-NNNN` format (e.g. `JOON-P-703` → `P-703`).

---

### `_clean_part_name(name)`

> Strips noise from part descriptions. Removes vendor codes, unit labels, and formatting artifacts.

**Removed patterns:** `JOONHEE`, `JOON-XXX`, `JHXXX`, `EA`, `NO X`, `nan`, trailing decimals

---

## 🗄️ Class: `DatabaseManager`

> Manages the MySQL database connection and record insertion.

---

### `__init__()`

- Loads credentials from `.env`
- Creates a SQLAlchemy engine
- Pre-loads existing `di_no`, `part_no`, `issue_date`, `delivery_date` records into memory for duplicate checking

---

### `_create_engine(connection_string)`

> Creates and returns a SQLAlchemy engine. Raises an exception if the connection fails.

---

### `_insert_new_records(df)`

> Inserts a DataFrame of new records into the `delivery_instructions` MySQL table.

**Date formatting:** Converts `issue_date` and `delivery_date` from `DD-MMM-YYYY` string to Python `date` objects before insertion.

**Database Schema:**

| Column | SQL Type |
| --- | --- |
| `di_no` | `BIGINT` |
| `issue_date` | `DATE` |
| `delivery_date` | `DATE` |
| `plant_loc` | `VARCHAR(100)` |
| `part_no` | `VARCHAR(50)` |
| `part_name` | `VARCHAR(255)` |
| `packaging_qty` | `INTEGER` |
| `no_of_cards` | `INTEGER` |
| `total_qty` | `INTEGER` |
| `kanban_no` | `JSON` |

---

## 🔄 Class: `DIProcessor`

> Orchestrates the full pipeline — from folder scanning to database insertion.

---

### `run()`

Processes every `.pdf` file found in the selected folder.

**Pipeline per PDF:**

```
Parse PDF → Extract DI No
      ↓
Check if DI No already exists in DB
      ↓ (if new)
Merge with existing records to find part-level duplicates
      ↓
Insert only new, non-duplicate records
      ↓
Update local cache to prevent re-insertion within same session
```

**Duplicate Handling:**

| Scenario | Action |
| --- | --- |
| DI No already in DB | Skip entire file |
| Part-level duplicates found | Print duplicate table, skip insert |
| No duplicates | Insert all new records |
| Empty parsed DataFrame | Skip file with warning |

---

## 🖱️ Function: `select_folder()`

> Opens a `tkinter` GUI dialog for the user to select the PDF source folder.

**Behaviour:**
- Hides the main tkinter window, shows only the folder dialog
- Counts and displays the number of `.pdf` files found
- Warns if the folder contains no PDFs and prompts to continue or cancel
- Returns the selected folder path, or `None` if cancelled

---

## 🚀 Entry Point

```python
if __name__ == "__main__":
    folder = select_folder()      # 1. User picks folder via GUI
    processor = DIProcessor(folder)
    processor.run()               # 2. Full pipeline runs
```

---

> 🗒️ **Note:** If a PDF fails to parse, the error and full traceback are printed and the script continues processing remaining files without interruption.
