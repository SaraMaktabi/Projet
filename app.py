import streamlit as st
from neo4j import GraphDatabase

# -------------------
# CONFIG
# -------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "rootroot"  # ⚠️ mets TON mot de passe

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# -------------------
# FUNCTIONS
# -------------------

def get_tracks():
    query = """
    MATCH (t:Track)
    WHERE t.track_name IS NOT NULL
    RETURN DISTINCT t.track_name AS name
    ORDER BY name
    """
    with driver.session() as session:
        return [record["name"] for record in session.run(query)]


def get_track_info(track_name):
    query = """
    MATCH (t:Track {track_name:$name})
    OPTIONAL MATCH (t)-[:PERFORMED_BY]->(a:Artist)
    OPTIONAL MATCH (t)-[:IN_GENRE]->(g:Genre)
    RETURN
        t.track_name AS track,
        coalesce(t.popularity, 0) AS popularity,
        coalesce(t.energy, 0) AS energy,
        coalesce(t.valence, 0) AS valence,
        collect(DISTINCT a.artist_name) AS artists,
        collect(DISTINCT g.genre_name) AS genres
    """
    with driver.session() as session:
        return session.run(query, name=track_name).single()


def get_recommendations(track_name):
    query = """
    MATCH (t:Track {track_name:$name})-[:SIMILAR_TO]->(rec:Track)
    RETURN
        rec.track_name AS track,
        coalesce(rec.popularity, 0) AS popularity
    ORDER BY popularity DESC
    LIMIT 5
    """
    with driver.session() as session:
        # 🔑 consommation UNIQUE du résultat
        return list(session.run(query, name=track_name))


# -------------------
# UI
# -------------------

st.set_page_config(
    page_title="Music Recommendation System",
    layout="centered"
)

st.title("🎵 Music Recommendation System")
st.write("Recommandation musicale basée sur **Neo4j + Similarité hybride**")

tracks = get_tracks()

selected_track = st.selectbox(
    "🎧 Choisis une chanson",
    tracks
)

if selected_track:
    info = get_track_info(selected_track)

    if info:
        st.subheader("📀 Informations de la chanson")
        st.write(f"**Titre :** {info['track']}")
        st.write(f"**Artistes :** {', '.join(info['artists']) if info['artists'] else '—'}")
        st.write(f"**Genres :** {', '.join(info['genres']) if info['genres'] else '—'}")
        st.write(f"**Popularité :** {info['popularity']}")
        st.write(f"**Énergie :** {info['energy']}")
        st.write(f"**Valence :** {info['valence']}")

        st.subheader("🔁 Recommandations similaires")

        recs = get_recommendations(selected_track)

        if recs:
            for r in recs:
                st.write(f"🎶 {r['track']} (popularité : {r['popularity']})")
        else:
            st.info("Aucune recommandation trouvée pour cette chanson.")
