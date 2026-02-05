# predictor.py
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import json
from datetime import datetime
import os
import threading
from collections import deque
from config import MODELS_DIR
from database import db_manager, ACTIVE_THRESHOLDS

class PrinterMaintenancePredictor:
    def __init__(self):
        self.classifier = RandomForestClassifier(n_estimators=150, random_state=42, n_jobs=-1, max_depth=20)
        self.parts_predictors = {}
        self.scaler = StandardScaler()
        self.telemetry_history = deque(maxlen=50000)
        self.is_trained = False
        self.training_in_progress = False
        
        # Extended statistics structure
        self.stats = {
            'total_received': 0, 
            'total_batches': 0, 
            'predictions_made': 0,
            'maintenance_predicted': 0, 
            'training_count': 0, 
            'last_training_time': None, 
            'last_accuracy': 0.0,
            'feature_importance': {},   # NOWE
            'confusion_matrix': [],     # NOWE
            'detailed_metrics': {}      # NOWE
        }
        self.printer_history_cache = {} 
        self.load_model()
        
        # Feature names in the order they appear in prepare_features
        self.feature_names = [
            'Liczba Stron', 'Zużycie Bębna', 'Temp. Fusera', 'Poziom Tonera', 
            'Liczba Zacięć', 'Zużycie Rolek', 'Śr. Interwał', 'Dni od Serwisu', 'Ryzyko Czasowe'
        ]
    
    def get_printer_history_stats(self, printer_id):
        if printer_id in self.printer_history_cache:
            return self.printer_history_cache[printer_id]

        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT completed_at FROM service_interventions WHERE printer_id = ? AND status = 'completed' ORDER BY completed_at ASC", (printer_id,))
            dates = [datetime.fromisoformat(row[0]) for row in cursor.fetchall() if row[0]]
            
            if len(dates) < 2:
                stats = {'avg_service_interval_days': 180.0, 'total_interventions': len(dates), 'days_since_last_fix': 0}
            else:
                intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                avg_interval = sum(intervals) / len(intervals) if intervals else 180.0
                days_since = (datetime.now() - dates[-1]).days
                stats = {'avg_service_interval_days': float(avg_interval), 'total_interventions': len(dates), 'days_since_last_fix': days_since}
            
            self.printer_history_cache[printer_id] = stats
            return stats

    def add_telemetry_batch(self, batch_data):
        self.telemetry_history.extend(batch_data)
        self.stats['total_received'] += len(batch_data)
        self.stats['total_batches'] += 1
        
        if len(self.telemetry_history) >= 100 and self.stats['total_received'] % 500 == 0 and not self.training_in_progress:
            threading.Thread(target=self.train_model, daemon=True).start()
    
    def prepare_features(self, data, training=False):
        if isinstance(data, list): df = pd.DataFrame(data)
        else: df = pd.DataFrame([data])
            
        features_df = pd.DataFrame()
        features_df['total_pages'] = df.get('total_pages', 0)
        features_df['drum_wear'] = df.get('drum_wear_percent', 0)
        features_df['fuser_temp'] = df.get('fuser_temperature', 0)
        features_df['toner_level'] = df.get('toner_level_percent', 0)
        features_df['paper_jams'] = df.get('paper_jams_count', 0)
        features_df['roller_wear'] = df.get('roller_wear_percent', 0)
        
        avg_intervals = []
        days_since_list = []
        freq_scores = []
        
        printer_ids = df.get('printer_id', ['unknown']*len(df))
        
        for pid in printer_ids:
            hist = self.get_printer_history_stats(pid)
            avg_intervals.append(hist['avg_service_interval_days'])
            
            if 'days_since_maintenance' in df.columns:
                val = df.loc[df['printer_id'] == pid, 'days_since_maintenance'].values[0] if not df.empty else 0
                days_since_list.append(val)
            else:
                days_since_list.append(hist['days_since_last_fix'])
            
            risk = hist['days_since_last_fix'] / (hist['avg_service_interval_days'] + 1)
            freq_scores.append(risk)

        features_df['avg_service_interval'] = avg_intervals
        features_df['days_since_maint'] = days_since_list
        features_df['time_risk_factor'] = freq_scores
        
        feature_cols = ['total_pages', 'drum_wear', 'fuser_temp', 'toner_level', 'paper_jams', 'roller_wear', 'avg_service_interval', 'days_since_maint', 'time_risk_factor']
        return features_df[feature_cols].fillna(0).values
    
    def generate_labels(self, data):
        labels = []
        parts_needed = []
        
        for record in data:
            pid = record.get('printer_id', 'unknown')
            hist = self.get_printer_history_stats(pid)
            time_risk = hist['days_since_last_fix'] / (hist['avg_service_interval_days'] + 1)
            
            needs_maintenance = (
                record['drum_wear_percent'] > ACTIVE_THRESHOLDS['drum_wear_percent'] or
                record['roller_wear_percent'] > ACTIVE_THRESHOLDS['roller_wear_percent'] or
                record['paper_jams_count'] > ACTIVE_THRESHOLDS['paper_jams_count'] or
                record['fuser_temperature'] > ACTIVE_THRESHOLDS['fuser_temperature'] or
                time_risk > 1.2
            )
            labels.append(1 if needs_maintenance else 0)
            
            parts = []
            if record['drum_wear_percent'] > ACTIVE_THRESHOLDS['drum_wear_percent']: parts.append('drum_unit')
            if record['roller_wear_percent'] > ACTIVE_THRESHOLDS['roller_wear_percent']: parts.append('pickup_roller')
            if record['toner_level_percent'] < 10: parts.append('toner_cartridge')
            if record['fuser_temperature'] > ACTIVE_THRESHOLDS['fuser_temperature']: parts.append('fuser_assembly')
            if time_risk > 1.2 and not parts: parts.append('general_maintenance')
            parts_needed.append(parts)
        
        return np.array(labels), parts_needed
    
    def train_model(self):
        if len(self.telemetry_history) < 50 or self.training_in_progress: return
        self.training_in_progress = True
        try:
            data_list = list(self.telemetry_history)
            X = self.prepare_features(data_list, training=True)
            y, parts_labels = self.generate_labels(data_list)
            
            X_scaled = self.scaler.fit_transform(X)
            self.classifier.fit(X_scaled, y)

            # --- CALCULATING DETAILED METRICS ---
            y_pred = self.classifier.predict(X_scaled)
            
            # 1. Feature Importance
            importances = self.classifier.feature_importances_
            # Conversion to a list of floats
            feat_imp_dict = {name: float(imp) for name, imp in zip(self.feature_names, importances)}
            
             #2. Classification report
            report = classification_report(y, y_pred, output_dict=True, zero_division=0)
            
            #3. Matrix of errors
            cm = confusion_matrix(y, y_pred)
            # Flattening and conversion to int (TN, FP, FN, TP)
            cm_flat = [int(x) for x in cm.ravel()] if cm.size == 4 else [0,0,0,0]

            self.stats.update({
                'feature_importance': feat_imp_dict,
                'confusion_matrix': cm_flat,
                'detailed_metrics': {
                    'precision': float(report['1']['precision']) if '1' in report else 0.0,
                    'recall': float(report['1']['recall']) if '1' in report else 0.0,
                    'f1_score': float(report['1']['f1-score']) if '1' in report else 0.0,
                    'support': int(report['1']['support']) if '1' in report else 0
                }
            })
            # ---------------------------------------
            
            all_parts = ['drum_unit', 'pickup_roller', 'toner_cartridge', 'fuser_assembly', 'general_maintenance']
            for part in all_parts:
                y_part = np.array([1 if part in parts else 0 for parts in parts_labels])
                if y_part.sum() > 5:
                    sub_clf = RandomForestClassifier(n_estimators=50, max_depth=10)
                    sub_clf.fit(X_scaled, y_part)
                    self.parts_predictors[part] = sub_clf
            
            accuracy = self.classifier.score(X_scaled, y)
            self.stats['last_accuracy'] = accuracy
            self.stats['training_count'] += 1
            self.stats['last_training_time'] = datetime.now().isoformat()
            self.is_trained = True
            self.save_model()
            self.printer_history_cache = {}
            
            print(f"✅ Model wytrenowany. Dokładność: {accuracy:.2f}, F1: {self.stats['detailed_metrics']['f1_score']:.2f}")

        except Exception as e:
            print(f"❌ Błąd treningu: {e}")
        finally:
            self.training_in_progress = False

    def predict_batch(self, batch_data):
        if not self.is_trained:
            return [{'printer_id': d.get('printer_id'), 'needs_maintenance': False, 'confidence': 0.0, 'parts_needed': []} for d in batch_data], []

        X = self.prepare_features(batch_data)
        X_scaled = self.scaler.transform(X)
        predictions = self.classifier.predict(X_scaled)
        probabilities = self.classifier.predict_proba(X_scaled)
        
        results, interventions_to_create = [], []
        
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            for i, data in enumerate(batch_data):
                pred = predictions[i]
                confidence = probabilities[i][1] if pred == 1 else probabilities[i][0]
                printer_id = data.get('printer_id', 'unknown')
                model = data.get('model', 'standard')
                location = data.get('location', 'Nieznana')
                
                cursor.execute("""
                    INSERT INTO printers (printer_id, model_type, location) 
                    VALUES (?, ?, ?)
                    ON CONFLICT(printer_id) DO UPDATE SET 
                        model_type = excluded.model_type,
                        location = excluded.location
                """, (printer_id, model, location))
                
                parts_needed = []
                for part_name, sub_clf in self.parts_predictors.items():
                    if sub_clf.predict(X_scaled[i:i+1])[0] == 1: parts_needed.append(part_name)
                
                hist = self.get_printer_history_stats(printer_id)
                cursor.execute("""
                    INSERT INTO predictions (
                        printer_id, needs_maintenance, confidence, drum_wear, roller_wear, 
                        fuser_temp, toner_level, paper_jams, parts_needed, avg_service_interval
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    printer_id, bool(pred), float(confidence),
                    data.get('drum_wear_percent', 0), data.get('roller_wear_percent', 0),
                    data.get('fuser_temperature', 0), data.get('toner_level_percent', 0),
                    data.get('paper_jams_count', 0), json.dumps(parts_needed), hist['avg_service_interval_days']
                ))
                
                results.append({
                    'printer_id': printer_id, 'needs_maintenance': bool(pred),
                    'confidence': float(confidence), 'parts_needed': parts_needed, 'time_risk_metrics': hist
                })
                
                if pred == 1 and confidence >= ACTIVE_THRESHOLDS['confidence_threshold']:
                    cursor.execute("SELECT id FROM service_interventions WHERE printer_id = ? AND status IN ('pending', 'assigned')", (printer_id,))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO service_interventions (printer_id, prediction_id, status) VALUES (?, ?, 'pending')", (printer_id, cursor.lastrowid))
                        interventions_to_create.append(printer_id)
        return results, interventions_to_create

    def save_model(self):
        try:
            os.makedirs(MODELS_DIR, exist_ok=True)
            joblib.dump(self.classifier, f'{MODELS_DIR}/classifier.pkl')
            joblib.dump(self.scaler, f'{MODELS_DIR}/scaler.pkl')
            joblib.dump(self.parts_predictors, f'{MODELS_DIR}/parts_predictor.pkl')
            # Optional: Save stats to a JSON file so they survive a restart
            with open(f'{MODELS_DIR}/stats.json', 'w') as f:
                json.dump(self.stats, f)
        except Exception: pass

    def load_model(self):
        try:
            if os.path.exists(f'{MODELS_DIR}/classifier.pkl'):
                self.classifier = joblib.load(f'{MODELS_DIR}/classifier.pkl')
                self.scaler = joblib.load(f'{MODELS_DIR}/scaler.pkl')
                self.parts_predictors = joblib.load(f'{MODELS_DIR}/parts_predictor.pkl')
                self.is_trained = True
            
            if os.path.exists(f'{MODELS_DIR}/stats.json'):
                with open(f'{MODELS_DIR}/stats.json', 'r') as f:
                    self.stats = json.load(f)
        except Exception: pass

predictor = PrinterMaintenancePredictor()