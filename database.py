import sqlite3
from contextlib import contextmanager
from config import DEFAULT_THRESHOLDS, DB_PATH

# Global variable storing current settings in memory
ACTIVE_THRESHOLDS = DEFAULT_THRESHOLDS.copy()

class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.init_database()
        self.load_settings()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # --- 1. Table of Settings ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- 2. Printer Settings ---
            # Creating a complete structure for new installations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS printers (
                    printer_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'active',
                    model_type TEXT DEFAULT 'standard',
                    location TEXT DEFAULT 'Nieznana',
                    installation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP NULL,
                    deletion_reason TEXT NULL
                )
            """)
            
           
            
            # Adding the “location” column
            try:
                cursor.execute("ALTER TABLE printers ADD COLUMN location TEXT DEFAULT 'Nieznana'")
                print("🔧 Migracja: Dodano kolumnę 'location' do tabeli printers.")
            except sqlite3.OperationalError:
                pass # The column already exists, we ignore the error.
            
           
            try:
                cursor.execute("ALTER TABLE printers ADD COLUMN model_type TEXT DEFAULT 'standard'")
                print("🔧 Migracja: Dodano kolumnę 'model_type' do tabeli printers.")
            except sqlite3.OperationalError:
                pass # The column already exists, we ignore the error.
            # -----------------------------------------------------
            
            # --- 4. Prediction Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    printer_id TEXT,
                    needs_maintenance BOOLEAN,
                    confidence REAL,
                    drum_wear REAL,
                    roller_wear REAL,
                    fuser_temp REAL,
                    toner_level REAL,
                    paper_jams INTEGER,
                    parts_needed TEXT,
                    avg_service_interval REAL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (printer_id) REFERENCES printers(printer_id)
                )
            """)
            
            # --- 5. Intervention Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS service_interventions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    printer_id TEXT,
                    prediction_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    technician_name TEXT NULL,
                    vehicle_id TEXT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    assigned_at TIMESTAMP NULL,
                    completed_at TIMESTAMP NULL,
                    notes TEXT NULL,
                    FOREIGN KEY (printer_id) REFERENCES printers(printer_id),
                    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
                )
            """)
            
            # --- 6. Technician Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS technicians (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    phone TEXT,
                    status TEXT DEFAULT 'available',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_printer ON predictions(printer_id, timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_interventions_printer ON service_interventions(printer_id, completed_at DESC)")
            
            # Adding default technicians (if the table is empty)
            cursor.execute("SELECT COUNT(*) FROM technicians")
            if cursor.fetchone()[0] == 0:
                sample_techs = [
                    ('Jan Kowalski', 'SRV-001', '+48 123 456 789'),
                    ('Anna Nowak', 'SRV-002', '+48 234 567 890')
                ]
                cursor.executemany("INSERT INTO technicians (name, vehicle_id, phone) VALUES (?, ?, ?)", sample_techs)
            
            conn.commit()

    def load_settings(self):
        """Ładuje ustawienia z DB do pamięci"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM system_settings")
            rows = cursor.fetchall()
            
            if not rows:
                print("⚙️ Inicjalizacja domyślnych ustawień w DB...")
                for key, val in DEFAULT_THRESHOLDS.items():
                    cursor.execute("INSERT INTO system_settings (key, value) VALUES (?, ?)", (key, str(val)))
            else:
                print("⚙️ Ładowanie ustawień z bazy danych...")
                for row in rows:
                    key = row['key']
                    val = row['value']
                    if key in ACTIVE_THRESHOLDS:
                        ACTIVE_THRESHOLDS[key] = float(val)

    def update_setting(self, key, value):
        """Aktualizuje ustawienie w DB i pamięci"""
        with self.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, str(value)))
        
        ACTIVE_THRESHOLDS[key] = float(value)

# Singleton instance of database
db_manager = DatabaseManager()