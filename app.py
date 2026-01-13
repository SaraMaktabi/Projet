import streamlit as st
import re
from neo4j import GraphDatabase
from pyvis.network import Network
import streamlit.components.v1 as components

# ================= CONFIG =================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "12345678"
NEO4J_DB = "music-recommendation"

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# ================= UTILS =================
def clean_text(text, max_len=50):
    if not text:
        return "—"
    text = re.sub(r"[\n\r\t]+", " ", str(text))
    text = re.sub(r"[\"'`;]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_len else text[:max_len] + "…"

def clean_list(values):
    return sorted(set(clean_text(v) for v in values if v))

# ================= DATABASE =================
def get_all_artists():
    q = """
    MATCH (a:Artist)
    WHERE a.artist_name IS NOT NULL
    RETURN DISTINCT a.artist_name AS name
    ORDER BY name
    """
    with driver.session(database=NEO4J_DB) as s:
        return [r["name"] for r in s.run(q)]

def get_all_genres():
    q = """
    MATCH (g:Genre)
    WHERE g.genre_name IS NOT NULL
    RETURN DISTINCT g.genre_name AS name
    ORDER BY name
    """
    with driver.session(database=NEO4J_DB) as s:
        return [r["name"] for r in s.run(q)]

def get_tracks(artist_filter=None, genre_filter=None, min_popularity=0, max_popularity=100):
    conditions = ["t.track_name IS NOT NULL"]
    
    if min_popularity > 0 or max_popularity < 100:
        conditions.append(f"t.popularity >= {min_popularity} AND t.popularity <= {max_popularity}")
    
    optional_match = []
    where_clauses = []
    
    if artist_filter and artist_filter != "Tous les artistes":
        optional_match.append("OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)")
        where_clauses.append("a.artist_name = $artist")
    
    if genre_filter and genre_filter != "Tous les genres":
        optional_match.append("OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)")
        where_clauses.append("g.genre_name = $genre")
    
    where_str = " AND ".join(conditions + where_clauses) if (conditions or where_clauses) else ""
    
    q = f"""
    MATCH (t:Track)
    {' '.join(optional_match)}
    WHERE {where_str}
    RETURN DISTINCT t.track_name AS name
    ORDER BY name
    """
    
    params = {}
    if artist_filter and artist_filter != "Tous les artistes":
        params["artist"] = artist_filter
    if genre_filter and genre_filter != "Tous les genres":
        params["genre"] = genre_filter
    
    with driver.session(database=NEO4J_DB) as s:
        return [r["name"] for r in s.run(q, **params)]

def get_track_info(track):
    q = """
    MATCH (t:Track {track_name:$name})
    OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)
    OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)
    RETURN
      t.track_name AS track,
      coalesce(t.popularity,0) AS popularity,
      coalesce(t.energy,0.0) AS energy,
      coalesce(t.valence,0.0) AS valence,
      coalesce(t.danceability,0.0) AS danceability,
      coalesce(t.acousticness,0.0) AS acousticness,
      coalesce(t.instrumentalness,0.0) AS instrumentalness,
      coalesce(t.liveness,0.0) AS liveness,
      coalesce(t.speechiness,0.0) AS speechiness,
      collect(DISTINCT a.artist_name) AS artists,
      collect(DISTINCT g.genre_name) AS genres
    """
    with driver.session(database=NEO4J_DB) as s:
        return s.run(q, name=track).single()

def get_recommendations(track):
    q = """
    MATCH (t:Track {track_name:$name})-[:SIMILAR_TO]->(r:Track)
    OPTIONAL MATCH (r)-[:PERFORMED_BY]->(a:Artist)
    RETURN r.track_name AS track,
           r.popularity AS popularity,
           r.energy AS energy,
           r.valence AS valence,
           collect(DISTINCT a.artist_name) AS artists
    ORDER BY popularity DESC
    LIMIT 5
    """
    with driver.session(database=NEO4J_DB) as s:
        return list(s.run(q, name=track))

# ================= GRAPH =================
def render_graph(track):
    q = """
    MATCH (t:Track {track_name:$name})
    OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)
    OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)
    OPTIONAL MATCH (t)-[:SIMILAR_TO]->(s:Track)
    RETURN
      collect(DISTINCT a.artist_name) AS artists,
      collect(DISTINCT g.genre_name) AS genres,
      collect(DISTINCT s.track_name) AS similars
    """
    with driver.session(database=NEO4J_DB) as s:
        r = s.run(q, name=track).single()

    net = Network(
        height="620px",
        width="100%",
        bgcolor="#020617",
        font_color="white",
        directed=True
    )

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -26000,
          "springLength": 160
        }
      },
      "edges": {
        "arrows": { "to": { "enabled": true } },
        "font": { "size": 14 }
      },
      "interaction": {
        "zoomView": true,
        "dragView": true
      }
    }
    """)

    net.add_node(track, label="♪ " + clean_text(track),
                 shape="star", size=42, color="#2563eb", title="Chanson sélectionnée")

    for a in r["artists"]:
        net.add_node(a, label="♫ " + clean_text(a),
                     shape="circle", size=30, color="#22c55e", title="Artiste")
        net.add_edge(track, a, label="PERFORMED_BY", width=2)

    for g in r["genres"]:
        net.add_node(g, label="♬ " + clean_text(g),
                     shape="box", size=24, color="#a855f7", title="Genre")
        net.add_edge(track, g, label="IN_GENRE", width=2)

    for s in r["similars"]:
        net.add_node(s, label="♪ " + clean_text(s),
                     shape="dot", size=26, color="#38bdf8", title="Chanson similaire")
        net.add_edge(track, s, label="SIMILAR_TO", width=3)

    net.save_graph("graph.html")
    with open("graph.html", "r", encoding="utf-8") as f:
        components.html(f.read(), height=650, scrolling=True)

# ================= UI =================
st.set_page_config("Music Recommendation System", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css');

* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

body {
    background: 
        linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(30, 41, 59, 0.9) 50%, rgba(51, 65, 85, 0.85) 100%),
        url('https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1920&q=80') center/cover no-repeat fixed;
}

.main {
    background: transparent;
}

.stApp {
    background: 
        linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(30, 41, 59, 0.9) 50%, rgba(51, 65, 85, 0.85) 100%),
        url('https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1920&q=80') center/cover no-repeat fixed;
}

.card {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    padding: 28px;
    border-radius: 20px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), 
                0 0 0 1px rgba(255, 255, 255, 0.1) inset;
    color: #f1f5f9;
    margin-bottom: 24px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeInUp 0.6s ease-out;
}

.card:hover {
    transform: translateY(-4px) scale(1.01);
    box-shadow: 0 16px 48px rgba(59, 130, 246, 0.4), 
                0 0 0 1px rgba(59, 130, 246, 0.3) inset;
    border-color: rgba(59, 130, 246, 0.4);
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

@keyframes glow {
    0%, 100% { box-shadow: 0 0 20px rgba(59, 130, 246, 0.3); }
    50% { box-shadow: 0 0 40px rgba(59, 130, 246, 0.6), 0 0 60px rgba(139, 92, 246, 0.4); }
}

.filter-card {
    background: rgba(59, 130, 246, 0.1);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    padding: 32px;
    border-radius: 24px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3),
                0 0 0 1px rgba(59, 130, 246, 0.2) inset;
    margin-bottom: 32px;
    border: 1px solid rgba(59, 130, 246, 0.3);
    animation: fadeInUp 0.5s ease-out;
    transition: all 0.4s ease;
}

.filter-card:hover {
    box-shadow: 0 12px 48px rgba(59, 130, 246, 0.4);
    border-color: rgba(59, 130, 246, 0.5);
}

.title-header {
    background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 50%, #c084fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 3.5em;
    font-weight: 300;
    text-align: center;
    margin-bottom: 16px;
    letter-spacing: -0.02em;
    animation: fadeInUp 0.8s ease-out, pulse 3s ease-in-out infinite;
}

.subtitle {
    text-align: center;
    color: #94a3b8;
    font-size: 1.15em;
    margin-bottom: 40px;
    font-weight: 500;
    animation: fadeInUp 1s ease-out;
}

.sub { 
    color: #94a3b8;
    font-size: 0.95em;
    font-weight: 500;
}

.scroll { 
    max-height: 380px; 
    overflow-y: auto;
    padding-right: 10px;
}

.scroll::-webkit-scrollbar {
    width: 10px;
}

.scroll::-webkit-scrollbar-track {
    background: rgba(30, 41, 59, 0.5);
    border-radius: 10px;
}

.scroll::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border-radius: 10px;
    border: 2px solid rgba(30, 41, 59, 0.5);
}

.scroll::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
}

.icon-title {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
    color: #ffffff !important;
    font-weight: 300 !important;
    font-size: 1.3em;
    animation: fadeInUp 0.7s ease-out;
}

.icon-title i {
    color: #ffffff !important;
    font-size: 1.1em;
    animation: pulse 2s ease-in-out infinite;
}

.metric-card {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    padding: 28px;
    border-radius: 20px;
    border: 2px solid rgba(59,130,246,0.3);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    text-align: center;
    position: relative;
    overflow: hidden;
    animation: fadeInUp 0.6s ease-out;
}

.metric-card::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(59, 130, 246, 0.1) 0%, transparent 70%);
    opacity: 0;
    transition: opacity 0.4s ease;
}

.metric-card:hover::before {
    opacity: 1;
}

.metric-card:hover {
    transform: translateY(-8px) scale(1.05);
    box-shadow: 0 16px 48px rgba(59,130,246,0.4), 0 0 0 1px rgba(59,130,246,0.5) inset;
    border-color: rgba(59,130,246,0.6);
}

.metric-icon {
    font-size: 3em;
    margin-bottom: 16px;
    display: block;
    animation: pulse 2s ease-in-out infinite;
    filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.3));
}

.metric-label {
    font-size: 0.85em;
    color: #94a3b8;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 12px;
}

.metric-value {
    font-size: 2.8em;
    font-weight: 900;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
}

.feature-bar {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(15px);
    -webkit-backdrop-filter: blur(15px);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 12px;
    border: 1px solid rgba(59,130,246,0.2);
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeInUp 0.6s ease-out;
}

.feature-bar:hover {
    transform: translateY(-4px) scale(1.03);
    box-shadow: 0 8px 24px rgba(59,130,246,0.3);
    border-color: rgba(59,130,246,0.5);
    background: rgba(255, 255, 255, 0.08);
}

.feature-icon {
    font-size: 1.8em;
    color: #60a5fa;
    margin-bottom: 12px;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3));
}

.feature-label {
    font-size: 0.8em;
    color: #cbd5e1;
    font-weight: 700;
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.feature-value {
    font-size: 1.4em;
    font-weight: 800;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-top: 10px;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
    color: #cbd5e1;
    font-weight: 500;
    padding: 8px;
    border-radius: 8px;
    transition: all 0.3s ease;
}

.legend-item:hover {
    background: rgba(59, 130, 246, 0.1);
    transform: translateX(4px);
}

.legend-icon {
    width: 35px;
    text-align: center;
    font-size: 1.3em;
}

div[data-testid="stMetricValue"] {
    font-size: 1.8em;
    font-weight: 700;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

h2, h3, h4 {
    color: #ffffff !important;
    font-weight: 300 !important;
}

h2 {
    font-size: 1.8em;
}

h3 {
    font-size: 1.4em;
}

h4 {
    font-size: 1.2em;
}

/* Styles pour les selectbox et inputs */
div[data-baseweb="select"] > div {
    background: rgba(30, 41, 59, 0.6) !important;
    backdrop-filter: blur(10px) !important;
    -webkit-backdrop-filter: blur(10px) !important;
    border: 2px solid rgba(59,130,246,0.4) !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3) !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    color: #f1f5f9 !important;
}

div[data-baseweb="select"]:hover > div {
    border-color: rgba(59,130,246,0.7) !important;
    box-shadow: 0 6px 20px rgba(59,130,246,0.3) !important;
    background: rgba(30, 41, 59, 0.8) !important;
}

div[data-baseweb="select"] [role="option"] {
    color: #1e293b !important;
}

input {
    color: #f1f5f9 !important;
}

/* Style pour le slider */
div[data-testid="stSlider"] > div > div > div {
    background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899) !important;
    height: 6px !important;
    border-radius: 10px !important;
}

div[data-testid="stSlider"] [role="slider"] {
    background: linear-gradient(135deg, #60a5fa, #a78bfa) !important;
    border: 4px solid rgba(255, 255, 255, 0.9) !important;
    box-shadow: 0 4px 16px rgba(59,130,246,0.5), 0 0 20px rgba(139, 92, 246, 0.3) !important;
    width: 24px !important;
    height: 24px !important;
    transition: all 0.3s ease !important;
}

div[data-testid="stSlider"] [role="slider"]:hover {
    transform: scale(1.2) !important;
    box-shadow: 0 6px 24px rgba(59,130,246,0.6), 0 0 30px rgba(139, 92, 246, 0.5) !important;
}

/* Valeurs du slider */
div[data-testid="stSlider"] [data-testid="stTickBarMin"],
div[data-testid="stSlider"] [data-testid="stTickBarMax"],
div[data-testid="stSlider"] div[data-baseweb="slider"] > div:last-child {
    color: #cbd5e1 !important;
    font-weight: 500 !important;
}

div[data-testid="stSlider"] label {
    color: #f1f5f9 !important;
}

.filter-label {
    display: flex;
    align-items: center;
    gap: 10px;
    color: #ffffff !important;
    font-weight: 700 !important;
    font-size: 1.05em;
    margin-bottom: 12px;
    padding: 12px 16px;
    background: rgba(59, 130, 246, 0.15);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border-radius: 12px;
    border-left: 4px solid #60a5fa;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    transition: all 0.3s ease;
}

.filter-label:hover {
    background: rgba(59, 130, 246, 0.25);
    transform: translateX(4px);
    border-left-color: #a78bfa;
}

.search-section {
    background: rgba(139, 92, 246, 0.1);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    padding: 28px;
    border-radius: 20px;
    border: 2px solid rgba(139,92,246,0.3);
    box-shadow: 0 8px 32px rgba(139,92,246,0.2), 
                0 0 0 1px rgba(139,92,246,0.1) inset;
    margin-bottom: 32px;
    animation: fadeInUp 0.6s ease-out, glow 3s ease-in-out infinite;
    transition: all 0.4s ease;
}

.search-section:hover {
    box-shadow: 0 12px 48px rgba(139,92,246,0.3);
    border-color: rgba(139,92,246,0.5);
}

.search-label {
    display: flex;
    align-items: center;
    gap: 12px;
    color: #ffffff !important;
    font-weight: 700 !important;
    font-size: 1.2em;
    margin-bottom: 16px;
}

.search-label i {
    color: #a78bfa;
    font-size: 1.3em;
    animation: pulse 2s ease-in-out infinite;
}

.results-badge {
    background: linear-gradient(135deg, #8b5cf6, #ec4899);
    color: white;
    padding: 6px 16px;
    border-radius: 24px;
    font-size: 0.8em;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4);
    letter-spacing: 0.5px;
    animation: pulse 2s ease-in-out infinite;
}

/* Styles pour les tabs */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(30, 41, 59, 0.6);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-bottom: 2px solid rgba(59,130,246,0.3);
    gap: 16px;
    padding: 16px;
    border-radius: 16px 16px 0 0;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.stTabs [data-baseweb="tab"] {
    background: rgba(59,130,246,0.1);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 2px solid rgba(59,130,246,0.3);
    border-radius: 12px;
    padding: 14px 28px;
    color: #cbd5e1;
    font-weight: 700;
    font-size: 1.05em;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.stTabs [data-baseweb="tab"]:hover {
    background: rgba(59,130,246,0.2);
    border-color: rgba(59,130,246,0.5);
    color: #f1f5f9;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(59,130,246,0.3);
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899) !important;
    color: white !important;
    border-color: transparent !important;
    box-shadow: 0 8px 24px rgba(59,130,246,0.4), 0 0 40px rgba(139, 92, 246, 0.3) !important;
    transform: translateY(-4px) !important;
}

.tab-content {
    background: rgba(30, 41, 59, 0.4);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    padding: 32px;
    border-radius: 0 16px 16px 16px;
    border: 1px solid rgba(59,130,246,0.2);
    border-top: none;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

</style>
""", unsafe_allow_html=True)

st.markdown('''
<div style="text-align: center; padding: 20px 0 40px 0;">
    <h1 class="title-header">
        <i class="fas fa-music" style="margin-right: 16px;"></i>
        Music Recommendation System
        <i class="fas fa-music" style="margin-left: 16px;"></i>
    </h1>
    <p class="subtitle">
        <i class="fas fa-database"></i> Neo4j
        <span style="margin: 0 12px; color: #60a5fa;">•</span>
        <i class="fas fa-project-diagram"></i> Graph Recommendation
        <span style="margin: 0 12px; color: #a78bfa;">•</span>
        <i class="fas fa-chart-line"></i> Streamlit
    </p>
    <div style="width: 100px; height: 4px; background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899); margin: 20px auto; border-radius: 2px;"></div>
</div>
''', unsafe_allow_html=True)

# ================= FILTRES =================
st.markdown('<div class="filter-card">', unsafe_allow_html=True)
st.markdown('<h3 class="icon-title"><i class="fas fa-filter"></i> Filtres de recherche</h3>', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown('<div class="filter-label"><i class="fas fa-user-music"></i> Artiste</div>', unsafe_allow_html=True)
    artists = ["Tous les artistes"] + get_all_artists()
    selected_artist = st.selectbox("", artists, label_visibility="collapsed", key="artist_filter")

with col2:
    st.markdown('<div class="filter-label"><i class="fas fa-guitar"></i> Genre</div>', unsafe_allow_html=True)
    genres = ["Tous les genres"] + get_all_genres()
    selected_genre = st.selectbox("", genres, label_visibility="collapsed", key="genre_filter")

with col3:
    st.markdown('<div class="filter-label"><i class="fas fa-fire"></i> Popularité</div>', unsafe_allow_html=True)
    popularity_range = st.slider("", 0, 100, (0, 100), label_visibility="collapsed", key="popularity_filter")

st.markdown('</div>', unsafe_allow_html=True)

# ================= SELECTION =================
tracks = get_tracks(
    artist_filter=selected_artist,
    genre_filter=selected_genre,
    min_popularity=popularity_range[0],
    max_popularity=popularity_range[1]
)

if not tracks:
    st.warning("Aucune chanson ne correspond à vos critères de filtrage.")
    st.markdown('<div style="background: rgba(245, 158, 11, 0.1); padding: 16px; border-radius: 12px; border-left: 4px solid #f59e0b; color: #fbbf24;"><i class="fas fa-exclamation-triangle" style="margin-right: 8px;"></i> Aucune chanson ne correspond à vos critères de filtrage.</div>', unsafe_allow_html=True)
    st.stop()

st.markdown('<div class="search-section">', unsafe_allow_html=True)
st.markdown(f'''
<div class="search-label">
    <i class="fas fa-search"></i> 
    Rechercher une chanson
    <span class="results-badge">{len(tracks)} résultats</span>
</div>
''', unsafe_allow_html=True)
selected = st.selectbox("", tracks, format_func=lambda x: clean_text(x), label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

if selected:
    info = get_track_info(selected)

    st.markdown('<h2 class="icon-title"><i class="fas fa-play-circle"></i> Now Playing</h2>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="card" style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(139, 92, 246, 0.2)); border: 2px solid rgba(59, 130, 246, 0.4);">
      <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
        <i class="fas fa-compact-disc" style="font-size: 3em; color: #60a5fa; animation: spin 4s linear infinite;"></i>
        <div>
          <h2 style="color: #ffffff; margin-bottom: 8px; font-size: 2em; font-weight: 300;">
            <i class="fas fa-music"></i> {clean_text(info['track'],80)}
          </h2>
          <p class="sub" style="margin-bottom: 6px; font-size: 1.1em;"><i class="fas fa-user" style="color: #60a5fa;"></i> {', '.join(clean_list(info['artists']))}</p>
          <p class="sub" style="font-size: 1.05em;"><i class="fas fa-tags" style="color: #a78bfa;"></i> {', '.join(clean_list(info['genres']))}</p>
        </div>
      </div>
    </div>
    <style>
    @keyframes spin {{
      from {{ transform: rotate(0deg); }}
      to {{ transform: rotate(360deg); }}
    }}
    </style>
    """, unsafe_allow_html=True)

    # ================= TABS =================
    tab1, tab2, tab3, tab4 = st.tabs([
        " Analyse Audio", 
        " Recommandations", 
        " Graphe", 
        " Détails"
    ])
    
    # Custom tab styling with icons
    st.markdown('''
    <style>
    .stTabs [data-baseweb="tab"]:nth-child(1)::before {
        content: "\\f080";
        font-family: "Font Awesome 6 Free";
        font-weight: 900;
        margin-right: 8px;
    }
    .stTabs [data-baseweb="tab"]:nth-child(2)::before {
        content: "\\f001";
        font-family: "Font Awesome 6 Free";
        font-weight: 900;
        margin-right: 8px;
    }
    .stTabs [data-baseweb="tab"]:nth-child(3)::before {
        content: "\\f542";
        font-family: "Font Awesome 6 Free";
        font-weight: 900;
        margin-right: 8px;
    }
    .stTabs [data-baseweb="tab"]:nth-child(4)::before {
        content: "\\f0ca";
        font-family: "Font Awesome 6 Free";
        font-weight: 900;
        margin-right: 8px;
    }
    </style>
    ''', unsafe_allow_html=True)

    # ================= TAB 1: AUDIO ANALYSIS =================
    with tab1:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown('<h3 class="icon-title"><i class="fas fa-gauge-high"></i> Métriques principales</h3>', unsafe_allow_html=True)
        c1,c2,c3 = st.columns(3)
        with c1:
            st.markdown(f'''
            <div class="metric-card">
                <i class="fas fa-fire metric-icon" style="color:#ef4444;"></i>
                <div class="metric-label">Popularité</div>
                <div class="metric-value">{info["popularity"]}</div>
            </div>
            ''', unsafe_allow_html=True)
        with c2:
            st.markdown(f'''
            <div class="metric-card">
                <i class="fas fa-bolt metric-icon" style="color:#f59e0b;"></i>
                <div class="metric-label">Énergie</div>
                <div class="metric-value">{round(info["energy"],2)}</div>
            </div>
            ''', unsafe_allow_html=True)
        with c3:
            st.markdown(f'''
            <div class="metric-card">
                <i class="fas fa-smile metric-icon" style="color:#10b981;"></i>
                <div class="metric-label">Valence</div>
                <div class="metric-value">{round(info["valence"],2)}</div>
            </div>
            ''', unsafe_allow_html=True)

        st.markdown('<h3 class="icon-title" style="margin-top:24px;"><i class="fas fa-sliders-h"></i> Caractéristiques détaillées</h3>', unsafe_allow_html=True)
        cols = st.columns(5)
        feats = ["danceability","acousticness",
                 "instrumentalness","liveness","speechiness"]
        icons = ["fa-walking", "fa-volume-off", "fa-guitar", "fa-microphone-alt", "fa-comment"]
        colors = ["#8b5cf6", "#06b6d4", "#f59e0b", "#ef4444", "#10b981"]
        labels = ["Danceability", "Acousticness", "Instrumentalness", "Liveness", "Speechiness"]
        
        for col, f, icon, color, label in zip(cols, feats, icons, colors, labels):
            value = float(info[f])
            percentage = int(value * 100)
            col.markdown(f'''
            <div class="feature-bar">
                <div class="feature-icon"><i class="fas {icon}" style="color:{color};"></i></div>
                <div class="feature-label">{label}</div>
                <div style="background:#e2e8f0; border-radius:20px; height:8px; overflow:hidden;">
                    <div style="background:{color}; width:{percentage}%; height:100%; border-radius:20px; transition:width 0.5s ease;"></div>
                </div>
                <div class="feature-value">{percentage}%</div>
            </div>
            ''', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= TAB 2: RECOMMENDATIONS =================
    with tab2:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        recs = get_recommendations(selected)
        if recs:
            st.markdown(f'<p style="color:#64748b; margin-bottom:16px;"><i class="fas fa-lightbulb"></i> Découvrez {len(recs)} chansons similaires basées sur cette sélection</p>', unsafe_allow_html=True)
            
            for idx, r in enumerate(recs, 1):
                st.markdown(f"""
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <p style="font-size:1.1em; margin:0;"><i class="fas fa-music" style="color:#3b82f6;"></i> <b>{clean_text(r['track'])}</b></p>
                        <span style="background:#8b5cf6; color:white; padding:4px 12px; border-radius:20px; font-weight:600; font-size:0.85em;">#{idx}</span>
                    </div>
                    <p class="sub" style="margin-bottom:8px;"><i class="fas fa-user"></i> {', '.join(clean_list(r['artists']))}</p>
                    <div style="display:flex; gap:16px; margin-top:12px;">
                        <div style="flex:1;">
                            <i class="fas fa-fire" style="color:#ef4444;"></i> Popularité: <b>{r['popularity']}</b>
                        </div>
                        <div style="flex:1;">
                            <i class="fas fa-bolt" style="color:#f59e0b;"></i> Énergie: <b>{round(r['energy'],2)}</b>
                        </div>
                        <div style="flex:1;">
                            <i class="fas fa-smile" style="color:#10b981;"></i> Valence: <b>{round(r['valence'],2)}</b>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div style="background: rgba(59, 130, 246, 0.1); padding: 16px; border-radius: 12px; border-left: 4px solid #3b82f6; color: #60a5fa;"><i class="fas fa-info-circle" style="margin-right: 8px;"></i> Aucune recommandation disponible pour cette chanson.</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= TAB 3: GRAPH =================
    with tab3:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown('<h3 class="icon-title"><i class="fas fa-info-circle"></i> Clé de lecture</h3>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card">
            <div class="legend-item"><span class="legend-icon">⭐</span> <b>Chanson sélectionnée</b> - Le centre du graphe</div>
            <div class="legend-item"><span class="legend-icon">♪</span> <b>Chanson similaire</b> - Recommandations</div>
            <div class="legend-item"><span class="legend-icon">♫</span> <b>Artiste</b> - Qui performe la chanson</div>
            <div class="legend-item"><span class="legend-icon">♬</span> <b>Genre</b> - Classification musicale</div>
            <div class="legend-item"><span class="legend-icon">→</span> <b>Relations</b> - Connexions entre nœuds</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('<h3 class="icon-title" style="margin-top:20px;"><i class="fas fa-project-diagram"></i> Graphe local interactif</h3>', unsafe_allow_html=True)
        st.markdown('<p style="color:#64748b; font-size:0.9em;"><i class="fas fa-mouse"></i> Glissez pour déplacer les nœuds • Zoom pour zoomer</p>', unsafe_allow_html=True)
        render_graph(selected)
        
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= TAB 4: DETAILS =================
    with tab4:
        st.markdown('<div class="tab-content">', unsafe_allow_html=True)
        
        st.markdown('<h3 class="icon-title"><i class="fas fa-file-alt"></i> Informations complètes</h3>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            <div class="card">
                <h4><i class="fas fa-music"></i> Chanson</h4>
                <p style="font-size:1.1em; color:#3b82f6; font-weight:600; margin-bottom:8px;"></p>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f"""
            <div class="card">
                <p><b>Titre:</b> {clean_text(info['track'], 100)}</p>
                <p><b>Artistes:</b> {', '.join(clean_list(info['artists']))}</p>
                <p><b>Genres:</b> {', '.join(clean_list(info['genres']))}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="card">
                <h4><i class="fas fa-chart-bar"></i> Statistiques</h4>
            </div>
            """, unsafe_allow_html=True)
            
            stats = [
                ("Popularité", info["popularity"], "fa-fire", "#ef4444"),
                ("Énergie", round(info["energy"], 2), "fa-bolt", "#f59e0b"),
                ("Valence", round(info["valence"], 2), "fa-smile", "#10b981"),
                ("Danceability", int(float(info["danceability"]) * 100), "fa-person-walking", "#8b5cf6"),
                ("Acousticness", int(float(info["acousticness"]) * 100), "fa-guitar", "#06b6d4"),
                ("Instrumentalness", int(float(info["instrumentalness"]) * 100), "fa-music", "#ec4899"),
            ]
            
            for stat_name, stat_value, icon_class, icon_color in stats:
                st.markdown(f"""
                <div style="background:rgba(59,130,246,0.05); padding:16px; border-radius:12px; margin-bottom:10px; border-left:4px solid {icon_color}; backdrop-filter: blur(10px);">
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                        <i class="fas {icon_class}" style="font-size: 1.5em; color: {icon_color};"></i>
                        <p style="margin:0; color:#cbd5e1; font-size:0.95em; font-weight: 600;"><b>{stat_name}</b></p>
                    </div>
                    <p style="margin:0; font-size:1.5em; font-weight:800; background: linear-gradient(135deg, {icon_color}, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{stat_value}</p>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
