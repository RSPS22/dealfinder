import os
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from docx import Document

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['LOI_FOLDER'] = 'generated_lois'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['LOI_FOLDER'], exist_ok=True)

properties_df = pd.DataFrame()

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    global properties_df
    if 'properties_df' not in globals() or properties_df.empty:
        total_props = 0
        loi_sent_count = 0
        high_potential_count = 0
        avg_offer = 0
    else:
        total_props = len(properties_df)
        loi_sent_count = properties_df['loi sent'].sum() if 'loi sent' in properties_df else 0
        high_potential_count = properties_df['high potential'].sum() if 'high potential' in properties_df else 0
        avg_offer = round(properties_df['offer price'].mean(), 2) if 'offer price' in properties_df else 0
    return render_template('dashboard.html', total=total_props, loi_count=loi_sent_count, high_count=high_potential_count, avg_offer=avg_offer)


@app.route('/upload', methods=['POST'])
def upload():
    global properties_df
    prop_file = request.files['propertyFile']
    comp_file = request.files['compsFile']
    business_name = request.form.get('businessName', '').strip()
    user_name = request.form.get('userName', '').strip()
    user_email = request.form.get('userEmail', '').strip()

    prop_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(prop_file.filename))
    comp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(comp_file.filename))
    prop_file.save(prop_path)
    comp_file.save(comp_path)

    properties_df = pd.read_csv(prop_path)
    comps_df = pd.read_csv(comp_path)

    properties_df.columns = [col.strip().lower() for col in properties_df.columns]
    comps_df.columns = [col.strip().lower() for col in comps_df.columns]

    rename_map = {
        'listing agent first name': 'agent first name',
        'listing agent last name': 'agent last name',
        'listing agent email': 'agent email',
        'listing agent phone': 'agent phone'
    }
    for k, v in rename_map.items():
        if k in properties_df.columns:
            properties_df[v] = properties_df[k]

    sqft_col = next((col for col in comps_df.columns if 'living' in col.lower() and ('sqft' in col.lower() or 'square feet' in col.lower())), None)
    price_col = next((col for col in comps_df.columns if any(key in col.lower() for key in ['sale', 'sold', 'last sale amount'])), None)

    if not sqft_col or not price_col:
        return "Missing required columns in comps file.", 400

    comps_df = comps_df[comps_df[sqft_col] > 0]
    comps_df['_clean_price'] = pd.to_numeric(comps_df[price_col].astype(str).str.replace(',', ''), errors='coerce')
    comps_df['_clean_sqft'] = pd.to_numeric(comps_df[sqft_col].astype(str).str.replace(',', ''), errors='coerce')
    comps_df['$/sqft'] = comps_df['_clean_price'] / comps_df['_clean_sqft']
    avg_psf = comps_df['$/sqft'].mean()

    prop_sqft_col = next((col for col in comps_df.columns if 'living' in col.lower() and ('sqft' in col.lower() or 'square feet' in col.lower())), None)
    if not prop_sqft_col:
        properties_df['arv'] = 0
    else:
        properties_df['arv'] = properties_df[prop_sqft_col] * avg_psf

    properties_df['offer price'] = properties_df.apply(
        lambda row: min(row['arv'] * 0.65, row['listing price'] * 0.95) if pd.notnull(row['arv']) and pd.notnull(row['listing price']) else 0,
        axis=1
    )

    properties_df['high potential'] = properties_df.apply(
        lambda row: row['offer price'] <= row['arv'] * 0.60 if pd.notnull(row['offer price']) and pd.notnull(row['arv']) else False,
        axis=1
    )

    properties_df['condition override'] = 'Medium'
    properties_df['loi sent'] = False
    properties_df['follow-up sent'] = False

    for i, row in properties_df.iterrows():
        row_id = str(row.get('id') or f"row_{i}")
        filename = f"LOI_{row_id}.docx"
        filepath = os.path.join(app.config['LOI_FOLDER'], filename)
        try:
            doc = Document()
            doc.add_heading("Letter of Intent", level=1)
            doc.add_paragraph(f"Property: {row.get('address', '')}")
            doc.add_paragraph(f"Offer Price: ${round(row.get('offer price', 0)):,.0f}")
            doc.add_paragraph("This offer is subject to inspection and contract.")
            doc.add_paragraph(f"Buyer: {business_name or '[Business Name]'}")
            doc.add_paragraph(f"Contact: {user_name or '[Your Name]'}")
            doc.add_paragraph(f"Email: {user_email or '[Your Email]'}")
            doc.add_paragraph("Phone: (555) 555-5555")
            doc.save(filepath)
            properties_df.at[i, 'loi file'] = filename
        except:
            properties_df.at[i, 'loi file'] = ""

    return jsonify(success=True)

@app.route('/data')
def data():
    global properties_df
    df = properties_df.copy()
    expected_cols = [
        'id', 'address', 'city', 'state', 'zip', 'listing price',
        'arv', 'offer price', 'high potential', 'condition override',
        'loi sent', 'follow-up sent', 'loi file',
        'agent first name', 'agent last name', 'agent email', 'agent phone'
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
    return df[expected_cols].rename(columns=lambda x: x.title()).to_dict(orient='records')

@app.route('/save_override', methods=['POST'])
def save_override():
    global properties_df
    data = request.json
    row_id = data['id']
    override = data['override']
    idx = properties_df[properties_df['id'] == row_id].index
    if not idx.empty:
        i = idx[0]
        properties_df.at[i, 'condition override'] = override
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/update_flags', methods=['POST'])
def update_flags():
    global properties_df
    data = request.json
    row_id = data['id']
    loi_sent = data['loiSent']
    followup_sent = data['followupSent']
    idx = properties_df[properties_df['id'] == row_id].index
    if not idx.empty:
        i = idx[0]
        properties_df.at[i, 'loi sent'] = loi_sent
        properties_df.at[i, 'follow-up sent'] = followup_sent
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/download_loi/<filename>')
def download_loi(filename):
    path = os.path.join(app.config['LOI_FOLDER'], filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True)