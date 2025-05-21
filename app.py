import os
import pandas as pd
from flask import Flask, render_template, request, redirect, jsonify
from docx import Document

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
LOI_TEMPLATE_PATH = 'Offer_Sheet_Template.docx'
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
    try:
        prop_file = request.files.get('propertyFile')
        comps_file = request.files.get('compsFile')
        business_name = request.form.get('businessName', '')
        user_name = request.form.get('userName', '')
        user_email = request.form.get('userEmail', '')

        if not prop_file or not comps_file:
            return jsonify({'error': 'Missing files'}), 400

        prop_df = pd.read_csv(prop_file)
        comps_df = pd.read_csv(comps_file)

        if 'Listing Price' not in prop_df.columns or 'Living Square Feet' not in prop_df.columns:
            return jsonify({'error': 'Missing required columns in property file.'}), 400
        price_col = next((c for c in comps_df.columns if 'sold' in c.lower() and 'price' in c.lower()), None)
        if not price_col and 'Last Sale Amount' in comps_df.columns:
            price_col = 'Last Sale Amount'
        sqft_col = next((c for c in comps_df.columns if 'living' in c.lower() or 'sqft' in c.lower()), None)
        if not sqft_col and 'Living Square Feet' in comps_df.columns:
            sqft_col = 'Living Square Feet'
        if not price_col or not sqft_col:
            return jsonify({'error': 'Missing required columns in comps file.'}), 400

        comps_df[price_col] = comps_df[price_col].replace('[\$,]', '', regex=True).astype(float)
        comps_df[sqft_col] = comps_df[sqft_col].replace('[\$,]', '', regex=True).astype(float)
        comps_df['$/sqft'] = comps_df[price_col] / comps_df[sqft_col]
        avg_price_per_sqft = comps_df['$/sqft'].mean()

        prop_df['Living Square Feet'] = prop_df['Living Square Feet'].replace('[\$,]', '', regex=True).astype(float)
        prop_df['ARV'] = prop_df['Living Square Feet'] * avg_price_per_sqft
        prop_df['Offer Price'] = (prop_df['ARV'] * 0.60).round(-2)
        prop_df['High Potential'] = (prop_df['Offer Price'] / prop_df['ARV']) <= 0.55

        loi_files = []
        for idx, row in prop_df.iterrows():
            try:
                doc = Document(LOI_TEMPLATE_PATH)
                for para in doc.paragraphs:
                    if '{property_address}' in para.text:
                        para.text = para.text.replace('{property_address}', str(row.get('Address', '')))
                    if '{offer_price}' in para.text:
                        para.text = para.text.replace('{offer_price}', f"${row['Offer Price']:,.0f}")
                    if '{business_name}' in para.text:
                        para.text = para.text.replace('{business_name}', business_name)
                    if '{user_name}' in para.text:
                        para.text = para.text.replace('{user_name}', user_name)
                    if '{user_email}' in para.text:
                        para.text = para.text.replace('{user_email}', user_email)

                loi_filename = f"LOI_{idx}.docx"
                filepath = os.path.join(UPLOAD_FOLDER, loi_filename)
                doc.save(filepath)
                loi_files.append(loi_filename)
            except Exception as e:
                loi_files.append('Error')

        prop_df['LOI File'] = loi_files
        prop_df['LOI Sent'] = False
        prop_df['Follow-Up Sent'] = False

        prop_df['ARV'] = prop_df['ARV'].apply(lambda x: f"${x:,.0f}")
        prop_df['Offer Price'] = prop_df['Offer Price'].apply(lambda x: f"${x:,.0f}")
        properties_df = prop_df

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))