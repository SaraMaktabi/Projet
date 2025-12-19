import pandas as pd
import numpy as np
import re

# ==========================
# 1. CHARGEMENT ROBUSTE
# ==========================

df = pd.read_csv(
    "C:/Users/makta/OneDrive/Documents/Semestre 7 4iiR/Big Data/Projet/dataset.csv",
    sep=",",
    engine="python",
    quotechar='"',
    quoting=3,
    on_bad_lines="skip",
    encoding="utf-8"
)

print("Dataset chargé :", df.shape)

# ==========================
# 2. NETTOYAGE DES COLONNES
# ==========================

# Suppression colonnes vides
df.dropna(axis=1, how="all", inplace=True)

# Suppression colonnes Unnamed
df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

# Nettoyage noms colonnes (;;;;;)
df.columns = (
    df.columns
    .str.strip()
    .str.replace(";", "", regex=False)
    .str.replace("  ", " ")
)

print("Colonnes propres :", df.columns.tolist())

# ==========================
# 3. NETTOYAGE DES DONNÉES
# ==========================

# Valeurs manquantes
df["artists"] = df["artists"].fillna("")
df["track_name"] = df["track_name"].fillna("unknown")
df["album_name"] = df["album_name"].fillna("unknown")
df["track_genre"] = df["track_genre"].fillna("unknown")

# Colonnes numériques
num_cols = [
    "popularity", "duration_ms", "danceability", "energy",
    "speechiness", "acousticness", "instrumentalness",
    "liveness", "valence", "tempo"
]

for col in num_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# Boolean
if "explicit" in df.columns:
    df["explicit"] = df["explicit"].fillna(False).astype(bool)

# ==========================
# 4. CRÉATION DES TRACKS
# ==========================

tracks = df[[
    "track_id",
    "track_name",
    "popularity",
    "duration_ms",
    "explicit",
    "danceability",
    "energy",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo"
]].drop_duplicates()

tracks.to_csv("tracks.csv", index=False)
print("tracks.csv créé")

# ==========================
# 5. CRÉATION DES ARTISTS
# ==========================

artist_rows = []

for artists in df["artists"]:
    split_artists = [a.strip() for a in re.split("[,;]", artists) if a.strip()]
    for artist in split_artists:
        artist_rows.append({"artist_name": artist})

artists_df = pd.DataFrame(artist_rows).drop_duplicates()
artists_df["artist_id"] = (
    artists_df["artist_name"]
    .str.lower()
    .str.replace(" ", "_")
    .str.replace("[^a-z0-9_]", "", regex=True)
)

artists_df.to_csv("artists.csv", index=False)
print("artists.csv créé")

# ==========================
# 6. CRÉATION DES GENRES
# ==========================

genres_df = df[["track_genre"]].drop_duplicates()
genres_df.columns = ["genre_name"]
genres_df["genre_id"] = (
    genres_df["genre_name"]
    .str.lower()
    .str.replace(" ", "_")
    .str.replace("[^a-z0-9_]", "", regex=True)
)

genres_df.to_csv("genres.csv", index=False)
print("genres.csv créé")

# ==========================
# 7. RELATION TRACK - ARTIST
# ==========================

track_artist = []

for _, row in df.iterrows():
    track_id = row["track_id"]
    artists = [a.strip() for a in re.split("[,;]", row["artists"]) if a.strip()]

    for artist in artists:
        track_artist.append({
            "track_id": track_id,
            "artist_id": artist.lower().replace(" ", "_")
        })

track_artist_df = pd.DataFrame(track_artist).drop_duplicates()
track_artist_df.to_csv("track_artist_rel.csv", index=False)
print("track_artist_rel.csv créé")

# ==========================
# 8. RELATION TRACK - GENRE
# ==========================

track_genre_df = df[["track_id", "track_genre"]].copy()
track_genre_df["genre_id"] = (
    track_genre_df["track_genre"]
    .str.lower()
    .str.replace(" ", "_")
    .str.replace("[^a-z0-9_]", "", regex=True)
)

track_genre_df = track_genre_df[["track_id", "genre_id"]].drop_duplicates()
track_genre_df.to_csv("track_genre_rel.csv", index=False)
print("track_genre_rel.csv créé")

# ==========================
# 9. DONNÉES POUR SIMILARITÉ HYBRIDE
# ==========================

df["embedding_text"] = (
    df["track_name"] + " by " +
    df["artists"] + " genre " +
    df["track_genre"]
)

embedding_input = df[[
    "track_id",
    "embedding_text",
    "danceability",
    "energy",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo"
]].drop_duplicates()

embedding_input.to_csv("tracks_embeddings_input.csv", index=False)
print("tracks_embeddings_input.csv créé")

# ==========================
# FIN
# ==========================

print("✅ DATASET NETTOYÉ — PRÊT POUR NEO4J & SIMILARITÉ HYBRIDE")
