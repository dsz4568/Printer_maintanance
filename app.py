from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import os
from database import db_manager, ACTIVE_THRESHOLDS
from predictor import predictor
from config import MODELS_DIR

app = Flask(__name__)
CORS(app)

# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/telemetry/batch', methods=['POST'])
def receive_telemetry_batch():
    try:
        data = request.get_json()
        batch = data.get('telemetry_batch', [])
        if not batch: return jsonify({'error': 'Empty batch'}), 400
        
        predictor.add_telemetry_batch(batch)
        preds, new_ints = predictor.predict_batch(batch)
        
        return jsonify({
            'received': True, 
            'maintenance_needed': sum(1 for p in preds if p['needs_maintenance']), 
            'new_interventions': len(new_ints)
        }), 200
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Returns aggregated data for charts (Faults + Technicians)"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Fault distribution
            cursor.execute("SELECT parts_needed FROM predictions WHERE needs_maintenance = 1 ORDER BY id DESC LIMIT 200")
            rows = cursor.fetchall()
            
            part_counts = {}
            for row in rows:
                if row['parts_needed']:
                    try:
                        parts = json.loads(row['parts_needed'])
                        for part in parts:
                            readable_name = {
                                'drum_unit': 'Bęben', 'pickup_roller': 'Rolki',
                                'toner_cartridge': 'Toner', 'fuser_assembly': 'Fuser', 'general_maintenance': 'Przegląd'
                            }.get(part, part)
                            part_counts[readable_name] = part_counts.get(readable_name, 0) + 1
                    except: pass
            
            # 2. Technician Statistics
            cursor.execute("""
                SELECT technician_name, COUNT(*) as count 
                FROM service_interventions 
                WHERE status = 'completed' AND technician_name IS NOT NULL 
                GROUP BY technician_name 
                ORDER BY count DESC
            """)
            tech_rows = cursor.fetchall()
            tech_stats = {row['technician_name']: row['count'] for row in tech_rows}
            
            return jsonify({'fault_distribution': part_counts, 'tech_stats': tech_stats})
    except Exception as e:
        print(f"Błąd statystyk: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings/thresholds', methods=['POST'])
def update_thresholds():
    data = request.get_json()
    try:
        if 'drum_wear_percent' in data: db_manager.update_setting('drum_wear_percent', float(data['drum_wear_percent']))
        if 'roller_wear_percent' in data: db_manager.update_setting('roller_wear_percent', float(data['roller_wear_percent']))
        if 'paper_jams_count' in data: db_manager.update_setting('paper_jams_count', int(data['paper_jams_count']))
        if 'fuser_temperature' in data: db_manager.update_setting('fuser_temperature', float(data['fuser_temperature']))
        if 'confidence_threshold' in data:
            val = float(data['confidence_threshold'])
            if val > 1.0: val = val / 100.0
            db_manager.update_setting('confidence_threshold', val)
        return jsonify({'success': True, 'current_thresholds': ACTIVE_THRESHOLDS})
    except Exception as e: return jsonify({'error': str(e)}), 400

@app.route('/api/technicians', methods=['POST'])
def add_technician():
    data = request.get_json()
    if not all(k in data for k in ['name', 'vehicle_id', 'phone']): return jsonify({'error': 'Missing data'}), 400
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO technicians (name, vehicle_id, phone, status) VALUES (?, ?, ?, 'available')", (data['name'], data['vehicle_id'], data['phone']))
        tid = cursor.lastrowid
    return jsonify({'success': True, 'id': tid}), 201

@app.route('/api/technicians/<int:tech_id>', methods=['DELETE'])
def delete_technician(tech_id):
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM service_interventions WHERE technician_name = (SELECT name FROM technicians WHERE id = ?) AND status = 'assigned'", (tech_id,))
        if cursor.fetchone()[0] > 0: return jsonify({'error': 'Technik ma aktywne zadania'}), 400
        cursor.execute("DELETE FROM technicians WHERE id = ?", (tech_id,))
    return jsonify({'success': True}), 200

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_data():
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        # Downloading predictions along with the model and location
        cursor.execute("""
            SELECT p.*, pr.model_type, pr.location 
            FROM predictions p
            JOIN printers pr ON p.printer_id = pr.printer_id
            ORDER BY p.timestamp DESC LIMIT 20
        """)
        recent_preds = [dict(row) for row in cursor.fetchall()]
        
        for p in recent_preds:
            p['parts_needed'] = json.loads(p['parts_needed']) if p['parts_needed'] else []
            p['needs_maintenance'] = bool(p['needs_maintenance'])
            
        cursor.execute("SELECT count(*) FROM service_interventions WHERE status='pending'")
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM printers WHERE status='active'")
        active = cursor.fetchone()[0]
        
    # We pass the ENTIRE predictor.stats object ---
    # We combine the model statistics with the is_trained flag
    model_stats = predictor.stats.copy()
    model_stats['is_trained'] = predictor.is_trained
        
    return jsonify({
        'model_stats': model_stats,
        'prediction_stats': {'pending_interventions': pending},
        'data_stats': {'active_printers': active},
        'recent_predictions': recent_preds,
        'thresholds': ACTIVE_THRESHOLDS
    })

@app.route('/api/interventions', methods=['GET'])
def get_interventions():
    status = request.args.get('status', 'all')
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM service_interventions"
        args = []
        if status != 'all':
            query += " WHERE status = ?"
            args.append(status)
        query += " ORDER BY created_at DESC LIMIT 50"
        cursor.execute(query, args)
        return jsonify({'interventions': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/interventions/<int:iid>/assign', methods=['POST'])
def assign_intervention(iid):
    data = request.get_json()
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, vehicle_id FROM technicians WHERE id=?", (data.get('technician_id'),))
        tech = cursor.fetchone()
        if not tech: return jsonify({'error': 'Tech not found'}), 404
        cursor.execute("UPDATE service_interventions SET status='assigned', technician_name=?, vehicle_id=?, assigned_at=CURRENT_TIMESTAMP WHERE id=?", (tech['name'], tech['vehicle_id'], iid))
    return jsonify({'success': True})

@app.route('/api/interventions/<int:iid>/complete', methods=['POST'])
def complete_intervention(iid):
    data = request.get_json()
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE service_interventions SET status='completed', completed_at=CURRENT_TIMESTAMP, notes=? WHERE id=?", (data.get('notes',''), iid))
        
        # Clearing the history cache for this printer.
        cursor.execute("SELECT printer_id FROM service_interventions WHERE id=?", (iid,))
        row = cursor.fetchone()
        if row and row[0] in predictor.printer_history_cache: 
            del predictor.printer_history_cache[row[0]]
            
    return jsonify({'success': True})

@app.route('/api/technicians', methods=['GET'])
def get_technicians():
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM technicians")
        return jsonify({'technicians': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/printers', methods=['GET'])
def get_printers():
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM printers WHERE status='active'")
        return jsonify({'printers': [dict(row) for row in cursor.fetchall()]})

@app.route('/api/printers/<pid>/delete', methods=['POST'])
def delete_printer(pid):
    with db_manager.get_connection() as conn:
        conn.execute("UPDATE printers SET status='deleted' WHERE printer_id=?", (pid,))
    return jsonify({'success': True})

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

if __name__ == '__main__':
    print("🚀 Serwer uruchomiony: http://localhost:5000")
    os.makedirs(MODELS_DIR, exist_ok=True)
    app.run(host='0.0.0.0', port=5000)