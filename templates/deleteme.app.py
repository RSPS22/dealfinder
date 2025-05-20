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
    return render_template('dashboard.html')

@app.route('/upload', methods=['POST'])
def upload():
    global properties_df
    prop_file = request.files['propertyFile']
    comp_file = request.files['compsFile']
    prop_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(prop_file.filename))
    comp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(comp_file.filename))
    prop_file.save(prop_path)
    comp_file.save(comp_path)

    properties_df = pd.read_csv(prop_path)
    comps_df = pd.read_csv(comp_path)

    comps_df = comps_df[comps_df['Living Square Feet'] > 0]
    comps_df['$/Sqft'] = comps_df['Last Sale Amount'] / comps_df['Living Square Feet']
    avg_psf = comps_df['$/Sqft'].mean()

    properties_df['ARV'] = properties_df['Living Square Feet'] * avg_psf
    properties_df['Offer Price'] = properties_df.apply(
        lambda row: min(row['ARV'] * 0.65, row['Listing Price'] * 0.95) if pd.notnull(row['ARV']) and pd.notnull(row['Listing Price']) else 0,
        axis=1
    )
    properties_df['High Potential'] = properties_df.apply(
        lambda row: row['Offer Price'] <= row['ARV'] * 0.6 if pd.notnull(row['Offer Price']) and pd.notnull(row['ARV']) else False,
        axis=1
    )

    properties_df['Condition Override'] = 'Medium'
    properties_df['LOI Sent'] = False
    properties_df['Follow-Up Sent'] = False

    for i, row in properties_df.iterrows():
        filename = f"LOI_{row['Id']}.docx"
        filepath = os.path.join(app.config['LOI_FOLDER'], filename)
        doc = Document()
        doc.add_paragraph(f"LOI for: {row.get('Address', '')}")
        doc.save(filepath)
        properties_df.at[i, 'LOI File'] = filename

    return jsonify(success=True)

@app.route('/data')
def data():
    global properties_df
    df = properties_df.copy()
    required = ['LOI Sent', 'Follow-Up Sent', 'Condition Override', 'LOI File', 'ARV', 'Offer Price', 'High Potential']
    for col in required:
        if col not in df.columns:
            if col in ['LOI Sent', 'Follow-Up Sent']:
                df[col] = False
            elif col == 'Condition Override':
                df[col] = 'Medium'
            else:
                df[col] = ''
    return df.to_json(orient='records')

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
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/update_flags', methods=['POST'])
def update_flags():
    global properties_df
    data = request.json
    row_id = data['id']
    loi_sent = data['loiSent']
    followup_sent = data['followupSent']
    idx = properties_df[properties_df['Id'] == row_id].index
    if not idx.empty:
        i = idx[0]
        properties_df.at[i, 'LOI Sent'] = loi_sent
        properties_df.at[i, 'Follow-Up Sent'] = followup_sent
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/download_loi/<filename>')
def download_loi(filename):
    return send_file(os.path.join(app.config['LOI_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
