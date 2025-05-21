from flask import Flask, request, render_template, jsonify
import pandas as pd
import os
from docx import Document

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    try:
        prop_file = request.files['propertyFile']
        comps_file = request.files['compsFile']
        business_name = request.form.get('businessName', '')
        user_name = request.form.get('userName', '')
        user_email = request.form.get('userEmail', '')

        prop_df = pd.read_csv(prop_file)
        comps_df = pd.read_csv(comps_file)

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
        prop_df['Offer Price'] = prop_df['ARV'] * 0.6
        prop_df['High Potential'] = prop_df['Offer Price'] <= prop_df['ARV'] * 0.55
        prop_df['LOI Sent'] = False
        prop_df['Follow-Up Sent'] = False

        prop_df['ARV'] = prop_df['ARV'].apply(lambda x: f"${x:,.0f}")
        prop_df['Offer Price'] = prop_df['Offer Price'].apply(lambda x: f"${x:,.0f}")

        properties_df = prop_df
        properties = properties_df.to_dict(orient='records')

        return render_template('dashboard.html', properties=properties, business_name=business_name, user_name=user_name, user_email=user_email)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
