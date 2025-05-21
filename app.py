import os
from flask import Flask, render_template, request, redirect, send_file
import pandas as pd
from docx import Document

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

properties_df = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    global properties_df
    return render_template('dashboard.html', properties=properties_df.to_dict(orient='records') if properties_df is not None else [])

@app.route('/upload', methods=['POST'])
def upload():
    global properties_df
    prop_file = request.files.get('propertyFile')
    comps_file = request.files.get('compsFile')
    if prop_file and comps_file:
        prop_path = os.path.join(UPLOAD_FOLDER, prop_file.filename)
        comp_path = os.path.join(UPLOAD_FOLDER, comps_file.filename)
        prop_file.save(prop_path)
        comps_file.save(comp_path)
        properties_df = pd.read_csv(prop_path)
        comps_df = pd.read_csv(comp_path)

        if 'Listing Price' in properties_df.columns and 'Living Square Feet' in properties_df.columns:
            properties_df['ARV'] = properties_df['Listing Price']
            properties_df['Offer Price'] = properties_df['ARV'] * 0.60
            properties_df['High Potential'] = properties_df['Offer Price'] <= properties_df['ARV'] * 0.55

        return redirect('/')
    return "Missing files", 400

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))