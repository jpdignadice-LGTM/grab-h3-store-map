import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster
import h3
import pandas as pd

st.set_page_config(
    page_title="Grab Store Cannibalization Map", 
    layout="wide", 
    page_icon="⬡"
)

# Configuration URL
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSJGD3mdZMoxEKcUAi96ci1tpgA64q7b3IcKAXSpescfRa8e3eulvKrtHBYBXLvY8yRThoFuO0Dc6Ag/pub?output=csv"
H3_RESOLUTION = 7

def clean_numeric(val):
    """Safely converts currency/text fields to numeric values without crashing."""
    if pd.isna(val):
        return 0.0
    clean_str = str(val).replace("₱", "").replace("$", "").replace(",", "").strip()
    try:
        return float(clean_str)
    except ValueError:
        return 0.0

@st.cache_data(ttl=86400)
def fetch_and_process_data(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()
    return df

st.title("⬡ Grab Market Coverage & Cannibalization Risk Map")

with st.sidebar:
    st.header("🔄 Control Panel")
    if st.button("🔴 Force Refresh Live Data", use_container_width=True):
        st.cache_data.clear()
        st.success("Cache cleared! Re-fetching Google Sheets...")
        st.rerun()
        
    st.markdown("---")
    st.markdown("""
    **Legend Indicators:**
    * 🟢 **ACTIVE** Store Pins
    * 🔵 **Existing** Store Pins
    * 🟡 **ONBOARDING** Store Pins
    * 🟥 **Red Hexagons:** Cannibalization Risk Zone (2+ Stores)
    * 🟪 **Gray Hexagons:** Isolated Territory Zone (1 Store)
    """)

try:
    raw_df = fetch_and_process_data(SHEET_CSV_URL)
    
    required_columns = ["LATITUDE", "LONGITUDE", "Store Name", "Store Code", "GRAB STATUS"]
    missing = [col for col in required_columns if col not in raw_df.columns]
    
    if missing:
        st.error(f"❌ Column Header Error: Missing columns: {missing}")
    else:
        # Initialize map centered directly over Manila
        m = folium.Map(location=[14.5995, 120.9842], zoom_start=11, tiles=None)
        folium.TileLayer('CartoDB dark_matter', name="🌙 Dark Mode (Default)").add_to(m)
        folium.TileLayer('OpenStreetMap', name="☀️ Light Mode").add_to(m)

        # High-performance marker clustering container
        marker_cluster = MarkerCluster(name="📍 Clustered Store Locations").add_to(m)
        layer_h3_grid = folium.FeatureGroup(name="⬡ Cannibalization Risk Grid", overlay=True)

        h3_clusters = {}

        for index, row in raw_df.iterrows():
            try:
                lat = clean_numeric(row["LATITUDE"])
                lon = clean_numeric(row["LONGITUDE"])

                # Filter coordinates to avoid world-map rendering loops
                if lat == 0.0 or lon == 0.0 or pd.isna(lat) or pd.isna(lon):
                    continue
                if not (13.0 <= lat <= 16.0 and 119.0 <= lon <= 123.0):
                    continue

                sales_col = "Sales" if "Sales" in raw_df.columns else ("Net Sales" if "Net Sales" in raw_df.columns else None)
                
                spd_val = clean_numeric(row.get("SPD", 0))
                sales_val = clean_numeric(row.get(sales_col, 0)) if sales_col else 0.0
                apc_val = clean_numeric(row.get("APC", 0))

                h3_address = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)

                if h3_address not in h3_clusters:
                    h3_clusters[h3_address] = {"count": 0, "total_spd": 0.0, "total_sales": 0.0, "total_apc": 0.0, "store_details": []}

                h3_clusters[h3_address]["count"] += 1
                h3_clusters[h3_address]["total_spd"] += spd_val
                h3_clusters[h3_address]["total_sales"] += sales_val
                h3_clusters[h3_address]["total_apc"] += apc_val
                h3_clusters[h3_address]["store_details"].append({
                    "name": row['Store Name'], "code": row['Store Code'], "status": str(row["GRAB STATUS"]).strip()
                })

                popup_html = f"""
                <div style="font-family: Arial, sans-serif; min-width: 200px; font-size: 12px; color: #2c3e50;">
                    <h4 style="margin:0 0 5px 0; color:#2980b9;"><b>{row['Store Name']}</b></h4>
                    <p style="margin:2px 0;"><b>Code:</b> {row['Store Code']}</p>
                    <hr style="margin: 5px 0; border-top: 1px solid #ddd;">
                    <table style="width:100%;">
                        <tr><td><b>SPD:</b></td><td style="text-align:right;">{spd_val:,.0f}</td></tr>
                        <tr><td><b>Net Sales:</b></td><td style="text-align:right; color:#27ae60; font-weight:bold;">₱{sales_val:,.0f}</td></tr>
                        <tr><td><b>APC:</b></td><td style="text-align:right;">₱{apc_val:,.2f}</td></tr>
                    </table>
                </div>
                """

                status = str(row["GRAB STATUS"]).strip().upper()
                if status == "ACTIVE":
                    pin_color = "green"
                elif status == "EXISTING STORE":
                    pin_color = "blue"
                elif status == "ONBOARDING":
                    pin_color = "orange"
                else:
                    pin_color = "purple"

                # Add pins to the high-speed cluster instead of raw map layers
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_html, max_width=320),
                    tooltip=str(row['Store Name']),
                    icon=folium.Icon(color=pin_color, icon="shopping-cart", prefix="fa"),
                ).add_to(marker_cluster)
                
            except Exception:
                continue

        # Build Polygons
        for h3_idx, cluster in h3_clusters.items():
            boundary_vertices = h3.cell_to_boundary(h3_idx)
            avg_apc = cluster["total_apc"] / cluster["count"] if cluster["count"] > 0 else 0
            is_competing = cluster["count"] > 1
            
            if is_competing:
                hex_line_color, hex_fill_color, hex_fill_opacity = "#e74c3c", "#c0392b", 0.3
                alert_badge = '<span style="background:#e74c3c; color:white; padding:3px 8px; border-radius:4px; font-weight:bold; font-size:11px;">⚠️ HIGH CANNIBALIZATION RISK</span>'
            else:
                hex_line_color, hex_fill_color, hex_fill_opacity = "#7f8c8d", "#95a5a6", 0.02
                alert_badge = '<span style="background:#27ae60; color:white; padding:3px 8px; border-radius:4px; font-weight:bold; font-size:11px;">✅ SAFE ZONE</span>'

            stores_list_items = "".join([f"<li style='margin-bottom:4px;'><b>[{s['status']}]</b> {s['name']} <small style='color:#7f8c8d;'>({s['code']})</small></li>" for s in cluster["store_details"]])

            hex_popup_html = f"""
            <div style="font-family: Arial, sans-serif; min-width: 280px; font-size: 12px; color: #2c3e50;">
                <div style="margin-bottom: 8px;">{alert_badge}</div>
                <p style="margin:4px 0;"><b>H3 Index:</b> <code>{h3_idx}</code></p>
                <p style="margin:4px 0;"><b>Total Stores:</b> <b>{cluster['count']}</b></p>
                <div style="margin-top:8px; background:#f8f9fa; padding:8px; border: 1px solid #dee2e6; border-radius:4px;">
                    <table style="width:100%; font-size:12px; border-collapse:collapse;">
                        <tr style="border-bottom:1px solid #eee;"><td style="padding:2px 0;">Combined SPD:</td><td style="text-align:right; font-weight:bold;">{cluster['total_spd']:,.0f}</td></tr>
                        <tr style="border-bottom:1px solid #eee;"><td style="padding:2px 0;">Combined Net Sales:</td><td style="text-align:right; font-weight:bold; color:#27ae60;">₱{cluster['total_sales']:,.0f}</td></tr>
                        <tr><td style="padding:2px 0;">Average APC:</td><td style="text-align:right; font-weight:bold; color:#2980b9;">₱{avg_apc:,.2f}</td></tr>
                    </table>
                </div>
                <p style="margin:10px 0 4px 0; font-weight:bold;">Breakdown:</p>
                <ul style="margin:0; padding-left:16px; max-height:120px; overflow-y:auto;">{stores_list_items}</ul>
            </div>
            """

            folium.Polygon(
                locations=boundary_vertices,
                popup=folium.Popup(hex_popup_html, max_width=360),
                tooltip=f"Zone {h3_idx}",
                color=hex_line_color,
                weight=1.5 if is_competing else 1,
                fill=True,
                fill_color=hex_fill_color,
                fill_opacity=hex_fill_opacity,
            ).add_to(layer_h3_grid)

        layer_h3_grid.add_to(m)
        folium.LayerControl(collapsed=False).add_to(m)

        # Render step using streamlined parameters
        st_folium(m, width="100%", height=710, use_container_width=True, returned_objects=[])

except Exception as e:
    st.error(f"⚠️ App error: {e}")
