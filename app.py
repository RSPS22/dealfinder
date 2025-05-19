import os
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from docx import Document
from datetime import datetime
import traceback

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['LOI_FOLDER'] = 'generated_lois'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['LOI_FOLDER'], exist_ok=True)

properties_df = pd.DataFrame()
user_info = {"businessName": "", "userName": "", "userEmail": ""}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    global properties_df, user_info
    try:
        prop_file = request.files.get('propertyFile')
        comp_file = request.files.get('compsFile')
        user_info['businessName'] = request.form.get('businessName', '')
        user_info['userName'] = request.form.get('userName', '')
        user_info['userEmail'] = request.form.get('userEmail', '')
        if not prop_file or not comp_file:
            print("Missing property or comps file in upload.")
            return jsonify(success=False, message="Missing files.")

        prop_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(prop_file.filename))
        prop_file.save(prop_path)
        properties_df = pd.read_csv(prop_path)

        if 'Id' not in properties_df.columns or 'Listing Price' not in properties_df.columns:
            print("Missing 'Id' or 'Listing Price' column in uploaded file.")
            return jsonify(success=False, message="Missing required columns.")

        if 'Condition Override' not in properties_df.columns:
            properties_df['Condition Override'] = 'Medium'
        if 'LOI Sent' not in properties_df.columns:
            properties_df['LOI Sent'] = False
        if 'Follow-Up Sent' not in properties_df.columns:
            properties_df['Follow-Up Sent'] = False

        properties_df['ARV'] = properties_df['Listing Price'] * 1.1
        properties_df['Offer Price'] = properties_df.apply(
            lambda row: min(row['ARV'] * 0.65, row['Listing Price'] * 0.95), axis=1

def is_high_potential(row):
    if pd.notnull(row['Offer Price']) and pd.notnull(row['Listing Price']):
        return row['Offer Price'] < row['Listing Price'] * 0.8
    return False

        properties_df['High Potential'] = properties_df.apply(is_high_potential, axis=1)
            lambda row: row['Offer Price'] < row['Listing Price'] * 0.8,
            axis=1

        for i, row in properties_df.iterrows():
            filename = f"LOI_{row['Id']}.docx"
            filepath = os.path.join(app.config['LOI_FOLDER'], filename)
            doc = Document()
            doc.add_paragraph(f"LOI for: {row.get('Address', '')}")
            doc.save(filepath)
            properties_df.at[i, 'LOI File'] = filename

        return jsonify(success=True)
    except Exception as e:
        print("UPLOAD ERROR:", e)
        traceback.print_exc()
        return jsonify(success=False, message=str(e))

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