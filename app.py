import os
import csv
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from datetime import datetime
from docx import Document
import traceback

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['LOI_FOLDER'] = 'generated_lois'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['LOI_FOLDER'], exist_ok=True)

properties_df = pd.DataFrame()
comps_df = pd.DataFrame()
user_info = {"businessName": "", "userName": "", "userEmail": ""}

def clean_numeric(val):
    try:
        return float(str(val).replace('$', '').replace(',', '').strip())
    except:
        return None

def safe_str(val):
    try:
        return str(val) if pd.notna(val) else ''
    except:
        return ''

def log_activity(action, property_id='N/A', address='N/A', details=''):
    log_path = os.path.join(app.config['UPLOAD_FOLDER'], 'activity_log.csv')
    log_entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'action': action,
        'property_id': property_id,
        'address': address,
        'details': details
    }
    file_exists = os.path.isfile(log_path)
    with open(log_path, mode='a', newline='', encoding='utf-8') as log_file:
        writer = csv.DictWriter(log_file, fieldnames=log_entry.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(log_entry)

def generate_loi(row, folder):
    try:
        template_path = os.path.join('templates', 'Offer_Sheet_Template.docx')
        if not os.path.exists(template_path):
            return None
        doc = Document(template_path)
        full_address = f"{safe_str(row.get('Address'))}, {safe_str(row.get('City'))}, {safe_str(row.get('State'))} {safe_str(row.get('Zip'))}"
        buyer = user_info['businessName']
        userinfo = f"Name: {user_info['userName']}\nEmail: {user_info['userEmail']}"
        for p in doc.paragraphs:
            for run in p.runs:
                run.text = run.text.replace('{{address}}', full_address)
                run.text = run.text.replace('{{price}}', f"${float(row.get('Offer Price', 0)):,.0f}")
                run.text = run.text.replace('{{buyer}}', buyer)
                run.text = run.text.replace('{{date}}', datetime.today().strftime('%B %d, %Y'))
                run.text = run.text.replace('{{userinfo}}', userinfo)
        filename = f"LOI_{row['Id']}.docx"
        path = os.path.join(folder, filename)
        doc.save(path)
        return filename
    except Exception as e:
        print(f"[LOI ERROR] {e}")
        print(traceback.format_exc())
        return None

def calculate_arv_and_offer(properties, comps):
    results = []
    for _, prop in properties.iterrows():
        sqft = clean_numeric(prop.get('Living Square Feet'))
        zip_code = prop.get('Zip')
        subdivision = str(prop.get('Subdivision')).strip().lower()
        year = clean_numeric(prop.get('Year Built'))
        beds = clean_numeric(prop.get('Bedrooms'))
        baths = clean_numeric(prop.get('Bathrooms'))

        filtered = comps[(comps['Zip'] == zip_code) &
                         (comps['Living Square Feet'].between(sqft - 300, sqft + 300)) &
                         (comps['Year Built'].between(year - 10, year + 10))]

        def score(c):
            score = 1.0
            if str(c.get('Subdivision')).strip().lower() == subdivision:
                score += 0.25
            if abs(clean_numeric(c.get('Bedrooms')) - beds) < 0.5:
                score += 0.1
            if abs(clean_numeric(c.get('Bathrooms')) - baths) < 0.5:
                score += 0.1
            return score

        if not filtered.empty:
            filtered['Weight'] = filtered.apply(score, axis=1)
            filtered['Weight'] = filtered['Weight'].fillna(1)
            try:
                weighted_sum = (filtered['Last Sale Amount'] * filtered['Weight']).sum()
                total_weighted_sqft = (filtered['Living Square Feet'] * filtered['Weight']).sum()
                avg_price_sqft = weighted_sum / total_weighted_sqft if total_weighted_sqft else None
            except:
                avg_price_sqft = None
        else:
            avg_price_sqft = None

        if avg_price_sqft:
            arv = avg_price_sqft * sqft
            condition = str(prop.get('Condition Override', 'Medium')).lower()
            repair = sqft * (15 if 'light' in condition else 35 if 'medium' in condition else 55)
            offer = arv * 0.7 - repair
            results.append((round(arv), round(offer)))
        else:
            results.append((None, None))
    properties['ARV'] = [r[0] for r in results]
    properties['Offer Price'] = [r[1] for r in results]
    properties['High Potential'] = (properties['Offer Price'] < properties['Listing Price']) & (properties['Days on Market'] > 20)
    return properties

def process_uploaded_files(prop_path, comp_path):
    props = pd.read_csv(prop_path, encoding='utf-8', encoding_errors='replace')
    comps = pd.read_csv(comp_path, encoding='utf-8', encoding_errors='replace')
    for col in ['Living Square Feet', 'Year Built', 'Bedrooms', 'Bathrooms', 'Listing Price', 'Days on Market']:
        if col in props.columns:
            props[col] = props[col].apply(clean_numeric)
    for col in ['Living Square Feet', 'Year Built', 'Bedrooms', 'Bathrooms', 'Last Sale Amount']:
        if col in comps.columns:
            comps[col] = comps[col].apply(clean_numeric)
    return props, comps

@app.route('/upload', methods=['POST'])
def upload():
    global properties_df, comps_df, user_info
    try:
        user_info['businessName'] = request.form.get('businessName', '')
        user_info['userName'] = request.form.get('userName', '')
        user_info['userEmail'] = request.form.get('userEmail', '')
        prop_file = request.files.get('propertyFile')
        comp_file = request.files.get('compsFile')
        if not prop_file or not comp_file:
            return jsonify(success=False, message="Missing file")
        prop_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(prop_file.filename))
        comp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(comp_file.filename))
        prop_file.save(prop_path)
        comp_file.save(comp_path)
        properties_df, comps_df = process_uploaded_files(prop_path, comp_path)
        if 'Condition Override' not in properties_df.columns:
            properties_df['Condition Override'] = 'Medium'
        properties_df = calculate_arv_and_offer(properties_df, comps_df)
        for i, row in properties_df.iterrows():
            if pd.notna(row.get('ARV')) and pd.notna(row.get('Offer Price')):
                filename = generate_loi(row, app.config['LOI_FOLDER'])
                if filename:
                    properties_df.at[i, 'LOI File'] = filename
        print(f"[UPLOAD COMPLETE] {len(properties_df)} properties processed.")
        return jsonify(success=True)
    except Exception as e:
        print("[UPLOAD ERROR]", e)
        print(traceback.format_exc())
        return jsonify(success=False, message=str(e))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/data')
def data():
    return properties_df.fillna('').to_json(orient='records')

@app.route('/save_override', methods=['POST'])
def save_override():
    global properties_df
    data = request.json
    row_id = data['id']
    override = data['override']
    idx = properties_df[properties_df['Id'] == row_id].index
    if not idx.empty:
        i = idx[0]
        properties_df.at[i, 'Condition Override'] = override
        sqft = properties_df.at[i, 'Living Square Feet']
        arv = properties_df.at[i, 'ARV']
        if pd.notna(sqft) and pd.notna(arv):
            repair = sqft * (15 if 'light' in override.lower() else 35 if 'medium' in override.lower() else 55)
            offer = arv * 0.7 - repair
            properties_df.at[i, 'Offer Price'] = round(offer)
            filename = generate_loi(properties_df.loc[i], app.config['LOI_FOLDER'])
            if filename:
                properties_df.at[i, 'LOI File'] = filename
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/download_loi/<filename>')
def download_loi(filename):
    return send_file(os.path.join(app.config['LOI_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)


































































































































































































